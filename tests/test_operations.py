"""OPS-001 regressions: private artifacts, cancellation, and redacted failures."""
import ast
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from goodsai import cli, demo, storage
from goodsai.contracts import load_config

PRIVATE = "SYNTHETIC-PRIVATE-TEXT-AND-KEY"
SERVICE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "uvicorn"))
if SERVICE_DEPS:
    from goodsai.api import create_app
    from httpx import ASGITransport, AsyncClient


class OperationsTests(unittest.TestCase):
    def test_cli_errors_never_echo_exception_payload_or_path(self):
        failures = [(ValueError(PRIVATE), 2), (KeyError(PRIVATE), 2),
                    (FileNotFoundError(PRIVATE), 2), (PermissionError(PRIVATE), 2),
                    (OSError(PRIVATE), 2), (RuntimeError(PRIVATE), 1)]
        for exception, expected in failures:
            with self.subTest(error=type(exception).__name__), patch.object(cli, "load_config", side_effect=exception):
                with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                    code = cli.main(["predict", "--input", PRIVATE, "--output", PRIVATE + ".jsonl"])
                self.assertEqual(code, expected)
                self.assertNotIn(PRIVATE, out.getvalue() + err.getvalue())
                self.assertNotIn("Traceback", err.getvalue())
                self.assertEqual(out.getvalue(), "")
                self.assertIn("goodsai:", err.getvalue())

    def test_cli_cancellation_is_nonzero_without_traceback(self):
        with patch.object(cli, "load_config", side_effect=KeyboardInterrupt), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(["inventory"]), 130)
        self.assertIn("interrupted", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_demo_error_payload_is_not_printed(self):
        with patch.object(demo, "run_demo", side_effect=RuntimeError(PRIVATE)), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(demo.main([]), 1)
        self.assertNotIn(PRIVATE, err.getvalue())

    def test_runtime_package_has_no_pickle_or_research_import(self):
        root = Path(storage.__file__).parent
        for path in root.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [name.name for name in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse(any(name.split(".")[0] in {"pickle", "pickletools", "profile_catalog", "catalog_guard"} for name in names), path.name)

    @unittest.skipIf(os.name == "nt", "POSIX permissions; Windows ACLs require separate validation")
    def test_private_outputs_even_with_permissive_umask(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "private" / "record.json"
            old_umask = os.umask(0)
            try:
                with storage.atomic_text(output) as stream:
                    stream.write(PRIVATE)
                    stage = list(output.parent.glob("*.goodsai-*.tmp"))
                    self.assertEqual(len(stage), 1)
                    self.assertEqual(stat.S_IMODE(stage[0].stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output.parent.stat().st_mode), 0o700)
                lock = output.with_name("." + output.name + ".goodsai.lock")
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)
            finally:
                os.umask(old_umask)

    @unittest.skipIf(os.name == "nt", "Symlink/hardlink behavior tested on POSIX")
    def test_foreign_lock_links_do_not_modify_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, output = root / "unrelated", root / "prediction.jsonl"
            target.write_text(PRIVATE)
            mode = stat.S_IMODE(target.stat().st_mode)
            lock = output.with_name("." + output.name + ".goodsai.lock")
            lock.symlink_to(target)
            with self.assertRaises(ValueError), storage.output_lock(output):
                self.fail("Linked lock accepted")
            lock.unlink()
            os.link(target, lock)
            with self.assertRaises(ValueError), storage.output_lock(output):
                self.fail("Hard-linked lock accepted")
            self.assertEqual(target.read_text(), PRIVATE)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), mode)

    @unittest.skipIf(os.name == "nt", "Symlinks require separate Windows privileges")
    def test_recovery_rejects_symlinked_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, target = root / "prediction.jsonl", root / "unrelated.json"
            target.write_text(PRIVATE)
            storage._journal_path(output.with_suffix(".manifest.json")).symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic link"), storage.prediction_snapshot(output):
                self.fail("Linked journal accepted")
            self.assertEqual(target.read_text(), PRIVATE)

    def test_keyboard_interrupt_and_system_exit_restore_prediction_pair(self):
        for signal in (KeyboardInterrupt, SystemExit):
            with self.subTest(signal=signal.__name__), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source, output = root / "input.jsonl", root / "output.jsonl"
                source.write_text(json.dumps({"schema_version": "0.1", "sku_id": "synthetic", "category_id": "761", "title": "Samsung"}) + "\n")
                cli.predict(source, output, load_config())
                manifest = output.with_suffix(".manifest.json")
                before = output.read_bytes(), manifest.read_bytes()
                replace = storage.os.replace
                def interrupted(src, dst):
                    if Path(src).name == "manifest.new":
                        raise signal()
                    return replace(src, dst)
                with patch.object(storage.os, "replace", side_effect=interrupted), self.assertRaises(signal):
                    cli.predict(source, output, load_config())
                self.assertEqual(before, (output.read_bytes(), manifest.read_bytes()))
                self.assertFalse(storage._journal_path(manifest).exists())
                self.assertFalse(list(root.glob(".goodsai-txn-*")))


@unittest.skipUnless(SERVICE_DEPS, "Requires .[serve,test]")
class OperationalApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_validation_exception_is_not_exposed(self):
        app = create_app()
        with patch("goodsai.api.Product.from_dict", side_effect=ValueError(PRIVATE)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/predict", json={"secret": PRIVATE})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(PRIVATE, response.text)

    async def test_unexpected_request_failure_logs_only_fixed_message(self):
        app = create_app()
        with patch("goodsai.api.Product.from_dict", side_effect=RuntimeError(PRIVATE)), self.assertLogs("goodsai.api", level="ERROR") as logs:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/predict", json={"secret": PRIVATE})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(PRIVATE, response.text + str(logs.output))
        self.assertNotIn("Traceback", str(logs.output))
