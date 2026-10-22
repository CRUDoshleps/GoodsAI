"""Reassess a completed storage audit under a newly approved risk target.

Never rewrites the original 99% experiment or labels it independent calibration.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from goodsai.config import load_config, validate_config
from goodsai.contracts import Product
from goodsai.cli import predict
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.storage_acceptance import (POLICY_VERSION, AUDIT_ANSWERS_SHA256, AUDIT_TOTAL,
                                        AUDIT_CORRECT, metadata)
from scripts.research.audit_splits import dump, require
from scripts.research.human_gold import checked, new_directory, seal
from scripts.research.storage_shadow import precision_lower


def pilot_config(target=.97):
    config = load_config()
    config["runtime"].update(auto_accept_enabled=True, auto_accept={
        "policy_version": POLICY_VERSION, "target_precision": target})
    return validate_config(config)


def reassess(audit, output, target=.97):
    state = metadata(pilot_config(target))
    audit = Path(audit).resolve()
    checked(audit, "storage-shadow-reviewed")
    source = audit / "human.metrics.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    require(report["review_complete"] and report["sample_size"] == AUDIT_TOTAL
            and report["counts"] == {"correct": AUDIT_CORRECT, "incorrect": 0, "unresolved": 0, "pending": 0}
            and report["answers_sha256"] == AUDIT_ANSWERS_SHA256
            and report["independent_reference"] is False, "not_the_approved_completed_audit")
    lower = precision_lower(report["counts"]["correct"], report["sample_size"])
    require(lower == state["exploratory_one_sided_lower_95"], "audit_bound_mismatch")
    result = {"policy": state, "scope": "post_audit_owner_approved_limited_pilot",
              "original_target_precision": .99, "original_numerical_target_met": False,
              "new_numerical_target_met": lower >= target,
              "source_audit_metrics_sha256": digest(source),
              "source_audit_manifest_sha256": digest(audit / "manifest.json"),
              "confidence_interpretation": "heuristic_not_probability",
              "independent_calibration_complete": False,
              "runtime_deployed": False, "llm_calls": 0, "model_api_cost_rub": 0,
              "limitations": report["limitations"] + [
                  "Risk target changed after results; not a new prospective experiment.",
                  "Decision authorizes only an opt-in pilot; independent calibration remains open."]}
    output = new_directory(output)
    dump(output / "assessment.json", result)
    seal(output, "storage-pilot-reassessment")
    return result


def _content(row):
    value = {k: v for k, v in row.items() if k != "run_id"}
    value["attributes"] = [{k: v for k, v in a.items() if k != "decision"} for a in row["attributes"]]
    return value


def compare(source, output, previous=None):
    """Run ordinary CLI writers twice, compare every value/score/span and decision.

    Only aggregates/hashes leave this private output directory. No reference or
    protected reserve is needed or accessed by the comparison.
    """
    source = Path(source).resolve()
    if previous:
        previous = Path(previous).resolve()
        previous_manifest = json.loads(previous.with_suffix(".manifest.json").read_text(encoding="utf-8"))
        require(previous_manifest["input_sha256"] == digest(source), "previous_input_mismatch")
    inputs = list(read_jsonl(source))
    forbidden = {"test", "test_reserved", "independent_test", "holdout", "test_reserve"}
    require(all(not forbidden.intersection(Product.from_dict(r).source_flags) for r in inputs), "protected_input")
    output = new_directory(output)
    configs = {"baseline": load_config(), "pilot": pilot_config(), "strict": pilot_config(.99)}
    manifests, rows = {}, {}
    for mode, config in configs.items():
        manifests[mode] = predict(source, output / (mode + ".jsonl"), config)
        rows[mode] = list(read_predictions(output / (mode + ".jsonl")))
    manifests["repeat"] = predict(source, output / "repeat.jsonl", configs["pilot"])
    require((output / "repeat.jsonl").read_bytes() == (output / "pilot.jsonl").read_bytes(), "nonrepeatable_pilot")
    require(len(rows["baseline"]) == len(rows["pilot"]) == len(rows["strict"]) == len(inputs), "population_mismatch")
    changed = Counter()
    for before, after, strict in zip(rows["baseline"], rows["pilot"], rows["strict"]):
        require(_content(before) == _content(after) == _content(strict), "extraction_changed")
        require([a["decision"] for a in before["attributes"]] == [a["decision"] for a in strict["attributes"]], "strict_target_must_review")
        for a, b in zip(before["attributes"], after["attributes"]):
            if a["decision"] != b["decision"]:
                require((a["decision"], b["decision"], b["attribute"], after["category_id"])
                        == ("review", "auto_accept", "storage_gb", "761"), "unapproved_decision_change")
                changed[b["rule_id"]] += 1
    if previous:
        old = list(read_predictions(Path(previous)))
        require(len(old) == len(inputs) and all(_content(a) == _content(b) for a,b in zip(old, rows["baseline"])), "previous_extraction_changed")
    decisions = {k: dict(Counter(a["decision"] for r in data for a in r["attributes"])) for k, data in rows.items()}
    result = {"cards": len(inputs), "input_sha256": digest(source), "extraction_unchanged": True,
              "repeat_predictions_identical": True, "previous_extraction_checked": previous is not None,
              "decision_counts": decisions, "accepted_by_rule": dict(changed),
              "accepted_pairs": sum(changed.values()), "policy": metadata(configs["pilot"]),
              "code_sha256": manifests["pilot"]["code_sha256"],
              "effective_config_sha256": manifests["pilot"]["effective_config_sha256"],
              "baseline_prediction_sha256": digest(output / "baseline.jsonl"),
              "pilot_prediction_sha256": digest(output / "pilot.jsonl"),
              "latency_ms": {mode: {"p50": m["extractor_p50_ms"], "p95": m["extractor_p95_ms"]}
                             for mode, m in manifests.items()},
              "quality_precision_recall_f1": None, "quality_note": "Decision replay is not independent quality evaluation.",
              "runtime_deployed": False, "llm_calls": 0, "model_api_cost_rub": 0}
    dump(output / "comparison.json", result)
    seal(output, "storage-pilot-comparison")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("reassess")
    p.add_argument("--audit-dir", type=Path, required=True)
    p.add_argument("--target-precision", type=float, default=.97)
    p.add_argument("--output-dir", type=Path, required=True)
    p = sub.add_parser("compare")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--previous-predictions", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (reassess(args.audit_dir, args.output_dir, args.target_precision) if args.command == "reassess"
              else compare(args.input, args.output_dir, args.previous_predictions))
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
