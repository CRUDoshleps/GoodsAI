"""Local batch CLI. Predict uses only stdlib; prepare additionally needs PyArrow."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

from goodsai import __version__
from goodsai.annotation import annotation_tasks
from goodsai.contracts import Product, load_config
from goodsai.data import check_output, digest, inventory_sources, prepare, read_jsonl, write_json, write_line
from goodsai.evaluate import evaluate
from goodsai.runtime import identity, peak_rss_bytes
from goodsai.storage import staged_prediction_pair
from goodsai.verify import Extractor


def predict(input_path: Path, output: Path, config: dict) -> dict:
    output = output.resolve()
    check_output(output, input_path)
    check_output(output.with_suffix(".manifest.json"), input_path)
    with staged_prediction_pair(output) as (staged_output, staged_manifest):
        report = _predict_staged(input_path, staged_output, staged_manifest, config)
    return report


def _predict_staged(input_path: Path, staged_output: Path, staged_manifest: Path, config: dict) -> dict:
    started = time.perf_counter()
    meta = identity(config)
    input_hash = digest(input_path)
    run_id = hashlib.sha256((input_hash + meta["code_sha256"] + meta["config_sha256"]).encode()).hexdigest()[:20]
    extractor = Extractor(config)
    seen = set()
    elapsed = []
    rows = errors = 0
    counts = defaultdict(Counter)
    reasons = Counter()
    slices = defaultdict(Counter)
    statuses = Counter()
    with staged_output.open("w", encoding="utf-8", newline="\n") as stream:
        for line_no, row in enumerate(read_jsonl(input_path), 1):
            sku = row.get("sku_id")
            if isinstance(sku, str) and sku in seen:
                raise ValueError(f"Duplicate SKU at line {line_no}")
            if isinstance(sku, str):
                seen.add(sku)
            tick = time.perf_counter()
            try:
                product = Product.from_dict(row)
            except ValueError:
                result = {"schema_version": "0.1", "run_id": run_id,
                          "sku_id": sku if isinstance(sku, str) else "", "category_id": None,
                          "status": "invalid_input", "attributes": [], "input_line": line_no,
                          "reason_codes": ["invalid_text_only_input"]}
                errors += 1
            else:
                # Programming errors must fail the run, never silently become empty successful answers.
                result = extractor.predict(product, run_id)
                slice_key = product.category_id + (":with_description" if product.description else ":title_only") if product.category_id else "unknown_category"
                slices[slice_key]["cards"] += 1
                filled = sum(a["value"] is not None for a in result["attributes"])
                slices[slice_key]["cards_with_candidate"] += filled > 0
                slices[slice_key]["candidate_pairs"] += filled
                slices[slice_key]["requested_pairs"] += len(result["attributes"])
                for a in result["attributes"]:
                    counts[product.category_id + ":" + a["attribute"]].update(requested=1, predicted=int(a["value"] is not None))
                    reasons.update(a["reason_codes"])
            elapsed.append(time.perf_counter() - tick)
            statuses[result["status"]] += 1
            write_line(stream, result)
            rows += 1
        if not rows:
            raise ValueError("Input contains no records")
    elapsed.sort()
    seconds = time.perf_counter() - started
    report = meta | {"version": __version__, "run_id": run_id, "input_sha256": input_hash,
                     "output_sha256": digest(staged_output), "rows": rows, "invalid_input_rows": errors,
                     "elapsed_seconds": seconds, "cards_per_second_including_io": rows / seconds,
                     "extractor_p50_ms": elapsed[(len(elapsed) - 1) // 2] * 1000,
                     "extractor_p95_ms": elapsed[int((len(elapsed) - 1) * .95)] * 1000,
                     "peak_process_rss_bytes": peak_rss_bytes(), "attribute_counts": dict(counts),
                     "slices": dict(slices), "status_counts": dict(statuses), "abstention_reasons": dict(reasons),
                     "llm_calls": 0, "quality_status": "not_evaluated_without_manual_gold",
                     "confidence_kind": "heuristic", "calibrated": False}
    write_json(staged_manifest, report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="goodsai")
    parser.add_argument("--config", help="Default: versioned configuration bundled with goodsai")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--output", type=Path, default=Path("data/processed/source_inventory.json"))
    p = sub.add_parser("prepare")
    p.add_argument("--catalog", type=Path, default=Path("outputs/eda/catalog_skus.parquet"))
    p.add_argument("--descriptions", type=Path, default=Path("data/raw/sku_desc.parquet"))
    p.add_argument("--inventory", type=Path, default=Path("data/raw/.local_inventory.json"))
    p.add_argument("--output-dir", type=Path, default=Path("data/processed/e1"))
    p = sub.add_parser("predict")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("evaluate")
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--gold", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("annotate")
    p.add_argument("--input", type=Path, default=Path("data/processed/e1/pilot.jsonl"))
    p.add_argument("--provenance", type=Path, default=Path("data/processed/e1/provenance.jsonl"))
    p.add_argument("--eda-sample", type=Path, help="Optional prior EDA export; otherwise reconstruct its deterministic SKU selection")
    p.add_argument("--output-dir", type=Path, default=Path("data/gold/e1"))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "inventory":
            result = inventory_sources(args.raw_dir, args.output)
        elif args.command == "prepare":
            started = time.perf_counter()
            result = prepare(args.catalog, args.descriptions, args.inventory, args.output_dir, config)
            result.update(elapsed_seconds=time.perf_counter() - started, peak_process_rss_bytes=peak_rss_bytes())
            write_json(args.output_dir / "prepare_manifest.json", result)
        elif args.command == "predict":
            result = predict(args.input, args.output, config)
        elif args.command == "evaluate":
            check_output(args.output, args.predictions, *([args.gold] if args.gold else []))
            result = evaluate(args.predictions, args.gold, config)
            write_json(args.output, result)
        else:
            result = annotation_tasks(args.input, args.provenance, args.eda_sample, args.output_dir, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"goodsai: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
