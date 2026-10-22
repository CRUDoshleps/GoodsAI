"""EXPERIMENT (branch exp/all-fields-auto-accept): auto_accept for EVERY configured field.

NOT AUDITED, NOT CALIBRATED, NOT FOR PRODUCTION OR THE SUBMISSION BRANCH.
Unlike storage-pilot-97-v1 (human audit) and silver-trial-v1 (catalog-silver
lower bound >= target), this policy has no evidence threshold at all: every
grounded rule value of a bound cell is auto-accepted, including fields whose
catalog agreement is poor (761 model ~54%) or unknown (482 capacity_l).
It exists to measure workload and error exposure of "accept everything".

A cell is active only when ALL hold:
  runtime.auto_accept_enabled is true,
  runtime.auto_accept_policies[category][attribute] == "all-fields-unaudited-v1",
  runtime.auto_accept_experiment == {"policy_version": "all-fields-unaudited-v1",
                                     "acknowledge_unaudited": true}.
Only method=rule values without reason codes; values are re-derived from the
rules and verifier on validation. LLM output is never auto-accepted. Values,
evidence and scores are unchanged; only the decision differs.
"""
from copy import deepcopy

EXPERIMENT_POLICY = "all-fields-unaudited-v1"


def validate_experiment(value):
    if (not isinstance(value, dict) or set(value) != {"policy_version", "acknowledge_unaudited"}
            or value["policy_version"] != EXPERIMENT_POLICY or value["acknowledge_unaudited"] is not True):
        raise ValueError("Unaudited auto_accept experiment requires explicit acknowledge_unaudited=true")
    return deepcopy(value)


def active_cells(config):
    runtime = config["runtime"]
    if not runtime["auto_accept_enabled"] or "auto_accept_experiment" not in runtime:
        return set()
    from goodsai.storage_acceptance import bound_cells
    return set(bound_cells(config, EXPERIMENT_POLICY))


def metadata(config):
    if "auto_accept_experiment" not in config["runtime"]:
        return None
    from goodsai.storage_acceptance import bound_cells
    from goodsai.trial_acceptance import EVIDENCE, LOWER
    active = active_cells(config)
    cells = {}
    for category, attribute in sorted(bound_cells(config, EXPERIMENT_POLICY)):
        evidence = EVIDENCE.get((category, attribute))
        cells.setdefault(category, {})[attribute] = {
            "active": (category, attribute) in active,
            "silver_tp": None if evidence is None else evidence["tp"],
            "silver_fp": None if evidence is None else evidence["fp"],
            "silver_one_sided_lower_95": LOWER.get((category, attribute)),
        }
    return {"policy_version": EXPERIMENT_POLICY, "enabled": config["runtime"]["auto_accept_enabled"],
            "cells": cells, "audited": False, "evidence_threshold": None, "human_audit": False,
            "independent_reference": False, "production_safe": False, "confidence_kind": "heuristic"}


def apply_policy(row, product, config):
    from goodsai.trial_acceptance import _eligible
    cells = active_cells(config)
    for attribute in row["attributes"]:
        if (row.get("category_id"), attribute["attribute"]) in cells and _eligible(row, attribute):
            attribute["decision"] = "auto_accept"


def validate_accepted(row, attribute, config, product=None):
    from goodsai.trial_acceptance import _eligible, rederive
    if ((row.get("category_id"), attribute["attribute"]) not in active_cells(config)
            or not _eligible(row, attribute)):
        raise ValueError("auto_accept is outside the approved policies")
    rederive(attribute, config, product)


def main():
    import argparse
    import json
    from pathlib import Path
    from goodsai.config import load_config, validate_config
    from goodsai.data import write_json
    parser = argparse.ArgumentParser(
        description="Create an UNAUDITED all-fields auto_accept experiment profile (no deployment)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load_config()
    runtime = config["runtime"]
    for category, attributes in config["categories"].items():
        for attribute in attributes:
            runtime["auto_accept_policies"][category][attribute] = EXPERIMENT_POLICY
    runtime.update(auto_accept_enabled=True,
                   auto_accept_experiment={"policy_version": EXPERIMENT_POLICY, "acknowledge_unaudited": True})
    try:
        config = validate_config(config)
        if args.output.exists():
            raise ValueError("Refusing to overwrite an existing profile")
        write_json(args.output, config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(metadata(config), sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
