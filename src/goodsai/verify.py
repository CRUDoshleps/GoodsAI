"""Deterministic merger: conflicts abstain; uncalibrated candidates require review."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from goodsai.contracts import Product, validate_prediction
from goodsai.normalize import BOUNDS, UNITS
from goodsai.rules import Rules


class Extractor:
    def __init__(self, config: dict):
        self.config = config
        self.rules = Rules(config)

    def predict(self, product: Product, run_id: str = "rules-v0") -> dict:
        requested = self.config["categories"].get(product.category_id)
        row = {"schema_version": "0.1", "run_id": run_id, "sku_id": product.sku_id,
               "category_id": product.category_id,
               "status": "processed" if requested else "unsupported_category", "attributes": []}
        if not requested:
            validate_prediction(row, self.config, product)
            return row
        grouped = defaultdict(list)
        for candidate in self.rules.candidates(product):
            if candidate.attribute not in requested:
                raise ValueError("Rule returned an attribute outside category schema")
            source = getattr(product, candidate.field) or ""
            if source[candidate.start:candidate.end] != candidate.text:
                raise ValueError("Rule violated raw evidence invariant")
            if candidate.attribute in BOUNDS:
                low, high = BOUNDS[candidate.attribute]
                try:
                    value = Decimal(candidate.value)
                    if (not value.is_finite() or not Decimal(str(low)) <= value <= Decimal(str(high))
                            or candidate.unit != UNITS[candidate.attribute]):
                        raise ValueError("Candidate outside schema")
                except InvalidOperation as exc:
                    raise ValueError("Invalid candidate number") from exc
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
                base["reason_codes"] = ["rule_not_implemented" if attr == "model" else "not_found_by_rules"]
            else:
                c = min(candidates, key=lambda c: (-c.score, c.field != "title", c.start, c.rule_id))
                base.update(value=c.value, unit=c.unit, confidence=c.score, decision="review",
                            rule_id=c.rule_id, evidence={"field": c.field, "start": c.start,
                                                       "end": c.end, "text": c.text})
            row["attributes"].append(base)
        validate_prediction(row, self.config, product)
        return row
