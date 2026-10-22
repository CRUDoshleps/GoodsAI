"""CONF-008 trial: opt-in auto_accept for six more fields from catalog-silver agreement.

This is a TRIAL, not a human audit and not an independent calibration. The
evidence below is the frozen catalog-silver agreement of the rules baseline
(reports/run_stats.json, producer f33e3fc, 3037 development cards / 1270
families). A catalog value is noisy silver: unknown/conflicting references are
excluded, and agreement is not proof of correctness. Targets were chosen after
looking at these numbers. The runtime rules changed after that run, so the
numbers describe the historical producer, not a guarantee for the current one.

A cell becomes active only when ALL of the following hold:
  runtime.auto_accept_enabled is true,
  runtime.auto_accept_policies[category][attribute] == "silver-trial-v1",
  runtime.auto_accept_trial.targets[category][attribute] is set, and
  the frozen one-sided 95% Clopper-Pearson lower bound >= that target.
Only method=rule candidates without reason codes are accepted; LLM output never is.
"""
from copy import deepcopy
import math

TRIAL_POLICY = "silver-trial-v1"
MIN_TARGET = .85
SOURCE = {"report": "reports/run_stats.json", "slice": "slices.category_attribute",
          "producer": "f33e3fcd1487a3d82f8ed684ebfaa56d8220f6e4",
          "reference_kind": "catalog_silver", "cards": 3037, "families": 1270}
# (category, attribute) -> catalog-silver agreement of rule predictions with a known reference.
EVIDENCE = {
    ("761", "ram_gb"): {"tp": 1581, "fp": 4},
    ("761", "battery_mah"): {"tp": 122, "fp": 3},
    ("761", "color"): {"tp": 1138, "fp": 85},
    ("761", "brand"): {"tp": 1714, "fp": 156},
    ("482", "brand"): {"tp": 610, "fp": 0},
    ("482", "color"): {"tp": 136, "fp": 11},
}
# Trial profile defaults: each target sits at or below its frozen lower bound.
DEFAULT_TARGETS = {
    "761": {"ram_gb": .99, "battery_mah": .93, "color": .91, "brand": .90},
    "482": {"brand": .99, "color": .87},
}


def lower_bound(tp, n, alpha=.05):
    """One-sided Clopper-Pearson lower bound for tp successes out of n (exact binomial)."""
    if tp == 0:
        return 0.
    if tp == n:
        return alpha ** (1 / n)

    def tail(p):  # P(X >= tp | n, p), in log space to avoid float overflow for large n
        if p <= 0:
            return 0.
        if p >= 1:
            return 1.
        log_p, log_q = math.log(p), math.log1p(-p)
        return sum(math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                            + k * log_p + (n - k) * log_q) for k in range(tp, n + 1))
    lo, hi = 0., 1.
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tail(mid) < alpha else (lo, mid)
    return lo


LOWER = {cell: lower_bound(e["tp"], e["tp"] + e["fp"]) for cell, e in EVIDENCE.items()}


def validate_trial(value):
    if (not isinstance(value, dict) or set(value) != {"policy_version", "targets"}
            or value["policy_version"] != TRIAL_POLICY or not isinstance(value["targets"], dict)):
        raise ValueError("Unknown auto_accept trial policy")
    for category, cells in value["targets"].items():
        if not isinstance(cells, dict) or not cells:
            raise ValueError("auto_accept trial targets must map categories to attribute targets")
        for attribute, target in cells.items():
            if (category, attribute) not in EVIDENCE:
                raise ValueError("auto_accept trial has no evidence for this category and attribute")
            if type(target) not in (int, float) or not MIN_TARGET <= target <= 1:
                raise ValueError("auto_accept trial target must be between 0.85 and 1")
    return deepcopy(value)


def targets(config):
    trial = config["runtime"].get("auto_accept_trial")
    return {} if trial is None else {(c, a): t for c, row in trial["targets"].items() for a, t in row.items()}


