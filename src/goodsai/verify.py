"""Deterministic merger: conflicts abstain; uncalibrated candidates require review."""
from collections import defaultdict

from goodsai.contracts import Product, validate_prediction
from goodsai.config import validate_config
from goodsai.category_registry import Registry
from goodsai.candidate_verifier import VerifierFactory, validate_candidate
from goodsai.rules import Rules
from goodsai.stages import CandidateSource, GateFactory


class Extractor:
    def __init__(self, config: dict, *, source: CandidateSource | None = None,
                 registry=None, gate_factory: GateFactory | None = None):
        self.config = validate_config(config)
        self.rules = Rules(self.config) if source is None else source
        self.registry = registry if registry is not None else Registry(self.config)
        self.gate_factory = gate_factory if gate_factory is not None else VerifierFactory(
            self.config, registry=self.registry, rules=self.rules if isinstance(self.rules, Rules) else None)

    def predict(self, product: Product, run_id: str = "rules-v0") -> dict:
        requested = self.config["categories"].get(product.category_id)
        row = {"schema_version": "0.1", "run_id": run_id, "sku_id": product.sku_id,
               "category_id": product.category_id,
               "status": "processed" if requested else "unsupported_category", "attributes": []}
        if not requested:
            validate_prediction(row, self.config, product, registry=self.registry)
            return row
        grouped = defaultdict(list)
        rejected = defaultdict(set)
        gate = self.gate_factory.create(product)
        for candidate in self.rules.candidates(product):
            validate_candidate(candidate, product, requested, self.config, registry=self.registry)
            reason = gate.reason(candidate)
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
        from goodsai.confidence import apply_scores
        apply_scores(product, row, grouped, self.config)
        validate_prediction(row, self.config, product, registry=self.registry)
        from goodsai.storage_acceptance import apply_policy
        apply_policy(row, product, self.config)
        from goodsai.trial_acceptance import apply_policy as apply_trial
        apply_trial(row, product, self.config)
        from goodsai.experiment_acceptance import apply_policy as apply_experiment
        apply_experiment(row, product, self.config)
        if self.config["runtime"]["auto_accept_enabled"]:
            validate_prediction(row, self.config, product, registry=self.registry)
        return row
