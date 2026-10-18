"""Integration checks of the synthetic demo; no organizer data or reference labels."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goodsai.cli import predict
from goodsai.contracts import load_config
from goodsai.data import digest, read_jsonl, write_json, write_line
from goodsai.demo import main, run_demo


class DemoTests(unittest.TestCase):
    def test_artifacts_match_real_predict_and_are_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = run_demo(root / "first")
            second = run_demo(root / "second")
            self.assertEqual(first["checks_passed"], 6)
            self.assertEqual(first["checks_total"], 6)
            self.assertEqual(first["status_counts"], {"processed": 4, "unsupported_category": 1, "invalid_input": 1})
            self.assertEqual(first["decision_counts"], {"review": 11, "abstain": 13})
            self.assertEqual(first["llm_calls"], 0)
            self.assertNotIn("f1", first)
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual((root / "first/predictions.jsonl").read_bytes(),
                             (root / "second/predictions.jsonl").read_bytes())
            direct = root / "direct.jsonl"
            predict(root / "first/input.jsonl", direct, load_config())
            self.assertEqual(direct.read_bytes(), (root / "first/predictions.jsonl").read_bytes())
            for name, artifact in first["artifacts"].items():
                self.assertEqual(artifact["path"], name)
                self.assertEqual(artifact["sha256"], digest(root / "first" / name))
                self.assertEqual(artifact["bytes"], (root / "first" / name).stat().st_size)
            self.assertEqual(json.loads((root / "first/summary.json").read_text(encoding="utf-8")), first)

    def test_existing_directory_is_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "demo"
            run_demo(output)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(["--output-dir", str(output)]), 2)
            self.assertIn("already exists", err.getvalue())
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            empty = Path(folder) / "empty"
            empty.mkdir()
            with self.assertRaises(FileExistsError):
                run_demo(empty)

    def test_raw_path_and_packaged_inputs_are_protected(self):
        from importlib.resources import files
        with tempfile.TemporaryDirectory() as folder:
            forbidden = Path(folder) / "data/raw/new-demo"
            with self.assertRaisesRegex(ValueError, "data/raw|raw data"):
                run_demo(forbidden)
            self.assertFalse(forbidden.parent.exists())
        examples = files("goodsai").joinpath("examples", "synthetic")
        with self.assertRaises(ValueError):
            run_demo(Path(str(examples)) / "new-demo")

    def test_incorrect_prediction_cannot_produce_success_summary(self):
        def corrupted_predict(source, output, config):
            report = predict(source, output, config)
            rows = list(read_jsonl(output))
            rows[0]["attributes"][0]["value"] = "WrongBrand"
            with output.open("w", encoding="utf-8") as stream:
                for row in rows:
                    write_line(stream, row)
            report["output_sha256"] = digest(output)
            write_json(output.with_suffix(".manifest.json"), report)
            return report
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "demo"
            with patch("goodsai.demo.predict", side_effect=corrupted_predict):
                with self.assertRaisesRegex(ValueError, "value check failed"):
                    run_demo(output)
            self.assertFalse((output / "summary.json").exists())
            self.assertTrue((output / "predictions.jsonl").exists())

    def test_module_runs_outside_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, "-m", "goodsai.demo", "--output-dir", "demo"],
                                    cwd=folder, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["checks_passed"], 6)
            self.assertTrue((Path(folder) / "demo/summary.json").exists())


if __name__ == "__main__":
    unittest.main()
