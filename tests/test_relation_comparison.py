"""Reproducible experiment harness tested solely with synthetic references."""
import json
from pathlib import Path
import tempfile
import unittest

from goodsai.contracts import Product, load_config
from goodsai.verify import Extractor
from scripts.research.compare_relation import run


class RelationComparisonTests(unittest.TestCase):
    def reference(self, folder):
        p = Product("synthetic", "761", "Смартфон Samsung Orbit Z83",
                    "Совместим с телефоном: экран 6,3 дюйма.")
        attrs = Extractor(load_config()).predict(p)["attributes"]
        labels = [{"attribute": a["attribute"], "status": "present" if a["value"] else "absent",
                   "value": a["value"], "unit": a["unit"], "evidence": a["evidence"]} for a in attrs]
        row = p.as_dict() | {"split": "development", "group_id": "synthetic-family",
                             "annotation_status": "reviewed", "label_source": "manual",
                             "annotator": "synthetic-test-fixture", "attributes": labels}
        path = folder / "reference.jsonl"
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def test_ablation_measures_false_positive_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            reference = self.reference(folder)
            original = reference.read_bytes()
            result = run(reference, folder / "run", repeats=2)
            self.assertEqual(result["transitions"], {"FP->TN": 1})
            self.assertEqual(result["lost_tp"], 0)
            self.assertEqual(result["variants"]["before"]["evaluation"]["metrics"]["micro"]["fp"], 1)
            self.assertEqual(result["variants"]["after"]["evaluation"]["metrics"]["micro"]["fp"], 0)
            self.assertEqual(reference.read_bytes(), original)
            self.assertFalse(result["independent_reference"])
            self.assertEqual(result["regression_gate"], "pass")
            with self.assertRaises(FileExistsError):
                run(reference, folder / "run")

    def test_test_or_draft_reference_rejected_before_any_predictions(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            reference = self.reference(folder)
            for key, value in [("split", "test"), ("annotation_status", "draft"), ("label_source", "ai_assisted")]:
                row = json.loads(reference.read_text(encoding="utf-8"))
                bad = folder / "invalid.jsonl"
                bad.write_text(json.dumps(row | {key: value}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "reviewed development"):
                    run(bad, folder / "invalid-run")
                self.assertFalse((folder / "invalid-run").exists())
