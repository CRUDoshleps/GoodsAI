"""Synthetic-only checks of sampling, quarantine, blind reserve and draft review."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/research" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


sampling = module("prepare_m2")
review = module("review_m2")


def write_rows(path, rows):
    sampling.jsonl(path, rows)
    return path


def fixture(root):
    products, splits = [], []
    for category in ["761", "482"]:
        for i in range(540):
            sku = category + ":" + str(i)
            token = hashlib.sha256(sku.encode()).hexdigest()
            products.append({"schema_version": "0.1", "sku_id": sku, "category_id": category,
                             "title": "Invented " + token, "description": token[::-1] if i < 500 else None})
            splits.append({"sku_id": sku, "category_id": category, "group_id": "g:" + sku,
                           "split": "development" if i % 2 else "test_reserved"})
    # Different original groups, same commercial skeleton: both must quarantine.
    for sku, split, code in [("mixed-a", "development", "AB100"), ("mixed-b", "test_reserved", "XY200")]:
        products.append({"schema_version": "0.1", "sku_id": sku, "category_id": "761",
                         "title": f"Phone Invented Nebula Q72 ({code})", "description": None})
        splits.append({"sku_id": sku, "category_id": "761", "group_id": sku, "split": split})
    return (write_rows(root / "input.jsonl", products), write_rows(root / "split.jsonl", splits),
            write_rows(root / "seen.jsonl", [{"sku_id": "761:501"}]))


class SamplingTests(unittest.TestCase):
    def test_near_join_matches_bruteforce_components(self):
        rng = random.Random(418)
        base = {str(i): set(rng.sample(range(20), rng.randint(1, 15))) for i in range(55)}
        base["copy"] = base["1"].copy()
        base["empty"] = set()
        for threshold in [.5, .9, 1.0]:
            fast, brute = sampling.Families(base), sampling.Families(base)
            sampling.near_join(base, threshold, fast, "near")
            for a, b in itertools.combinations(base, 2):
                union = base[a] | base[b]
                if union and len(base[a] & base[b]) / len(union) >= threshold:
                    brute.union(a, b, "brute")
            for a, b in itertools.combinations(base, 2):
                self.assertEqual(fast.root(a) == fast.root(b), brute.root(a) == brute.root(b))

    def test_normalized_html_and_code_variant_families(self):
        config = sampling.load_config()
        self.assertEqual(sampling.normalized("<b>ЁЖ</b> X-2"), sampling.normalized("еж x 2"))
        self.assertEqual(sampling.skeleton("Phone Brand Nebula P7 8/256GB (AB100) black", config),
                         sampling.skeleton("Phone Brand Nebula P7 16/512GB (XY200) white", config))

    def test_full_selection_repeatability_blindness_and_hash_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, splits, seen = fixture(root)
            before = sampling.source_hashes([source, splits, seen])
            for bundle in [root / "one", root / "two"]:
                sampling.freeze(bundle)
                result = sampling.select(bundle, source, splits, [seen])
                self.assertEqual(result["selected_counts"], {"development": 20, "test": 40})
                self.assertEqual(result["shortfalls"], [])
                self.assertEqual(review.validate_bundle(bundle)["status"], "verified")
            for name in ["selection.manifest.jsonl", "development.tasks.jsonl", "test_reserve.blank.jsonl",
                         "family.manifest.jsonl", "audit.edges.jsonl"]:
                self.assertEqual((root / "one" / name).read_bytes(), (root / "two" / name).read_bytes())
            selected = review.records(root / "one/selection.manifest.jsonl")
            self.assertFalse({r["sku_id"] for r in selected} & {"mixed-a", "mixed-b", "761:501"})
            families = {r["sku_id"]: r for r in review.records(root / "one/family.manifest.jsonl")}
            self.assertTrue(families["mixed-a"]["mixed_split_family"])
            self.assertEqual(families["mixed-a"]["family_id"], families["mixed-b"]["family_id"])
            blank = review.records(root / "one/test_reserve.blank.jsonl")
            self.assertFalse(any(k in r for r in blank for k in ["title", "description", "predictions", "vendor", "model"]))
            with self.assertRaisesRegex(ValueError, "never overwrite"):
                sampling.select(root / "one", source, splits, [seen])
            with self.assertRaises(FileExistsError):
                sampling.freeze(root / "one")
            self.assertEqual(sampling.source_hashes([source, splits, seen]), before)
            with (root / "one/development.tasks.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("{}\n")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                review.validate_bundle(root / "one")

    def test_split_and_policy_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, splits, seen = fixture(root)
            sampling.freeze(root / "bundle")
            metadata = review.records(splits)
            metadata[1]["group_id"] = metadata[0]["group_id"]
            write_rows(splits, metadata)
            with self.assertRaisesRegex(ValueError, "group crosses"):
                sampling.select(root / "bundle", source, splits, [seen])
            policy_path = root / "bundle/selection.policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["seed"] = "changed"
            sampling.dump(policy_path, policy)
            with self.assertRaisesRegex(ValueError, "frozen version"):
                sampling.select(root / "bundle", source, splits, [seen])

    def test_shortfalls_reported_no_forced_exposed_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = write_rows(root / "input.jsonl", [{"schema_version": "0.1", "sku_id": "seen",
                "category_id": "761", "title": "Invented blank", "description": None}])
            splits = write_rows(root / "split.jsonl", [{"sku_id": "seen", "category_id": "761",
                "group_id": "known-family", "split": "development"}])
            seen = write_rows(root / "seen.jsonl", [{"sku_id": "seen"}])
            sampling.freeze(root / "bundle")
            result = sampling.select(root / "bundle", source, splits, [seen])
            self.assertEqual(result["selected_counts"], {"development": 0, "test": 0})
            self.assertEqual(len(result["shortfalls"]), 8)


class DraftTests(unittest.TestCase):
    def test_exact_visible_unicode_evidence_and_model_normalization(self):
        task = {"title": "Invented", "description": "<p>Луна  X+7</p><script>Ghost</script>"}
        spec = {"value": "Луна X+7", "field": "description", "quote": "Луна  X+7", "note": "explicit"}
        label = review.make_label(task, "model", spec)
        e = label["evidence"]
        self.assertEqual(task["description"][e["start"]:e["end"]], e["text"])
        with self.assertRaisesRegex(ValueError, "characters/case"):
            review.make_label(task, "model", spec | {"value": "ЛУНА X+7"})
        with self.assertRaisesRegex(ValueError, "visible"):
            review.make_label(task, "model", spec | {"value": "Ghost", "quote": "Ghost"})
        with self.assertRaises(ValueError):
            review.make_label(task, "model", spec | {"quote": "Not in text"})
        with self.assertRaisesRegex(ValueError, "Non-present"):
            review.make_label(task, "model", {"status": "ambiguous", "value": "guess", "note": "unclear"})
        with self.assertRaisesRegex(ValueError, "unit"):
            review.make_label({"title": "8GB"}, "ram_gb", {"value": "8", "unit": "MB", "field": "title",
                                                          "quote": "8GB", "note": "wrong unit"})

    def test_build_does_not_promote_ai_and_evaluator_keeps_quality_na(self):
        from goodsai.evaluate import evaluate
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, splits, seen = fixture(root)
            sampling.freeze(root / "bundle")
            sampling.select(root / "bundle", source, splits, [seen])
            tasks = review.records(root / "bundle/development.tasks.jsonl")
            decisions = {r["review_id"]: {a["attribute"]: {"status": "absent", "note": "synthetic unknown"}
                                         for a in r["attributes"]} for r in tasks}
            sampling.dump(root / "decisions.json", decisions)
            report = review.build(root / "bundle", root / "decisions.json", root / "review")
            self.assertEqual(report["cards"], 20)
            rendered = (root / "review/development.review.md").read_text(encoding="utf-8")
            self.assertIn("| --- | --- | --- | --- |\n| brand", rendered)
            self.assertNotIn("| --- | --- | --- | --- |\n\n| brand", rendered)
            drafts = review.records(root / "review/development.ai-draft.jsonl")
            self.assertTrue(all(r["label_source"] == "ai" and r["annotation_status"] == "ai_draft"
                                and r["human_review_status"] == "pending" for r in drafts))
            with patch("goodsai.evaluate.read_predictions", return_value=iter([])):
                result = evaluate(root / "no-predictions", root / "review/development.ai-draft.jsonl", sampling.load_config())
            self.assertEqual(result["evaluation_status"], "unavailable")
            self.assertIsNone(result["f1"])
            with self.assertRaisesRegex(ValueError, "overwrite"):
                review.build(root / "bundle", root / "decisions.json", root / "review")
            self.assertIn("&lt;script&gt;", review.cell("<script>"))
            self.assertIn("````text", review.fence("```"))


if __name__ == "__main__":
    unittest.main()
