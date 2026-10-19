"""Prepare private silver inputs without opening the protected test for analysis."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from goodsai.contracts import load_config
from goodsai.data import digest, read_jsonl
from goodsai.runtime import identity
from goodsai.silver_prepare import MAPPING, SEED, VERSION, assemble, dump, unique, write_rows
from goodsai.silver_support import VERSION as SUPPORT_VERSION
from scripts.research.audit_splits import exposure_ids, verify as verify_audit


def prepare(args):
    import pyarrow.parquet as pq

    output = args.output_dir.resolve()
    if output.exists() or (ROOT / "outputs").resolve() not in output.parents:
        raise ValueError("new_private_outputs_directory_required")
    verify_audit(args.audit)
    audit = json.loads((args.audit / "audit.summary.json").read_text(encoding="utf-8"))
    expected_input = [x["sha256"] for x in audit["sources"] if x["file"] == args.input.name]
    if expected_input != [digest(args.input)]:
        raise ValueError("input_not_bound_to_audit")
    sources = {"input": args.input, "catalog": args.catalog, "audit": args.audit / "audit.summary.json",
               "reserve": args.reserve, "protocol": ROOT / "docs/research/silver_evaluation_protocol.md"}
    for index, path in enumerate(args.exposure_source):
        sources[f"exposure_{index}"] = path
    if args.traffic:
        sources["traffic"] = args.traffic
    fingerprints = {name: digest(path) for name, path in sources.items()}
    members = unique(read_jsonl(args.audit / "membership.jsonl"))
    exposed = set().union(*(exposure_ids(p) for p in args.exposure_source))
    reserve = unique(read_jsonl(args.reserve))
    if any(row.get("text_materialized") is not False or row.get("split") != "test_reserved" for row in reserve.values()):
        raise ValueError("invalid_metadata_only_reserve")
    # Bind the reserve to its existing preparation. Merely naming a new file
    # reserve must never silently bypass audited protection.
    if not any(x["sha256"] == fingerprints["reserve"] for x in audit["sources"]):
        raise ValueError("reserve_not_bound_to_audit")
    config = load_config(args.config)
    traffic = Counter() if args.traffic else None
    if args.traffic:
        for batch in pq.ParquetFile(args.traffic).iter_batches(columns=["sku_id"], batch_size=65536):
            for row in batch.to_pylist():
                if row["sku_id"] is not None:
                    traffic[str(row["sku_id"])] += 1
    catalog, universe, category_traffic = {}, Counter(), Counter()
    for batch in pq.ParquetFile(args.catalog).iter_batches(batch_size=4096):
        for row in batch.to_pylist():
            cats = json.loads(row["category_ids"])
            if not isinstance(cats, list) or len(cats) != 1:
                raise ValueError("single_category_projection_required")
            cat, sku = str(cats[0]), str(row["sku_id"])
            universe[cat] += 1
            category_traffic[cat] += traffic.get(sku, 0) if traffic is not None else 0
            if sku in members and members[sku]["split"] in {"development", "validation"} and not members[sku]["quarantine_reasons"]:
                if sku in catalog:
                    raise ValueError("duplicate_catalog_sku")
                catalog[sku] = row | {"category_id": cat, "params": json.loads(row["params_json"]) if row["params_json"] else []}
    inputs, refs, metadata, counts = assemble(read_jsonl(args.input), catalog, members, config,
        protected_ids=reserve, exposed_ids=exposed, traffic=traffic)
    # No report of private IDs or text is written to stdout/public artifacts.
    output.mkdir(parents=True)
    dump(output / "policy.json", {"version": VERSION, "seed": SEED, "mapping": MAPPING,
        "support_version": SUPPORT_VERSION, "sources": fingerprints, "runtime": identity(config),
        "config": config, "baseline_sha": "977c5ed", "independence": "development_feedback"})
    write_rows(output / "input.jsonl", inputs)
    write_rows(output / "reference.jsonl", refs)
    write_rows(output / "metadata.jsonl", metadata)
    import hashlib
    by_sku = {p["sku_id"]: p for p in inputs}
    development = sorted((m for m in metadata if m["original_split"] == "development"),
        key=lambda m: hashlib.sha256((SEED + ":llm:" + m["sku_id"]).encode()).hexdigest())
    screening, screening_families = [], set()
    # Round-robin by category, one card/family; selection never reads predictions.
    by_category = defaultdict(list)
    for m in development:
        by_category[m["category_id"]].append(m)
    while len(screening) < 200 and any(by_category.values()):
        for category in sorted(by_category):
            while by_category[category]:
                m = by_category[category].pop(0)
                if m["family_id"] not in screening_families:
                    screening.append(by_sku[m["sku_id"]])
                    screening_families.add(m["family_id"])
                    break
            if len(screening) >= 200:
                break
    write_rows(output / "llm_screening.input.jsonl", screening)
    # Fixed audit sample, independent of predictions. Empty human fields never
    # turn matcher output into a human-reviewed label.
    review = []
    by_state = defaultdict(list)
    for product, reference, meta in zip(inputs, refs, metadata):
        if meta["original_split"] != "development":
            continue
        for label in reference["attributes"]:
            if label["status"] == "known":
                by_state[label["support"]["state"]].append((product, label))
    for state, pairs in sorted(by_state.items()):
        pairs.sort(key=lambda pair: hashlib.sha256((SEED + pair[0]["sku_id"] + pair[1]["attribute"]).encode()).hexdigest())
        for product, label in pairs[:20]:
            review.append({"review_id": f"S{len(review)+1:03d}", "product": product, "catalog_label": label,
                           "human_support": None, "human_correctness": None, "reviewer": None})
    write_rows(output / "support_review.blank.jsonl", review)
    # Handoff obeys CONF-003 train adapter: no validation/test text in train.
    fit_ids = {m["sku_id"] for m in metadata if m["role"] == "fit"}
    refs_by_sku = {r["sku_id"]: r for r in refs}
    train = []
    for product in inputs:
        sku = product["sku_id"]
        if sku in fit_ids:
            params = []
            for label in refs_by_sku[sku]["attributes"]:
                if label["status"] == "known":
                    params.append({"name": label["attribute"], "value": label["value"], "unit": label["unit"]})
            train.append({k: product[k] for k in ["sku_id", "category_id", "title", "description"]} | {"params": params})
    write_rows(output / "train.jsonl", train)
    train_hash = digest(output / "train.jsonl")
    dump(output / "train.split.json", {"schema_version": "goodsai-train-split-1", "train_sha256": train_hash,
        "train_sku_ids": sorted(fit_ids), "validation_sku_ids": sorted(m["sku_id"] for m in metadata if m["role"] != "fit"),
        "test_sku_ids": sorted(sku for sku, m in members.items() if m["split"] == "test_reserved")})
    if traffic is not None:
        train_traffic = Counter()
        for p in train:
            train_traffic[p["category_id"]] += traffic.get(p["sku_id"], 0)
        dump(output / "train.traffic.json", {"schema_version": "goodsai-category-traffic-1", "scope": "train",
            "train_sha256": train_hash, "category_traffic": dict(train_traffic)})
    top = sorted(universe, key=lambda cat: (-category_traffic[cat], cat))[:30] if traffic is not None else []
    seller_roles = defaultdict(set)
    brand_roles = defaultdict(set)
    for m in metadata:
        if m["seller"]:
            seller_roles[m["seller"]].add(m["role"])
        if m["brand"]:
            brand_roles[m["brand"]].add(m["role"])
    manifest = {"version": VERSION, "reference_kind": "catalog_silver", "source_sha256": fingerprints,
        "counts": counts, "rows": len(inputs), "independent_quality": None,
        "family_groups": len({m["family_id"] for m in metadata}),
        "protected_reserve_rows": len(reserve), "protected_text_exported": False,
        "configured_categories": sorted(config["categories"]), "universe_rows": sum(universe.values()),
        "universe_categories": len(universe), "universe_configured_rows": sum(universe[c] for c in config["categories"]),
        "top30": [{"category_id": c, "rows": universe[c], "traffic_observations": category_traffic[c],
                   "runtime_supported": c in config["categories"]} for c in top],
        "traffic_kind": "query_clicks_row_count" if traffic is not None else "unavailable",
        "seller_role_crossings": sum(len(s) > 1 for s in seller_roles.values()),
        "brand_role_crossings": sum(len(s) > 1 for s in brand_roles.values()),
        "seller_disjoint": False, "brand_disjoint": False,
        "exposure_history": "supplied_ledgers_plus_frozen_audit_not_proof_of_completeness",
        "support_review_status": "pending_human_audit",
        "llm_screening_cards": len(screening),
        "preparation_tools": {str(p.relative_to(ROOT)): digest(p) for p in [
            Path(__file__), ROOT / "src/goodsai/silver_prepare.py", ROOT / "src/goodsai/silver_support.py",
            ROOT / "src/goodsai/text.py", ROOT / "src/goodsai/normalize.py"]},
        "artifacts": {p.name: digest(p) for p in sorted(output.iterdir())}}
    for name, path in sources.items():
        if digest(path) != fingerprints[name]:
            raise ValueError("source_changed_during_preparation")
    dump(output / "manifest.json", manifest)
    return {k: manifest[k] for k in ["version", "rows", "counts", "family_groups", "protected_reserve_rows"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/processed/e1/pilot.jsonl")
    parser.add_argument("--catalog", type=Path, default=ROOT / "outputs/eda/catalog_skus.parquet")
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--reserve", type=Path, default=ROOT / "data/gold/e1/m2/v2/test_reserve.blank.jsonl")
    parser.add_argument("--exposure-source", type=Path, action="append", required=True)
    parser.add_argument("--traffic", type=Path)
    parser.add_argument("--config")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), ensure_ascii=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("silver preparation failed: " + type(exc).__name__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
