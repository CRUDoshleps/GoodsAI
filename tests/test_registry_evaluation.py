"""Registry reference values outside train remain measurable (synthetic only)."""
import json
from pathlib import Path
import tempfile
import unittest

from goodsai.cli import predict
from goodsai.contracts import Product
from goodsai.evaluate import evaluate
from goodsai.learn_categories import attribute_id, build
from test_category_registry import fixtures


class ReferenceVocabularyTests(unittest.TestCase):
    def test_unseen_manual_value_is_false_negative_instead_of_evaluation_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config, _ = build(*fixtures(root))
            product = Product("invented-validation", "invented-category-0", "Материал: стекло;")
            source = root / "input.jsonl"
            source.write_text(json.dumps(product.as_dict(), ensure_ascii=False) + "\n")
            predictions = root / "predictions.jsonl"
            predict(source, predictions, config)
            reference = root / "reference.jsonl"
            labels = []
            for attr in config["categories"][product.category_id]:
                label = {"attribute": attr, "status": "unjudgeable", "value": None, "unit": None, "evidence": None}
                if attr == attribute_id("Материал"):
                    label.update(status="present", value="стекло", evidence={"field": "title", "start": 10, "end": 16, "text": "стекло"})
                labels.append(label)
            reference.write_text(json.dumps(product.as_dict() | {"attributes": labels, "annotation_status": "reviewed",
                "label_source": "manual", "annotator": "synthetic-fixture-only"}, ensure_ascii=False) + "\n")
            result = evaluate(predictions, reference, config)
            self.assertEqual(result["metrics"]["micro"]["fn"], 1)
            self.assertEqual(result["metrics"]["micro"]["recall"], 0)
            self.assertNotIn("стекло", config["category_registry"]["categories"][product.category_id]["attributes"][attribute_id("Материал")]["values"])


from contextlib import redirect_stderr, redirect_stdout
import io
import os
from unittest.mock import patch

from goodsai.config import load_config
from goodsai.data import digest
from goodsai.registry_evaluation import config_hash, main, run


def validation_fixture(root, value="стекло"):
    train, split, _traffic = fixtures(root)
    from goodsai.learn_categories import build
    config, _ = build(train, split, _traffic)
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False))
    product = Product("invented-validation", "invented-category-0", f"Материал: {value};")
    input_path = root / "validation-input.jsonl"
    input_path.write_text(json.dumps(product.as_dict(), ensure_ascii=False) + "\n")
    reference = root / "validation-reference.jsonl"
    ref = product.as_dict() | {"split": "validation", "group_id": "invented-heldout-family", "label_source": "manual",
        "annotator": "synthetic-fixture-not-human", "annotation_status": "reviewed", "attributes": [
            {"attribute": "old_material", "status": "present", "value": value, "unit": None,
             "evidence": {"field": "title", "start": 10, "end": 10+len(value), "text": value},
             "label_origin": "synthetic-not-real-quality"}]}
    reference.write_text(json.dumps(ref, ensure_ascii=False) + "\n")
    mapping_path = root / "mapping.json"
    mapping_path.write_text(json.dumps({"mapping_version": "1", "config_sha256": config_hash(config),
        "categories": {product.category_id: {"old_material": attribute_id("Материал")}}}))
    return [config_path, input_path, reference, split, mapping_path]


