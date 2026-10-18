"""Synthetic integration checks of freezing/ablation and reference isolation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts/research/compare_model_stage.py"
spec = importlib.util.spec_from_file_location("model_comparison", MODULE)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def reference(split="development", sku="synthetic-dev", group="invented-dev"):
    from goodsai.contracts import load_config
    title = "Смартфон Samsung Orbit X82"
    attrs = []
    for attr in load_config()["categories"]["761"]:
        value = {"brand": "Samsung", "model": "Orbit X82"}.get(attr)
        start = title.index(value) if value else None
        attrs.append({"attribute": attr, "status": "present" if value else "absent",
                      "value": value, "unit": None,
                      "evidence": {"field": "title", "start": start, "end": start + len(value), "text": value} if value else None})
    return {"schema_version": "0.1", "sku_id": sku, "title": title, "category_id": "761",
            "split": split, "group_id": group, "annotation_status": "reviewed",
            "label_source": "manual", "annotator": "synthetic-test", "attributes": attrs}


class ComparisonTests(unittest.TestCase):
    def write(self, path, row):
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def test_real_baseline_ablation_and_frozen_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gold = self.write(root / "dev.jsonl", reference())
            fingerprint = comparison.sha(gold)
            result = comparison.run(gold, root / "dev", repeats=1, allow_dictionary_changes=True)
            self.assertEqual(result["variants"]["A"]["model"]["fn"], 1)
            self.assertEqual(result["variants"]["B"]["model"]["fn"], 1)
            self.assertEqual(result["variants"]["C"]["model"]["tp"], 1)
            self.assertEqual(result["non_model_changes"], 0)
            model_input = list(comparison.rows(root / "dev/input.jsonl"))[0]
            self.assertNotIn("attributes", model_input)
            self.assertNotIn("group_id", model_input)
            self.assertNotIn("split", model_input)
            self.assertEqual(comparison.sha(gold), fingerprint)
            # Same destination must never overwrite the completed run.
            before = comparison.sha(root / "dev/experiment.manifest.json")
            with self.assertRaises(FileExistsError):
                comparison.run(gold, root / "dev", repeats=1)
            self.assertEqual(comparison.sha(root / "dev/experiment.manifest.json"), before)
            val = self.write(root / "val.jsonl", reference("validation", "synthetic-val", "invented-val"))
            comparison.run(val, root / "val", "validation", freeze_from=root / "dev", repeats=1,
                           allow_dictionary_changes=True)
            comparison.run(val, root / "feedback", "validation", freeze_from=root / "dev", repeats=1,
                           previous_run=root / "val", feedback_reference=True, allow_dictionary_changes=True)
            feedback = json.loads((root / "feedback/summary.json").read_text(encoding="utf-8"))
            self.assertEqual(feedback["reference_use"], "development_feedback")
            self.assertEqual(feedback["previous_comparison"]["lost_tp"], 0)
            self.assertEqual(feedback["previous_comparison"]["new_fp"], 0)
            overlap = self.write(root / "overlap.jsonl", reference("validation", "another-sku", "invented-dev"))
            with self.assertRaisesRegex(ValueError, "overlap"):
                comparison.run(overlap, root / "overlap", "validation", freeze_from=root / "dev", repeats=1)
            frozen = root / "dev/snapshots/C/src/goodsai/model_rules.py"
            frozen.write_text(frozen.read_text(encoding="utf-8") + "\n# modified\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Frozen package"):
                comparison.run(val, root / "tampered", "validation", freeze_from=root / "dev", repeats=1)

    def test_split_and_reference_restrictions_fail_before_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gold = self.write(root / "gold.jsonl", reference())
            for split, frozen in [("test_reserved", None), ("validation", None), ("development", root)]:
                with self.subTest(split=split), self.assertRaises(ValueError):
                    comparison.run(gold, root / split, split, freeze_from=frozen)
            wrong = reference()
            wrong["label_source"] = "ai"
            self.write(gold, wrong)
            with self.assertRaisesRegex(ValueError, "manual"):
                comparison.run(gold, root / "unreviewed")
            self.assertFalse((root / "unreviewed").exists())
            with self.assertRaisesRegex(ValueError, "Feedback flag"):
                comparison.run(gold, root / "bad-feedback", feedback_reference=True)

    def test_pair_deltas_keep_wrong_values_and_exclusions_visible(self):
        gold = reference()
        make = lambda value: {gold["sku_id"]: {"attributes": [dict(a, value=value if a["attribute"] == "model" else a["value"])
                                                           for a in gold["attributes"]]}}
        delta = comparison.compare([gold], {"A": make(None), "B": make(None), "C": make("Wrong X99")})
        self.assertEqual(delta[0]["before_verdict"], "FN")
        self.assertEqual(delta[0]["after_verdict"], "FP+FN")

    def test_dictionary_comparison_is_explicit_and_does_not_allow_schema_drift(self):
        from goodsai.contracts import load_config
        config = load_config()
        changed = config | {"colors": dict(config["colors"], invented=["invented"])}
        with self.assertRaisesRegex(ValueError, "allow-dictionary-changes"):
            comparison.check_configs(config, changed)
        self.assertEqual(comparison.check_configs(config, changed, True), ["colors"])
        for change in [{"schema_version": "2"}, {"categories": {"other": ["brand"]}}]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "schema"):
                comparison.check_configs(config, config | change, True)


if __name__ == "__main__":
    unittest.main()
