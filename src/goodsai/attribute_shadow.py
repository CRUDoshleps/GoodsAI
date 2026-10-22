"""Per-field shadow selection. This module never changes runtime decisions.

Targets apply to audited groups; raw rule scores remain heuristics. Existing
storage runtime authorization is deliberately not generalized by a shadow plan.
"""
from copy import deepcopy
import hashlib
import json
import math
import re

from goodsai.config import validate_config
from goodsai.contracts import validate_prediction
from goodsai.candidate_verifier import CandidateVerifier
from goodsai.normalize import UNITS
from goodsai.rules import Rules

VERSION = "attribute-shadow-1"
PROTECTED_FLAGS = frozenset({"train", "training", "test", "test_reserved", "test_reserve",
                             "closed_test", "exposed_test", "independent_test", "holdout"})
RULES = {
    "brand": ("brand.explicit-title.v1", "brand.explicit-subbrand.v2"),
    "model": ("model.labelled.v2", "model.phone-title.v2", "model.kettle-title.v2"),
    "ram_gb": ("memory.context.v1", "memory.title-pair.v1"),
    "storage_gb": ("memory.context.v1", "memory.title-pair.v1"),
    "screen_inches": ("screen_inches.explicit.v1",),
    "battery_mah": ("battery_mah.explicit.v1",),
    "capacity_l": ("capacity_l.explicit.v1",),
    "power_w": ("power_w.explicit.v1",),
    "color": ("color.explicit.v2",),
}
CATEGORY = {"761": re.compile(r"\b(?:смартфон\w*|smartphone)\b", re.I),
            "482": re.compile(r"\b(?:чайник\w*|kettle)\b", re.I)}
ACCESSORY = re.compile(r"\b(?:чех\w*|пл[её]нк\w*|case|cover|часы|часов|браслет\w*)\b", re.I)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def cell_id(category, attribute):
    return category + ":" + attribute


def default_plan(config):
    config = validate_config(config)
    if any(c not in CATEGORY or any(a not in RULES for a in attrs) for c, attrs in config["categories"].items()):
        raise ValueError("Shadow policy supports only the current two category schemas")
    policies = [{"category_id": category, "attribute": attribute,
                 "unit": UNITS.get(attribute), "rule_ids": list(RULES[attribute]),
                 "min_rule_score": 0.0, "target_precision": .99, "audit_families": 300}
                for category, attrs in config["categories"].items() for attribute in attrs]
    return validate_plan({"policy_version": VERSION, "config_sha256": fingerprint(config),
                          "seed": "goodsai-attribute-shadow-20261022-v1",
                          "confidence_level": .95, "batch_size": 50, "policies": policies}, config)


def validate_plan(value, config):
    keys = {"policy_version", "config_sha256", "seed", "confidence_level", "batch_size", "policies"}
    if (not isinstance(value, dict) or set(value) != keys or value["policy_version"] != VERSION
            or value["config_sha256"] != fingerprint(validate_config(config))
            or not isinstance(value["seed"], str) or not value["seed"].strip() or len(value["seed"]) > 256
            or type(value["confidence_level"]) is not float or value["confidence_level"] != .95
            or type(value["batch_size"]) is not int or not 1 <= value["batch_size"] <= 100
            or not isinstance(value["policies"], list) or not value["policies"]):
        raise ValueError("Invalid attribute shadow plan or frozen config hash")
    expected = {cell_id(c, a) for c, attrs in config["categories"].items() for a in attrs}
    seen = set()
    for p in value["policies"]:
        if not isinstance(p, dict) or set(p) != {"category_id", "attribute", "unit", "rule_ids",
                                               "min_rule_score", "target_precision", "audit_families"}:
            raise ValueError("Invalid field policy keys")
        category, attr = p["category_id"], p["attribute"]
        if (not isinstance(category, str) or not isinstance(attr, str)
                or category not in CATEGORY or attr not in RULES or cell_id(category, attr) not in expected
                or cell_id(category, attr) in seen or p["unit"] != UNITS.get(attr)
                or not isinstance(p["rule_ids"], list) or not p["rule_ids"]
                or any(not isinstance(r, str) or r not in RULES[attr] for r in p["rule_ids"])
                or len(set(p["rule_ids"])) != len(p["rule_ids"])):
            raise ValueError("Unknown, repeated or incompatible field policy")
        for key in ("min_rule_score", "target_precision"):
            number = p[key]
            if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1:
                raise ValueError("Policy numbers must be finite fractions")
        if p["target_precision"] == 0 or type(p["audit_families"]) is not int or not 1 <= p["audit_families"] <= 10000:
            raise ValueError("Invalid target or family budget")
        seen.add(cell_id(category, attr))
    if seen != expected:
        raise ValueError("Plan must explicitly cover every configured category/attribute")
    return deepcopy(value)


class Selector:
    """Recheck actual rule provenance after the existing common verifier."""
    def __init__(self, config, plan):
        self.config = validate_config(config)
        if self.config["runtime"]["auto_accept_enabled"]:
            raise ValueError("Shadow input profile must have runtime auto-accept disabled")
        self.plan = validate_plan(plan, self.config)
        self.rules = Rules(self.config)

    def select(self, product, prediction):
        validate_prediction(prediction, self.config, product)
        attrs = {a["attribute"]: a for a in prediction["attributes"]}
        gate = CandidateVerifier(product, self.config)
        candidates = [c for c in self.rules.candidates(product) if gate.reason(c) is None] if attrs else []
        result = {}
        for p in self.plan["policies"]:
            if p["category_id"] != product.category_id:
                continue
            attr = p["attribute"]
            a = attrs.get(attr)
            reason = None
            if PROTECTED_FLAGS.intersection(flag.casefold() for flag in product.source_flags):
                reason = "protected_input"
            elif prediction["status"] != "processed" or a is None or a["decision"] != "review":
                reason = "no_review_candidate"
            elif not CATEGORY[product.category_id].search(product.title) or ACCESSORY.search(product.title):
                reason = "category_not_explicit_or_accessory"
            elif (a["method"] != "rule" or a["rule_id"] not in p["rule_ids"]
                  or a["unit"] != p["unit"] or a["reason_codes"]):
                reason = "outside_rule_policy"
            elif a["confidence"] < p["min_rule_score"]:
                reason = "below_raw_score_filter"
            elif attr in {"ram_gb", "storage_gb"} and any(
                    "conflicting_evidence" in attrs.get(k, {}).get("reason_codes", []) for k in ("ram_gb", "storage_gb")):
                reason = "memory_conflict"
            elif len({(c.value, c.unit) for c in candidates if c.attribute == attr}) != 1:
                reason = "rule_conflict_or_missing"
            else:
                e = a["evidence"]
                if not any((c.attribute, c.value, c.unit, c.score, c.rule_id, c.field, c.start, c.end, c.text) ==
                           (attr, a["value"], a["unit"], a["confidence"], a["rule_id"], e["field"], e["start"], e["end"], e["text"])
                           for c in candidates):
                    reason = "rule_provenance_not_reproducible"
            result[cell_id(product.category_id, attr)] = reason
        return result
