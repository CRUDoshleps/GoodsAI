"""Opt-in, literal category schemas. Never load code/regex or targets at inference."""
from decimal import Decimal, InvalidOperation, localcontext
import re

from goodsai.stages import Candidate
from goodsai.text import visible_span, visible_view

VERSION = "1"
NUMBER = r"\d{1,12}(?:[.,]\d{1,6})?"
BAD = re.compile(r"\b(?:не|нет|без|от|до|около|примерно|более|менее|для|совместим\w*|друг\w*|аналог\w*|подходит|комплект\w*|упаковк\w*|вместо|not|without|compatible|bundle)\b", re.I)


def clean(value):
    return " ".join(value.split())


def decimal_value(value):
    if not isinstance(value, str) or not re.fullmatch(NUMBER, value):
        raise ValueError("Registry number must be a nonnegative plain decimal")
    try:
        with localcontext() as ctx:
            ctx.prec = 32  # Grammar permits at most 18 significant digits.
            number = Decimal(value.replace(",", "."))
            return format(number.normalize(), "f")
    except InvalidOperation as exc:
        raise ValueError("Invalid registry number") from exc


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Invalid category registry keys")


def _literal(value, maximum=256):
    if not isinstance(value, str) or not value or value != clean(value) or len(value) > maximum:
        raise ValueError("Invalid category registry literal")


def validate_registry(registry):
    _keys(registry, {"registry_version", "categories", "provenance"})
    if registry["registry_version"] != VERSION:
        raise ValueError("Unsupported category registry version")
    provenance = registry["provenance"]
    _keys(provenance, {"train_sha256", "split_sha256", "traffic_sha256", "training_cards", "fill_threshold", "top_k", "min_template_support"})
    for key in ("train_sha256", "split_sha256", "traffic_sha256"):
        if not isinstance(provenance[key], str) or not re.fullmatch(r"[a-f0-9]{64}", provenance[key]):
            raise ValueError("Invalid registry provenance hash")
    if (type(provenance["training_cards"]) is not int or provenance["training_cards"] <= 0
            or type(provenance["top_k"]) is not int or not 1 <= provenance["top_k"] <= 1000
            or type(provenance["min_template_support"]) is not int or provenance["min_template_support"] < 3
            or type(provenance["fill_threshold"]) not in (float, int)
            or not 0.5 <= provenance["fill_threshold"] <= 1):
        raise ValueError("Invalid registry learning policy")
    categories = registry["categories"]
    if not isinstance(categories, dict) or not 1 <= len(categories) <= provenance["top_k"]:
        raise ValueError("Empty or oversized registry")
    for category, entry in categories.items():
        _literal(category, 128)
        _keys(entry, {"training_cards", "attributes", "templates"})
        if type(entry["training_cards"]) is not int or entry["training_cards"] <= 0:
            raise ValueError("Invalid category support")
        attributes = entry["attributes"]
        if not isinstance(attributes, dict) or not 1 <= len(attributes) <= 128:
            raise ValueError("Invalid category attributes")
        for attribute, spec in attributes.items():
            if not isinstance(attribute, str) or not re.fullmatch(r"catalog_[a-f0-9]{16}", attribute):
                raise ValueError("Registry attribute IDs must use catalog namespace")
            _keys(spec, {"name", "kind", "unit", "values", "support"})
            _literal(spec["name"], 120)
            if not isinstance(spec["kind"], str) or spec["kind"] not in {"enum", "number"}:
                raise ValueError("Unsupported registry kind")
            if spec["unit"] is not None:
                _literal(spec["unit"], 32)
            if spec["kind"] == "enum" and spec["unit"] is not None:
                raise ValueError("Enum units must be null")
            if not isinstance(spec["values"], list) or not 1 <= len(spec["values"]) <= 1024:
                raise ValueError("Invalid registry dictionary")
            for value in spec["values"]:
                _literal(value)
                if spec["kind"] == "number" and decimal_value(value) != value:
                    raise ValueError("Registry numbers must be canonical")
            if len({v.casefold() for v in spec["values"]}) != len(spec["values"]):
                raise ValueError("Ambiguous registry dictionary")
            if (type(spec["support"]) is not int or not 1 <= spec["support"] <= entry["training_cards"]
                    or spec["support"] / entry["training_cards"] < provenance["fill_threshold"]):
                raise ValueError("Invalid attribute support")
        templates = entry["templates"]
        if not isinstance(templates, list) or len(templates) > 64:
            raise ValueError("Invalid registry templates")
        seen = set()
        for template in templates:
            _keys(template, {"kind", "attributes", "unit", "support", "observations"})
            if not isinstance(template["kind"], str):
                raise ValueError("Invalid numeric template kind")
            size = {"pair": 2, "dimensions": 3}.get(template["kind"])
            order = template["attributes"]
            if (size is None or not isinstance(order, list) or len(order) != size
                    or any(not isinstance(a, str) or a not in attributes for a in order) or len(set(order)) != size):
                raise ValueError("Invalid numeric template")
            _literal(template["unit"], 32)
            if any(attributes[a]["kind"] != "number" or attributes[a]["unit"] != template["unit"] for a in order):
                raise ValueError("Template unit does not match attributes")
            if (type(template["support"]) is not int or type(template["observations"]) is not int
                    or not provenance["min_template_support"] <= template["support"] <= template["observations"]
                    or template["support"] / template["observations"] < 0.95):
                raise ValueError("Insufficient template support/agreement")
            key = (template["kind"], template["unit"].casefold())
            if key in seen:
                raise ValueError("Ambiguous numeric template roles")
            seen.add(key)
    return registry


