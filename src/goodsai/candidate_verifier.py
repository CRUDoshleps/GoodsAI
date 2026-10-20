"""Source-independent v1 candidate gate; no provider, SKU lookup or acceptance score."""
from decimal import Decimal, InvalidOperation
import math
import re

from goodsai.category_registry import Registry
from goodsai.model_rules import QUANTITY, NETWORK
from goodsai.normalize import BOUNDS, NUMBER, UNITS, model_name
from goodsai.relation import RelationVerifier
from goodsai.rules import Rules, bounded_alias
from goodsai.stages import Candidate
from goodsai.text import visible_span

VERSION = "candidate-verifier-1"
UNIT_PATTERNS = {
    "storage_gb": r"GB|ГБ", "ram_gb": r"GB|ГБ",
    "screen_inches": r'дюйм\w*|inches?\b|["″]',
    "battery_mah": r"м[аa]\s*(?:[*·⋅]\s*)?ч|mAh",
    "capacity_l": r"мл|ml|литр\w*|л|L", "power_w": r"кВт|kW|Вт|W",
}


class CandidateError(ValueError):
    """Fixed public diagnostic, without input values, text or exception details."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_candidate(candidate, product, requested, config=None, *, registry=None):
    """Compatibility invariant check. Trusted generator bugs still fail fast."""
    if not isinstance(candidate, Candidate):
        raise CandidateError("verifier_bad_candidate", "Invalid candidate contract")
    registry = Registry(config) if registry is None and config is not None else registry
    if not isinstance(candidate.attribute, str) or candidate.attribute not in requested:
        raise CandidateError("verifier_unknown_attribute", "Candidate outside category schema")
    if not isinstance(candidate.field, str) or candidate.field not in {"title", "description"}:
        raise CandidateError("verifier_bad_field", "Invalid candidate field")
    source = getattr(product, candidate.field) or ""
    if (type(candidate.start) is not int or type(candidate.end) is not int
            or not 0 <= candidate.start < candidate.end <= len(source)):
        raise CandidateError("verifier_bad_offsets", "Invalid candidate offsets")
    if any(not isinstance(v, str) or not v.strip() for v in (candidate.value, candidate.text, candidate.rule_id)):
        raise CandidateError("verifier_bad_types", "Invalid candidate strings")
    if type(candidate.score) not in (int, float) or not 0 <= candidate.score <= 1 or not math.isfinite(candidate.score):
        raise CandidateError("verifier_bad_score", "Invalid candidate score")
    if candidate.unit != (registry.unit(product.category_id, candidate.attribute) if registry else UNITS.get(candidate.attribute)):
        raise CandidateError("verifier_bad_unit", "Invalid candidate unit")
    if source[candidate.start:candidate.end] != candidate.text:
        raise CandidateError("verifier_bad_evidence", "Candidate violated raw evidence invariant")
    if candidate.attribute == "model" and model_name(visible_span(source, candidate.start, candidate.end)) != candidate.value:
        raise CandidateError("verifier_bad_normalization", "Model value is not derived from visible evidence")
    if registry and registry.spec(product.category_id, candidate.attribute):
        visible = visible_span(source, candidate.start, candidate.end)
        if registry.normalize(product.category_id, candidate.attribute, candidate.value, candidate.unit) != candidate.value:
            raise CandidateError("verifier_bad_normalization", "Noncanonical registry candidate")
        if not registry.supported(product.category_id, candidate.attribute, candidate.value, visible):
            raise CandidateError("verifier_unsupported_value", "Registry candidate value is not derived from evidence")
    bounds = config["numeric_bounds"] if config is not None else BOUNDS
    if candidate.attribute in bounds:
        low, high = bounds[candidate.attribute]
        try:
            value = Decimal(candidate.value)
            if not value.is_finite() or not Decimal(str(low)) <= value <= Decimal(str(high)):
                raise CandidateError("verifier_out_of_range", "Candidate outside schema")
        except InvalidOperation as exc:
            raise CandidateError("verifier_bad_number", "Invalid candidate number") from exc


class CandidateVerifier:
    """One prepared gate per product; reason(None) is never a calibrated guarantee.

    All producing methods use reason(candidate). Internal rules additionally
    validate their structural invariant to expose implementation defects.
    Conflicts are merged afterwards, never resolved by this gate or by score.
    """
    def __init__(self, product, config, *, registry=None, rules=None, normalizer=None):
        self.product, self.config = product, config
        self.registry = registry if registry is not None else Registry(config)
        self.normalizer = normalizer if normalizer is not None else self.registry
        self.requested = self.registry.attributes(product.category_id)
        self.rules = Rules(config) if rules is None else rules
        self.models = self.rules.model_rules
        self.relations = RelationVerifier(product, config, models=self.models)

    def reason(self, candidate):
        try:
            validate_candidate(candidate, self.product, self.requested, self.config, registry=self.registry)
        except CandidateError as exc:
            return exc.code
        except ValueError:
            return "verifier_unsupported_value"
        reason = self.relations.reason(candidate)
        if reason:
            return reason
        # A registry has its own finite, train-derived normalization/support grammar.
        if self.registry.spec(self.product.category_id, candidate.attribute):
            return None
        text, _, starts, ends = self.relations.views[candidate.field]
        start, end = starts[candidate.start], ends[candidate.end]
        visible = text[start:end]
        if candidate.attribute in UNITS:
            if self.rules.uncertain(text, start):
                return "verifier_uncertain_value"
            return self._number_reason(candidate, text, start, end)
        if candidate.attribute in {"brand", "color"}:
            aliases = self.config["brands" if candidate.attribute == "brand" else "colors"]
            spellings = aliases.get(candidate.value)
            if spellings is not None:
                if any(re.search(bounded_alias(a), visible, re.I) for a in spellings):
                    return None
            elif candidate.attribute == "brand" and model_name(visible) == candidate.value:
                # Open-vocabulary model brands remain possible, without catalog lookup.
                if re.search(r"[^\W\d_]", visible) and visible.casefold() not in {
                        "смартфон", "телефон", "чайник", "электрочайник", "smartphone", "phone", "kettle"}:
                    return None
            return "verifier_unsupported_value"
        if candidate.attribute == "model":
            # No partial token, omitted family/suffix, brand, memory or color in model.
            if ((start and re.match(r"[\w/+-]", text[start - 1]))
                    or (end < len(text) and re.match(r"[\w/+-]", text[end]))
                    or (start > 1 and text[start - 1] == "." and text[start - 2].isalnum())
                    or (end + 1 < len(text) and text[end] == "." and text[end + 1].isalnum())):
                return "verifier_incomplete_model"
            spans = self.models.spans(self.product.category_id, candidate.field, text)
            if any(a <= start < end <= b and (a, b) != (start, end) for a, b, _ in spans):
                return "verifier_incomplete_model"
            brands = (self.models.phone_brands if self.config["category_profiles"][self.product.category_id] == "smartphone"
                      else self.models.model_brands)
            if (not re.search(r"[^\W\d_]", visible) or visible.casefold() in {
                    "смартфон", "телефон", "чайник", "электрочайник", "smartphone", "phone", "kettle"}
                    or self.models.prefix(visible, brands) or QUANTITY.search(visible)
                    or re.fullmatch(NETWORK, visible, re.I)
                    or any(re.search(bounded_alias(a), visible, re.I) for a in self.models.colors)):
                return "verifier_unsupported_model"
        return None

    def _number_reason(self, c, text, start, end):
        if start and text[start - 1] in "+-~≈":
            return "verifier_unsupported_value"
        if c.attribute in {"ram_gb", "storage_gb"}:
            # Pair order and explicit memory roles are shared with the agreed rules policy.
            for pair in self.rules.pair.finditer(text, max(0, start - 32), min(len(text), end + 32)):
                if pair.start() < end and pair.end() > start:
                    if self.rules.uncertain(text, pair.start()):
                        return "verifier_uncertain_value"
                    if not (start <= pair.start() and pair.end() <= end):
                        return "verifier_ambiguous_memory_role"
                    role = "ram" if c.attribute == "ram_gb" else "rom"
                    ram, rom = int(pair["ram"]), int(pair["rom"])
                    low_ram, high_ram = self.rules.limits["memory_pair_ram_bounds"]
                    low_rom, high_rom = self.rules.limits["memory_pair_storage_bounds"]
                    if (low_ram <= ram <= high_ram and low_rom <= rom <= high_rom and ram < rom
                            and c.value == str(int(pair[role]))):
                        return None
                    return "verifier_ambiguous_memory_role"
        pattern = rf"(?<![\w.,+/\-])(?P<n>{NUMBER}|\d{{5}})\s*(?P<u>{UNIT_PATTERNS[c.attribute]})(?!\w)"
        for match in re.compile(pattern, re.I).finditer(text, start, min(len(text), end + 1)):
            if match.end() > end:
                continue
            try:
                canonical = self.normalizer.normalize(self.product.category_id, c.attribute, match["n"], match["u"])
            except ValueError:
                continue
            if canonical != c.value:
                continue
            if self.rules.uncertain(text, match.start()):
                return "verifier_uncertain_value"
            if c.attribute in {"ram_gb", "storage_gb"}:
                radius = self.rules.limits["memory_role_distance_chars"] + 40
                left, right = max(0, start - radius), min(len(text), end + radius)
                if self.rules.memory_role(text[left:right], match.start() - left, match.end() - left) != c.attribute:
                    return "verifier_ambiguous_memory_role"
            return None
        return "verifier_unsupported_value"


class VerifierFactory:
    """Explicit profile-bound support grammar, shared by every producing method."""
    def __init__(self, config, *, registry=None, rules=None, normalizer=None):
        self.config = config
        self.registry = registry if registry is not None else Registry(config)
        self.rules = rules if rules is not None else Rules(config)
        self.normalizer = normalizer if normalizer is not None else self.registry

    def create(self, product):
        return CandidateVerifier(product, self.config, registry=self.registry,
                                 rules=self.rules, normalizer=self.normalizer)
