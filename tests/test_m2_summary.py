"""Synthetic checks: judged/excluded accounting and frozen report restrictions."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("m2_summary", Path(__file__).resolve().parents[1] / "scripts/research/summarize_m2.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class SummaryTests(unittest.TestCase):
    def fixture(self):
        labels = [{"attribute": attr, "status": status, "value": value, "unit": None}
                  for attr, status, value in [("model", "present", "Orbit X7"), ("brand", "present", "Acme"),
                                              ("color", "ambiguous", None), ("capacity_l", "absent", None)]]
        gold = [{"sku_id": "fictional", "review_id": "D01", "category_id": "invented", "attributes": labels}]
        pred = {"fictional": {"category_id": "invented", "attributes": [
            {"attribute": a["attribute"], "value": value, "unit": None}
            for a, value in zip(labels, ["Wrong X9", None, "blue", "1.7"])]}}
        return gold, pred

    def test_wrong_values_absent_and_excluded_candidates(self):
        gold, pred = self.fixture()
        result, diagnostics = summary.aggregate(gold, pred)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 2, 2))
        self.assertEqual((result["judged"], result["applicable"], result["excluded_with_candidate"]), (3, 4, 1))
        self.assertEqual(result["all_pair_coverage"], 3 / 4)
        self.assertEqual(result["prediction_coverage"], 2 / 3)
        self.assertEqual({r["outcome"] for r in diagnostics}, {"FP+FN", "FN", "FP", "excluded_candidate"})

    def test_pending_labels_and_identity_changes_fail(self):
        gold, pred = self.fixture()
        gold[0]["attributes"][0]["status"] = "unreviewed"
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            summary.aggregate(gold, pred)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summary.index_unique([gold[0], gold[0]])
        pred["fictional"]["category_id"] = "other"
        with self.assertRaisesRegex(ValueError, "category"):
            summary.aggregate(gold, pred)

    def test_closed_test_and_output_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "experiment.manifest.json").write_text(json.dumps({"status": "completed", "split": "test_reserved"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "development"):
                summary.run(root, root, root / "new-output")
            with self.assertRaises(FileExistsError):
                summary.run(root, root, root)
            with self.assertRaisesRegex(ValueError, "data/raw"):
                summary.run(root, root, root / "data/raw/report")


if __name__ == "__main__":
    unittest.main()
