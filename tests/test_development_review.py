"""Synthetic selection and AI-draft provenance; never real catalogue examples."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import development_review as dev


def fixture(root):
    audit = root / "audit"
    audit.mkdir()
    products, members = [], []
    for cat in ["761", "482"]:
        for description in [True, False]:
            for i in range(12):
                sku = f"{cat}-{description}-{i}"
                products.append({"schema_version": "0.1", "sku_id": sku, "category_id": cat,
                    "title": "Invented " + sku, "description": "<p>Synthetic-only text</p>" if description else None})
                members.append({"sku_id": sku, "category_id": cat, "split": "development", "group_id": sku,
                    "family_id": sku if i > 1 else f"shared-{cat}-{description}",
                    "family_exposed": False, "known_exposure": i == 0, "quarantine_reasons": []})
    # Poison fields may never reach Product/signals: metadata gate must precede parsing.
    products.append({"sku_id": "protected", "title": ["DO_NOT_PARSE_TEST_TEXT"], "description": 3})
    members.append({"sku_id": "protected", "split": "test_reserved", "family_id": "test-family",
                    "family_exposed": False, "known_exposure": False, "quarantine_reasons": []})
    source = root / "pilot.jsonl"
    dev.write_rows(source, products)
    dev.write_rows(audit / "eligible.split_manifest.jsonl", members)
    dev.dump(audit / "audit.policy.json", {"sources": {str(source): dev.digest(source)}})
    dev.dump(audit / "audit.summary.json", {"synthetic_unit_fixture": True})
    return audit


def select(audit, output):
    # The split auditor is separately integration-tested. Here isolate selection
    # from its already-verified metadata contract, including poisoned gated rows.
    with patch.object(dev, "verify") as verify:
        result = dev.select(audit, output)
        verify.assert_called_once()
    return result


def decisions(bundle, path):
    tasks = list(dev.read_jsonl(bundle / "development.tasks.jsonl"))
    obj = {t["review_id"]: {a["attribute"]: {"status": "absent", "note": "Synthetic missing field."}
                           for a in t["attributes"]} for t in tasks}
    dev.dump(path, obj)


class DevelopmentReviewTests(unittest.TestCase):
    def test_family_exposure_gate_stratification_and_stable_numbering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = fixture(root)
            result = select(audit, root / "selected")
            self.assertEqual(result["selected_cards"], 20)
            self.assertEqual(result["selected_families"], 20)
            self.assertEqual(set(result["cells"].values()), {5})
            tasks = list(dev.read_jsonl(root / "selected/development.tasks.jsonl"))
            self.assertEqual([t["review_id"] for t in tasks], ["D" + str(i) for i in range(21, 41)])
            self.assertTrue(all(t["split"] == "development" for t in tasks))
            self.assertFalse(any(t["sku_id"].endswith(("-0", "-1")) for t in tasks))
            self.assertFalse(any(t["sku_id"] == "protected" for t in tasks))

    def test_selection_repeats_byte_identically_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = fixture(root)
            select(audit, root / "one")
            select(audit, root / "two")
            self.assertTrue(all(p.read_bytes() == (root / "two" / p.name).read_bytes() for p in (root / "one").iterdir()))
            with self.assertRaisesRegex(ValueError, "new_output"):
                select(audit, root / "one")

    def test_no_forced_replacement_when_unexposed_families_are_insufficient(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = fixture(root)
            rows = list(dev.read_jsonl(audit / "eligible.split_manifest.jsonl"))
            for row in rows:
                row["family_exposed"] = True
            (audit / "eligible.split_manifest.jsonl").unlink()
            dev.write_rows(audit / "eligible.split_manifest.jsonl", rows)
            with self.assertRaisesRegex(ValueError, "insufficient"):
                select(audit, root / "out")
            self.assertFalse((root / "out/development.tasks.jsonl").exists())

    def test_ai_draft_never_promotes_human_review_or_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = fixture(root)
            select(audit, root / "selected")
            decisions(root / "selected", root / "decisions.json")
            result = dev.build(root / "selected", root / "decisions.json", root / "draft")
            self.assertEqual(result["human_reviewed_cards"], 0)
            self.assertFalse(result["independent_reference"])
            rows = list(dev.read_jsonl(root / "draft/development.ai-draft.jsonl"))
            self.assertTrue(all(r["annotation_status"] == "draft" and r["human_review_status"] == "pending"
                                and r["label_source"] == "ai_assisted" for r in rows))
            self.assertIsNone(json.loads((root / "draft/draft.manifest.json").read_text())["f1"])
            self.assertIn("D40", (root / "draft/development.review.md").read_text(encoding="utf-8"))

    def test_bad_witness_and_changed_selection_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = fixture(root)
            select(audit, root / "selected")
            decisions(root / "selected", root / "decisions.json")
            obj = json.loads((root / "decisions.json").read_text())
            obj["D21"]["brand"] = {"value": "Imaginary", "unit": None, "field": "title", "quote": "NOT_PRESENT", "note": "Synthetic invalid quote."}
            (root / "decisions.json").write_text(json.dumps(obj))
            with self.assertRaises(ValueError):
                dev.build(root / "selected", root / "decisions.json", root / "draft")
            with (root / "selected/development.tasks.jsonl").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "artifact_changed"):
                dev.build(root / "selected", root / "decisions.json", root / "other")

    def test_next_round_excludes_newly_exposed_families(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = fixture(root)
            select(audit, root / "one")
            decisions(root / "one", root / "decisions.json")
            dev.build(root / "one", root / "decisions.json", root / "draft")
            with patch.object(dev, "verify"):
                dev.select(audit, root / "two", [root / "draft/exposure.manifest.jsonl"])
            first = {r["family_id"] for r in dev.read_jsonl(root / "one/selection.manifest.jsonl")}
            second = {r["family_id"] for r in dev.read_jsonl(root / "two/selection.manifest.jsonl")}
            self.assertFalse(first & second)


if __name__ == "__main__":
    unittest.main()
