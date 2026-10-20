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
from goodsai.composition import Components, PipelineRuntime, build_runtime
from goodsai.policy import policy_for_settings, resolve_runtime_policy


def predict(input_path: Path, output: Path, config: dict, llm=None, *, runtime_policy=None,
            components: Components | None = None) -> dict:
    """Rules-only by default; ``llm`` is an opt-in ``goodsai.llm.LLMExtractor``."""
    runtime_policy = runtime_policy or policy_for_settings(config, llm.settings if llm else None)
    runtime = build_runtime(config, runtime_policy, components=components, legacy_llm=llm)
    output = output.resolve()
    check_output(output, input_path)
    check_output(output.with_suffix(".manifest.json"), input_path)
    with runtime.sink.stage(output) as (staged_output, staged_manifest):
        report = _predict_staged(input_path, staged_output, staged_manifest, runtime)
    return report


def _predict_staged(input_path: Path, staged_output: Path, staged_manifest: Path, runtime: PipelineRuntime) -> dict:
    started = time.perf_counter()
    config, llm = runtime.config, runtime.llm
    meta = identity(config) | runtime.metadata
    input_hash = digest(input_path)
    run_material = input_hash + meta["code_sha256"] + meta["effective_config_sha256"]
    run_id = hashlib.sha256(run_material.encode()).hexdigest()[:20]
    extractor = runtime.predictor
    seen = set()
    elapsed = []
    rows = errors = 0
    counts = defaultdict(Counter)
    reasons = Counter()
    slices = defaultdict(Counter)
    statuses = Counter()
    methods = Counter()
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
                    if a["value"] is not None:
                        methods[a["method"]] += 1
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
    if llm is not None:
        # Counts, tokens, cost and reason codes only: no card text, keys or endpoint.
        report["llm"] = llm.report()
        report["llm_calls"] = report["llm"]["calls"]
        report["method_counts"] = dict(methods)
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
    p.add_argument("--llm", action="store_true",
                   help="Opt-in LLM fallback for attributes rules did not find; endpoint and key come from "
                        "GOODSAI_LLM_BASE_URL / GOODSAI_LLM_API_KEY")
    p.add_argument("--llm-model",
                   help="Gateway model name (default: GOODSAI_LLM_MODEL)")
    p.add_argument("--llm-max-calls", type=int, help="Hard per-run budget of logical provider calls")
    p.add_argument("--llm-daily-max-calls", type=int,
                   help="Shared budget per Moscow day across runs using the same --llm-budget-file")
    p.add_argument("--llm-budget-file", type=Path,
                   help="Daily call ledger outside Git")
    p.add_argument("--llm-cache-dir", type=Path, help="Exact-request cache outside Git, e.g. outputs/llm-cache")
    p.add_argument("--llm-timeout", type=float)
    p.add_argument("--llm-attempts", type=int, help="Attempts per request, retries included (1-5)")
    p.add_argument("--llm-concurrency", type=int)
    p.add_argument("--llm-max-tokens", type=int)
    p.add_argument("--llm-circuit-breaker", type=int)
    p.add_argument("--llm-price-input-per-1k", type=float, help="Price per 1000 prompt tokens; cost is N/A without it")
    p.add_argument("--llm-price-output-per-1k", type=float, help="Price per 1000 completion tokens")
    p.add_argument("--llm-deadline", type=float,
                   help="Total seconds per card request: queue, attempts, backoff (1-900)")
    p.add_argument("--llm-max-response-bytes", type=int, help="Larger gateway bodies are rejected unread")
    p.add_argument("--llm-max-proposals", type=int, help="Answers with more proposals are rejected")
    p.add_argument("--llm-json-mode", action=argparse.BooleanOptionalAction, default=None,
                   help="Ask the gateway for response_format=json_object; answers are validated either way")
    p = sub.add_parser("llm-trace", help="One synthetic card through the live LLM route (counts against budgets)")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--llm-model")
    p.add_argument("--llm-budget-file", type=Path)
    p.add_argument("--llm-daily-max-calls", type=int)
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
            llm = None
            policy = resolve_runtime_policy(config, enabled=args.llm, overrides={
                "model": args.llm_model, "max_calls": args.llm_max_calls,
                "timeout_seconds": args.llm_timeout, "max_attempts": args.llm_attempts,
                "concurrency": args.llm_concurrency, "max_tokens": args.llm_max_tokens,
                "circuit_breaker": args.llm_circuit_breaker,
                "price_input_per_1k": args.llm_price_input_per_1k,
                "price_output_per_1k": args.llm_price_output_per_1k, "json_mode": args.llm_json_mode,
                "cache_dir": args.llm_cache_dir, "daily_max_calls": args.llm_daily_max_calls,
                "budget_ledger": args.llm_budget_file, "request_deadline_seconds": args.llm_deadline,
                "max_response_bytes": args.llm_max_response_bytes, "max_proposals": args.llm_max_proposals})
            result = predict(args.input, args.output, config, runtime_policy=policy)
            if "llm" in result and result["llm"]["disabled_reason"]:
                print(f"goodsai: LLM fallback disabled during run: {result['llm']['disabled_reason']}; "
                      "rule results are unchanged", file=sys.stderr)
        elif args.command == "llm-trace":
            from goodsai.llm import synthetic_trace
            policy = resolve_runtime_policy(config, enabled=True, overrides={
                "model": args.llm_model, "daily_max_calls": args.llm_daily_max_calls,
                "budget_ledger": args.llm_budget_file})
            check_output(args.output)
            # Trace may reduce a configured limit, never increase it.
            policy["llm"]["max_calls"] = min(1, policy["llm"]["max_calls"])
            runtime = build_runtime(config, policy)
            result = synthetic_trace(runtime.llm)
            result.update(runtime.metadata)
            write_json(args.output, result)
            if result["llm"]["calls"] != 1 or result["llm"]["failures"]:
                print("goodsai: live LLM trace did not complete: "
                      + ",".join(sorted(result["llm"]["failures"])), file=sys.stderr)
                return 3
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
