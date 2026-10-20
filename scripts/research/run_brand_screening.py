"""Run the existing local brand hybrid on a preselected frozen development screening.

Uses the existing composition/sink and GLiNER implementation, never a gateway.
Model weights, inputs and predictions remain private. No method is tuned here.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/research"))
from compare_silver_baseline import private_output
from goodsai.cli import _predict_staged
from goodsai.composition import build_runtime
from goodsai.contracts import load_config
from goodsai.data import digest, write_json
from goodsai.experimental_gliner import (HybridExtractor, LocalGliner, validate_artifact,
                                         CHECKPOINT, WEIGHTS_SHA256, POLICY)
from goodsai.silver_prepare import dump, verify_bundle


class MeasuredHybrid:
    def __init__(self, hybrid, stats):
        self.hybrid, self.stats = hybrid, stats

    def predict(self, product, run_id):
        result = self.hybrid.predict(product, run_id)
        diag = self.hybrid.last_diagnostics
        self.stats["cards"] += 1
        if diag.get("model_called") and not self.stats["model_calls"]:
            self.stats["first_model_call_including_lazy_load_seconds"] = diag.get("model_seconds")
        self.stats["model_calls"] += int(diag.get("model_called", False))
        self.stats["failures"] += int(bool(diag.get("failure")))
        self.stats["model_seconds"] += diag.get("model_seconds", 0)
        self.stats["accepted_brand_candidates"] += sum(a["method"] == "model" and a["value"] is not None
                                                        for a in result["attributes"])
        return result


def run(args):
    verify_bundle(args.bundle)
    baseline = json.loads((args.baseline_run / "run_stats.json").read_text(encoding="utf-8"))
    bundle_hash = digest(args.bundle / "manifest.json")
    if (baseline["freeze"]["bundle_manifest_sha256"] != bundle_hash
            or baseline["freeze"]["evaluator_sha256"] != digest(ROOT / "src/goodsai/silver_evaluate.py")):
        raise ValueError("frozen_baseline_or_evaluator_mismatch")
    artifact = validate_artifact(args.artifact)
    policy = json.loads((args.bundle / "policy.json").read_text(encoding="utf-8"))
    output = private_output(args.output_dir)
    dump(output / "config.json", policy["config"])
    config = load_config(output / "config.json")
    source = args.bundle / "llm_screening.input.jsonl"
    frozen_input = digest(source)
    dump(output / "freeze.json", {"bundle_manifest_sha256": bundle_hash, "input_sha256": frozen_input,
                                 "baseline_report_sha256": digest(args.baseline_run / "run_stats.json"),
                                 "artifact_manifest_sha256": digest(artifact / "artifact.json"),
                                 "checkpoint_revision": CHECKPOINT, "weights_sha256": WEIGHTS_SHA256,
                                 "policy": POLICY, "external_calls": "forbidden",
                                 "driver_sha256": digest(Path(__file__)),
                                 "regression_gate": "any_new_fp_or_lost_tp_blocks_recommendation"})
    base = build_runtime(config)
    stats = {}
    hybrid = HybridExtractor(config, LocalGliner(artifact), rules=base.predictor)
    runtime = replace(base, predictor=MeasuredHybrid(hybrid, stats))
    for temperature in ("cold", "warm"):
        stats.clear()
        stats.update(cards=0, model_calls=0, failures=0, model_seconds=0.0, accepted_brand_candidates=0,
                     first_model_call_including_lazy_load_seconds=None)
        target = output / (temperature + ".jsonl")
        with runtime.sink.stage(target) as (staged, manifest):
            report = _predict_staged(source, staged, manifest, runtime)
            report["brand_model"] = {**stats, "checkpoint_revision": CHECKPOINT, "policy": POLICY,
                                     "weights_sha256": WEIGHTS_SHA256,
                                     "artifact_manifest_sha256": digest(artifact / "artifact.json")}
            write_json(manifest, report)
    verify_bundle(args.bundle)
    validate_artifact(args.artifact)
    if digest(source) != frozen_input or digest(output / "cold.jsonl") != digest(output / "warm.jsonl"):
        raise ValueError("screening_changed_or_non_deterministic_predictions")
    dump(output / "manifest.json", {"artifacts": {p.name: digest(p) for p in sorted(output.iterdir())
                                                  if p.is_file() and not p.name.startswith(".")}})
    return {"status": "local_brand_screening_completed", "warm": dict(stats), "independent_quality": None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "baseline-run", "artifact", "output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    print(json.dumps(run(p.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
