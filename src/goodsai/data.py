"""Bounded preparation from the existing trusted EDA projection, never raw pickle loading."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from goodsai.contracts import Product
from goodsai.storage import atomic_text as _atomic_text, prediction_snapshot


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"Blank JSONL record at line {line_no}")
            try:
                row = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid JSON at line {line_no}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL object required at line {line_no}")
            yield row


def check_output(path: Path, *inputs: Path):
    resolved = path.resolve()
    raw = (Path.cwd() / "data/raw").resolve()
    if resolved == raw or raw in resolved.parents or any(resolved == p.resolve() for p in inputs):
        raise ValueError("Output must not overwrite raw data or an input file")


@contextmanager
def atomic_text(path: Path):
    check_output(path)
    with _atomic_text(path) as stream:
        yield stream


def read_predictions(path: Path):
    """Locked, recovered and checksum-verified predictions; standalone JSONL also accepted."""
    with prediction_snapshot(path) as verified:
        yield from read_jsonl(verified)


def write_line(stream, row: dict):
    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def write_json(path: Path, value: dict):
    with atomic_text(path) as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def inventory_sources(raw: Path, output: Path) -> dict:
    check_output(output)
    if output.resolve() == raw.resolve() or raw.resolve() in output.resolve().parents:
        raise ValueError("Write the inventory outside the raw directory")
    entries = []
    for name in ["skus.pkl", "sku_desc.parquet", "query_clicks.parquet"]:
        path = raw / name
        entries.append({"file": name, "bytes": path.stat().st_size, "sha256": digest(path)})
    result = {"files": entries, "note": "Local fingerprints, not independent source authentication."}
    write_json(output, result)
    return result


def prepare(catalog: Path, descriptions: Path, raw_inventory: Path, output: Path, config: dict) -> dict:
    import pyarrow.parquet as pq

    check_output(output, catalog, descriptions, raw_inventory)
    raw_root = descriptions.parent.resolve()
    if output.resolve() == raw_root or raw_root in output.resolve().parents:
        raise ValueError("Prepared output must be outside the raw source directory")
    # Verify existing official sources; no code or data is downloaded or unpickled.
    inventory = json.loads(raw_inventory.read_text(encoding="utf-8"))
    fingerprints = {}
    for entry in inventory["files"]:
        path = descriptions.parent / entry["file"]
        if path.name not in {"skus.pkl", "sku_desc.parquet"}:
            continue
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Official source differs from the local inventory")
        fingerprints[path.name] = entry["sha256"]
    if set(fingerprints) != {"skus.pkl", "sku_desc.parquet"}:
        raise ValueError("Inventory must describe the official catalog and descriptions")
    if digest(descriptions) != fingerprints["sku_desc.parquet"]:
        raise ValueError("Description path does not match the verified source")
    if not catalog.is_file():
        raise ValueError("Trusted catalog projection is missing; run the documented research preparation first")
    selected = {}
    columns = ["sku_id", "category_ids", "title", "vendor", "model", "seller"]
    for batch in pq.ParquetFile(catalog).iter_batches(batch_size=4096, columns=columns, use_threads=False):
        for row in batch.to_pylist():
            categories = json.loads(row["category_ids"])
            if not isinstance(categories, list) or len(categories) != 1:
                raise ValueError("Expected a single catalog category")
            if categories[0] not in config["categories"]:
                continue
            sku = row["sku_id"]
            if sku in selected:
                raise ValueError("Duplicate catalog SKU")
            selected[sku] = row | {"category_id": categories[0]}
    if not selected:
        raise ValueError("No configured categories found in catalog projection")
    joined = {}
    for batch in pq.ParquetFile(descriptions).iter_batches(
            batch_size=4096, columns=["sku_id", "title", "description"], use_threads=False):
        for row in batch.to_pylist():
            sku = str(row["sku_id"])
            if sku in selected:
                if sku in joined:
                    raise ValueError("Duplicate description SKU")
                joined[sku] = row
    input_path = output / "pilot.jsonl"
    provenance_path = output / "provenance.jsonl"
    counts = {cat: {"rows": 0, "with_description": 0, "title_only": 0, "title_mismatch": 0}
              for cat in config["categories"]}
    with atomic_text(input_path) as inputs, atomic_text(provenance_path) as provenance:
        for sku, row in sorted(selected.items()):
            desc = joined.get(sku)
            has_desc = bool(desc and desc["description"] and desc["description"].strip())
            flags = [] if has_desc else ["missing_description"]
            mismatch = bool(desc and desc["title"] != row["title"])
            if mismatch:
                flags.append("title_mismatch")
            product = Product(sku, row["category_id"], row["title"], desc["description"] if has_desc else None, tuple(flags))
            Product.from_dict(product.as_dict())
            write_line(inputs, product.as_dict())
            write_line(provenance, {"sku_id": sku, "category_id": row["category_id"],
                                   "vendor": row["vendor"], "model": row["model"], "seller": row["seller"],
                                   "description_title": desc["title"] if desc else None})
            c = counts[row["category_id"]]
            c["rows"] += 1
            c["with_description" if has_desc else "title_only"] += 1
            c["title_mismatch"] += int(mismatch)
    result = {"source_kind": "trusted_existing_research_projection", "mode": "text_only",
              "source_sha256": fingerprints, "projection_sha256": digest(catalog),
              "input_sha256": digest(input_path), "provenance_sha256": digest(provenance_path),
              "rows": len(selected), "counts": counts,
              "note": "Projection provenance is inherited from local EDA, not independently regenerated here."}
    write_json(output / "prepare_manifest.json", result)
    return result
