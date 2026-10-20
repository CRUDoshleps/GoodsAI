"""Synthetic checks only: frozen comparison safety and pre-prediction selection."""
import importlib.util
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl
from goodsai.silver_prepare import dump, write_rows
from goodsai.silver_prepare import assemble, VERSION

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checkpoint", ROOT / "scripts/research/prepare_checkpoint.py")
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)
import compare_silver_baseline as comparison


def pair(sku, tp=0, fp=0, fn=0):
    return {"sku_id": sku, "attribute": "brand", "category_id": "761", "method": "rules",
            "support": "supported", "reference_status": "known", "counts": {"tp": tp, "fp": fp, "fn": fn}}


class PairedTests(unittest.TestCase):
    def test_gains_do_not_cancel_regressions(self):
        old = [pair("gain", fn=1), pair("loss", tp=1), pair("wrong", fn=1)]
        new = [pair("gain", tp=1), pair("loss", fn=1), pair("wrong", fp=1, fn=1)]
        result, private = comparison.paired_changes(old, new)
        self.assertEqual(result["counts"]["new_tp"], 1)
        self.assertEqual(result["counts"]["lost_tp"], 1)
        self.assertEqual(result["counts"]["new_fp"], 1)
        self.assertEqual(len(private), 3)
        self.assertNotIn("sku_id", json.dumps(result))
        self.assertNotIn("value", json.dumps(private))

    def test_mismatched_population_rejected(self):
        with self.assertRaisesRegex(ValueError, "paired_population"):
            comparison.paired_changes([pair("a")], [pair("b")])
        with self.assertRaisesRegex(ValueError, "duplicate_paired"):
            comparison.paired_changes([pair("a"), pair("a")], [pair("a")])

    def test_output_refuses_existing_or_non_private_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "private_outputs"):
                comparison.private_output(Path(tmp) / "outside")
        with self.assertRaisesRegex(ValueError, "private_outputs"):
            comparison.private_output(ROOT / "outputs")

    def test_isolated_runtime_actual_cold_warm_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.jsonl"
            config = root / "config.json"
            write_rows(source, [Product("synthetic-only", "761", "Samsung").as_dict()])
            dump(config, load_config())
            before = digest(source)
            sha = comparison.git("rev-parse", "HEAD")
            with patch.dict("os.environ", {"GOODSAI_LLM_MODEL": "must-not-be-used", "OPENAI_API_KEY": "synthetic-never-a-secret"}):
                comparison.runtime_run(sha, config, source, root / "candidate")
            self.assertEqual(digest(source), before)
            a = root / "candidate/cold.jsonl"
            b = root / "candidate/warm.jsonl"
            self.assertEqual(digest(a), digest(b))
            manifest = json.loads(a.with_suffix(".manifest.json").read_text())
            self.assertEqual(manifest["git_commit"], sha)
            self.assertEqual(manifest["llm_calls"], 0)
            self.assertEqual(len(list(read_jsonl(a))), 1)

    def test_historical_runtime_accepts_its_frozen_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, config = root / "input.jsonl", root / "config.json"
            write_rows(source, [Product("synthetic-only", "761", "Samsung").as_dict()])
            sha = comparison.git("rev-parse", "f33e3fc^{commit}")
            config.write_text(comparison.git("show", sha + ":src/goodsai/baseline.json"))
            comparison.runtime_run(sha, config, source, root / "historical")
            comparison.runtime_run(comparison.git("rev-parse", "HEAD"), config, source, root / "current")
            for name in ("historical", "current"):
                manifest = json.loads((root / name / "cold.manifest.json").read_text())
                self.assertEqual(manifest["input_sha256"], digest(source))
                self.assertEqual(manifest["llm_calls"], 0)

    def test_handoff_has_fingerprints_and_no_fabricated_measurements(self):
        (ROOT / "outputs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            out = Path(tmp) / "new"
            args = argparse.Namespace(candidate="HEAD", output_dir=out, bundle=None,
                                      train=None, split=None, traffic=None, min_support=30)
            result = checkpoint.prepare(args)
            self.assertEqual(result["status"], "prepared_no_inference")
            handoff = json.loads((out / "eval-007.handoff.json").read_text())
            self.assertEqual(len(handoff["expected_bundle_manifest_sha256"]), 64)
            self.assertEqual(handoff["status"], "missing_private_bundle")
            model = json.loads((out / "eval-008.plan.json").read_text())
            self.assertIsNone(model["gateway_plan"]["packet_sha256_authorized"])
            self.assertTrue(all(v["status"] == "not_run" for v in model["methods"].values()))
            self.assertNotIn("accuracy", json.dumps(model))


class PilotTests(unittest.TestCase):
    def train(self, root, categories=("new-a", "new-b", "new-c", "761")):
        train, split, traffic = [root / x for x in ("train.jsonl", "split.json", "traffic.json")]
        data = [{"sku_id": f"{cat}-{i}", "category_id": cat, "title": "invented only", "description": None,
                 "params": [{"name": "Synthetic capacity", "value": "8", "unit": "GB"}]} for cat in categories for i in range(3)]
        write_rows(train, reversed(data))
        dump(split, {"schema_version": "goodsai-train-split-1", "train_sha256": digest(train),
                     "train_sku_ids": [r["sku_id"] for r in data], "validation_sku_ids": ["not-train"], "test_sku_ids": []})
        dump(traffic, {"schema_version": "goodsai-category-traffic-1", "scope": "train", "train_sha256": digest(train),
                       "category_traffic": {cat: 1 for cat in categories}})
        return train, split, traffic

    def test_selection_is_train_only_deterministic_and_not_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.train(Path(tmp))
            result = checkpoint.pilot_selection(*paths, excluded={"761"}, min_support=3)
            self.assertEqual([r["category_id"] for r in result["categories"]], ["new-a", "new-b", "new-c"])
            self.assertEqual(result["inference"], "not_run")
            self.assertIsNone(result["quality"])
            self.assertFalse(result["default_enable"])

    def test_insufficient_categories_not_replaced_by_existing_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.train(Path(tmp), ("new-a", "761"))
            result = checkpoint.pilot_selection(*paths, excluded={"761"}, min_support=3)
            self.assertEqual(result["status"], "insufficient_new_categories")
            self.assertEqual(len(result["categories"]), 1)

    def test_hash_tampering_and_non_train_membership_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.train(Path(tmp))
            with paths[0].open("a") as stream:
                stream.write('{}\n')
            with self.assertRaises(ValueError):
                checkpoint.pilot_selection(*paths, excluded=set(), min_support=3)


class FrozenPopulationTests(unittest.TestCase):
    def fixture(self, root, *, member_split="development", screening_split="development"):
        bundle, audit = root / "bundle", root / "audit"
        bundle.mkdir()
        audit.mkdir()
        config = json.loads(comparison.git("show", "f33e3fc:src/goodsai/baseline.json"))
        product = Product("synthetic-card", "761", "Samsung").as_dict()
        member = {"sku_id": "synthetic-card", "category_id": "761", "family_id": "synthetic-family",
                  "split": "development", "quarantine_reasons": [], "family_exposed": False}
        inputs, refs, metas, _ = assemble([product], {"synthetic-card": {"category_id": "761", "vendor": "Samsung"}},
                                         {"synthetic-card": member}, config)
        member["split"] = member_split
        metas[0]["original_split"] = screening_split
        metas[0]["role"] = comparison.frozen_role(member["family_id"], screening_split)
        write_rows(audit / "membership.jsonl", [member])
        write_rows(audit / "eligible.split_manifest.jsonl", [member])
        dump(audit / "audit.summary.json", {"synthetic_only": True})
        exposure = root / "exposure.jsonl"
        write_rows(exposure, [])
        sources = {"audit": digest(audit / "audit.summary.json"), "exposure_0": digest(exposure)}
        for name, data in (("input.jsonl", inputs), ("reference.jsonl", refs), ("metadata.jsonl", metas),
                           ("llm_screening.input.jsonl", inputs), ("train.jsonl", []), ("support_review.blank.jsonl", [])):
            write_rows(bundle / name, data)
        dump(bundle / "train.split.json", {})
        dump(bundle / "policy.json", {"config": config, "sources": sources})
        dump(bundle / "manifest.json", {"version": VERSION, "reference_kind": "catalog_silver",
                                        "source_sha256": sources, "artifacts": {p.name: digest(p) for p in bundle.iterdir()}})
        return bundle, audit, digest(bundle / "manifest.json"), {"exposure_0": str(exposure)}

    def test_hash_sources_and_forbidden_families_fail_closed(self):
        for split in ("development", "test_reserved"):
            with self.subTest(split=split), tempfile.TemporaryDirectory() as tmp:
                bundle, audit, checksum, sources = self.fixture(Path(tmp), member_split=split)
                with patch.object(comparison, "verify_audit", return_value={"status": "synthetic"}):
                    if split == "test_reserved":
                        with self.assertRaisesRegex(ValueError, "forbidden_or_mismatched_family"):
                            comparison.check_population(bundle, audit, checksum, sources)
                    else:
                        self.assertEqual(len(comparison.check_population(bundle, audit, checksum, sources)[1]), 1)
                        with self.assertRaisesRegex(ValueError, "frozen_bundle_hash"):
                            comparison.check_population(bundle, audit, "0" * 64, sources)
                        with self.assertRaisesRegex(ValueError, "all_frozen_source"):
                            comparison.check_population(bundle, audit, checksum, {})
                        Path(sources["exposure_0"]).write_text('{}\n')
                        with self.assertRaisesRegex(ValueError, "preparation_source_changed"):
                            comparison.check_population(bundle, audit, checksum, sources)

    def test_validation_screening_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, audit, checksum, sources = self.fixture(Path(tmp), member_split="validation", screening_split="validation")
            with patch.object(comparison, "verify_audit", return_value={"status": "synthetic"}):
                with self.assertRaisesRegex(ValueError, "invalid_screening_population"):
                    comparison.check_population(bundle, audit, checksum, sources)

    def test_complete_synthetic_driver_runs_both_commits_with_one_reference(self):
        (ROOT / "outputs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            root = Path(tmp)
            bundle, audit, checksum, sources = self.fixture(root)
            args = argparse.Namespace(bundle=bundle, audit=audit, bundle_sha256=checksum, repeats=100,
                                      source=[k + "=" + v for k, v in sources.items()], baseline="f33e3fc",
                                      candidate="HEAD", output_dir=root / "comparison")
            # The tiny synthetic audit is deliberately not represented as a real EVAL-002 audit.
            # All source/frozen checks and both actual isolated rules workers run normally.
            with patch.object(comparison, "verify_audit", return_value={"status": "synthetic"}):
                result = comparison.run(args)
            self.assertEqual(result["cards"], 1)
            self.assertEqual(result["paired"]["new_fp"], 0)
            self.assertEqual(result["paired"]["lost_tp"], 0)
            public = json.loads((args.output_dir / "run_stats.json").read_text())
            self.assertIsNone(public["independent_quality"])
            self.assertIsNone(public["compute_cost_rub"])
            self.assertNotIn("synthetic-card", json.dumps(public))
            self.assertEqual(public["variants"]["historical"]["cards"], public["variants"]["candidate"]["cards"])


if __name__ == "__main__":
    unittest.main()
