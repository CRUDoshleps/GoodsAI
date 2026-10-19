"""Deterministic merger: conflicts abstain; uncalibrated candidates require review."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import math

from goodsai.contracts import Product, validate_prediction
from goodsai.config import validate_config
from goodsai.normalize import BOUNDS, UNITS, model_name
from goodsai.relation import RelationVerifier
from goodsai.rules import Rules
from goodsai.stages import CandidateSource
from goodsai.text import visible_span


def validate_candidate(candidate, product: Product, requested: list[str], config: dict | None = None) -> None:
    """Validate internal rule candidates before field access and merging."""
    if not isinstance(candidate.attribute, str) or candidate.attribute not in requested:
        raise ValueError("Rule returned an attribute outside category schema")
    if not isinstance(candidate.field, str) or candidate.field not in {"title", "description"}:
        raise ValueError("Invalid candidate field")
    source = getattr(product, candidate.field) or ""
    if (type(candidate.start) is not int or type(candidate.end) is not int
            or not 0 <= candidate.start < candidate.end <= len(source)):
        raise ValueError("Invalid candidate offsets")
    if any(not isinstance(v, str) or not v.strip() for v in (candidate.value, candidate.text, candidate.rule_id)):
        raise ValueError("Invalid candidate strings")
    if (type(candidate.score) not in (int, float) or not math.isfinite(candidate.score)
            or not 0 <= candidate.score <= 1 or candidate.unit != UNITS.get(candidate.attribute)):
        raise ValueError("Invalid candidate score/unit")
    if source[candidate.start:candidate.end] != candidate.text:
        raise ValueError("Rule violated raw evidence invariant")
    if candidate.attribute == "model" and model_name(visible_span(source, candidate.start, candidate.end)) != candidate.value:
        raise ValueError("Model value is not derived from visible evidence")
    bounds = config["numeric_bounds"] if config is not None else BOUNDS
    if candidate.attribute in bounds:
        low, high = bounds[candidate.attribute]
        try:
            value = Decimal(candidate.value)
            if not value.is_finite() or not Decimal(str(low)) <= value <= Decimal(str(high)):
                raise ValueError("Candidate outside schema")
        except InvalidOperation as exc:
            raise ValueError("Invalid candidate number") from exc


class Extractor:
    def __init__(self, config: dict, *, source: CandidateSource | None = None):
        self.config = validate_config(config)
        self.rules = Rules(self.config) if source is None else source

    def predict(self, product: Product, run_id: str = "rules-v0") -> dict:
        requested = self.config["categories"].get(product.category_id)
        row = {"schema_version": "0.1", "run_id": run_id, "sku_id": product.sku_id,
               "category_id": product.category_id,
               "status": "processed" if requested else "unsupported_category", "attributes": []}
        if not requested:
            validate_prediction(row, self.config, product)
            return row
        grouped = defaultdict(list)
        rejected = defaultdict(set)
        relations = RelationVerifier(product)
        for candidate in self.rules.candidates(product):
            validate_candidate(candidate, product, requested, self.config)
            reason = relations.reason(candidate)
            if reason:
                rejected[candidate.attribute].add(reason)
            else:
                grouped[candidate.attribute].append(candidate)
        for attr in requested:
            candidates = grouped[attr]
            values = {(c.value, c.unit) for c in candidates}
            base = {"attribute": attr, "value": None, "unit": None, "confidence": None,
                    "confidence_kind": "heuristic", "decision": "abstain", "method": "rule",
                    "rule_id": None, "evidence": None, "reason_codes": []}
            if len(values) > 1:
                base["reason_codes"] = ["conflicting_evidence"]
            elif not candidates:
                base["reason_codes"] = sorted(rejected[attr]) or ["not_found_by_rules"]
            else:
                c = min(candidates, key=lambda c: (-c.score, c.field != "title", c.start, c.rule_id))
                base.update(value=c.value, unit=c.unit, confidence=c.score, decision="review",
                            rule_id=c.rule_id, evidence={"field": c.field, "start": c.start,
                                                       "end": c.end, "text": c.text})
            row["attributes"].append(base)
        validate_prediction(row, self.config, product)
        return row
