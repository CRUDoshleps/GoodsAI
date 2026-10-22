"""Strict text-only boundary and output invariants, independent of data loaders."""
from dataclasses import dataclass
import math

from goodsai.config import load_config
from goodsai.category_registry import Registry
from goodsai.normalize import model_name
from goodsai.text import visible_span


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


def validate_prediction(row: dict, config: dict, product: Product | None = None, *, registry=None) -> None:
    registry = Registry(config) if registry is None else registry
    if not isinstance(row, dict) or row.get("schema_version") != "0.1" or not isinstance(row.get("sku_id"), str):
        raise ValueError("Invalid prediction identity/schema")
    if not isinstance(row.get("status"), str) or row["status"] not in {"processed", "unsupported_category", "invalid_input", "error"}:
        raise ValueError("Invalid prediction status")
    if row.get("category_id") is not None and not isinstance(row["category_id"], str):
        raise ValueError("Invalid prediction category")
    expected = config["categories"].get(row.get("category_id"), [])
    attrs = row.get("attributes")
    if not isinstance(attrs, list) or any(not isinstance(a, dict) for a in attrs):
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
        if a.get("decision") not in {"review", "auto_accept"} or a.get("confidence_kind") != "heuristic":
            raise ValueError("Only heuristic review or explicitly approved storage pilot candidates are supported")
        score = a.get("confidence")
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Invalid heuristic score")
        if not isinstance(a.get("value"), str) or not a["value"]:
            raise ValueError("Candidate value must be a nonempty string")
        if a.get("unit") != registry.unit(row.get("category_id"), a["attribute"]):
            raise ValueError("Candidate unit does not match schema")
        if registry.normalize(row.get("category_id"), a["attribute"], a["value"], a["unit"]) != a["value"]:
            raise ValueError("Candidate number is not canonical")
        e = a.get("evidence", {})
        if (not isinstance(e, dict) or not isinstance(e.get("field"), str)
                or e["field"] not in {"title", "description"} or type(e.get("start")) is not int
                or type(e.get("end")) is not int or not 0 <= e["start"] < e["end"]
                or not isinstance(e.get("text"), str) or not e["text"]):
            raise ValueError("Invalid evidence")
        if product:
            source = getattr(product, e["field"]) or ""
            if e["end"] > len(source) or source[e["start"]:e["end"]] != e["text"]:
                raise ValueError("Evidence does not match original text")
            if registry.spec(product.category_id, a["attribute"]) and not registry.supported(product.category_id, a["attribute"], a["value"], visible_span(source, e["start"], e["end"])):
                raise ValueError("Registry value is not supported by evidence grammar")
            if a["attribute"] == "model" and model_name(visible_span(source, e["start"], e["end"])) != a["value"]:
                raise ValueError("Model value is not the approved normalization of visible evidence")
        if a["decision"] == "auto_accept":
            from goodsai.storage_acceptance import validate_accepted
            validate_accepted(row, a, config, product)
