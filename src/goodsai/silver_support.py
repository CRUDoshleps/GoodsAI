"""Frozen, prediction-independent lexical support diagnostics, never runtime rules.

A match is not semantic proof. Unresolved roles/ownership stay unknown. Raw spans
are emitted privately for a human audit; no catalog value becomes an input hint.
"""
import re
import unicodedata

from goodsai.normalize import UNITS, number, numeric
from goodsai.text import visible_view

VERSION = "silver-support-1"
NUMBER = r"\d+(?:[.,]\d+)?"
UNIT_PATTERNS = {
    "storage_gb": r"TB|ТБ|GB|ГБ", "ram_gb": r"TB|ТБ|GB|ГБ",
    "screen_inches": r'inch(?:es)?|дюйм\w*|[\"″]',
    "battery_mah": r"mAh|мА\s*\*?\s*ч",
    "capacity_l": r"ml|мл|литр\w*|л|L", "power_w": r"kW|кВт|W|Вт",
}
ROLE = {
    "storage_gb": r"ROM|накопител\w*|встроенн\w*\s+памят\w*",
    "ram_gb": r"RAM|ОЗУ|оперативн\w*\s+памят\w*",
    "screen_inches": r"диагонал\w*|экран\w*",
    "battery_mah": r"аккумулятор\w*|батаре\w*",
    "capacity_l": r"об[ъь]ем\w*|вместимост\w*",
    "power_w": r"мощност\w*",
}


def fold(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").split())


def canonical(attribute, raw, unit, config):
    """Strict reference-only normalization. Missing numeric units are not inferred."""
    if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
        raise ValueError("unsupported_reference_value")
    text = str(raw).strip()
    if not text:
        raise ValueError("empty_reference_value")
    if attribute in UNITS:
        match = re.fullmatch(rf"\s*({NUMBER})\s*({UNIT_PATTERNS[attribute]})?\s*", text, re.I)
        if not match:
            raise ValueError("unsupported_numeric_reference")
        embedded = match[2]
        if unit is not None and not isinstance(unit, str):
            raise ValueError("invalid_reference_unit")
        declared = unit.strip() if unit else embedded
        if not declared or not re.fullmatch(UNIT_PATTERNS[attribute], declared, re.I):
            raise ValueError("unknown_reference_unit")
        if embedded and unit and fold(embedded) != fold(unit):
            raise ValueError("conflicting_reference_units")
        value = match[1]
        if attribute in {"storage_gb", "ram_gb"} and fold(declared) in {"tb", "тб"}:
            value, declared = str(number(value) * 1000), "GB"
        result = numeric(attribute, value, declared)
        return result, UNITS[attribute]
    if unit not in (None, ""):
        raise ValueError("unexpected_reference_unit")
    if attribute in {"brand", "color"}:
        dictionary = config["brands" if attribute == "brand" else "colors"]
        found = {key for key, aliases in dictionary.items() if fold(text) in {fold(x) for x in [key, *aliases]}}
        if len(found) == 1:
            return found.pop(), None
        # Unmapped brand names are still reference facts; colors require an
        # explicit dictionary normalization to compare with canonical outputs.
        if attribute == "color":
            raise ValueError("unmapped_reference_color")
    return " ".join(text.split()), None


def _context_uncertain(text, start):
    prefix = text[max(0, start - 45):start]
    return bool(re.search(r"(?:\bне|\bбез|\bдо|\bот|\bдля|совместим\w*)\s+(?:\w+\s+){0,2}$", prefix, re.I))


def support(product, attribute, value, unit, config):
    """Tri-state support; literal occurrence without resolved role is unknown."""
    found, uncertain = [], []
    for field in ("title", "description"):
        raw = getattr(product, field) or ""
        text, positions = visible_view(raw)
        if attribute in UNITS:
            matches = re.finditer(rf"(?<![\w.,])({NUMBER})\s*({UNIT_PATTERNS[attribute]})(?!\w)", text, re.I)
            for match in matches:
                try:
                    observed, _ = canonical(attribute, match[1], match[2], config)
                except ValueError:
                    continue
                if observed != value:
                    continue
                prefix = text[max(0, match.start() - 50):match.start()]
                role = re.search(rf"(?:{ROLE[attribute]})\s*[:=—-]?\s*$", prefix, re.I)
                # Units uniquely identify these attributes; role is mandatory
                # for memory and screen, where unrelated numbers are common.
                role_ok = bool(role) or attribute in {"capacity_l", "power_w", "battery_mah"}
                (found if role_ok else uncertain).append((field, raw, positions, match.start(), match.end(), text))
        else:
            aliases = [value]
            if attribute in {"brand", "color"}:
                aliases += config["brands" if attribute == "brand" else "colors"].get(value, [])
            for alias in sorted(set(aliases)):
                pattern = r"(?<!\w)" + r"\s+".join(re.escape(x) for x in alias.split()) + r"(?!\w)"
                for match in re.finditer(pattern, text, re.I):
                    found.append((field, raw, positions, match.start(), match.end(), text))
    valid = []
    for field, raw, positions, start, end, text in found:
        if _context_uncertain(text, start):
            uncertain.append((field, raw, positions, start, end, text))
            continue
        span = positions[start:end]
        if not span or any(x is None for x in span):
            continue
        a, b = span[0][0], span[-1][1]
        valid.append({"field": field, "start": a, "end": b, "text": raw[a:b]})
    if valid:
        return {"state": "supported", "reason": "lexical_role_unit_match", "evidence": valid[0]}
    if uncertain:
        return {"state": "unknown", "reason": "literal_with_ambiguous_role_or_context", "evidence": None}
    return {"state": "unsupported", "reason": "no_match_under_frozen_matcher", "evidence": None}
