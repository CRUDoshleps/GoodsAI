"""Bounded preparation from the existing trusted EDA projection, never raw pickle loading."""
from contextlib import contextmanager
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

from goodsai.contracts import Product
from goodsai.storage import atomic_text as _atomic_text, prediction_snapshot, output_lock


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


SOURCE_PROFILES = {
    "text-only": ("skus.pkl", "sku_desc.parquet"),
    "analytics": ("skus.pkl", "sku_desc.parquet", "query_clicks.parquet"),
}


def verify_sources(raw: Path, inventory: Path, profile: str = "text-only") -> dict:
    """Verify required sources, including legacy inventories, without reading pickle."""
    if profile not in SOURCE_PROFILES:
        raise ValueError("Unknown source profile")
    value = json.loads(inventory.read_text(encoding="utf-8"))
    entries = value.get("files") if isinstance(value, dict) else None
    if not isinstance(entries, list):
        raise ValueError("Invalid source inventory")
    indexed = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("file") not in SOURCE_PROFILES["analytics"]:
            raise ValueError("Invalid inventory source name")
        name = entry["file"]
        checksum = entry.get("sha256")
        if (name in indexed or type(entry.get("bytes")) is not int or entry["bytes"] < 0
                or not isinstance(checksum, str) or len(checksum) != 64
                or any(c not in "0123456789abcdef" for c in checksum)):
            raise ValueError("Invalid or duplicate inventory entry")
        indexed[name] = entry
    if not set(SOURCE_PROFILES[profile]) <= indexed.keys():
        raise ValueError("Inventory must describe all required sources for the profile")
    fingerprints = {}
    for name in SOURCE_PROFILES[profile]:
        entry, path = indexed[name], raw / name
        if not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Official source differs from the local inventory")
        fingerprints[name] = entry["sha256"]
    return fingerprints


def inventory_sources(raw: Path, output: Path, profile: str = "text-only", *, reference: Path | None = None) -> dict:
    check_output(output)
    if output.resolve() == raw.resolve() or raw.resolve() in output.resolve().parents:
        raise ValueError("Write the inventory outside the raw directory")
    if profile not in SOURCE_PROFILES:
        raise ValueError("Unknown source profile")
    reference_hashes = verify_sources(raw, reference, profile) if reference is not None else None
    entries = []
    for name in SOURCE_PROFILES[profile]:
        path = raw / name
        entries.append({"file": name, "bytes": path.stat().st_size, "sha256": digest(path)})
    if reference_hashes is not None and {e["file"]: e["sha256"] for e in entries} != reference_hashes:
        raise ValueError("Official source differs from the local inventory")
    result = {"version": "source-inventory-v2", "profile": profile, "files": entries,
              "optional_files": [{"file": name, "present": (raw / name).is_file(), "used": False}
                                 for name in SOURCE_PROFILES["analytics"] if name not in SOURCE_PROFILES[profile]],
              "verified_reference_sha256": digest(reference) if reference else None,
              "note": "Local fingerprints, not independent source authentication. Optional files are not read."}
    with output_lock(output):
        if output.exists() or output.is_symlink():
            raise ValueError("Use a new inventory output; existing fingerprints must not be overwritten")
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return result


@contextmanager
def preparation_directory(output: Path, *inputs: Path):
    """Publish a new complete directory; errors never replace prior artifacts."""
    check_output(output, *inputs)
    resolved = output.resolve()
    if any(resolved in p.resolve().parents for p in inputs):
        raise ValueError("Prepared output must not contain an input")
    with output_lock(output):
        if output.exists() or output.is_symlink():
            raise ValueError("Use a new output directory; prepared data must not be overwritten")
        with tempfile.TemporaryDirectory(prefix=".goodsai-prepare-", dir=output.parent) as temporary:
            stage = Path(temporary) / "bundle"
            stage.mkdir()
            yield stage
            os.rename(stage, output)


def prepare(catalog: Path, descriptions: Path, raw_inventory: Path, output: Path, config: dict) -> dict:
    # Source verification precedes publication and never deserializes raw pickle.
    fingerprints = verify_sources(descriptions.parent, raw_inventory)
    if digest(descriptions) != fingerprints["sku_desc.parquet"]:
        raise ValueError("Description path does not match the verified source")
    raw_root = descriptions.parent.resolve()
    if output.resolve() == raw_root or raw_root in output.resolve().parents:
        raise ValueError("Prepared output must be outside the raw source directory")
    with preparation_directory(output, catalog, descriptions, raw_inventory) as stage:
        return _prepare(catalog, descriptions, raw_inventory, stage, config, fingerprints)


