"""ENV-002 runner integrity, failure recovery and isolation; synthetic inputs only."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.release import clean_run as runner
from goodsai.cli import predict
from goodsai.contracts import load_config


class CleanRunTests(unittest.TestCase):
    def test_cached_run_rechecks_every_artifact_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "prediction").write_text("synthetic")
            identity = {"git_commit": "fixture"}
            report = {"status": "passed", "identity": identity, "files": {"prediction": runner.sha(root / "prediction")}}
            self.assertTrue(runner.verified_cached(root, report, identity))
            self.assertFalse(runner.verified_cached(root, report, {"git_commit": "changed"}))
            (root / "prediction").write_text("changed")
            with self.assertRaisesRegex(ValueError, "artifacts changed"):
                runner.verified_cached(root, report, identity)
            report["files"] = {"../escape": "fake"}
            with self.assertRaises(ValueError):
                runner.verified_cached(root, report, identity)

    def test_reservation_excludes_second_writer_and_releases_after_error(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.assertRaisesRegex(ValueError, "synthetic"):
                with runner.reserve(output):
                    with self.assertRaises(FileExistsError):
                        with runner.reserve(output):
                            self.fail("second writer acquired lock")
                    raise ValueError("synthetic")
            self.assertFalse((output / ".runner-lock").exists())

    def test_external_pair_validates_manifest_evidence_and_card_count(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / "input.jsonl").write_text(json.dumps({"schema_version": "0.1", "sku_id": "new-external",
                    "category_id": "482", "title": "Чайник Bosch KX-82 1,7 л 2200 Вт"}) + "\n", encoding="utf-8")
            predict(work / "input.jsonl", work / "predictions.jsonl", load_config())
            runner.verify_pair(work)
            result = json.loads((work / "predictions.jsonl").read_text(encoding="utf-8"))
            result["attributes"][0]["evidence"]["text"] = "wrong"
            (work / "predictions.jsonl").write_text(json.dumps(result) + "\n")
            with self.assertRaises(ValueError):
                runner.verify_pair(work)

    def test_failure_report_is_safe_and_retry_preserves_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            source = output / "source.jsonl"
            source.write_text("SECRET synthetic input")
            with patch.object(runner, "destination", return_value=output), patch.object(runner, "preflight", return_value={"git_commit": "fixture"}), \
                    patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 7, b"SECRET", b"SECRET")):
                first = runner.run(output, source)
                second = runner.run(output, source)
            self.assertEqual(first["status"], "failed")
            self.assertEqual(first["stages"][0]["exit_code"], 7)
            self.assertEqual(second["attempt"], "attempt-0002")
            self.assertTrue((output / "attempt-0001").is_dir())
            self.assertNotIn("SECRET", (output / "report.json").read_text())
            self.assertNotIn("SECRET", (output / "report.md").read_text())

    def test_timeout_is_named_and_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with patch.object(runner, "destination", return_value=output), patch.object(runner, "preflight", return_value={"git_commit": "fixture"}), \
                    patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired("private", 1, output=b"SECRET")):
                report = runner.run(output, output / "unused")
            self.assertEqual(report["stages"][0]["error_kind"], "TimeoutExpired")
            self.assertIsNone(report["stages"][0]["exit_code"])
            self.assertEqual(report["status"], "failed")

    def test_preflight_rejects_dirty_source_low_disk_and_wrong_python(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with patch.object(runner.sys, "version_info", (3, 11)):
                with self.assertRaisesRegex(ValueError, "3.12"):
                    runner.preflight(output, output)
            with patch.object(runner.sys, "version_info", (3, 12)), patch.object(runner.platform, "system", return_value="Linux"), \
                    patch.object(runner.platform, "machine", return_value="x86_64"), patch.object(runner, "git", return_value="dirty"):
                with self.assertRaisesRegex(ValueError, "clean checkout"):
                    runner.preflight(output, output)
            with patch.object(runner.sys, "version_info", (3, 12)), patch.object(runner.platform, "system", return_value="Linux"), \
                    patch.object(runner.platform, "machine", return_value="x86_64"), patch.object(runner, "git", return_value=""), \
                    patch.object(runner.shutil, "disk_usage", return_value=shutil_usage()):
                with self.assertRaisesRegex(ValueError, "512 MiB"):
                    runner.preflight(output, output)

    def test_destination_rejects_outside_outputs(self):
        with self.assertRaises(ValueError):
            runner.destination(runner.ROOT / "data/raw/new-run")
        with self.assertRaises(ValueError):
            runner.destination(runner.ROOT / "src/new-run")


def shutil_usage():
    from collections import namedtuple
    return namedtuple("usage", "total used free")(100, 99, 1)
