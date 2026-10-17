"""Strict text-only boundary and output invariants, independent of data loaders."""
from dataclasses import dataclass
from importlib.resources import files
import json
import math
from pathlib import Path

from goodsai.normalize import UNITS, numeric


def load_config(path: str | None = None) -> dict:
    text = Path(path).read_text(encoding="utf-8") if path else files("goodsai").joinpath("baseline.json").read_text(encoding="utf-8")
    config = json.loads(text)
    if config.get("schema_version") != "0.1" or not config.get("categories"):
        raise ValueError("Unsupported configuration")
    return config


@dataclass(frozen=True)
class Product:
    sku_id: str
    category_id: str | None
    title: str
    description: str | None = None
    source_flags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, row: dict) -> "Product":
        allowed = {"schema_version", "sku_id", "category_id", "title", "description", "seller_attributes", "source_flags"}
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValueError("Unknown input fields: text-only input must not contain targets or metadata")
        if row.get("schema_version") != "0.1":
            raise ValueError("schema_version must be 0.1")
        if not isinstance(row.get("sku_id"), str) or not row["sku_id"].strip():
            raise ValueError("sku_id must be a nonempty string")
        if row.get("category_id") is not None and not isinstance(row["category_id"], str):
            raise ValueError("category_id must be a string or null")
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            raise ValueError("title must be a nonempty string")
        if row.get("description") is not None and not isinstance(row["description"], str):
            raise ValueError("description must be a string or null")
        if row.get("seller_attributes", []) != []:
            raise ValueError("Seller attributes are forbidden in text-only E1")
        flags = row.get("source_flags", [])
        if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
            raise ValueError("source_flags must be a list of strings")
        return cls(row["sku_id"], row.get("category_id"), row["title"], row.get("description"), tuple(flags))

    def as_dict(self) -> dict:
        return {"schema_version": "0.1", "sku_id": self.sku_id, "category_id": self.category_id,
                "title": self.title, "description": self.description,
                "seller_attributes": [], "source_flags": list(self.source_flags)}


def validate_prediction(row: dict, config: dict, product: Product | None = None) -> None:
    if row.get("schema_version") != "0.1" or not isinstance(row.get("sku_id"), str):
        raise ValueError("Invalid prediction identity/schema")
    if row.get("status") not in {"processed", "unsupported_category", "invalid_input", "error"}:
        raise ValueError("Invalid prediction status")
    expected = config["categories"].get(row.get("category_id"), [])
    attrs = row.get("attributes")
    if not isinstance(attrs, list):
        raise ValueError("attributes must be a list")
    if row["status"] == "processed" and (not expected or [a.get("attribute") for a in attrs] != expected):
        raise ValueError("Each requested attribute must occur exactly once, in schema order")
    if row["status"] != "processed" and attrs:
        raise ValueError("Unprocessed records must not contain predictions")
    if product and (row["sku_id"], row.get("category_id")) != (product.sku_id, product.category_id):
        raise ValueError("Prediction identity changed")
    for a in attrs:
        if a.get("decision") == "abstain":
            if any(a.get(k) is not None for k in ["value", "unit", "confidence", "evidence"]) or not a.get("reason_codes"):
                raise ValueError("Abstention must be explicit and empty")
            continue
        if a.get("decision") != "review" or a.get("confidence_kind") != "heuristic":
            raise ValueError("Uncalibrated baseline can only return heuristic review candidates")
        score = a.get("confidence")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Invalid heuristic score")
        if not isinstance(a.get("value"), str) or not a["value"]:
            raise ValueError("Candidate value must be a nonempty string")
        if a.get("unit") != UNITS.get(a["attribute"]):
            raise ValueError("Candidate unit does not match schema")
        if a["attribute"] in UNITS and numeric(a["attribute"], a["value"], a["unit"]) != a["value"]:
            raise ValueError("Candidate number is not canonical")
        e = a.get("evidence", {})
        if (e.get("field") not in {"title", "description"} or type(e.get("start")) is not int
                or type(e.get("end")) is not int or not 0 <= e["start"] < e["end"]
                or not isinstance(e.get("text"), str) or not e["text"]):
            raise ValueError("Invalid evidence")
        if product:
            source = getattr(product, e["field"]) or ""
            if source[e["start"]:e["end"]] != e["text"]:
                raise ValueError("Evidence does not match original text")