def _prepare(catalog: Path, descriptions: Path, raw_inventory: Path, output: Path,
             config: dict, fingerprints: dict) -> dict:
    import pyarrow.parquet as pq
    check_output(output, catalog, descriptions, raw_inventory)
    if not catalog.is_file():
        raise ValueError("Trusted catalog projection is missing; run the documented research preparation first")
    with pq.ParquetFile(catalog) as catalog_file, pq.ParquetFile(descriptions) as description_file:
        return _prepare_tables(catalog, descriptions, raw_inventory, output, config, fingerprints,
                               catalog_file, description_file)


def _prepare_tables(catalog, descriptions, raw_inventory, output, config, fingerprints,
                    catalog_file, description_file):
    import pyarrow as pa

    selected = {}
    columns = ["sku_id", "category_ids", "title", "vendor", "model", "seller"]
    sources = {"catalog_projection": catalog, "descriptions": descriptions, "inventory": raw_inventory}
    before = {name: digest(path) for name, path in sources.items()}
    schemas = {}
    for name, parquet, required in [("catalog", catalog_file, columns),
                                     ("descriptions", description_file, ["sku_id", "title", "description"])]:
        schema = parquet.schema_arrow
        if any(schema.names.count(col) != 1 for col in required):
            raise ValueError("Missing or duplicate required Parquet columns")
        for col in required:
            dtype = schema.field(col).type
            if not (pa.types.is_string(dtype) or pa.types.is_large_string(dtype) or pa.types.is_null(dtype)
                    or (col == "sku_id" and name == "descriptions" and pa.types.is_integer(dtype))):
                raise ValueError("Invalid required Parquet column type")
        schemas[name] = {col: str(schema.field(col).type) for col in required}
    seen = set()
    filtered = Counter()
    for batch in catalog_file.iter_batches(batch_size=4096, columns=columns, use_threads=False):
        for row in batch.to_pylist():
            sku = row["sku_id"]
            if not isinstance(sku, str) or not sku.strip() or sku in seen:
                raise ValueError("Duplicate or invalid catalog SKU")
            seen.add(sku)
            categories = json.loads(row["category_ids"]) if isinstance(row["category_ids"], str) else None
            if not isinstance(categories, list) or len(categories) != 1 or not isinstance(categories[0], str):
                raise ValueError("Expected a single catalog category")
            if categories[0] not in config["categories"]:
                filtered[categories[0]] += 1
                continue
            if not isinstance(row["title"], str) or not row["title"].strip():
                raise ValueError("Selected catalog title must be nonempty text")
            selected[sku] = row | {"category_id": categories[0]}
    if not selected:
        raise ValueError("No configured categories found in catalog projection")
    joined = {}
    desc_seen = set()
    for batch in description_file.iter_batches(
            batch_size=4096, columns=["sku_id", "title", "description"], use_threads=False):
        for row in batch.to_pylist():
            identity = row["sku_id"]
            if identity is None or isinstance(identity, bool) or not str(identity).strip():
                raise ValueError("Invalid description SKU")
            sku = str(identity)
            if sku in desc_seen:
                raise ValueError("Duplicate description SKU")
            desc_seen.add(sku)
            if sku in selected:
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
    if any(digest(path) != before[name] for name, path in sources.items()):
        raise ValueError("Preparation source changed during the run")
    if verify_sources(descriptions.parent, raw_inventory) != fingerprints:
        raise ValueError("Preparation source changed during the run")
    result = {"version": "prepare-v2", "source_kind": "trusted_existing_research_projection", "mode": "text_only",
              "source_sha256": fingerprints, "projection_sha256": digest(catalog),
              "inventory_sha256": before["inventory"], "required_schemas": schemas,
              "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=True).encode()).hexdigest(),
              "tool_sha256": digest(Path(__file__)), "python": platform.python_version(),
              "input_sha256": digest(input_path), "provenance_sha256": digest(provenance_path),
              "rows": len(selected), "counts": counts,
              "accounting": {"catalog_rows": len(seen), "selected_rows": len(selected),
                             "filtered_category_rows": sum(filtered.values()), "filtered_categories": dict(sorted(filtered.items())),
                             "description_rows": len(desc_seen), "matched_description_rows": len(joined),
                             "unmatched_description_rows": len(desc_seen) - len(joined),
                             "selected_without_description_row": len(selected) - len(joined),
                             "matched_blank_description_rows": sum(not r["description"] or not r["description"].strip() for r in joined.values()),
                             "dropped_selected_rows": 0},
              "split_status": "not_checked; use the frozen EVAL-002 audit handoff, never resample existing test",
              "text_policy": "Keep original Unicode/HTML and offsets; catalog title wins; blank description becomes null.",
              "note": "Projection provenance is inherited from local EDA, not independently regenerated here."}
    write_json(output / "prepare_manifest.json", result)
    return result
