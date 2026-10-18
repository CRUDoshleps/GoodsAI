"""Crash and concurrency checks use real child processes and synthetic JSONL only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from goodsai.cli import predict
from goodsai.contracts import load_config
from goodsai.data import atomic_text, digest, read_predictions
from goodsai.evaluate import evaluate
from goodsai import storage


WORKER = r'''
import json,sys
from pathlib import Path
from goodsai import storage
from goodsai.cli import predict
from goodsai.contracts import load_config
from goodsai.data import atomic_text,read_predictions
mode,source,output,ready=sys.argv[1:]
source,output,ready=map(Path,[source,output,ready])
def wait():
    ready.write_text('ready')
    sys.stdin.readline()
if mode=='atomic':
    with atomic_text(output) as f:
        f.write('child')
        wait()
elif mode=='recovery':
    replace=storage.os.replace
    def interrupted(src,dst):
        replace(src,dst)
        if Path(src).name=='restore-0': wait()
    storage.os.replace=interrupted
    list(read_predictions(output))
elif mode=='committed':
    recover=storage._recover
    def interrupted(out,manifest):
        journal=storage._journal_path(manifest)
        if journal.exists() and json.loads(journal.read_text())['phase']=='committed': wait()
        recover(out,manifest)
    storage._recover=interrupted
    predict(source,output,load_config())
else:
    replace=storage.os.replace
    def interrupted(src,dst):
        replace(src,dst)
        if Path(src).name==mode and Path(dst).parent==output.parent: wait()
    storage.os.replace=interrupted
    predict(source,output,load_config())
'''


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "input.jsonl"
        self.output = self.root / "predictions.jsonl"
        self.manifest = self.output.with_suffix(".manifest.json")
        self.config = load_config()
        self.source.write_text(json.dumps({"schema_version": "0.1", "sku_id": "old",
                               "category_id": "761", "title": "Samsung Synthetic 8/256GB"}) + "\n", encoding="utf-8")

    def start(self, mode):
        ready = self.root / ("ready-" + str(time.monotonic_ns()))
        child = subprocess.Popen([sys.executable, "-c", WORKER, mode, str(self.source),
                                  str(self.output), str(ready)], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop, child)
        deadline = time.monotonic() + 15
        while not ready.exists():
            if child.poll() is not None:
                _, err = child.communicate()
                self.fail("Worker exited before checkpoint: " + err.decode("utf-8", errors="replace"))
            if time.monotonic() > deadline:
                self.fail("Worker checkpoint timed out")
            time.sleep(.01)
        return child

    @staticmethod
    def stop(child):
        if child.poll() is None:
            child.terminate()
        child.communicate(timeout=15)

    def seed(self):
        predict(self.source, self.output, self.config)
        old = self.output.read_bytes(), self.manifest.read_bytes()
        self.source.write_text(json.dumps({"schema_version": "0.1", "sku_id": "new",
                               "category_id": "761", "title": "Samsung Synthetic 12/512GB"}) + "\n", encoding="utf-8")
        return old

    def assert_clean_pair(self, old=None):
        rows = list(read_predictions(self.output))
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["output_sha256"], digest(self.output))
        self.assertTrue(all(r["run_id"] == manifest["run_id"] for r in rows))
        if old:
            self.assertEqual(old, (self.output.read_bytes(), self.manifest.read_bytes()))
        self.assertFalse(storage._journal_path(self.manifest).exists())
        self.assertFalse(list(self.root.glob(".goodsai-txn-*")))
        return rows

    def test_single_file_exception_preserves_old_and_foreign_temp(self):
        self.output.write_text("old", encoding="utf-8")
        foreign = self.output.with_name(self.output.name + ".tmp")
        foreign.write_text("foreign", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            with atomic_text(self.output) as stream:
                stream.write("new")
                raise RuntimeError("interrupted")
        self.assertEqual(self.output.read_text(), "old")
        self.assertEqual(foreign.read_text(), "foreign")
        self.assertFalse(list(self.root.glob("*.goodsai-*.tmp")))

    def test_competing_process_is_rejected_and_other_output_is_independent(self):
        child = self.start("atomic")
        with self.assertRaises(storage.OutputBusyError):
            with atomic_text(self.output):
                self.fail("Competing writer acquired destination")
        cli = subprocess.run([sys.executable, "-m", "goodsai.cli", "predict", "--input", str(self.source),
                              "--output", str(self.output)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(cli.returncode, 2)
        self.assertIn("Output is busy", cli.stderr)
        self.assertNotIn("Traceback", cli.stderr)
        other = self.root / "independent.jsonl"
        with atomic_text(other) as stream:
            stream.write("independent")
        self.assertEqual(other.read_text(), "independent")
        child.communicate(input=b"\n", timeout=15)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(self.output.read_text(), "child")

    def test_killed_single_writer_releases_lock_and_stale_temp_is_reclaimed(self):
        self.output.write_text("old")
        child = self.start("atomic")
        self.stop(child)
        self.assertEqual(self.output.read_text(), "old")
        with atomic_text(self.output) as stream:
            stream.write("next")
        self.assertEqual(self.output.read_text(), "next")
        self.assertFalse(list(self.root.glob("*.goodsai-*.tmp")))

    def test_failure_between_pair_replacements_rolls_back_both(self):
        old = self.seed()
        replace = storage.os.replace
        def failed(source, destination):
            if Path(source).name == "manifest.new" and Path(destination) == self.manifest:
                raise OSError("Injected publication failure")
            return replace(source, destination)
        with patch("goodsai.storage.os.replace", side_effect=failed):
            with self.assertRaisesRegex(OSError, "Injected publication failure"):
                predict(self.source, self.output, self.config)
        self.assert_clean_pair(old)

    def test_malformed_input_does_not_replace_previous_pair(self):
        old = self.seed()
        self.source.write_text("{broken json\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid JSON"):
            predict(self.source, self.output, self.config)
        self.assert_clean_pair(old)

    def test_first_publication_failure_leaves_no_partial_pair(self):
        replace = storage.os.replace
        def failed(source, destination):
            if Path(source).name == "manifest.new" and Path(destination) == self.manifest:
                raise OSError("Injected first-publication failure")
            return replace(source, destination)
        with patch("goodsai.storage.os.replace", side_effect=failed):
            with self.assertRaises(OSError):
                predict(self.source, self.output, self.config)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(storage._journal_path(self.manifest).exists())

    def test_kill_between_replacements_recovers_old_pair_and_rejects_live_readers(self):
        old = self.seed()
        child = self.start("data.new")
        with self.assertRaises(storage.OutputBusyError):
            list(read_predictions(self.output))
        with self.assertRaises(storage.OutputBusyError):
            predict(self.source, self.output, self.config)
        # Different extensions share a manifest basename, and must not race either.
        with self.assertRaises(storage.OutputBusyError):
            predict(self.source, self.output.with_suffix(".csv"), self.config)
        self.stop(child)
        self.assert_clean_pair(old)
        predict(self.source, self.output, self.config)
        self.assertEqual(self.assert_clean_pair()[0]["sku_id"], "new")

    def test_kill_before_commit_rolls_back_but_after_commit_keeps_new_pair(self):
        for mode, expected in [("manifest.new", "old"), ("committed", "new")]:
            with self.subTest(mode=mode):
                self.source.write_text(json.dumps({"schema_version": "0.1", "sku_id": "old",
                                       "category_id": "761", "title": "Samsung Synthetic 8/256GB"}) + "\n")
                self.seed()
                child = self.start(mode)
                self.stop(child)
                self.assertEqual(self.assert_clean_pair()[0]["sku_id"], expected)

    def test_recovery_itself_can_be_interrupted_and_retried(self):
        old = self.seed()
        child = self.start("data.new")
        self.stop(child)
        recovery = self.start("recovery")
        self.stop(recovery)
        self.assert_clean_pair(old)

    def test_corrupt_backup_is_not_silently_accepted_or_discarded(self):
        self.seed()
        child = self.start("data.new")
        self.stop(child)
        journal = storage._journal_path(self.manifest)
        state = json.loads(journal.read_text())
        (self.root / state["directory"] / "old-0").write_text("damaged")
        with self.assertRaisesRegex(ValueError, "recovery failed"):
            list(read_predictions(self.output))
        with self.assertRaisesRegex(ValueError, "recovery failed"):
            predict(self.source, self.output, self.config)
        self.assertTrue(journal.exists())

    def test_invalid_journal_cannot_delete_an_unrelated_directory(self):
        self.seed()
        child = self.start("data.new")
        self.stop(child)
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        marker = unrelated / "keep.txt"
        marker.write_text("keep")
        journal = storage._journal_path(self.manifest)
        state = json.loads(journal.read_text())
        state["directory"] = "../" + self.root.name + "/unrelated"
        journal.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "recovery failed"):
            list(read_predictions(self.output))
        self.assertEqual(marker.read_text(), "keep")
        self.assertTrue(journal.exists())

    def test_reader_and_evaluator_reject_mismatched_manifest_but_accept_standalone(self):
        predict(self.source, self.output, self.config)
        with self.output.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            list(read_predictions(self.output))
        gold = self.root / "gold.jsonl"
        gold.write_text("")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            evaluate(self.output, gold, self.config)
        self.manifest.write_text("[]")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            list(read_predictions(self.output))
        standalone = self.root / "standalone.jsonl"
        standalone.write_text(json.dumps({"sku_id": "standalone"}) + "\n")
        self.assertEqual(list(read_predictions(standalone)), [{"sku_id": "standalone"}])


if __name__ == "__main__":
    unittest.main()
