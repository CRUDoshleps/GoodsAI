"""DATA-001: prepare text-only data and bind it to an existing frozen split audit.

No split assignment, labels, predictions or reserve text is generated here.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from goodsai.contracts import load_config
from goodsai.data import digest, preparation_directory, prepare, verify_sources, write_json
from scripts.research.audit_splits import verify as verify_audit


def bind_audit(bundle, input_sha256):
    """Reuse exact/normalized/near/family quarantine evidence, not a new split."""
    checked = verify_audit(bundle)
    summary = Path(bundle) / "audit.summary.json"
    report = json.loads(summary.read_text(encoding="utf-8"))
    input_entries = [s for s in report["sources"] if s["file"] == "pilot.jsonl"]
    if len(input_entries) != 1 or input_entries[0]["sha256"] != input_sha256:
        raise ValueError("prepared_input_differs_from_frozen_split_audit")
    return {"summary_sha256": digest(summary), "status": checked["status"],
            "rows": checked["rows"], "eligible_rows": checked["eligible_rows"],
            "quarantined_rows": checked["quarantined_rows"],
            "corrected": report["corrected"], "detectors": report["detectors"],
            "near_join": report["near_join"],
            "limitations": report["limitations"],
            "artifacts": report["artifacts"],
            "reserve_text_exported": False, "predictions_generated": False}


def build(catalog, descriptions, inventory, split_audit, output, config):
    raw = descriptions.parent.resolve()
    if output.resolve() == raw or raw in output.resolve().parents:
        raise ValueError("prepared_output_must_be_outside_raw_sources")
    # Fail before expensive preparation if the supplied immutable audit is stale.
    verify_audit(split_audit)
    with preparation_directory(output, catalog, descriptions, inventory, split_audit) as stage:
        prepared = prepare(catalog, descriptions, inventory, stage / "prepared", config)
        audit = bind_audit(split_audit, prepared["input_sha256"])
        if prepared["rows"] != audit["rows"]:
            raise ValueError("prepared_row_count_differs_from_split_audit")
        manifest = {"version": "dataset-handoff-v1", "mode": "text_only",
                    "preparation": prepared, "split_audit": audit,
                    "files": {p.name: digest(p) for p in sorted((stage / "prepared").iterdir())
                              if p.is_file() and not p.name.startswith(".")},
                    "evaluation_status": "development_feedback; no independent quality or new test split"}
        write_json(stage / "dataset.manifest.json", manifest)
    return manifest


def verify(bundle, catalog, descriptions, inventory, split_audit):
    manifest = json.loads((bundle / "dataset.manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != "dataset-handoff-v1":
        raise ValueError("unknown_dataset_handoff_version")
    expected = {"pilot.jsonl", "provenance.jsonl", "prepare_manifest.json"}
    actual = {p.name for p in (bundle / "prepared").iterdir() if not p.name.startswith(".")}
    if set(manifest["files"]) != expected or actual != expected:
        raise ValueError("dataset_artifact_inventory_mismatch")
    for name, checksum in manifest["files"].items():
        if (bundle / "prepared" / name).is_symlink() or digest(bundle / "prepared" / name) != checksum:
            raise ValueError("dataset_artifact_hash_mismatch")
    prepared = manifest["preparation"]
    if json.loads((bundle / "prepared/prepare_manifest.json").read_text(encoding="utf-8")) != prepared:
        raise ValueError("dataset_prepare_manifest_mismatch")
    if (verify_sources(descriptions.parent, inventory) != prepared["source_sha256"]
            or digest(catalog) != prepared["projection_sha256"]
            or digest(inventory) != prepared["inventory_sha256"]
            or digest(descriptions) != prepared["source_sha256"]["sku_desc.parquet"]):
        raise ValueError("dataset_source_hash_mismatch")
    if bind_audit(split_audit, digest(bundle / "prepared/pilot.jsonl")) != manifest["split_audit"]:
        raise ValueError("dataset_split_audit_mismatch")
    return {"status": "verified", "rows": prepared["rows"],
            "eligible_rows": manifest["split_audit"]["eligible_rows"],
            "quarantined_rows": manifest["split_audit"]["quarantined_rows"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("outputs/eda/catalog_skus.parquet"))
    parser.add_argument("--descriptions", type=Path, default=Path("data/raw/sku_desc.parquet"))
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--split-audit", type=Path, required=True)
    parser.add_argument("--config")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output-dir", type=Path)
    destination.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify:
            result = verify(args.verify, args.catalog, args.descriptions, args.inventory, args.split_audit)
        else:
            manifest = build(args.catalog, args.descriptions, args.inventory, args.split_audit,
                             args.output_dir, load_config(args.config))
            result = {"status": "prepared", "rows": manifest["preparation"]["rows"],
                      "eligible_rows": manifest["split_audit"]["eligible_rows"],
                      "quarantined_rows": manifest["split_audit"]["quarantined_rows"]}
    except (OSError, ValueError, KeyError, TypeError):
        # Neither card text nor paths/targets from parser exceptions leave stdout.
        parser.exit(2, "dataset preparation failed; check source hashes, schemas, frozen audit and new destination\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
