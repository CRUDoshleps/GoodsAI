"""Publish numeric aggregates from frozen diagnostics, never cards or labels."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from goodsai.contracts import load_config
from goodsai.data import digest, read_jsonl
from goodsai.runtime import identity

COUNTS = frozenset("tp fp fn requested judged predicted known unknown conflict assessed_candidates unassessed_candidates known_supported tp_supported support_unknown support_unsupported mismatched_supported review abstain gold_present gold_absent false_on_absent".split())
RATIOS = frozenset("precision recall f1 recall_supported coverage_all_requested prediction_coverage correct_coverage false_value_rate assessed_candidate_fraction".split())


def require(condition, code):
    if not condition:
        raise ValueError(code)


def number(value, *, count=False):
    require(value is None or (type(value) in {int, float} and math.isfinite(value)), "invalid_aggregate_number")
    if count:
        require(type(value) is int and value >= 0, "invalid_aggregate_count")
    return value


def metrics(source):
    require({"tp", "fp", "fn"} <= source.keys(), "incomplete_metric")
    result = {k: number(v, count=k in COUNTS) for k, v in source.items() if k in COUNTS | RATIOS}
    require(all(v is None or 0 <= v <= 1 for k, v in result.items() if k in RATIOS), "invalid_metric_ratio")
    return result


def table(source, allowed):
    require(source.keys() <= allowed, "unexpected_slice_identity")
    return {key: metrics(row) for key, row in sorted(source.items())}


def interval(source):
    if source.get("status") not in {"paired_group_bootstrap", "group_bootstrap"}:
        return {"status": "unavailable"}
    result = {"status": source["status"], "confidence_level": number(source["confidence_level"]),
              "groups": number(source["groups"], count=True),
              "repeats": number(source["repeats"], count=True), "intervals": {}}
    for key in sorted(RATIOS & source["intervals"].keys()):
        raw = source["intervals"][key]
        result["intervals"][key] = {k: number(raw[k], count=k == "valid_replicates")
                                    for k in ("lower", "upper", "valid_replicates")}
    return result


def project(silver, human, producer, reviewed_rows, current):
    """Explicit field and dimension allowlists; no arbitrary source strings copied."""
    freeze = silver["freeze"]
    require(freeze["reference_kind"] == "catalog_silver" and freeze["external_calls"] == "forbidden",
            "wrong_silver_protocol")
    require(human["sample_kind"] == "error_selected_development"
            and human["reference_origin"] == "ai_assisted_human_reviewed"
            and human["independent_reference"] is False and human["reviewed_attributes"] == ["model"],
            "wrong_human_protocol")
    expected = human["method_provenance"]["fixed"]
    require(all(producer.get(k) == expected[k] for k in expected), "producer_not_bound_to_human_report")
    require(producer["git_commit"] == freeze["after"] and producer["input_sha256"] == freeze["input_sha256"]
            and producer["git_dirty"] is False and producer["llm_calls"] == 0, "wrong_frozen_producer")
    require(current["code_sha256"] == producer["code_sha256"]
            and current["config_sha256"] == producer["config_sha256"], "current_runtime_differs_from_frozen")
    for value in (freeze["before"], freeze["after"]):
        require(re.fullmatch(r"[0-9a-f]{40}", value), "invalid_source_commit")
    for value in (freeze["input_sha256"], freeze["reference_sha256"], freeze["source_bundle_sha256"],
                  producer["code_sha256"], producer["config_sha256"], human["source_reference_sha256"]):
        require(re.fullmatch(r"[0-9a-f]{64}", value), "invalid_source_hash")
    require(re.fullmatch(r"[0-9a-f]{64}", human["evaluator_sha256"]), "invalid_source_hash")
    config = load_config()
    categories, attributes = set(config["categories"]), set().union(*map(set, config["categories"].values()))
    category_attributes = {cat + ":" + attr for cat, attrs in config["categories"].items() for attr in attrs}
    variants = {}
    for name in ("before", "after"):
        source = silver["variants"][name]
        require(source["reference_kind"] == "catalog_silver" and source["evaluation_role"] == "development_feedback",
                "unexpected_variant_role")
        dimensions = source["slices"]
        variants[name] = {"agreement": metrics(source["agreement"]),
            "per_attribute": table(source["per_attribute"], attributes),
            "per_category": table(source["per_category"], categories),
            "category_attribute": table(dimensions["category_attribute"], category_attributes),
            "text": table(dimensions["text"], {"title_only", "with_description"}),
            "reference_frequency": table(dimensions["reference_frequency"], {"frequent", "rare", "unknown"}),
            "partition_role": table(dimensions["role"], {"fit", "calibration", "diagnostic", "development_feedback"}),
            "grouped_ci": interval(source["grouped_ci"]),
            "seller_summary": {k: number(source["seller_slices"][k], count=k != "macro_f1")
                               for k in ("known_sellers", "groups_under_20_requested_pairs", "macro_f1")}}
    cohort = list(reviewed_rows)
    require(len(cohort) == human["cards"] and len({r["sku_id"] for r in cohort}) == len(cohort),
            "reviewed_population_mismatch")
    for row in cohort:
        require(row["original_split"] in {"development", "validation"}
                and row["independent_reference"] is False and row["ai_assisted"] is True
                and row["annotation_status"] == "reviewed", "wrong_reviewed_membership")
        require(row["category_id"] in categories, "unexpected_reviewed_category")
    reviewed = {}
    for name in ("historical", "reported_candidate", "pre_fix_main", "fixed"):
        raw = human["metrics"][name]
        require(raw["pending_cards"] == 0 and raw["missing_prediction_cards"] == 0
                and raw["unprocessed_prediction_cards"] == 0, "incomplete_human_predictions")
        values = raw["metrics"]
        reviewed[name] = {"model": metrics(values["attribute:model"]),
            "per_category": {cat: metrics(values["category:" + cat]) for cat in sorted(categories)
                             if "category:" + cat in values}, "excluded_other_pairs": number(raw["excluded_pairs"], count=True)}
    return {"schema": "goodsai-public-quality-1", "date": "2026-10-21",
        "runtime": {"baseline_git_sha": freeze["before"], "fixed_git_sha": freeze["after"],
                    "code_sha256": producer["code_sha256"], "config_sha256": producer["config_sha256"],
                    "default_checkout_matches_frozen": True, "external_model_calls": 0,
                    "api_cost_rub": 0, "local_compute_cost_rub": None, "latency_benchmark": None},
        "catalog_silver": {"role": "development_feedback", "variants": variants,
            "paired_counts": {k: number(silver["paired"]["counts"][k], count=True)
                              for k in ("new_tp", "new_fp", "lost_tp", "removed_fp", "new_fn", "removed_fn")},
            "paired_grouped_ci": interval(silver["paired_grouped_ci"]),
            "unassessed_model_candidate_delta": variants["after"]["per_attribute"]["model"]["unassessed_candidates"]
                - variants["before"]["per_attribute"]["model"]["unassessed_candidates"],
            "traffic_quality": None},
        "reviewed_regressions": {"role": "error_selected_development", "origin": "ai_assisted_human_reviewed",
            "cards": len(cohort), "families": len({r["family_id"] for r in cohort}),
            "category_support": dict(sorted(Counter(r["category_id"] for r in cohort).items())),
            "reviewed_attributes": ["model"], "independent_reference": False, "variants": reviewed},
        "provenance": {"input_sha256": freeze["input_sha256"], "silver_reference_sha256": freeze["reference_sha256"],
            "source_bundle_sha256": freeze["source_bundle_sha256"],
            "reviewed_reference_sha256": human["source_reference_sha256"],
            "evaluator_sha256": human["evaluator_sha256"]},
        "independent_human_quality": None, "confidence_kind": "heuristic", "auto_accept": False,
        "limitations": ["Catalog agreement uses noisy labels and exposed development families.",
                        "Model error-selected human review is AI-assisted, all-positive and not independent.",
                        "Unreviewed attributes are excluded; results do not estimate catalogue-wide human precision.",
                        "Unknown/conflict pairs are visible; seller identities and small-group values are not published.",
                        "Two configured categories do not establish quality for new categories or all sellers.",
                        "No controlled latency benchmark, traffic weights, calibration or VM deployment is claimed."]}


def markdown(report):
    lines = ["# GoodsAI: frozen quality evidence, 21.10.2026", "",
        "Rules-only comparison; catalog-silver and AI-assisted reviewed model regressions are separate.",
        "Independent human quality: N/A. Confidence: heuristic; auto_accept: disabled.", "",
        "| Variant / scope | TP | FP | FN |", "| --- | ---: | ---: | ---: |"]
    for name, item in report["catalog_silver"]["variants"].items():
        m = item["agreement"]
        lines.append(f"| {name} / catalog-silver | {m['tp']} | {m['fp']} | {m['fn']} |")
    for name, item in report["reviewed_regressions"]["variants"].items():
        m = item["model"]
        lines.append(f"| {name} / error-selected model review | {m['tp']} | {m['fp']} | {m['fn']} |")
    lines += ["", "Per-attribute/category, title-only/description, rare-value support, unknown/conflict,",
              "family intervals, seller aggregate support and source hashes:",
              "[quality_20261021.json](quality_20261021.json).", ""]
    lines += ["- " + item for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def export(args):
    for path, expected in ((args.silver, args.silver_sha256), (args.human, args.human_sha256)):
        require(digest(path) == expected, "source_report_hash_mismatch")
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    human = read(args.human)
    require(digest(args.reference) == human["source_reference_sha256"], "reviewed_reference_hash_mismatch")
    report = project(read(args.silver), human, read(args.producer), read_jsonl(args.reference), identity(load_config()))
    report["provenance"].update(silver_report_sha256=args.silver_sha256, human_report_sha256=args.human_sha256,
                                producer_manifest_sha256=digest(args.producer), exporter_sha256=digest(Path(__file__)))
    output = args.output_dir.resolve()
    require(output.is_relative_to((ROOT / "outputs").resolve()) and not output.exists(), "new_private_output_required")
    output.mkdir(parents=True)
    (output / "quality_20261021.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "quality_20261021.md").write_text(markdown(report), encoding="utf-8")
    return {"status": "aggregate_exported", "independent_human_quality": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("silver", "human", "producer", "reference", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("silver-sha256", "human-sha256"):
        parser.add_argument("--" + name, required=True)
    try:
        print(json.dumps(export(parser.parse_args())))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        code = str(exc) if type(exc) is ValueError and re.fullmatch(r"[a-z][a-z0-9_]+", str(exc)) else type(exc).__name__
        parser.exit(2, "quality report: " + code + "\n")


if __name__ == "__main__":
    main()
