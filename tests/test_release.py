"""Release integrity/publication checks on invented cards and a disposable Git repo."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from goodsai.cli import predict
from goodsai.contracts import load_config
from goodsai.data import digest
from goodsai.evaluate import evaluate

PROJECT = Path(__file__).resolve().parents[1]
MODULE = PROJECT / "scripts/release/build_release.py"
spec = importlib.util.spec_from_file_location("release_builder", MODULE)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.root = Path(cls.folder.name) / "repo"
        cls.root.mkdir()
        shutil.copytree(PROJECT / "src/goodsai", cls.root / "src/goodsai",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (cls.root / "scripts/release").mkdir(parents=True)
        shutil.copyfile(MODULE, cls.root / "scripts/release/build_release.py")
        (cls.root / "README.md").write_text("# Synthetic release fixture\n", encoding="utf-8")
        (cls.root / "pyproject.toml").write_text('[project]\nname="synthetic-fixture"\nversion="0.0.0"\n', encoding="utf-8")
        (cls.root / ".gitignore").write_text("/outputs/\n__pycache__/\n.env\n", encoding="utf-8")
        for args in [("init", "--quiet"), ("config", "core.autocrlf", "false"), ("add", "."),
                     ("-c", "user.name=Synthetic QA", "-c", "user.email=qa@example.invalid",
                      "commit", "--quiet", "-m", "synthetic source")]:
            subprocess.run(["git", "-C", str(cls.root), *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.commit = release.git(cls.root, "rev-parse", "HEAD")
        (cls.root / "outputs").mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root / "outputs")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.output = self.work / "bundle"
        self.config = load_config()
        self.product = {"schema_version": "0.1", "sku_id": "invented-phone", "category_id": "761",
                        "title": "Смартфон Samsung Orbit X82", "description": "PRIVATE-SYNTHETIC-CARD"}
        self.unknown = {"schema_version": "0.1", "sku_id": "invented-unknown", "category_id": "99999",
                        "title": "Invented unsupported product"}
        self.input = self.work / "input.jsonl"
        self.write_rows(self.input, [self.product, self.unknown])
        self.predictions = self.work / "predictions.jsonl"
        meta = {"git_commit": self.commit, "git_dirty": False,
                "code_sha256": release.code_hash(self.root), "config_sha256": release.config_hash(self.config),
                "python": "synthetic-test", "platform": "synthetic-test",
                "rules_version": self.config["rules_version"], "dictionary_version": self.config["dictionary_version"]}
        with patch("goodsai.cli.identity", return_value=meta):
            predict(self.input, self.predictions, self.config)
        self.eda = self.work / "eda.md"
        self.eda.write_text("# Invented EDA\nTwo synthetic cards, no catalogue data.\n", encoding="utf-8")
        self.presentation = self.work / "presentation.md"
        self.presentation.write_text("# Invented technical slides\n## Approach\nRules only.\n## Limits\nSynthetic fixture.\n", encoding="utf-8")
        self.spec = {"spec_version": "1", "source_commit": self.commit,
                     "config": self.record(self.root / "src/goodsai/baseline.json"),
                     "input": self.record(self.input), "predictions": self.record(self.predictions),
                     "eda": self.record(self.eda), "presentation": self.record(self.presentation)}

    @staticmethod
    def write_rows(path, rows):
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def record(self, path):
        return {"path": path.relative_to(self.root).as_posix(), "sha256": digest(path)}

    def run_build(self, spec=None):
        return release.build(self.output, self.spec if spec is None else spec, root=self.root)

    def add_reference(self):
        title = self.product["title"]
        labels = []
        for name in self.config["categories"]["761"]:
            value = {"brand": "Samsung", "model": "Orbit X82"}.get(name)
            start = title.index(value) if value else None
            labels.append({"attribute": name, "status": "present" if value else "absent", "value": value,
                           "unit": None, "evidence": {"field": "title", "start": start,
                           "end": start + len(value), "text": value} if value else None})
        row = self.product | {"split": "development", "annotation_status": "reviewed", "label_source": "manual",
                              "annotator": "invented-fixture", "attributes": labels}
        path = self.work / "reference.jsonl"
        self.write_rows(path, [row])
        self.spec.update(reference=self.record(path), reference_kind="ai_assisted_reviewed_development")
        return path, row

    def assert_incomplete(self, result, code):
        self.assertEqual(result["status"], "incomplete")
        self.assertIn(code, [issue["code"] for issue in result["issues"]])
        saved = json.loads((self.output / "release.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(result, saved)

    def test_complete_bundle_checks_all_six_and_never_claims_quality_without_gold(self):
        result = self.run_build()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(set(result["required_artifacts"]), set(release.REQUIRED))
        self.assertTrue(all(a["status"] == "verified" for a in result["required_artifacts"].values()))
        self.assertEqual(result["checks"]["rows"], 2)
        self.assertEqual(result["checks"]["status_counts"], {"processed": 1, "unsupported_category": 1})
        self.assertEqual(result["publication"], "local_only")
        self.assertEqual(result["release_approval"], "not_granted")
        quality = json.loads((self.output / "public/quality.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["report"]["evaluation_status"], "unavailable")
        self.assertIsNone(quality["report"]["f1"])
        for item in result["files"]:
            path = self.output / item["path"]
            self.assertEqual(digest(path), item["sha256"])
        # Raw texts and external documents have no path into the public export.
        self.assertIn(b"PRIVATE-SYNTHETIC-CARD", (self.output / "private/input.jsonl").read_bytes())
        for path in (self.output / "public").rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE-SYNTHETIC-CARD", path.read_bytes())
        with zipfile.ZipFile(self.output / "public/code.zip") as archive:
            self.assertIn("src/goodsai/cli.py", archive.namelist())
            self.assertIn("scripts/release/build_release.py", archive.namelist())
            self.assertFalse(any(name.startswith(("data/", "outputs/")) for name in archive.namelist()))

    def test_reviewed_reference_subset_and_supplied_metrics_are_checked(self):
        path, _ = self.add_reference()
        old = self.work / "metrics.json"
        old.write_text(json.dumps(evaluate(self.predictions, path, self.config)), encoding="utf-8")
        self.spec["metrics"] = self.record(old)
        result = self.run_build()
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["quality"]["independent_reference"])
        report = json.loads((self.output / "public/quality.json").read_text(encoding="utf-8"))["report"]
        self.assertEqual(report["metrics"]["micro"]["tp"], 2)

    def test_missing_or_empty_documents_cannot_produce_complete(self):
        for name in ["eda", "presentation"]:
            with self.subTest(name=name):
                old = getattr(self, name)
                data = old.read_bytes()
                old.unlink()
                self.output = self.work / (name + "-missing")
                self.assert_incomplete(self.run_build(), "missing_artifact")
                old.write_bytes(data)
        self.presentation.write_text("", encoding="utf-8")
        self.output = self.work / "empty"
        self.assert_incomplete(self.run_build(), "empty_artifact")

    def test_stale_hash_and_prediction_identity_are_rejected(self):
        self.eda.write_text("Changed after approval", encoding="utf-8")
        self.assert_incomplete(self.run_build(), "artifact_hash_mismatch")
        self.spec["eda"] = self.record(self.eda)
        manifest_path = self.predictions.with_suffix(".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["code_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.output = self.work / "wrong-identity"
        self.assert_incomplete(self.run_build(), "prediction_identity_mismatch")

    def test_rehashed_wrong_sku_is_still_rejected(self):
        rows = [json.loads(line) for line in self.predictions.read_text(encoding="utf-8").splitlines()]
        rows[1]["sku_id"] = "invented-other-sku"
        self.write_rows(self.predictions, rows)
        manifest_path = self.predictions.with_suffix(".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["output_sha256"] = digest(self.predictions)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.spec["predictions"] = self.record(self.predictions)
        self.assert_incomplete(self.run_build(), "sku_mismatch")

    def test_reference_text_and_pending_labels_are_rejected(self):
        path, row = self.add_reference()
        row["title"] = "Different invented title"
        self.write_rows(path, [row])
        self.spec["reference"] = self.record(path)
        self.assert_incomplete(self.run_build(), "reference_input_mismatch")
        row["title"] = self.product["title"]
        row["annotation_status"] = "pending"
        self.write_rows(path, [row])
        self.spec["reference"] = self.record(path)
        self.output = self.work / "pending"
        self.assert_incomplete(self.run_build(), "reference_unreviewed")

    def test_reserved_reference_is_not_evaluated(self):
        path, row = self.add_reference()
        row["split"] = "test_reserved"
        self.write_rows(path, [row])
        self.spec["reference"] = self.record(path)
        with patch.object(release, "evaluate", side_effect=AssertionError("must not evaluate reserved test")):
            self.assert_incomplete(self.run_build(), "reserved_reference")

    def test_wrong_metrics_and_unproven_metrics_are_rejected(self):
        path, _ = self.add_reference()
        old = self.work / "metrics.json"
        wrong = evaluate(self.predictions, path, self.config)
        wrong["metrics"]["micro"]["tp"] += 1
        old.write_text(json.dumps(wrong), encoding="utf-8")
        self.spec["metrics"] = self.record(old)
        self.assert_incomplete(self.run_build(), "metrics_mismatch")
        del self.spec["reference"]
        del self.spec["reference_kind"]
        self.output = self.work / "unproven"
        self.assert_incomplete(self.run_build(), "metrics_without_reference")

    def test_dirty_checkout_and_wrong_commit_are_rejected(self):
        self.spec["source_commit"] = "0" * 40
        self.assert_incomplete(self.run_build(), "source_commit_mismatch")
        self.spec["source_commit"] = self.commit
        dirty = self.root / "untracked.txt"
        try:
            dirty.write_text("synthetic dirty tree", encoding="utf-8")
            self.output = self.work / "dirty"
            self.assert_incomplete(self.run_build(), "dirty_source")
        finally:
            dirty.unlink()

    def test_external_config_and_non_rules_manifests_are_rejected(self):
        config = self.work / "config-with-external-settings.json"
        config.write_text(json.dumps(self.config | {"api_key": "SYNTHETIC-DO-NOT-PUBLISH"}), encoding="utf-8")
        self.spec["config"] = self.record(config)
        self.assert_incomplete(self.run_build(), "unsupported_config")
        self.assertFalse((self.output / "public/pipeline/config.json").exists())
        self.spec["config"] = self.record(self.root / "src/goodsai/baseline.json")
        manifest_path = self.predictions.with_suffix(".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["llm_calls"] = 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.output = self.work / "unsupported-runtime"
        self.assert_incomplete(self.run_build(), "unsupported_runtime")

    def test_same_inputs_produce_the_same_bundle_hashes(self):
        first = self.run_build()
        self.output = self.work / "second-bundle"
        second = self.run_build()
        self.assertEqual(first, second)

    def test_transferred_bundle_verification_and_tamper_detection(self):
        self.run_build()
        checked = release.verify_bundle(self.output)
        self.assertEqual(checked["status"], "verified")
        (self.output / "private/presentation.md").write_text("Changed in transit", encoding="utf-8")
        with self.assertRaisesRegex(release.BuildError, "absent or changed"):
            release.verify_bundle(self.output)

    def test_verifier_rejects_traversal_and_extra_files(self):
        self.run_build()
        marker = self.output / "release.manifest.json"
        manifest = json.loads(marker.read_text(encoding="utf-8"))
        manifest["files"][0]["path"] = "../../not-a-bundle-file"
        marker.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(release.BuildError, "remain inside"):
            release.verify_bundle(self.output)
        self.output = self.work / "extra"
        self.run_build()
        (self.output / "public/extra.json").write_text('{"unapproved":"fixture"}', encoding="utf-8")
        with self.assertRaisesRegex(release.BuildError, "inventory differs"):
            release.verify_bundle(self.output)

    def test_incomplete_bundle_cannot_pass_transfer_check(self):
        self.eda.unlink()
        self.run_build()
        with self.assertRaisesRegex(release.BuildError, "Incomplete"):
            release.verify_bundle(self.output)

    def test_existing_directory_and_unsafe_output_are_not_modified(self):
        self.run_build()
        before = {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            self.run_build()
        self.assertEqual(before, {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob("*") if p.is_file()})
        forbidden = self.root / "data/raw/bundle"
        with self.assertRaisesRegex(release.BuildError, "outputs"):
            release.build(forbidden, self.spec, root=self.root)
        self.assertFalse(forbidden.parent.exists())

    def test_validation_failure_does_not_publish_exception_payload(self):
        self.add_reference()
        with patch.object(release, "evaluate", side_effect=ValueError("PRIVATE-EXCEPTION-PAYLOAD")):
            self.assert_incomplete(self.run_build(), "artifact_validation_failed")
        self.assertNotIn("PRIVATE-EXCEPTION-PAYLOAD", (self.output / "release.manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("PRIVATE-EXCEPTION-PAYLOAD", (self.output / "public/report.md").read_text(encoding="utf-8"))

    def test_smoke_uses_only_packaged_examples_and_is_not_a_six_artifact_release(self):
        result = release.build(self.output, root=self.root, smoke=True)
        self.assertEqual(result["status"], "synthetic_smoke")
        self.assertEqual(result["checks"]["passed"], 6)
        self.assertIsNone(result["quality"]["f1"])
        self.assertEqual(result["required_artifacts"]["eda"]["status"], "missing")
        self.assertEqual(result["required_artifacts"]["presentation"]["status"], "missing")
        self.assertFalse((self.output / "private").exists())
        self.output = self.work / "external-smoke"
        self.assert_incomplete(release.build(self.output, self.spec, root=self.root, smoke=True), "smoke_external_input")

    def test_cli_failure_is_nonzero_and_sanitized(self):
        missing = self.work / "missing-spec.json"
        with redirect_stderr(io.StringIO()) as error, redirect_stdout(io.StringIO()):
            code = release.main(["assemble", "--spec", str(missing), "--output-dir", str(self.output)])
        self.assertEqual(code, 2)
        self.assertIn("release assembly failed", error.getvalue())


if __name__ == "__main__":
    unittest.main()
