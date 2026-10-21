"""Synthetic workflow checks only: no real reserve, humans, model calls or quality claims."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.contracts import Product, load_config
from goodsai.data import digest
from goodsai.runtime import identity
from goodsai.policy import policy_for_settings, runtime_metadata
from goodsai.verify import Extractor
from scripts.research import human_gold as human
from scripts.research import quality_evidence as quality
from test_human_gold import fixture, release, response


def json_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True) + "\n", encoding="utf-8")


def json_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows), encoding="utf-8")


def artifact(path):
    return {"path": str(path), "sha256": digest(path)}


def present(value="Invented", method="rule"):
    return {"attribute": "model", "value": value, "unit": None, "confidence": .8,
            "confidence_kind": "heuristic", "decision": "review", "method": method,
            "rule_id": "synthetic.saved.v1", "reason_codes": [],
            "evidence": {"field": "title", "start": 0, "end": len(value), "text": value}}


class QualityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "outputs/result"

    def supplied(self):
        fixture(self.root)
        for slot in ("A", "B"):
            release(self.root, slot)
            path = response(self.root, slot)
            data = human.read(path)
            for index in (0, 1, 3):
                data["tasks"][index]["attributes"][1].update(status="present", value="Invented", unit=None,
                    evidence={"field": "title", "text": "Invented", "start": 0, "end": 8})
            data["tasks"][4]["attributes"][0].update(status="ambiguous", notes="Synthetic unjudgeable brand")
            json_file(path, data)
        human.reconcile(self.root / "A", self.root / "answers-A.json", self.root / "agreement",
                        self.root / "B", self.root / "answers-B.json")
        decision = human.read(self.root / "agreement/adjudication.template.json")
        decision.update(approved=True, adjudicator="synthetic_c", all_labels_checked=True,
                        human_only=True, no_test_based_tuning=True)
        json_file(self.root / "signed.json", decision)
        human.finalize(self.root / "A", self.root / "answers-A.json", self.root / "B", self.root / "answers-B.json",
                       self.root / "signed.json", self.root / "reference")
        rows = list(human.read_jsonl(self.root / "reference/reference.jsonl"))
        inputs = self.root / "input.jsonl"
        products = [Product.from_dict({k: r[k] for k in quality.INPUT_FIELDS if k in r}) for r in rows]
        json_lines(inputs, [p.as_dict() for p in products])
        config = load_config()
        config_path = self.root / "config.json"
        json_file(config_path, config)
        saved = []
        for name in quality.RUNS:
            predictions = [Extractor(config).predict(p, "synthetic-" + name) for p in products]
            if name == "baseline":
                predictions[0]["attributes"][1] = present()
                predictions[3]["attributes"][1] = present()
            else:
                predictions[1]["attributes"][1] = present(method="model")
                predictions[2]["attributes"][1] = present(method="model")  # New FP on absent.
                predictions[3]["attributes"][1] = present(rows[3]["title"], method="model")  # FP+FN.
            path = self.root / name / "predictions.jsonl"
            json_lines(path, predictions)
            meta = identity(config) | runtime_metadata(config, policy_for_settings(config)) | {
                                      "git_dirty": False, "rows": 40, "status_counts": {"processed": 40},
                                      "run_id": "synthetic-" + name, "input_sha256": digest(inputs),
                                      "output_sha256": digest(path)}
            manifest = path.with_suffix(".manifest.json")
            json_file(manifest, meta)
            saved.append({"name": name, "status": "completed", "predictions": artifact(path),
                          "manifest": artifact(manifest), "config": artifact(config_path)})
        spec = quality.template() | {"purpose": "synthetic_workflow_check", "input": artifact(inputs),
                 "reference_package": artifact(self.root / "reference/manifest.json"),
                 "review_packages": {slot: artifact(self.root / slot / "manifest.json") for slot in ("A", "B")},
                 "runs": saved}
        path = self.root / "spec.json"
        json_file(path, spec)
        return path, spec

    def test_prepare_never_reads_data_and_metrics_stay_unavailable(self):
        with patch.object(quality, "human_reference", side_effect=AssertionError("must not open reference")), \
             patch.object(quality, "evaluate_runs", side_effect=AssertionError("must not evaluate")):
            report = quality.prepare(self.output, root=self.root)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["independent_reference"])
        self.assertTrue(all(report[k] is None for k in ["precision", "recall", "f1"]))
        self.assertEqual(quality.verify(self.output)["metrics_recomputed"], False)
        with self.assertRaises(ValueError):
            quality.prepare(self.output, root=self.root)

    def test_template_assemble_is_explicitly_blocked_not_successful_quality(self):
        path = self.root / "spec.json"
        json_file(path, quality.template())
        report = quality.assemble(path, self.output, root=self.root)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("independent_human_gold_missing", report["blockers"])
        self.assertFalse((self.output / "private/human").exists())

    def test_replays_human_workflow_reuses_evaluator_and_retains_paired_regressions(self):
        path, _ = self.supplied()
        with patch.object(quality, "evaluate", wraps=quality.evaluate) as evaluator:
            report = quality.assemble(path, self.output, root=self.root)
        self.assertEqual(evaluator.call_count, 2)
        self.assertEqual(report["status"], "synthetic_workflow_checked")
        self.assertEqual(report["final_acceptance"], "blocked")
        self.assertFalse(report["independent_reference"])
        baseline = report["runs"]["baseline"]["evaluation"]
        self.assertEqual(baseline["excluded_pairs"], 1)
        self.assertEqual((baseline["metrics"]["micro"]["tp"], baseline["metrics"]["micro"]["fn"]), (2, 1))
        hybrid = report["runs"]["hybrid"]["evaluation"]
        self.assertEqual((hybrid["metrics"]["micro"]["tp"], hybrid["metrics"]["micro"]["fp"],
                          hybrid["metrics"]["micro"]["fn"]), (1, 2, 2))
        self.assertEqual((report["paired"]["new_tp"], report["paired"]["new_fp"], report["paired"]["lost_tp"]), (1, 2, 2))
        self.assertIn("category_attribute:761:model", baseline["metrics"])
        expected = digest(self.output / "manifest.json")
        self.assertTrue(quality.verify(self.output, expected)["metrics_recomputed"])
        public = "\n".join(p.read_text(encoding="utf-8") for p in (self.output / "public").iterdir())
        for secret in ["Invented", "synthetic_a", str(self.root), '"sku_id"', '"gold_value"']:
            self.assertNotIn(secret, public)
        # Verification repeats without original human packages/answers, on captured data.
        (self.root / "answers-A.json").unlink()
        self.assertTrue(quality.verify(self.output, expected)["metrics_recomputed"])

    def test_missing_hybrid_is_not_run_never_implicitly_baseline(self):
        path, spec = self.supplied()
        spec["runs"][1] = {"name": "hybrid", "status": "not_run", "reason": "model_artifacts_unavailable"}
        json_file(path, spec)
        report = quality.assemble(path, self.output, root=self.root)
        self.assertEqual(report["runs"]["hybrid"]["status"], "not_run")
        self.assertIsNone(report["runs"]["hybrid"]["evaluation"])
        self.assertEqual(report["paired"]["status"], "not_run")

    def test_declared_missing_reference_hash_and_fake_gold_are_rejected_atomically(self):
        path, spec = self.supplied()
        for record in [dict(path="missing.json", sha256="a" * 64),
                       dict(path=str(self.root / "reference/manifest.json"), sha256="0" * 64),
                       artifact(self.root / "A/manifest.json")]:
            with self.subTest(record=record):
                changed = copy.deepcopy(spec)
                changed["reference_package"] = record
                json_file(path, changed)
                with self.assertRaises(ValueError):
                    quality.assemble(path, self.output, root=self.root)
                self.assertFalse(self.output.exists())

    def test_human_signoff_not_bypassed_by_resealing_reference(self):
        path, spec = self.supplied()
        decision = self.root / "reference/adjudication.signed.json"
        changed = quality.read(decision) | {"human_only": False}
        json_file(decision, changed)
        (self.root / "reference/manifest.json").unlink()
        human.seal(self.root / "reference", "reference")
        spec["reference_package"] = artifact(self.root / "reference/manifest.json")
        json_file(path, spec)
        with self.assertRaisesRegex(ValueError, "human_signoff"):
            quality.assemble(path, self.output, root=self.root)
        self.assertFalse(self.output.exists())

    def test_resealed_labels_must_match_replayed_human_answers(self):
        path, spec = self.supplied()
        reference = self.root / "reference/reference.jsonl"
        rows = list(human.read_jsonl(reference))
        rows[0]["attributes"][1].update(status="absent", value=None, unit=None, evidence=None)
        json_lines(reference, rows)
        (self.root / "reference/manifest.json").unlink()
        human.seal(self.root / "reference", "reference")
        spec["reference_package"] = artifact(self.root / "reference/manifest.json")
        json_file(path, spec)
        with self.assertRaisesRegex(ValueError, "reference_replay"):
            quality.assemble(path, self.output, root=self.root)

    def test_run_identity_counts_config_and_evidence_must_match(self):
        path, spec = self.supplied()
        original = quality.read(self.root / "baseline/predictions.manifest.json")
        for change in [{"input_sha256": "0" * 64}, {"code_sha256": "0" * 64}, {"git_dirty": True},
                       {"rows": 39}, {"status_counts": {"processed": 39}}, {"run_id": "wrong"},
                       {"effective_config_sha256": "0" * 64}]:
            with self.subTest(change=change):
                json_file(self.root / "baseline/predictions.manifest.json", original | change)
                spec["runs"][0]["manifest"] = artifact(self.root / "baseline/predictions.manifest.json")
                json_file(path, spec)
                with self.assertRaises(ValueError):
                    quality.assemble(path, self.output, root=self.root)
                self.assertFalse(self.output.exists())
        json_file(self.root / "baseline/predictions.manifest.json", original)
        predictions = self.root / "baseline/predictions.jsonl"
        rows = list(human.read_jsonl(predictions))
        rows[0]["attributes"][1]["evidence"]["text"] = "Invented!"
        json_lines(predictions, rows)
        json_file(self.root / "baseline/predictions.manifest.json", original | {"output_sha256": digest(predictions)})
        spec["runs"][0].update(predictions=artifact(predictions), manifest=artifact(predictions.with_suffix(".manifest.json")))
        json_file(path, spec)
        with self.assertRaises(ValueError):
            quality.assemble(path, self.output, root=self.root)

    def test_changed_frozen_audit_sources_stop_assembly(self):
        path, _ = self.supplied()
        with (self.root / "pilot.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "source_hash_mismatch"):
            quality.assemble(path, self.output, root=self.root)
        self.assertFalse(self.output.exists())

    def test_text_mismatch_and_missing_predictions_are_not_excluded_from_metrics(self):
        path, spec = self.supplied()
        original_input = (self.root / "input.jsonl").read_bytes()
        inputs = list(human.read_jsonl(self.root / "input.jsonl"))
        inputs[0]["title"] += " text changed"
        json_lines(self.root / "input.jsonl", inputs)
        spec["input"] = artifact(self.root / "input.jsonl")
        json_file(path, spec)
        with self.assertRaisesRegex(ValueError, "input_reference_text"):
            quality.assemble(path, self.output, root=self.root)
        (self.root / "input.jsonl").write_bytes(original_input)
        spec["input"] = artifact(self.root / "input.jsonl")
        predictions = self.root / "baseline/predictions.jsonl"
        json_lines(predictions, list(human.read_jsonl(predictions))[:-1])
        manifest = predictions.with_suffix(".manifest.json")
        json_file(manifest, quality.read(manifest) | {"output_sha256": digest(predictions), "rows": 39})
        spec["runs"][0].update(predictions=artifact(predictions), manifest=artifact(manifest))
        json_file(path, spec)
        with self.assertRaisesRegex(ValueError, "prediction_sku"):
            quality.assemble(path, self.output, root=self.root)

    def test_repeat_is_identical_and_recomputed_metrics_detect_rehashed_bad_report(self):
        path, _ = self.supplied()
        quality.assemble(path, self.output, root=self.root)
        other = self.root / "outputs/repeat"
        quality.assemble(path, other, root=self.root)
        self.assertEqual(digest(self.output / "manifest.json"), digest(other / "manifest.json"))
        report_path = self.output / "public/report.json"
        report = quality.read(report_path)
        report["runs"]["baseline"]["evaluation"]["metrics"]["micro"]["tp"] += 1
        json_file(report_path, report)
        # Update integrity records: semantic verification must still reject false metrics.
        manifest_path = self.output / "manifest.json"
        manifest = quality.read(manifest_path)
        manifest["artifacts"]["public/report.json"] = digest(report_path)
        json_file(manifest_path, manifest)
        json_file(self.output / "public/integrity.json", {"version": quality.VERSION,
                  "manifest_sha256": digest(manifest_path), "artifacts": manifest["artifacts"]})
        with self.assertRaisesRegex(ValueError, "recomputed_metrics"):
            quality.verify(self.output)

    def test_named_hybrid_and_required_baseline_are_not_silently_dropped(self):
        path, spec = self.supplied()
        for runs in [spec["runs"][:1], spec["runs"][::-1],
                     [{"name": "baseline", "status": "not_run", "reason": "no_baseline"}, spec["runs"][1]]]:
            with self.subTest(runs=runs):
                json_file(path, spec | {"runs": runs})
                with self.assertRaises(ValueError):
                    quality.assemble(path, self.output, root=self.root)
                self.assertFalse(self.output.exists())

    def test_failed_prediction_row_stays_visible_as_fn_and_lost_tp(self):
        path, spec = self.supplied()
        predictions = self.root / "hybrid/predictions.jsonl"
        rows = list(human.read_jsonl(predictions))
        rows[3].update(status="error", attributes=[])
        json_lines(predictions, rows)
        manifest = predictions.with_suffix(".manifest.json")
        json_file(manifest, quality.read(manifest) | {"output_sha256": digest(predictions),
                  "status_counts": {"processed": 39, "error": 1}})
        spec["runs"][1].update(predictions=artifact(predictions), manifest=artifact(manifest))
        json_file(path, spec)
        report = quality.assemble(path, self.output, root=self.root)
        run = report["runs"]["hybrid"]
        self.assertEqual(run["evaluation"]["unprocessed_prediction_cards"], 1)
        self.assertEqual(run["status_counts"]["error"], 1)
        self.assertEqual(run["evaluation"]["metrics"]["micro"]["fn"], 2)
        self.assertEqual(report["paired"]["lost_tp"], 2)
        self.assertTrue(quality.verify(self.output)["metrics_recomputed"])

    def test_public_report_tamper_extra_file_and_trusted_digest_rejected(self):
        quality.prepare(self.output, root=self.root)
        with self.assertRaisesRegex(ValueError, "manifest_hash"):
            quality.verify(self.output, "0" * 64)
        extra = self.output / "extra.txt"
        extra.write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory"):
            quality.verify(self.output)
        extra.unlink()
        with (self.output / "public/report.json").open("a", encoding="utf-8") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(ValueError, "bundle_hash"):
            quality.verify(self.output)

    def test_preparation_and_cli_preserve_private_bounds_and_safe_errors(self):
        with self.assertRaisesRegex(ValueError, "private_outputs"):
            quality.prepare(self.root / "data/raw/forbidden", root=self.root)
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error), self.assertRaises(SystemExit) as caught:
            quality.main(["assemble", "--spec", str(self.root / "PRIVATE-NO-SUCH-FILE.json"),
                          "--output-dir", str(quality.ROOT / "outputs/unused-eval003")])
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn("PRIVATE-NO-SUCH-FILE", error.getvalue())
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