def literal_pattern(value):
    return re.escape(value).replace(r"\ ", r"[^\S\n]+")


def template_pattern(kind, unit):
    size = {"pair": 2, "dimensions": 3}[kind]
    separator = r"\s*/\s*" if kind == "pair" else r"\s*[xх×]\s*"
    return re.compile(r"(?<![\w.,/+\-])" + separator.join(rf"(?P<n{i}>{NUMBER})" for i in range(size))
                      + r"\s*" + literal_pattern(unit) + r"(?!\w)", re.I)


class Registry:
    def __init__(self, config):
        self.config = config
        self.entries = config.get("category_registry", {}).get("categories", {})
        self._sources = {}

    def attributes(self, category_id):
        return tuple(self.config["categories"].get(category_id, ()))

    def spec(self, category_id, attribute):
        return self.entries.get(category_id, {}).get("attributes", {}).get(attribute)

    def unit(self, category_id, attribute):
        from goodsai.normalize import UNITS
        spec = self.spec(category_id, attribute)
        return spec["unit"] if spec else UNITS.get(attribute)

    def normalize(self, category_id, attribute, value, unit):
        from goodsai.normalize import UNITS, numeric
        spec = self.spec(category_id, attribute)
        if not spec:
            return numeric(attribute, value, unit, self.config["numeric_bounds"]) if attribute in UNITS else value
        if unit != spec["unit"]:
            raise ValueError("Registry unit mismatch")
        if spec["kind"] == "number":
            # New numeric values may generalize; only literal unit/decimal normalization.
            return decimal_value(value)
        owners = {v.casefold(): v for v in spec["values"]}
        try:
            return owners[clean(value).casefold()]
        except KeyError as exc:
            raise ValueError("Registry enum outside train dictionary") from exc

    def normalize_reference(self, category_id, attribute, value, unit):
        """Validate reference independently of the inference/train vocabulary.

        Human labels outside train must count as false negatives, not disappear
        or fail evaluation. This does not expand the extraction dictionary.
        """
        spec = self.spec(category_id, attribute)
        if spec and spec["kind"] == "enum":
            if unit != spec["unit"] or not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid reference value/unit")
            owners = {v.casefold(): v for v in spec["values"]}
            return owners.get(clean(value).casefold(), clean(value))
        return self.normalize(category_id, attribute, value, unit)

    def supported(self, category_id, attribute, value, evidence):
        spec = self.spec(category_id, attribute)
        if not spec:
            return True
        # Re-extract through the same finite grammar; a number elsewhere in the
        # evidence or an unrelated dictionary word is insufficient.
        from goodsai.contracts import Product
        product = Product("evidence-check", category_id, evidence)
        if category_id not in self._sources:
            self._sources[category_id] = LearnedRules(self.config, category_id=category_id)
        return any(c.attribute == attribute and c.value == value for c in self._sources[category_id].candidates(product))


class LearnedRules:
    def __init__(self, config, *, category_id=None):
        self.config = config
        self.registry = Registry(config)
        self.compiled = {}
        for category, entry in self.registry.entries.items():
            if category_id is not None and category != category_id:
                continue
            fields = []
            for attribute, spec in entry["attributes"].items():
                label = literal_pattern(spec["name"])
                if spec["kind"] == "number":
                    value = NUMBER + (r"\s*" + literal_pattern(spec["unit"]) if spec["unit"] else "")
                else:
                    value = "(?:" + "|".join(literal_pattern(v) for v in sorted(spec["values"], key=lambda x: (-len(x), x))) + ")"
                # Full labeled value only, never a prefix of an unknown shade/value.
                pattern = re.compile(r"(?:^|(?<=[;\n]))[^\S\n]*(?:" + label + r")[^\S\n]*[:=][^\S\n]*(?P<v>" + value
                                     + r")(?=[^\S\n]*(?:[;\n]|$))", re.I)
                fields.append((attribute, spec, pattern))
            self.compiled[category] = (fields, [(t, template_pattern(t["kind"], t["unit"])) for t in entry["templates"]])

    def candidates(self, product):
        fields, templates = self.compiled.get(product.category_id, ([], []))
        for field in ("title", "description"):
            source = getattr(product, field) or ""
            text, positions = visible_view(source)
            matches = []
            for attribute, spec, pattern in fields:
                for match in pattern.finditer(text):
                    raw = match["v"]
                    if spec["kind"] == "number":
                        raw = re.match(NUMBER, raw)[0]
                    value = self.registry.normalize(product.category_id, attribute, raw, spec["unit"])
                    matches.append((attribute, value, spec["unit"], match, "registry.key-value.v1"))
            for template, pattern in templates:
                for match in pattern.finditer(text):
                    for i, attribute in enumerate(template["attributes"]):
                        matches.append((attribute, decimal_value(match[f"n{i}"]), template["unit"], match, "registry." + template["kind"] + ".v1"))
            for attribute, value, unit, match, rule_id in matches:
                start, end = match.span()
                # Conservative clause guard supplements category-independent verifier.
                clause = max(text.rfind(c, 0, start) for c in ";\n.!?") + 1
                if BAD.search(text[clause:start]) or re.search(r"(?:[~≈+\-]|\d\s*[-–—])\s*$", text[clause:start]):
                    continue
                if any(pos is None for pos in positions[start:end]):
                    continue
                first, last = positions[start][0], positions[end - 1][1]
                fragment = source[first:last]
                # Reject hidden/block crossings even for malformed HTML.
                try:
                    visible_span(source, first, last)
                except ValueError:
                    continue
                yield Candidate(attribute, value, unit, field, first, last, fragment,
                                self.config["rule_scores"]["quantity"], rule_id)
