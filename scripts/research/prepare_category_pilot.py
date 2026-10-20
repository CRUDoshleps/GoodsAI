"""Prepare a private CONF-004 train/contract draft, never run extraction.

Reuses an existing safe catalog projection, EVAL-002 fingerprints and registry
builder. The proposal does not resolve #5/#10/#44 or authorize inference.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/research"))
from audit_splits import norm, sha, verify as verify_audit
from compare_silver_baseline import private_output
from goodsai.category_registry import clean
from goodsai.data import digest, read_jsonl
from goodsai.learn_categories import publish
from goodsai.silver_prepare import dump, write_rows

# Existing EDA retained params for these three real categories. Fixed before
# predictions; no category replacement or attribute tuning against outputs.
FIELDS = {
    "987": ["Оперативная память (RAM)_search", "Общий объем накопителя_search",
            "Диагональ экрана_search", "Материал корпуса_search", "Цвет_search"],
    "1682": ["Диагональ_search", "Технология экрана_search", "Цвет_search", "Частота обновления_search"],
    "1263": ["Диагональ_search", "Частота обновления_search", "Тип матрицы_search", "Цвет_search"],
}


def project_params(params, names, counts):
    grouped = defaultdict(set)
    invalid = set()
    if not isinstance(params, list):
        counts["invalid_param_container"] += 1
        return []
    for param in params:
        if not isinstance(param, dict) or param.get("@name") not in names:
            continue
        name, value, unit = param["@name"], param.get("#text"), param.get("@unit")
        if (not isinstance(value, str) or not clean(value) or len(clean(value)) > 256
                or (unit is not None and (not isinstance(unit, str) or not clean(unit) or len(clean(unit)) > 32))):
            counts["invalid_param_literal"] += 1
            invalid.add(name)
            continue
        grouped[name].add((clean(value), clean(unit) if unit is not None else None))
    result = []
    for name, values in sorted(grouped.items()):
        if len(values) != 1 or name in invalid:
            counts["conflicting_param_name_excluded"] += 1
            continue
        value, unit = next(iter(values))
        result.append({"name": name, "value": value, "unit": unit})
    return result


def run(args):
    import pyarrow.parquet as pq
    if not 30 <= args.max_per_category <= 1000:
        raise ValueError("pilot_training_cap_outside_supported_range")
    verify_audit(args.audit)
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    source_paths = {"catalog": args.catalog, "profile": args.profile,
                    "audit": args.audit / "audit.summary.json"}
    if args.traffic:
        expected = json.loads((ROOT / "reports/run_stats.json").read_text(encoding="utf-8"))["provenance"]["sources"]["traffic"]
        if digest(args.traffic) != expected:
            raise ValueError("existing_traffic_source_fingerprint_mismatch")
        source_paths["traffic"] = args.traffic
    hashes = {k: digest(p) for k, p in source_paths.items()}
    output = private_output(args.output_dir)
    dump(output / "selection.freeze.json", {"categories_and_source_fields": FIELDS,
        "sources_sha256": hashes, "max_train_per_category": args.max_per_category,
        "selection": "one_per_normalized_title_family_sorted_by_hash_before_any_predictions",
        "inference": "forbidden_pending_contract", "driver_sha256": digest(Path(__file__)),
        "independent_quality": None, "family_limit": "exact_normalized_title_only_near_family_review_pending"})
    members = {p["sku_id"]: p for p in read_jsonl(args.audit / "membership.jsonl")}
    protected_titles = {p["normalized_title_sha256"] for p in read_jsonl(args.audit / "fingerprints.jsonl")
                        if "normalized_title_sha256" in p}
    candidates = defaultdict(dict)
    counts = Counter()
    for batch in pq.ParquetFile(args.catalog).iter_batches(
            columns=["sku_id", "category_ids", "title", "params_json"], batch_size=4096):
        for source in batch.to_pylist():
            cats = json.loads(source["category_ids"])
            if len(cats) != 1 or str(cats[0]) not in FIELDS:
                continue
            cat, sku, title = str(cats[0]), str(source["sku_id"]), source["title"]
            counts["source_rows:" + cat] += 1
            if sku in members or not isinstance(title, str) or not title.strip() or len(title) > 32768:
                counts["excluded_identity_or_title"] += 1
                continue
            family = sha(norm(title))
            if family in protected_titles:
                counts["excluded_existing_E1_title_family"] += 1
                continue
            params = project_params(json.loads(source["params_json"] or "null"), FIELDS[cat], counts)
            if not params:
                counts["without_scoped_train_labels"] += 1
                continue
            row = {"sku_id": sku, "category_id": cat, "title": title, "description": None, "params": params}
            previous = candidates[cat].get(family)
            if previous is None or sku < previous["sku_id"]:
                candidates[cat][family] = row
    selected, family_rows = [], []
    for cat in sorted(FIELDS):
        ordered = sorted(candidates[cat], key=lambda f: sha("conf004-20261020:" + f))[:args.max_per_category]
        if len(ordered) < 30:
            raise ValueError("insufficient_preselected_category_train_support")
        for family in ordered:
            row = candidates[cat][family]
            selected.append(row)
            family_rows.append({"sku_id": row["sku_id"], "family_id": family, "role": "train"})
    write_rows(output / "train.jsonl", selected)
    write_rows(output / "train.families.jsonl", family_rows)
    train_hash = digest(output / "train.jsonl")
    dump(output / "train.split.json", {"schema_version": "goodsai-train-split-1", "train_sha256": train_hash,
        "train_sku_ids": [p["sku_id"] for p in selected],
        "validation_sku_ids": sorted(s for s, m in members.items() if m["split"] == "validation"),
        "test_sku_ids": sorted(s for s, m in members.items() if m["split"] == "test_reserved")})
    registry = None
    if args.traffic:
        categories = {p["sku_id"]: p["category_id"] for p in selected}
        traffic = Counter({cat: 0 for cat in FIELDS})
        for batch in pq.ParquetFile(args.traffic).iter_batches(columns=["sku_id"], batch_size=65536):
            for source in batch.to_pylist():
                cat = categories.get(str(source["sku_id"]))
                if cat:
                    traffic[cat] += 1
        dump(output / "train.traffic.json", {"schema_version": "goodsai-category-traffic-1", "scope": "train",
            "train_sha256": train_hash, "category_traffic": dict(traffic)})
        registry = publish(output / "train.jsonl", output / "train.split.json", output / "train.traffic.json",
                           output / "draft-registry", top_k=3, fill_threshold=.5, min_template_support=3)
    names = {str(c["id"]): c["name"] for c in profile["category_counts"]}
    report = {"status": "private_train_and_contract_draft_only", "inference": "not_run", "quality": None,
        "categories": [{"id": c, "name": names[c], "train_rows": sum(p["category_id"] == c for p in selected),
                        "proposed_source_fields": FIELDS[c]} for c in sorted(FIELDS)],
        "counts": dict(counts), "registry_learning": registry, "sources_sha256": hashes,
        "default_enable": False, "requires": ["#5/#10/#44 acceptance", "owner mapping/units/required fields decision",
        "near-family review beyond exact titles", "separate approved evaluation input/reference before real inference"]}
    dump(output / "pilot.plan.json", report)
    verify_audit(args.audit)
    if any(digest(source_paths[k]) != value for k, value in hashes.items()):
        raise ValueError("pilot_sources_changed")
    dump(output / "manifest.json", {"artifacts": {p.relative_to(output).as_posix(): digest(p)
        for p in sorted(output.rglob("*")) if p.is_file()}})
    return {"status": report["status"], "categories": report["categories"], "registry_learning": registry}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("catalog", "profile", "audit", "output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--traffic", type=Path)
    p.add_argument("--max-per-category", default=300, type=int)
    print(json.dumps(run(p.parse_args()), ensure_ascii=False))


if __name__ == "__main__":
    main()
