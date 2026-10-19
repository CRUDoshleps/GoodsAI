"""Private catalog-reference preparation on a frozen, audited E1 partition."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from goodsai.contracts import Product
from goodsai.data import digest, read_jsonl, write_line
from goodsai.silver_support import canonical, support

VERSION = "catalog-silver-1"
SEED = "goodsai-silver-20261019-v1"
# Explicit source fields only; no fuzzy field selection or unit inference.
MAPPING = {
    "761": {
        "brand": [], "model": ["Модель_search"],
        "storage_gb": ["Встроенная память (ROM)_search", "Встроенная память"],
        "ram_gb": ["Оперативная память (RAM)_search", "Оперативная память"],
        "screen_inches": ["Диагональ_search", "Диагональ экрана"],
        "battery_mah": ["Емкость аккумулятора_search", "Емкость аккумулятора"],
        "color": ["Цвет_search", "Цвет"],
    },
    "482": {
        "brand": [], "model": ["Модель_search"],
        "capacity_l": ["Объем_search", "Объем воды"],
        "power_w": ["Потребляемая мощность_search", "Потребляемая мощность"],
        "color": ["Цвет_search", "Цвет"],
    },
}


def dump(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write("\n")


def write_rows(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            write_line(stream, row)


def unique(rows):
    result = {}
    for row in rows:
        key = row.get("sku_id")
        if not isinstance(key, str) or not key or key in result:
            raise ValueError("duplicate_or_invalid_sku")
        result[key] = row
    return result


def role(family, split):
    if split == "validation":
        return "development_feedback"
    bucket = int(hashlib.sha256((SEED + family).encode()).hexdigest(), 16) % 100
    return "fit" if bucket < 70 else "calibration" if bucket < 80 else "diagnostic"


def labels(catalog, config):
    cat = catalog["category_id"]
    params = catalog.get("params", [])
    if not isinstance(params, list) or any(not isinstance(x, dict) for x in params):
        raise ValueError("invalid_catalog_params")
    result = []
    for attr in config["categories"][cat]:
        entries = [(p.get("@name"), p.get("#text"), p.get("@unit")) for p in params
                   if p.get("@name") in MAPPING.get(cat, {}).get(attr, [])]
        if attr == "brand":
            entries += [("vendor", catalog.get("vendor"), None)]
        if attr == "model":
            entries += [("model", catalog.get("model"), None)]
        normalized, rejected, provenance = set(), [], []
        for name, raw, unit in entries:
            if raw in (None, ""):
                continue
            provenance.append({"field": name, "raw_value": raw, "raw_unit": unit})
            try:
                normalized.add(canonical(attr, raw, unit, config))
            except ValueError as exc:
                rejected.append(str(exc))
        status = "known" if len(normalized) == 1 and not rejected else "conflict" if len(normalized) > 1 else "unknown"
        value, unit = next(iter(normalized)) if status == "known" else (None, None)
        result.append({"attribute": attr, "status": status, "value": value, "unit": unit,
                       "provenance": provenance, "reasons": sorted(set(rejected))})
    return result


def assemble(products, catalog, members, config, protected_ids=(), exposed_ids=(), traffic=None):
    """Pure preparation for synthetic checks and the real verified adapter.

    Does not resample old partitions. A protected/exposed family propagates to
    every member, even when its identity was supplied only on one SKU.
    """
    protected_ids, exposed_ids = set(protected_ids), set(exposed_ids)
    if protected_ids - members.keys() or exposed_ids - members.keys():
        raise ValueError("ledger_identity_outside_audited_population")
    protected = {members[s]["family_id"] for s in protected_ids}
    exposed = {members[s]["family_id"] for s in exposed_ids}
    family_splits = defaultdict(set)
    for m in members.values():
        if (not isinstance(m.get("family_id"), str) or not m["family_id"]
                or m.get("split") not in {"development", "validation", "test_reserved"}
                or not isinstance(m.get("quarantine_reasons"), list)):
            raise ValueError("invalid_audited_membership")
        if not m["quarantine_reasons"]:
            family_splits[m["family_id"]].add(m["split"])
    if any(len(s) > 1 for s in family_splits.values()):
        raise ValueError("cross_split_family")
    inputs, references, metadata, counts = [], [], [], Counter()
    available = unique(products)
    if available.keys() != members.keys():
        raise ValueError("audited_input_population_mismatch")
    for sku, member in sorted(members.items()):
        family, split = member["family_id"], member["split"]
        if member["quarantine_reasons"] or split not in {"development", "validation"} or family in protected:
            counts["excluded_protected_or_quarantine"] += 1
            continue
        if family in exposed and split != "development":
            counts["excluded_new_exposure_feedback_family"] += 1
            continue
        product = Product.from_dict(available[sku])
        if product.category_id not in config["categories"]:
            counts["excluded_unconfigured_category"] += 1
            continue
        source = catalog.get(sku)
        if source is None or source["category_id"] != product.category_id:
            raise ValueError("catalog_join_mismatch")
        refs = labels(source, config)
        for label in refs:
            label["support"] = support(product, label["attribute"], label["value"], label["unit"], config) if label["status"] == "known" else {"state": "unknown", "reason": "reference_not_known", "evidence": None}
        weight = None if traffic is None else traffic.get(sku, 0)
        if weight is not None and (type(weight) not in (float, int) or not math.isfinite(weight) or weight < 0):
            raise ValueError("invalid_traffic_weight")
        assigned = role(family, split)
        meta = {"sku_id": sku, "category_id": product.category_id, "family_id": family,
                "original_split": split, "role": assigned, "evaluation_role": "development_feedback",
                "exposed": bool(member.get("family_exposed")) or family in exposed,
                "traffic": weight, "seller": source.get("seller"), "brand": source.get("vendor"),
                "text_slice": "with_description" if product.description else "title_only"}
        inputs.append(product.as_dict())
        references.append({"sku_id": sku, "category_id": product.category_id,
                           "reference_kind": "catalog_silver", "attributes": refs})
        metadata.append(meta)
        counts[assigned] += 1
    if not inputs:
        raise ValueError("empty_eligible_population")
    return inputs, references, metadata, dict(counts)


def verify_bundle(bundle):
    bundle = Path(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or manifest.get("reference_kind") != "catalog_silver":
        raise ValueError("silver_manifest_version")
    required = {"policy.json", "input.jsonl", "reference.jsonl", "metadata.jsonl", "train.jsonl", "train.split.json", "support_review.blank.jsonl", "llm_screening.input.jsonl"}
    if not required <= manifest["artifacts"].keys():
        raise ValueError("missing_silver_artifact")
    if {p.name for p in bundle.iterdir()} != set(manifest["artifacts"]) | {"manifest.json"}:
        raise ValueError("silver_artifact_inventory_mismatch")
    for name, checksum in manifest["artifacts"].items():
        if "/" in name or "\\" in name or Path(name).name != name or (bundle / name).is_symlink() or digest(bundle / name) != checksum:
            raise ValueError("silver_artifact_hash_mismatch")
    return manifest
