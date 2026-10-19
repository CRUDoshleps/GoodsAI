"""Only synthetic primitive catalogues are inspected or decoded in these checks."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import stat
import tempfile
import unittest
from unittest.mock import patch

from catalog_guard import validate_scan, verified_catalog
import inspect_pickle
import profile_catalog


class CatalogBoundaryTests(unittest.TestCase):
    def source(self, root):
        path = root / "catalog.pkl"
        value = {"yml_catalog": {"@date": "synthetic", "shop": {
            "categories": {"category": [{"@id": "761", "#text": "Synthetic"}]},
            "offers": {"offer": [{"@id": "invented", "name": "PRIVATE-SYNTHETIC-CARD",
                                   "categories": {"categoryId": "761"}, "param": []}]}}}}
        path.write_bytes(pickle.dumps(value, protocol=4))
        scan = inspect_pickle.inspect(path)
        metadata = root / "scan.json"
        metadata.write_text(json.dumps(scan))
        return path, scan, metadata

    def test_valid_catalog_publishes_projection_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, scan, metadata = self.source(root)
            before = source.read_bytes()
            out = root / "out"
            args = ["--trusted-pickle", "--input", str(source), "--scan", str(metadata), "--output-dir", str(out)]
            with redirect_stdout(io.StringIO()) as log:
                profile_catalog.main(args)
            self.assertNotIn("PRIVATE-SYNTHETIC-CARD", log.getvalue())
            report = json.loads((out / "catalog_profile.json").read_text())
            self.assertEqual(report["rows"], 1)
            self.assertEqual(report["source_sha256"], scan["source_sha256"])
            snapshot = {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()}
            with self.assertRaises(FileExistsError):
                profile_catalog.main(args)
            self.assertEqual(snapshot, {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()})
            self.assertEqual(source.read_bytes(), before)
            if os.name != "nt":
                for name in ("catalog_profile.json", "catalog_skus.parquet"):
                    self.assertEqual(stat.S_IMODE((out / name).stat().st_mode), 0o600)
            self.assertFalse(list(out.glob(".goodsai-profile-*")))

    def test_missing_trust_flag_rejects_before_reading(self):
        from contextlib import redirect_stderr
        with patch.object(Path, "open", side_effect=AssertionError("Input was opened")), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                profile_catalog.main([])

    def test_research_outputs_cannot_write_to_raw_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _, metadata = self.source(root)
            raw = root / "data/raw"
            with patch("goodsai.data.Path.cwd", return_value=root):
                with self.assertRaises(ValueError):
                    inspect_pickle.main([str(source), str(raw / "scan.json")])
                with self.assertRaises(ValueError):
                    profile_catalog.main(["--trusted-pickle", "--input", str(source), "--scan", str(metadata), "--output-dir", str(raw)])
            self.assertFalse(raw.exists())

    def test_mismatch_is_rejected_before_decode_and_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, scan, metadata = self.source(root)
            source.write_bytes(source.read_bytes() + b"changed")
            with patch.object(profile_catalog.CatalogReader, "load", side_effect=AssertionError("Decode must not start")), self.assertRaises(ValueError):
                profile_catalog.main(["--trusted-pickle", "--input", str(source), "--scan", str(metadata), "--output-dir", str(root / "out")])
            self.assertFalse((root / "out/catalog_skus.parquet").exists())

    def test_mutation_and_path_replacement_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for replace in (False, True):
                source, scan, _ = self.source(root)
                with self.subTest(replace=replace), self.assertRaises(ValueError):
                    with verified_catalog(source, scan) as stream:
                        stream.read()
                        if replace:
                            alternate = root / "alternate.pkl"
                            alternate.write_bytes(source.read_bytes())
                            os.replace(alternate, source)
                        else:
                            source.write_bytes(b"changed")

    def test_decode_failure_cleans_private_stage_without_public_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _, metadata = self.source(root)
            with patch.object(profile_catalog.CatalogReader, "load", side_effect=ValueError("synthetic failure")), self.assertRaises(ValueError):
                profile_catalog.main(["--trusted-pickle", "--input", str(source), "--scan", str(metadata), "--output-dir", str(root / "out")])
            self.assertFalse((root / "out/catalog_skus.parquet").exists())
            self.assertFalse(list((root / "out").glob(".goodsai-profile-*")))

    def test_scan_metadata_is_strict(self):
        with tempfile.TemporaryDirectory() as folder:
            _, scan, _ = self.source(Path(folder))
            for patch_value in [{"opcodes": {"REDUCE": 1}}, {"memo_entries": True},
                                {"referenced_indices": [-1]}, {"source_sha256": "invalid"}]:
                with self.subTest(patch_value=patch_value), self.assertRaises(ValueError):
                    validate_scan(scan | patch_value)

    def test_change_after_profile_prevents_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _, metadata = self.source(root)
            original = profile_catalog.profile
            def mutate(stream, scan, stage):
                result = original(stream, scan, stage)
                source.write_bytes(b"changed after decoding")
                return result
            out = root / "out"
            with patch.object(profile_catalog, "profile", side_effect=mutate), self.assertRaises(ValueError):
                profile_catalog.main(["--trusted-pickle", "--input", str(source), "--scan", str(metadata), "--output-dir", str(out)])
            self.assertFalse((out / "catalog_skus.parquet").exists())
            self.assertFalse((out / "catalog_profile.json").exists())
            self.assertFalse(list(out.glob(".goodsai-profile-*")))

    def test_forbidden_opcode_blocks_even_a_cached_extension(self):
        # A malicious opcode report cannot authorize an opcode in the decoder.
        for payload in [b"\x80\x04\x82\x01.", b"\x80\x04)R."]:
            with patch.dict(pickle._extension_cache, {1: "PRIVATE-CACHED-VALUE"}), self.assertRaisesRegex(ValueError, "forbidden"):
                profile_catalog.CatalogReader(io.BytesIO(payload), set(), lambda _: None).load()

    def test_inspector_never_overwrites_source_or_previous_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _, _ = self.source(root)
            before = source.read_bytes()
            with self.assertRaises(ValueError):
                inspect_pickle.main([str(source), str(source)])
            report = root / "report.json"
            with redirect_stdout(io.StringIO()):
                inspect_pickle.main([str(source), str(report)])
            snapshot = report.read_bytes()
            with self.assertRaises(FileExistsError):
                inspect_pickle.main([str(source), str(report)])
            self.assertEqual(snapshot, report.read_bytes())
            self.assertEqual(before, source.read_bytes())