def metadata(config):
    trial = config["runtime"].get("auto_accept_trial")
    if trial is None:
        return None
    from goodsai.storage_acceptance import bound_cells
    enabled = config["runtime"]["auto_accept_enabled"]
    bound = set(bound_cells(config, TRIAL_POLICY))
    cells = {}
    for (category, attribute), target in sorted(targets(config).items()):
        lower = LOWER[(category, attribute)]
        active = enabled and (category, attribute) in bound and lower >= target
        reason = ("trial_active" if active else "disabled" if not enabled
                  else "cell_not_bound" if (category, attribute) not in bound else "evidence_below_target")
        evidence = EVIDENCE[(category, attribute)]
        cells.setdefault(category, {})[attribute] = {
            "target_precision": target, "active": active, "reason": reason,
            "silver_tp": evidence["tp"], "silver_fp": evidence["fp"],
            "silver_one_sided_lower_95": lower}
    return {"policy_version": TRIAL_POLICY, "enabled": enabled, "cells": cells, "source": deepcopy(SOURCE),
            "human_audit": False, "independent_reference": False, "target_chosen_after_results": True,
            "confidence_kind": "heuristic"}


def active_cells(config):
    state = metadata(config)
    if state is None:
        return set()
    return {(c, a) for c, row in state["cells"].items() for a, cell in row.items() if cell["active"]}


def _eligible(row, attribute):
    return (row.get("status") == "processed" and attribute.get("decision") in {"review", "auto_accept"}
            and attribute.get("method") == "rule" and attribute.get("reason_codes") == []
            and attribute.get("value") is not None and attribute.get("evidence") is not None)


def apply_policy(row, product, config):
    """Change review to auto_accept for active trial cells; values/evidence/scores untouched."""
    cells = active_cells(config)
    for attribute in row["attributes"]:
        if (row.get("category_id"), attribute["attribute"]) in cells and _eligible(row, attribute):
            attribute["decision"] = "auto_accept"


def validate_accepted(row, attribute, config, product=None):
    if ((row.get("category_id"), attribute["attribute"]) not in active_cells(config)
            or not _eligible(row, attribute)):
        raise ValueError("auto_accept is outside the approved policies")
    if product is None:
        return  # Persisted outputs lack source text; full grounding requires Product.
    # Re-derive gate-approved rule candidates: no forged rule IDs, values or evidence, no conflicts.
    from goodsai.rules import Rules
    from goodsai.candidate_verifier import CandidateVerifier
    name = attribute["attribute"]
    gate = CandidateVerifier(product, config)
    accepted = [c for c in Rules(config).candidates(product) if c.attribute == name and gate.reason(c) is None]
    if len({(c.value, c.unit) for c in accepted}) > 1:
        raise ValueError("Conflicting values cannot be auto-accepted")
    e = attribute["evidence"]
    if not any((c.value, c.unit, c.rule_id, c.field, c.start, c.end, c.text) ==
               (attribute["value"], attribute["unit"], attribute["rule_id"],
                e["field"], e["start"], e["end"], e["text"]) for c in accepted):
        raise ValueError("Auto-accepted value is not supported by the rules")


def main():
    import argparse
    import json
    from pathlib import Path
    from goodsai.config import load_config, validate_config
    from goodsai.data import write_json
    from goodsai.storage_acceptance import POLICY_VERSION, MIN_TARGET as STORAGE_TARGET
    parser = argparse.ArgumentParser(description="Create an opt-in CONF-008 trial profile (no deployment)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--without-storage-pilot", action="store_true",
                        help="leave 761/storage_gb in review instead of storage-pilot-97-v1")
    args = parser.parse_args()
    config = load_config()
    runtime = config["runtime"]
    for category, cells in DEFAULT_TARGETS.items():
        for attribute in cells:
            runtime["auto_accept_policies"][category][attribute] = TRIAL_POLICY
    runtime.update(auto_accept_enabled=True,
                   auto_accept_trial={"policy_version": TRIAL_POLICY, "targets": deepcopy(DEFAULT_TARGETS)})
    if args.without_storage_pilot:
        runtime["auto_accept_policies"]["761"]["storage_gb"] = "review"
    else:
        runtime["auto_accept"] = {"policy_version": POLICY_VERSION, "target_precision": STORAGE_TARGET}
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
