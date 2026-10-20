"""One local command: rules -> noisy-reference diagnostics -> offline calibration."""
import argparse
import json
import hashlib
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from goodsai.cli import predict
from goodsai.contracts import load_config
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.silver_calibration import calibrate
from goodsai.silver_evaluate import bootstrap, evaluate_rows
from goodsai.silver_comparison import paired_changes
from goodsai.silver_prepare import dump, verify_bundle, write_rows
from goodsai.storage import prediction_snapshot


def run(args):
    source_manifest = verify_bundle(args.bundle)
    policy = json.loads((args.bundle / "policy.json").read_text(encoding="utf-8"))
    output = args.output_dir.resolve()
    if output.exists() or (ROOT / "outputs").resolve() not in output.parents:
        raise ValueError("new_private_outputs_directory_required")
    if args.repeats < 100 or args.repeats > 10000:
        raise ValueError("invalid_bootstrap_repeats")
    output.mkdir(parents=True)
    input_path = args.bundle / "input.jsonl"
    config = policy["config"]
    source_hash = digest(args.bundle / "manifest.json")
    inputs = list(read_jsonl(input_path))
    refs = list(read_jsonl(args.bundle / "reference.jsonl"))
    metadata = list(read_jsonl(args.bundle / "metadata.jsonl"))
    # An immutable evaluation setup is emitted before inference.
    dump(output / "evaluation.policy.json", {"bundle_sha256": source_hash,
        "bootstrap_repeats": args.repeats, "config": config, "route": "rules_only",
        "external_calls": "forbidden", "candidates": args.candidate,
        "candidate_regression_gate": "any_new_fp_or_lost_tp_blocks_recommendation"})
    cold = predict(input_path, output / "predictions.jsonl", config)
    warm = predict(input_path, output / "repeat.jsonl", config)
    if digest(output / "predictions.jsonl") != digest(output / "repeat.jsonl"):
        raise ValueError("non_deterministic_prediction_values")
    report, pairs, groups = evaluate_rows(inputs, refs, metadata, read_predictions(output / "predictions.jsonl"), config, args.repeats)
    calibration, model = calibrate(pairs)
    dump(output / "calibration.json", calibration)
    if model:
        dump(output / "offline_model.json", model)
    write_rows(output / "pair_diagnostics.jsonl", pairs)
    write_rows(output / "family_counts.jsonl", [{"family_id": k, "counts": v} for k, v in sorted(groups.items())])
    variants = {"rules": {"status": "measured", "agreement": report["agreement"], "grouped_ci": report["grouped_ci"]}}
    for spec in args.candidate:
        name, separator, path = spec.partition("=")
        if not separator or not name or name in variants or name not in {"registry", "gliner", "llm", "control"}:
            raise ValueError("invalid_or_duplicate_candidate_name")
        path = Path(path)
        captured = output / (name + ".predictions.jsonl")
        # Keep a consistent immutable copy of both files under the existing
        # storage lock. A producer cannot replace the manifest between identity
        # validation and scoring and leave a mixed comparison in this report.
        with prediction_snapshot(path) as verified:
            shutil.copyfile(verified, captured)
            shutil.copyfile(path.with_suffix(".manifest.json"), captured.with_suffix(".manifest.json"))
        path = captured
        manifest_path = path.with_suffix(".manifest.json")
        candidate_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        configs = dict(item.split("=", 1) for item in args.candidate_config)
        candidate_config = load_config(configs[name]) if name in configs else config
        candidate_config_hash = hashlib.sha256(json.dumps(candidate_config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if candidate_manifest.get("config_sha256") != candidate_config_hash:
            raise ValueError("candidate_config_hash_mismatch")
        if any(candidate_config["categories"].get(cat) != attrs for cat, attrs in config["categories"].items()):
            raise ValueError("candidate_requested_schema_changed")
        candidate_inputs = inputs
        if candidate_manifest.get("input_sha256") == digest(args.bundle / "llm_screening.input.jsonl"):
            candidate_inputs = list(read_jsonl(args.bundle / "llm_screening.input.jsonl"))
        elif candidate_manifest.get("input_sha256") != digest(input_path):
            raise ValueError("candidate_input_mismatch")
        ids = {p["sku_id"] for p in candidate_inputs}
        candidate_refs = [r for r in refs if r["sku_id"] in ids]
        candidate_meta = [m for m in metadata if m["sku_id"] in ids]
        baseline_subset, baseline_pairs, baseline_groups = evaluate_rows(candidate_inputs, candidate_refs, candidate_meta,
            (p for p in read_predictions(output / "predictions.jsonl") if p["sku_id"] in ids), config, args.repeats)
        candidate, candidate_pairs, other = evaluate_rows(candidate_inputs, candidate_refs, candidate_meta, read_predictions(path), candidate_config, args.repeats)
        transitions, changed_pairs = paired_changes(baseline_pairs, candidate_pairs)
        write_rows(output / (name + ".changed_pairs.private.jsonl"), changed_pairs)
        regressions = transitions["counts"].get("new_fp", 0) or transitions["counts"].get("lost_tp", 0)
        variants[name] = {"status": "measured", "prediction_sha256": digest(path),
            "cards": len(ids), "scope": "full_frozen_population" if len(ids) == len(inputs) else "preselected_development_screening",
            "paired_rules_agreement": baseline_subset["agreement"],
            "manifest_sha256": digest(manifest_path), "agreement": candidate["agreement"],
            "paired_delta_vs_rules": bootstrap(baseline_groups, args.repeats, other=other),
            "paired_transitions": transitions,
            "recommendation": "blocked_regression_requires_defect" if regressions else "development_measurement_requires_cost_and_artifact_review",
            "per_attribute": candidate["per_attribute"], "per_category": candidate["per_category"],
            "slices": candidate["slices"], "resources": public_runtime(candidate_manifest),
            "actual_producer": {k: candidate_manifest.get(k) for k in ("git_commit", "code_sha256", "config_sha256", "effective_config_sha256")},
            "usage": public_usage(candidate_manifest)}
        if name == "llm" and not (candidate_manifest.get("llm_calls", 0) or candidate_manifest.get("llm", {}).get("cache_hits", 0)):
            variants[name]["status"] = "route_not_exercised"
            variants[name]["reason"] = "no_provider_calls_or_cache_hits_not_an_llm_quality_experiment"
    reasons = {"registry": "colleague_train_registry_not_integrated_on_frozen_population",
               "gliner": "local_weights_and_frozen_candidate_run_not_supplied",
               "llm": "live_gateway_trace_and_frozen_candidate_artifacts_remain_on_VM"}
    for name, reason in reasons.items():
        variants.setdefault(name, {"status": "not_run", "reason": reason})
    report["variants"] = variants
    report["calibration"] = calibration
    report["preparation"] = {k: source_manifest[k] for k in ["counts", "family_groups", "protected_reserve_rows", "universe_rows", "universe_categories", "universe_configured_rows", "top30", "seller_role_crossings", "brand_role_crossings", "exposure_history", "support_review_status"]}
    report["provenance"] = {"bundle_manifest_sha256": source_hash,
        "sources": source_manifest["source_sha256"], "baseline_declared_sha": policy["baseline_sha"],
        "runtime": {k: cold[k] for k in ["code_sha256", "config_sha256", "git_commit", "git_dirty", "python", "platform"]},
        "predictions_sha256": digest(output / "predictions.jsonl"),
        "runtime_config_changed": False}
    report["resources"] = {"cold": public_runtime(cold), "warm": public_runtime(warm),
                           "repeat_values_identical": True, "compute_cost_rub": None,
                           "usage": public_usage(cold)}
    if digest(args.bundle / "manifest.json") != source_hash:
        raise ValueError("bundle_changed_during_evaluation")
    verify_bundle(args.bundle)
    dump(output / "run_stats.json", report)
    (output / "metrics.md").write_text(markdown(report), encoding="utf-8")
    dump(output / "manifest.json", {"schema": "goodsai-silver-evaluation-1", "artifacts": {p.name: digest(p) for p in sorted(output.iterdir())}, "bundle_sha256": source_hash})
    return {"status": "measured_catalog_agreement", "cards": report["cards"], "agreement": report["agreement"],
            "calibration_status": calibration["status"], "independent_quality": None}


def public_runtime(manifest):
    return {k: manifest.get(k) for k in ["rows", "elapsed_seconds", "cards_per_second_including_io", "extractor_p50_ms", "extractor_p95_ms", "peak_process_rss_bytes", "invalid_input_rows", "status_counts"]}


def public_usage(manifest):
    raw = manifest.get("llm", {})
    rows = manifest.get("rows")
    cost = raw.get("cost", 0 if manifest.get("llm_calls") == 0 else None)
    # Strict allowlist: provider URL/key, prompt/cache paths and raw responses
    # cannot flow into the public report, even from a colleague's manifest.
    return {"calls": manifest.get("llm_calls"), "compute_cost": None,
        **{k: raw[k] for k in ["model", "prompt_version", "data_policy", "calls", "attempts", "retries", "cache_hits", "cache_overhead_seconds", "singleflight_waits", "cost", "cost_status", "failures", "rejected", "cards_routed", "cards_without_gap", "cards_skipped_no_signal", "attributes_skipped_no_signal", "attributes_requested", "proposals", "accepted", "accepted_by_attribute", "provider_seconds"] if k in raw},
        "input_tokens": raw.get("input_tokens", raw.get("prompt_tokens")),
        "output_tokens": raw.get("output_tokens", raw.get("completion_tokens")),
        "cost": cost, "cost_denominator_sku": rows,
        "estimated_cost_per_1000_sku_in_provider_price_units": cost * 1000 / rows
            if type(cost) in (int, float) and type(rows) is int and rows > 0 else None,
        "billing_limitation": "provider_usage_estimate_not_invoice_unknown_failed_request_tokens_not_imputed"}


def markdown(report):
    def fmt(value):
        return "N/A" if value is None else f"{value:.4f}"
    lines = ["# Catalog-silver evaluation", "", "Reference: noisy catalog. Role: development_feedback.",
        "Independent human quality: N/A. Auto-accept: forbidden. Support matcher awaits human audit.", "",
        f"Cards: {report['cards']}; families: {report['preparation']['family_groups']}; protected reserve: {report['preparation']['protected_reserve_rows']} (not predicted).", "",
        "| Attribute | TP | FP | FN | Agreement P | R | F1 | Supported R | Coverage |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for attr, count in sorted(report["per_attribute"].items()):
        lines.append(f"| {attr} | {count['tp']} | {count['fp']} | {count['fn']} | " + " | ".join(fmt(count[k]) for k in ["precision", "recall", "f1", "recall_supported", "coverage_all_requested"]) + " |")
    lines += ["", "## Variants", "", "| Method | Status | Catalog F1 |", "|---|---|---:|"]
    for name, variant in report["variants"].items():
        lines.append(f"| {name} | {variant['status']} | {fmt(variant.get('agreement', {}).get('f1'))} |")
    lines += ["", "## Interpretation", "",
        "Unknown catalog labels are not negatives; wrong known values count FP+FN. See run_stats.json for denominators, unknown/conflict/support counts, slices and grouped CI.",
        "Top-30 is a metadata ranking, not 30 implemented schemas. Current runtime supports two categories. Seller/brand crossings are disclosed; this split is not seller-disjoint.",
        "Closed test was not evaluated. Old validation is feedback. A catalog mismatch may be a catalog error and requires adjudication.",
        "Calibration: " + report["calibration"]["status"] + ". Any fitted score remains offline and does not establish true correctness probability.",
        "Current known adversarial failure RED SOLUTION/color remains outside this evaluator; this report does not certify release readiness.", "",
        "Reproduction: docs/research/silver_evaluation_protocol.md and docs/SILVER_EVALUATION.md."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate", action="append", default=[], help="registry|gliner|llm|control=predictions.jsonl, frozen full input or screening subset")
    parser.add_argument("--candidate-config", action="append", default=[], help="NAME=config.json, requested schema must remain identical")
    parser.add_argument("--repeats", type=int, default=1000)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("silver evaluation failed: " + type(exc).__name__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
