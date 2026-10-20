"""Prepare private, hash-bound handoffs for #123/#124/#125, without inference.

Missing artifacts stay blockers. This command never creates a new split, invents
quality numbers, calls a gateway, or authorizes a data transfer.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/research"))
from compare_silver_baseline import git, private_output
from goodsai.data import digest
from goodsai.learn_categories import load_inputs, rows
from goodsai.silver_prepare import SEED, dump, verify_bundle


def pilot_selection(train, split, traffic, *, excluded, min_support=30, limit=3):
    """Select by train support/traffic only; never inspect predictions/reference."""
    if type(min_support) is not int or min_support < 3 or type(limit) is not int or limit < 3:
        raise ValueError("at_least_three_categories_and_minimum_train_support_required")
    paths, hashes, allowed, counts = load_inputs(train, split, traffic)
    supports, attributes = Counter(), {}
    for row in rows(paths[0], allowed):
        category = row["category_id"]
        supports[category] += 1
        attributes.setdefault(category, Counter()).update(p["name"] for p in row["params"])
    eligible = [c for c, n in supports.items() if c not in excluded and n >= min_support]
    selected = sorted(eligible, key=lambda c: (-counts.get(c, 0), -supports[c], c))[:limit]
    result = {"status": "selection_proposed_awaiting_contract" if len(selected) >= 3 else "insufficient_new_categories",
              "selection_algorithm": "exclude_existing_then_min_train_support_then_traffic_desc_support_desc_category_asc",
              "minimum_train_support": min_support, "requested_categories": limit,
              "excluded_default_categories": sorted(excluded),
              "categories": [{"category_id": c, "train_rows": supports[c],
                              "train_attribute_names": sorted(attributes[c]),
                              "mapping_and_units": "needs_owner_approval"} for c in selected],
              "train_sha256": hashes[0], "split_sha256": hashes[1], "traffic_sha256": hashes[2],
              "quality": None, "inference": "not_run", "default_enable": False,
              "limitations": ["Counts do not establish real category identity or attribute diversity.",
                              "Laptop identity, required fields, mapping/units and family isolation need owner review.",
                              "Selection is a proposal; blockers #5/#10/#44 are not resolved by this script."]}
    if [digest(p) for p in paths] != hashes:
        raise ValueError("train_sources_changed")
    return result


def prepare(args):
    # Public aggregates supply expected fingerprints, not private data or fresh metrics.
    history = json.loads((ROOT / "reports/run_stats.json").read_text())
    provenance = history["provenance"]
    sha = git("rev-parse", args.candidate + "^{commit}")
    bundle_status = "missing_private_bundle"
    if args.bundle:
        verify_bundle(args.bundle)
        if digest(args.bundle / "manifest.json") != provenance["bundle_manifest_sha256"]:
            raise ValueError("historical_frozen_bundle_mismatch")
        bundle_status = "hash_verified_audit_and_sources_still_required"
    out = private_output(args.output_dir)
    common = {"created_utc": datetime.now(timezone.utc).isoformat(), "candidate_sha": sha,
              "preparation_driver_sha256": digest(Path(__file__)), "seed": SEED,
              "reference_kind": "catalog_silver", "evaluation_role": "development_feedback",
              "independent_quality": None, "auto_accept": "forbidden", "test_reserve": "closed",
              "inference": "not_run", "historical_aggregates_are_fresh_measurements": False}
    frozen = {**common, "issue": 123, "status": bundle_status,
              "expected_bundle_manifest_sha256": provenance["bundle_manifest_sha256"],
              "historical_producer_sha": provenance["runtime"]["git_commit"],
              "expected_preparation_sources": provenance["sources"],
              "evaluator_sha256": digest(ROOT / "src/goodsai/silver_evaluate.py"),
              "support_matcher_sha256": digest(ROOT / "src/goodsai/silver_support.py"),
              "comparison_driver_sha256": digest(ROOT / "scripts/research/compare_silver_baseline.py"),
              "required": ["existing EVAL-006 bundle", "matching EVAL-002 audit and original source paths",
                           "all exposure ledgers, including any access since preparation", "two exact Git commits"],
              "regression_gate": "any_new_fp_or_lost_tp_blocks_candidate_and_requires_defect",
              "external_model_calls": "forbidden"}
    pilot = {**common, "issue": 124, "status": "blocked_contract_and_train_handoff",
             "dependencies": [5, 10, 44], "minimum_categories": 3, "default_enable": False,
             "selection": "train-only support/traffic, fixed before predictions; no replacement after failure",
             "required_before_inference": ["approved train/split/family/source hashes", "owner-approved category/attribute/unit mapping",
                                           "accept existing registry interface #44", "separate opt-in config; E1 remains compatible"],
             "checks": ["actual CLI and HTTP", "canonical values and exact evidence", "absent/conflict/negation/HTML",
                        "unknown value, unsupported input, invalid config", "E1 regression and input target exclusion"],
             "measurement": {"schema_availability": None, "synthetic_checks": None,
                             "catalog_agreement": None, "human_quality": None}}
    train_paths = (args.train, args.split, args.traffic)
    if any(train_paths):
        if not all(train_paths):
            raise ValueError("train_split_and_traffic_required_together")
        from goodsai.contracts import load_config
        pilot["pilot_proposal"] = pilot_selection(*train_paths, excluded=set(load_config()["categories"]),
                                                  min_support=args.min_support)
    benchmark = {**common, "issue": 125, "status": "blocked_frozen_baseline_and_packet_authorization",
                 "dependencies": [123, 16, 25], "input": "existing llm_screening.input.jsonl, same for every method",
                 "selection": "existing pre-prediction development screening; no outcome-based filtering",
                 "methods": {name: {"status": "not_run"} for name in ("rules", "llm", "brand_hybrid")},
                 "combined": "not_implemented_not_run",
                 "existing_adapters": ["goodsai.cli", "goodsai.llm", "goodsai.experimental_gliner"],
                 "gateway_plan": {"model": "openai/gpt-oss-120b", "price_input_rub_per_million": 15.86,
                                  "price_output_rub_per_million": 61.0, "prices_source": "owner_supplied_screenshot_2026-10-20",
                                  "max_physical_attempts_per_run": 100, "daily_attempts_cap": 300,
                                  "concurrency": 2, "remaining_global_budget": None,
                                  "packet_sha256_authorized": None, "spend_limit_rub_authorized": None,
                                  "credentials": "environment_only_never_in_artifact"},
                 "before_calls": ["freeze #123 and screening input/reference hashes", "validate existing local brand artifact hashes",
                                  "explicit team packet/model/spend authorization; confirm global remaining calls and rubles",
                                  "freeze timeout/deadline/token limits and shared budget ledger"],
                 "keep_gate": "positive_new_tp_and_zero_new_fp_and_zero_lost_tp_and_complete_measured_usage",
                 "unknown_cost": None, "partial_run": "must_report_achieved_size_and_budget_skips",
                 "independent_acceptance_40": "not_satisfied"}
    for name, content in (("eval-007.handoff.json", frozen), ("conf-004.plan.json", pilot), ("eval-008.plan.json", benchmark)):
        dump(out / name, content)
    dump(out / "manifest.json", {"schema": "goodsai-checkpoint-preparation-1", "artifacts": {
        p.name: digest(p) for p in sorted(out.iterdir())}})
    return {"status": "prepared_no_inference", "issues": [123, 124, 125], "bundle": bundle_status}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--bundle", type=Path)
    for name in ("train", "split", "traffic"):
        p.add_argument("--" + name, type=Path)
    p.add_argument("--min-support", default=30, type=int)
    print(json.dumps(prepare(p.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
