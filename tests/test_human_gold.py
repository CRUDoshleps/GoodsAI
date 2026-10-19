"""Synthetic-only blind-review workflow; no real test contents or human answers."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import audit_splits as audit
from scripts.research import human_gold as gold


def replace_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")


def fixture(root):
    config = gold.load_config()
    products, splits, families, reserves = [], [], [], []
    for i in range(40):
        sku, cat = str(i), "761" if i < 20 else "482"
        products.append({"schema_version": "0.1", "sku_id": sku, "category_id": cat,
            "title": "Invented " + hashlib.sha256(sku.encode()).hexdigest(), "description": None})
        m = {"sku_id": sku, "category_id": cat, "split": "test_reserved", "group_id": "g" + sku}
        splits.append(m)
        families.append(m | {"family_id": "f" + sku, "known_exposure": False,
                              "family_exposed": False, "mixed_split_family": False})
        reserves.append(m | {"family_id": "f" + sku, "review_id": f"T{i+1:02d}", "text_materialized": False,
            "attributes": [{"attribute": a, "status": "unreviewed", "value": None, "unit": None,
                            "evidence": None} for a in config["categories"][cat]]})
    source, split, family, reserve = [root / n for n in
        ["pilot.jsonl", "split.jsonl", "family.jsonl", "test_reserve.blank.jsonl"]]
    for path, records in zip([source, split, family, reserve], [products, splits, families, reserves]):
        audit.write_rows(path, records)
    summary = root / "m2-summary.json"
    audit.dump(summary, {"artifacts": {p.name: audit.digest(p) for p in [family, reserve]},
        "protected_sources": {str(p): audit.digest(p) for p in [source, split]}, "known_exposure_rows": 0})
    audit.audit(source, split, family, summary, reserve, [], root / "audit")
    gold.prepare(root / "audit", root / "metadata", "HEAD")
    return source


def release(root, slot):
    freeze = gold.read(root / "metadata/freeze.template.json")
    freeze.update(approved=True, approved_by="synthetic_coordinator", methods_and_thresholds_frozen=True,
                  no_test_based_tuning=True)
    freeze["reviewers"] = {"A": {"id": "synthetic_a"}, "B": {"id": "synthetic_b"}, "C": {"id": "synthetic_c"}}
    path = root / ("freeze-" + slot + ".json")
    gold.dump(path, freeze)
    gold.materialize(root / "metadata", path, slot, root / slot)


def response(root, slot, status="absent"):
    payload = gold.read(root / slot / "tasks.private.json")
    result = {k: payload[k] for k in ["package_id", "slot", "reviewer_id"]}
    result["attestation"] = dict(human_only=True, no_predictions_or_ai=True, worked_independently=True)
    result["tasks"] = []
    for task in payload["tasks"]:
        attrs = [a | {"status": status, "notes": "synthetic uncertainty" if status == "ambiguous" else ""}
                 for a in task["attributes"]]
        result["tasks"].append({"task_id": task["task_id"], "attributes": attrs})
    path = root / ("answers-" + slot + ".json")
    gold.dump(path, result)
    return path


class HumanGoldTests(unittest.TestCase):
    def test_metadata_preparation_does_not_parse_or_export_test_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture(root)
            original = gold.read_jsonl
            def guarded(path):
                self.assertNotEqual(Path(path).resolve(), source.resolve())
                yield from original(path)
            with patch.object(gold, "read_jsonl", guarded):
                result = gold.prepare(root / "audit", root / "second", "HEAD")
            self.assertEqual(result["cards"], 40)
            self.assertEqual(result["pairs"], 240)
            self.assertFalse(result["text_materialized"])
            for path in (root / "second").iterdir():
                self.assertNotIn("Invented ", path.read_text(encoding="utf-8"))
            self.assertFalse((root / "second/review.html").exists())

    def test_freeze_is_not_auto_approved_and_source_guard_precedes_materialization(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture(root)
            with self.assertRaisesRegex(ValueError, "human_method_freeze"):
                gold.materialize(root / "metadata", root / "metadata/freeze.template.json", "A", root / "forbidden")
            self.assertFalse((root / "forbidden").exists())
            release(root, "A")
            self.assertIn("Invented ", (root / "A/review.html").read_text(encoding="utf-8"))
            self.assertNotIn('"sku_id"', (root / "A/tasks.private.json").read_text())
            with source.open("a") as stream:
                stream.write("\n")
            with self.assertRaises(ValueError):
                gold.materialize(root / "metadata", root / "freeze-A.json", "B", root / "B")

    def test_single_review_never_exports_gold_or_agreement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            release(root, "A")
            answer = response(root, "A")
            report = gold.reconcile(root / "A", answer, root / "comparison")
            self.assertFalse(report["independent_reference"])
            self.assertIsNone(report["agreement"])
            self.assertIsNone(report["precision"])
            self.assertFalse((root / "comparison/reference.jsonl").exists())

    def test_two_reviews_require_third_human_signoff_even_without_disagreements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            for slot in ["A", "B"]:
                release(root, slot)
                response(root, slot)
            report = gold.reconcile(root / "A", root / "answers-A.json", root / "cmp", root / "B", root / "answers-B.json")
            self.assertEqual(report["status"], "pending_human_signoff")
            self.assertEqual(report["agreement"]["canonical_exact"], 1)
            self.assertIsNone(report["agreement"]["status_cohen_kappa"])
            decision = gold.read(root / "cmp/adjudication.template.json")
            with self.assertRaisesRegex(ValueError, "third_human"):
                gold.finalize(root / "A", root / "answers-A.json", root / "B", root / "answers-B.json",
                              root / "cmp/adjudication.template.json", root / "no-gold")
            decision.update(approved=True, adjudicator="synthetic_c", all_labels_checked=True,
                            human_only=True, no_test_based_tuning=True)
            gold.dump(root / "signed.json", decision)
            result = gold.finalize(root / "A", root / "answers-A.json", root / "B", root / "answers-B.json",
                                   root / "signed.json", root / "gold")
            self.assertTrue(result["independent_reference"])
            self.assertEqual(len(list(gold.read_jsonl(root / "gold/reference.jsonl"))), 40)

    def test_disagreement_resolution_is_complete_explicit_and_bound_to_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            for slot in ["A", "B"]:
                release(root, slot)
                response(root, slot)
            b = gold.read(root / "answers-B.json")
            b["tasks"][0]["attributes"][0].update(status="ambiguous", notes="synthetic ambiguity")
            replace_json(root / "answers-B.json", b)
            report = gold.reconcile(root / "A", root / "answers-A.json", root / "cmp", root / "B", root / "answers-B.json")
            self.assertEqual(report["disagreement_pairs"], 1)
            d = gold.read(root / "cmp/adjudication.template.json")
            d.update(approved=True, adjudicator="synthetic_c", all_labels_checked=True, human_only=True, no_test_based_tuning=True)
            gold.dump(root / "d.json", d)
            with self.assertRaisesRegex(ValueError, "invalid_adjudication"):
                gold.finalize(root / "A", root / "answers-A.json", root / "B", root / "answers-B.json", root / "d.json", root / "out")
            d["decisions"][0].update(label=b["tasks"][0]["attributes"][0], reason="independent synthetic adjudication")
            replace_json(root / "d.json", d)
            gold.finalize(root / "A", root / "answers-A.json", root / "B", root / "answers-B.json", root / "d.json", root / "out")
            d["response_sha256"]["A"] = "0" * 64
            replace_json(root / "d.json", d)
            with self.assertRaisesRegex(ValueError, "signoff_response"):
                gold.finalize(root / "A", root / "answers-A.json", root / "B", root / "answers-B.json", root / "d.json", root / "other")

    def test_identity_attestation_schema_and_pending_labels_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            release(root, "A")
            path = response(root, "A")
            base = gold.read(path)
            for mutate in [lambda x: x.update(slot="B"),
                           lambda x: x["attestation"].update(human_only=False),
                           lambda x: x["tasks"].pop(),
                           lambda x: x["tasks"][0]["attributes"].pop(),
                           lambda x: x["tasks"][0]["attributes"][0].update(status="unreviewed"),
                           lambda x: x.update(predictions=[]),
                           lambda x: x["tasks"][0]["attributes"].__setitem__(0,None)]:
                changed = copy.deepcopy(base)
                mutate(changed)
                replace_json(path, changed)
                with self.assertRaises(ValueError):
                    gold.answers(root / "A", path)
            replace_json(path, base)
            self.assertEqual(gold.answers(root / "A", path)[2], 0)

    def test_unicode_repeated_hidden_evidence_and_model_policy(self):
        task = {"title": "😀 X X", "description": "<p>Shown</p><script>Hidden</script>"}
        label = {"evidence": {"field": "title", "text": "X", "start": 2}}
        self.assertEqual(gold.evidence(label, task)["end"], 3)
        label["evidence"]["start"] = None
        with self.assertRaisesRegex(ValueError, "repeated"):
            gold.evidence(label, task)
        label["evidence"] = {"field": "description", "text": "Hidden", "start": None}
        with self.assertRaises(ValueError):
            gold.evidence(label, task)

    def test_completed_present_labels_are_canonical_and_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            release(root, "A")
            path = response(root, "A")
            data = gold.read(path)
            label = data["tasks"][0]["attributes"][1]
            label.update(status="present", value="Invented", unit=None,
                         evidence={"field": "title", "text": "Invented", "start": None})
            replace_json(path, data)
            clean = gold.answers(root / "A", path)[1]
            self.assertEqual(clean["T01"][1]["evidence"]["start"], 0)
            label["value"] = "INVENTED"
            replace_json(path, data)
            with self.assertRaisesRegex(ValueError, "model_minimal"):
                gold.answers(root / "A", path)

    def test_package_mutation_and_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            with self.assertRaises(ValueError):
                gold.prepare(root / "audit", root / "metadata", "HEAD")
            with (root / "metadata/schema.json").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "package_hash"):
                gold.materialize(root / "metadata", root / "metadata/freeze.template.json", "A", root / "A")


if __name__ == "__main__":
    unittest.main()