class RegistryValidationRunTests(unittest.TestCase):
    def test_unknown_reference_preserved_and_unmapped_fields_not_labeled_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = validation_fixture(root)
            hashes = [digest(p) for p in paths]
            output = root / "run"
            report = run(*paths, output)
            self.assertEqual(report["evaluation"]["metrics"]["micro"]["fn"], 1)
            self.assertEqual(report["evaluation"]["metrics"]["micro"]["judged"], 1)
            self.assertEqual(report["mapping_counts"]["unmapped_target_labels"], 5)
            mapped = json.loads((output / "mapped_reference.jsonl").read_text())
            self.assertEqual(sum(a["status"] == "unjudgeable" for a in mapped["attributes"]), 5)
            self.assertEqual(sum(a["status"] == "absent" for a in mapped["attributes"]), 0)
            self.assertEqual(report["slices"][0]["attribute_name"], "Материал")
            self.assertEqual(report["independent_quality"], "not_verified_by_tool")
            self.assertEqual(hashes, [digest(p) for p in paths])
            self.assertNotIn("invented-validation", (output / "report.md").read_text())
            self.assertNotIn("Материал: стекло", (output / "report.json").read_text())
            if os.name != "nt":
                self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                self.assertEqual((output / "report.json").stat().st_mode & 0o777, 0o600)
            artifacts = json.loads((output / "artifacts.json").read_text())
            for name, sha in artifacts["sha256"].items():
                self.assertEqual(digest(output / name), sha)
            with self.assertRaises(ValueError):
                run(*paths, output)

    def test_same_known_reference_maps_and_scores_as_correct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = run(*validation_fixture(root, "металл"), root / "run")
            self.assertEqual(report["evaluation"]["metrics"]["micro"]["tp"], 1)
            self.assertEqual(report["evaluation"]["metrics"]["micro"]["f1"], 1)
            self.assertIs(load_config()["runtime"]["auto_accept_enabled"], False)

    def test_mapping_hash_duplicate_targets_and_missing_source_rejected(self):
        for error in ("hash", "duplicate", "missing_source"):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                paths = validation_fixture(root)
                mapping = json.loads(paths[4].read_text())
                if error == "hash":
                    mapping["config_sha256"] = "0"*64
                elif error == "duplicate":
                    mapping["categories"]["invented-category-0"]["another"] = attribute_id("Материал")
                else:
                    mapping["categories"]["invented-category-0"] = {"typo": attribute_id("Материал")}
                paths[4].write_text(json.dumps(mapping))
                with self.assertRaises(ValueError):
                    run(*paths, root / "run")
                self.assertFalse((root / "run").exists())

    def test_train_or_test_input_pending_silver_text_mismatch_and_unit_fail(self):
        for error in ("train", "test", "pending", "silver", "text", "unit", "evidence", "duplicate_ref"):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                paths = validation_fixture(root)
                source = json.loads(paths[1].read_text())
                ref = json.loads(paths[2].read_text())
                split = json.loads(paths[3].read_text())
                if error == "train":
                    source["sku_id"] = split["train_sku_ids"][0]
                elif error == "test":
                    source["sku_id"] = split["test_sku_ids"][0]
                elif error == "pending":
                    ref["annotation_status"] = "pending"
                elif error == "silver":
                    ref["label_source"] = "catalog_silver"
                elif error == "text":
                    ref["title"] = "Изменённая карточка"
                elif error == "unit":
                    ref["attributes"][0]["unit"] = "GB"
                elif error == "evidence":
                    ref["attributes"][0]["evidence"]["start"] = 9
                paths[1].write_text(json.dumps(source, ensure_ascii=False)+"\n")
                paths[2].write_text((json.dumps(ref, ensure_ascii=False)+"\n") * (2 if error == "duplicate_ref" else 1))
                with self.assertRaises(ValueError):
                    run(*paths, root / "run")
                self.assertFalse((root / "run").exists())

    def test_changed_split_not_silently_rebound_to_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = validation_fixture(root)
            paths[3].write_text(paths[3].read_text()+" ")
            with self.assertRaises(ValueError):
                run(*paths, root / "run")

    def test_inputs_changed_during_prediction_publish_no_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = validation_fixture(root)
            from goodsai.registry_evaluation import predict as actual_predict
            def mutation(*args):
                result = actual_predict(*args)
                paths[4].write_text(paths[4].read_text()+" ")
                return result
            with patch("goodsai.registry_evaluation.predict", side_effect=mutation), self.assertRaises(ValueError):
                run(*paths, root / "run")
            self.assertFalse((root / "run").exists())

    def test_no_mapped_judgments_is_unavailable_and_cli_exit_two(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = validation_fixture(root)
            mapping = json.loads(paths[4].read_text())
            mapping["categories"]["invented-category-0"] = {}
            paths[4].write_text(json.dumps(mapping))
            arguments = []
            for name, path in zip(("config", "input", "reference", "split", "mapping"), paths):
                arguments.extend(["--"+name, str(path)])
            arguments.extend(["--output-dir", str(root / "run")])
            with redirect_stdout(io.StringIO()):
                code = main(arguments)
            self.assertEqual(code, 2)
            report = json.loads((root / "run" / "report.json").read_text())
            self.assertEqual(report["status"], "unavailable")
            self.assertIsNone(report["evaluation"]["precision"])
            self.assertEqual(report["mapping_counts"]["unmapped_target_labels"], 6)
            self.assertIn("N/A", (root / "run" / "report.md").read_text())

    def test_cli_failure_is_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = validation_fixture(root)
            paths[4].write_text('{"SECRET-TEXT":NaN}')
            stderr = io.StringIO()
            arguments = []
            for name, path in zip(("config", "input", "reference", "split", "mapping"), paths):
                arguments.extend(["--"+name, str(path)])
            arguments.extend(["--output-dir", str(root / "run")])
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                code = main(arguments)
            self.assertEqual(code, 2)
            self.assertNotIn("SECRET", stderr.getvalue())
            self.assertFalse((root / "run").exists())
            for failure, expected in ((RuntimeError("SECRET-CARD-TEXT"), 1), (KeyboardInterrupt(), 130)):
                stderr = io.StringIO()
                with patch("goodsai.registry_evaluation.run", side_effect=failure), redirect_stderr(stderr):
                    self.assertEqual(main(arguments), expected)
                self.assertNotIn("SECRET", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
