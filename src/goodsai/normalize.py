"""Canonical decimal values. No guesses from product model knowledge."""
from decimal import Decimal, InvalidOperation
import re
from goodsai.config import default_bounds

UNITS = {"storage_gb": "GB", "ram_gb": "GB", "screen_inches": "inch",
         "battery_mah": "mAh", "capacity_l": "L", "power_w": "W"}
BOUNDS = default_bounds()  # Compatibility default; custom inference passes its own bounds.
NUMBER = r"\d{1,4}(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,3})?"


def model_name(visible: str) -> str:
    """Only whitespace changes are approved for explicit commercial names."""
    return " ".join(visible.split())


def number(value: str) -> Decimal:
    cleaned = re.sub(r"[ \u00a0\u202f]", "", value).replace(",", ".")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if not result.is_finite():
        raise ValueError("Nonfinite number")
    return result


def numeric(attribute: str, raw: str, raw_unit: str, bounds: dict | None = None) -> str:
    value = number(raw)
    unit = raw_unit.casefold().replace(" ", "")
    if attribute == "capacity_l" and unit in {"мл", "ml"}:
        value /= 1000
    if attribute == "power_w" and unit in {"квт", "kw"}:
        value *= 1000
    low, high = (BOUNDS if bounds is None else bounds)[attribute]
    if not Decimal(str(low)) <= value <= Decimal(str(high)):
        raise ValueError("Outside category bounds")
    if attribute in {"storage_gb", "ram_gb", "battery_mah"} and value != value.to_integral_value():
        raise ValueError("Expected an integral capacity")
    return format(value.normalize(), "f")
