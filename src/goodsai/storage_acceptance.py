"""Opt-in, group-audited storage pilot; heuristic scores are not probabilities.

The risk target was changed by the project owner AFTER the 145-case audit.
This bounded exception does not certify independent calibration or other fields.
"""
from copy import deepcopy
import re

POLICY_VERSION = "storage-pilot-97-v1"
REVIEW = "review"
# The only category x attribute cells with a completed audit. A cell may name its
# audited policy or "review"; anything else is rejected before inference. New
# entries require a new audit (for example CONF-006) and an architect decision.
AUDITED_POLICIES = {("761", "storage_gb"): POLICY_VERSION}
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


def default_cell_policies(categories):
    """Every configured category x attribute; audited cells name their policy, others review."""
    return {category: {attribute: AUDITED_POLICIES.get((category, attribute), REVIEW)
                       for attribute in attributes}
            for category, attributes in categories.items()}


def validate_cell_policies(value, categories=None):
    """Check every given cell; return the section unchanged (idempotent for derived profiles).

    A cell is either review or the audited policy of exactly that category and
    attribute, so no value can grant auto_accept to an unaudited cell. Cells that
    are absent, or belong to an unconfigured category/attribute, act as review.
    """
    if not isinstance(value, dict):
        raise ValueError("auto_accept_policies must be an object")
    for category, cells in value.items():
        if not isinstance(category, str) or not isinstance(cells, dict):
            raise ValueError("auto_accept_policies must map category IDs to attribute objects")
        for attribute, policy in cells.items():
            if policy != REVIEW and policy != AUDITED_POLICIES.get((category, attribute), REVIEW):
                raise ValueError("auto_accept policy is not audited for this category and attribute")
    return deepcopy(value)


def effective_cell_policies(config):
    """Complete view over every configured category x attribute, in schema order."""
    given = config["runtime"].get("auto_accept_policies")
    if given is None:
        return default_cell_policies(config["categories"])
    return {category: {attribute: given.get(category, {}).get(attribute, REVIEW) for attribute in attributes}
            for category, attributes in config["categories"].items()}


def bound_cells(config, policy_version=POLICY_VERSION):
    return [(category, attribute) for category, row in effective_cell_policies(config).items()
            for attribute, policy in row.items() if policy == policy_version]


def metadata(config):
    runtime = config["runtime"]
    policy = runtime.get("auto_accept")
    if policy is None:
        return None
    target_met = AUDIT_LOWER >= policy["target_precision"]
    enabled = runtime["auto_accept_enabled"]
    bound = ("761", "storage_gb") in bound_cells(config)
    active = enabled and bound and target_met
    reason = ("pilot_active" if active else "disabled" if not enabled
              else "cell_not_bound" if not bound else "audit_bound_below_target")
    return deepcopy(policy) | {
        "enabled": enabled, "active": active, "reason": reason,
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
