"""Measure candidate-set recall/resources on an explicitly permitted span reference, never a blind test."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time
import tracemalloc

from goodsai.contracts import Product
from goodsai.data import check_output, digest, read_jsonl, write_json
from goodsai.span_index import ALGORITHM_VERSION, SpanConfig, build_span_index, fingerprint


def reference_records(path):
    if path is None:
        return {}, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict) or not isinstance(payload.get("reference_kind"), str)
            or payload["reference_kind"] not in {"synthetic", "reviewed_development"}
            or not isinstance(payload.get("records"), list)):
        raise ValueError("Use an explicitly permitted synthetic/reviewed_development span reference")
    records = {}
    for row in payload["records"]:
        if (not isinstance(row, dict) or not isinstance(row.get("sku_id"), str) or not row["sku_id"]
                or row["sku_id"] in records or not isinstance(row.get("spans"), list)):
            raise ValueError("Invalid or duplicate span reference record")
        spans = []
        for span in row["spans"]:
            if (not isinstance(span, dict) or not isinstance(span.get("field"), str)
                    or span["field"] not in {"title", "description"} or type(span.get("start")) is not int
                    or type(span.get("end")) is not int or not 0 <= span["start"] < span["end"]):
                raise ValueError("Invalid span reference offsets/field")
            spans.append((span["field"], span["start"], span["end"]))
        if len(set(spans)) != len(spans):
            raise ValueError("Duplicate reference spans")
        records[row["sku_id"]] = set(spans)
    return records, payload["reference_kind"]


def measure(input_path, reference_path=None, config=None):
    config = config or SpanConfig()
    input_hash = digest(input_path)
    reference_hash = digest(reference_path) if reference_path else None
    references, kind = reference_records(reference_path)
    seen = set()
    statuses = Counter()
    reasons = Counter()
    matched = labelled = total_spans = 0
    seconds = 0.0
    peak = 0
    for row in read_jsonl(input_path):
        product = Product.from_dict(row)
        if product.sku_id in seen:
            raise ValueError("Duplicate input SKU")
        seen.add(product.sku_id)
        if tracemalloc.is_tracing():
            raise ValueError("Run measurement outside another tracemalloc session")
        tracemalloc.start()
        tick = time.perf_counter()
        try:
            index = build_span_index(product, config)  # No labels/target are passed to the generator.
            seconds += time.perf_counter() - tick
            peak = max(peak, tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
        statuses[index.status] += 1
        reasons.update(index.reason_codes)
        total_spans += len(index.entries)
        candidates = {(entry.field, entry.start, entry.end) for entry in index.entries}
        expected = references.get(product.sku_id, set())
        if any(end > len(getattr(product, field) or "") for field, _, end in expected):
            raise ValueError("Reference span exceeds source field")
        labelled += len(expected)
        matched += len(expected & candidates)
    if not seen or set(references) - seen:
        raise ValueError("Empty input or reference SKU absent from input")
    if (digest(input_path) != input_hash
            or reference_path and digest(reference_path) != reference_hash):
        raise ValueError("Input/reference changed during measurement")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    import goodsai.span_index as generator
    import goodsai.text as mapping
    return {"report_version": "1", "algorithm_version": ALGORITHM_VERSION, "git_commit": commit, "git_dirty": dirty,
            "generator_sha256": digest(Path(generator.__file__)), "mapping_sha256": digest(Path(mapping.__file__)),
            "measurement_sha256": digest(Path(__file__)), "config": asdict(config),
            "config_sha256": fingerprint(asdict(config)), "input_sha256": input_hash,
            "reference_sha256": reference_hash,
            "reference_kind": kind, "rows": len(seen), "status_counts": dict(statuses), "reason_counts": dict(reasons),
            "span_count": total_spans, "build_seconds_with_tracemalloc": seconds,
            "peak_traced_python_bytes": peak, "reference_spans": labelled, "matched_spans": matched,
            "missing_spans": labelled - matched, "candidate_set_recall": matched / labelled if labelled else None,
            "independent_quality": False, "llm_calls": 0,
            "note": "Exact candidate offsets only; no attribute prediction, precision, semantic correctness or independent quality claim."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--config", type=Path, help="JSON object with SpanConfig limits only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        check_output(args.output, args.input, *([args.reference] if args.reference else []), *([args.config] if args.config else []))
        if args.output.exists():
            raise ValueError("Output exists; choose a new report path")
        config = SpanConfig(**json.loads(args.config.read_text(encoding="utf-8"))) if args.config else SpanConfig()
        report = measure(args.input, args.reference, config)
        write_json(args.output, report)
    except (ValueError, TypeError, OSError) as exc:
        print(f"span-index measurement failed ({type(exc).__name__}); check source/reference/config and choose a new output", file=sys.stderr)
        return 2
    print(json.dumps({key: report[key] for key in ("rows", "span_count", "status_counts", "reference_spans", "matched_spans", "candidate_set_recall")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
