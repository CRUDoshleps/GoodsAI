"""Opt-in, group-audited storage pilot; heuristic scores are not probabilities.

The risk target was changed by the project owner AFTER the 145-case audit.
This bounded exception does not certify independent calibration or other fields.
"""
from copy import deepcopy
import re

POLICY_VERSION = "storage-pilot-97-v1"
MIN_TARGET = .97
AUDIT_CORRECT = AUDIT_TOTAL = 145
AUDIT_LOWER = .05 ** (1 / AUDIT_TOTAL)
AUDIT_ANSWERS_SHA256 = "1ed9b66ac9acfb59a18a35183fd311da1525468c78a80b978def8db5c52a169c"
RULE_IDS = frozenset({"memory.context.v1", "memory.title-pair.v1"})
PHONE = re.compile(r'\b(?:смартфон\w*|smartphone)\b', re.I)
OTHER = re.compile(r'\b(?:часы|часов|браслет\w*|чех\w*|пленк\w*|плёнк\w*|case|watch|cover)\b', re.I)


def validate_policy(value):
    if (not isinstance(value, dict) or set(value) != {"policy_version", "target_precision"}
            or value["policy_version"] != POLICY_VERSION):
        raise ValueError("Unknown storage acceptance policy")
    target = value["target_precision"]
    if type(target) not in (int, float) or not MIN_TARGET <= target <= 1:
        raise ValueError("Storage pilot target_precision must be between 0.97 and 1")
    return deepcopy(value)


def metadata(config):
    runtime = config["runtime"]
    policy = runtime.get("auto_accept")
    if policy is None:
        return None
    target_met = AUDIT_LOWER >= policy["target_precision"]
    enabled = runtime["auto_accept_enabled"]
    return deepcopy(policy) | {
        "enabled": enabled, "active": enabled and target_met,
        "reason": "pilot_active" if enabled and target_met else "disabled" if not enabled else "audit_bound_below_target",
        "category_id": "761", "attribute": "storage_gb",
        "audit_correct": AUDIT_CORRECT, "audit_total": AUDIT_TOTAL,
        "exploratory_one_sided_lower_95": AUDIT_LOWER,
        "answers_sha256": AUDIT_ANSWERS_SHA256,
        "independent_reference": False, "target_chosen_after_audit": True,
        "confidence_kind": "heuristic",
    }


def candidate_eligible(row, product=None):
    """Same text/rule scope as storage-shadow-1; call after ordinary verification.

    Without original text this is only a structural check for persisted records.
    Runtime always supplies the Product and verifies grounding separately.
    """
    if row.get("category_id") != "761" or row.get("status") != "processed":
        return False
    if product is not None and (not PHONE.search(product.title) or OTHER.search(product.title)):
        return False
    attrs = {a["attribute"]: a for a in row["attributes"]}
    a = attrs.get("storage_gb", {})
    if (a.get("decision") not in {"review", "auto_accept"} or a.get("method") != "rule"
            or a.get("unit") != "GB" or a.get("rule_id") not in RULE_IDS or a.get("reason_codes") != []):
        return False
    return not any("conflicting_evidence" in attrs.get(k, {}).get("reason_codes", [])
                   for k in ("storage_gb", "ram_gb"))


def apply_policy(row, product, config):
    """No candidate generation, gold lookup, SKU routing or score reinterpretation."""
    state = metadata(config)
    if state and state["active"] and candidate_eligible(row, product):
        next(a for a in row["attributes"] if a["attribute"] == "storage_gb")["decision"] = "auto_accept"


def validate_accepted(row, attribute, config, product=None):
    state = metadata(config)
    if (not state or not state["active"] or attribute["attribute"] != "storage_gb"
            or not candidate_eligible(row, product)):
        raise ValueError("auto_accept is outside the approved storage pilot")
    if product is None:
        return  # Persisted outputs lack source text; full grounding requires Product.
    # Do not accept a fabricated rule ID/value/evidence or a source injection.
    from goodsai.rules import Rules
    from goodsai.candidate_verifier import CandidateVerifier
    rules, gate = Rules(config), CandidateVerifier(product, config)
    accepted = []
    for candidate in rules.candidates(product):
        if candidate.attribute in {"storage_gb", "ram_gb"} and gate.reason(candidate) is None:
            accepted.append(candidate)
    for name in ("storage_gb", "ram_gb"):
        if len({(c.value, c.unit) for c in accepted if c.attribute == name}) > 1:
            raise ValueError("Conflicting memory cannot be auto-accepted")
    e = attribute["evidence"]
    if not any((c.attribute, c.value, c.unit, c.rule_id, c.field, c.start, c.end, c.text) ==
               ("storage_gb", attribute["value"], attribute["unit"], attribute["rule_id"],
                e["field"], e["start"], e["end"], e["text"]) for c in accepted):
        raise ValueError("Auto-accepted storage is not supported by the approved rules")


def main():
    import argparse
    from pathlib import Path
    from goodsai.config import load_config, validate_config
    from goodsai.data import write_json
    parser = argparse.ArgumentParser(description="Create an opt-in storage pilot profile (no deployment)")
    parser.add_argument("--target-precision", type=float, default=MIN_TARGET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load_config()
    config["runtime"].update(auto_accept_enabled=True, auto_accept={
        "policy_version": POLICY_VERSION, "target_precision": args.target_precision})
    try:
        config = validate_config(config)
        if args.output.exists():
            raise ValueError("Refusing to overwrite an existing profile")
        write_json(args.output, config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    import json
    print(json.dumps(metadata(config), sort_keys=True))


if __name__ == "__main__":
    main()
