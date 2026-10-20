"""Explicitly authorized organizer-gateway screening using the existing LLM adapter.

Private input is accepted only by its exact authorized hash. Credentials come
from environment, never arguments/files in Git. Calls share the existing ledger.
"""
import argparse
import json
import math
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/research"))
from compare_silver_baseline import private_output
from goodsai.cli import predict
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl, write_json
from goodsai.llm import DailyLedger, LLMExtractor, LLMSettings, build_messages, provider_from_env
from goodsai.silver_prepare import dump, verify_bundle


def planning_cost_bound(prompt_bytes, calls, output_tokens):
    # Conservative planning estimate, not a tokenizer proof or billing invoice.
    # Actual provider usage and charged quota still need reconciliation.
    return calls * ((prompt_bytes + 4096) * 15.86 / 1_000_000 + output_tokens * 61 / 1_000_000)


def run(args):
    if (not 1 <= args.max_calls <= 100 or not math.isfinite(args.spend_limit_rub) or args.spend_limit_rub <= 0
            or args.model != "openai/gpt-oss-120b"):
        raise ValueError("unsupported_frozen_budget_or_model")
    verify_bundle(args.bundle)
    baseline = json.loads((args.baseline_run / "run_stats.json").read_text(encoding="utf-8"))
    bundle_hash = digest(args.bundle / "manifest.json")
    source = args.bundle / "llm_screening.input.jsonl"
    if digest(source) != args.authorized_packet_sha256:
        raise ValueError("exact_packet_authorization_required")
    if (baseline["freeze"]["bundle_manifest_sha256"] != bundle_hash
            or baseline["freeze"]["evaluator_sha256"] != digest(ROOT / "src/goodsai/silver_evaluate.py")):
        raise ValueError("frozen_baseline_or_evaluator_mismatch")
    policy = json.loads((args.bundle / "policy.json").read_text(encoding="utf-8"))
    settings = LLMSettings(model=args.model, max_calls=args.max_calls, max_attempts=1,
        max_tokens=2048, concurrency=2, daily_max_calls=300, timeout_seconds=30,
        request_deadline_seconds=60, price_input_per_1k=.01586, price_output_per_1k=.061,
        budget_ledger=args.budget_ledger.resolve())
    products = [Product.from_dict(p) for p in read_jsonl(source)]
    metadata = {m["sku_id"]: m for m in read_jsonl(args.bundle / "metadata.jsonl")}
    if not products or any(metadata[p.sku_id]["original_split"] != "development" for p in products):
        raise ValueError("development_only_screening_required")
    sizes = [len(json.dumps(build_messages(p, policy["config"]["categories"][p.category_id],
                                          policy["config"], settings), ensure_ascii=False).encode()) for p in products]
    bound = planning_cost_bound(max(sizes), args.max_calls, settings.max_tokens)
    if bound > args.spend_limit_rub:
        raise ValueError("planning_bound_exceeds_authorized_spend")
    ledger = DailyLedger(settings.budget_ledger, settings.daily_max_calls)
    used = ledger.used()
    if used >= settings.daily_max_calls:
        raise ValueError("shared_daily_call_budget_exhausted")
    output = private_output(args.output_dir)
    dump(output / "config.json", policy["config"])
    config = load_config(output / "config.json")
    from dataclasses import replace
    settings = replace(settings, cache_dir=output / "cache", cache_namespace="eval008-20261020")
    prior = None
    seed = getattr(args, "cache_seed_run", None)
    if seed:
        # Reuse only an immutable run on this exact packet/model/config. Never
        # alter its cache: the next bounded batch gets its own verified copy.
        inventory = json.loads((seed / "manifest.json").read_text(encoding="utf-8"))["artifacts"]
        for name, checksum in inventory.items():
            path = seed / name
            if (Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink()
                    or not path.resolve().is_relative_to(seed.resolve())
                    or digest(path) != checksum):
                raise ValueError("cache_seed_artifact_mismatch")
        producer = json.loads((seed / "cold.manifest.json").read_text(encoding="utf-8"))
        from goodsai.runtime import identity
        if (producer["input_sha256"] != args.authorized_packet_sha256
                or producer["config_sha256"] != identity(config)["config_sha256"]
                or producer["llm"]["model"] != settings.model
                or producer["llm"]["prompt_version"] != settings.identity()["prompt_version"]):
            raise ValueError("cache_seed_packet_model_or_config_mismatch")
        for name in inventory:
            if name.startswith("cache/"):
                destination = output / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(seed / name, destination)
                if digest(destination) != inventory[name]:
                    raise ValueError("cache_seed_changed_during_copy")
        # Warm can retry a cold failure while the logical run cap still has room.
        # Its counters are cumulative; billing must include those physical calls.
        warm = json.loads((seed / "warm.manifest.json").read_text(encoding="utf-8"))
        if any(warm.get(k) != producer.get(k) for k in ("input_sha256", "config_sha256", "code_sha256")):
            raise ValueError("cache_seed_warm_identity_mismatch")
        billed = warm.get("llm_acquisition", warm["llm"])
        prior = {k: billed.get(k) for k in ("calls", "attempts", "prompt_tokens", "completion_tokens", "cost")}
        prior["manifest_sha256"] = digest(seed / "manifest.json")
    dump(output / "freeze.json", {"bundle_manifest_sha256": bundle_hash,
        "authorized_packet_sha256": args.authorized_packet_sha256, "cards": len(products),
        "authorization_record": args.authorization_record, "model": settings.model,
        "max_calls": settings.max_calls, "max_attempts": 1, "max_tokens": settings.max_tokens,
        "concurrency": settings.concurrency, "request_deadline_seconds": settings.request_deadline_seconds,
        "daily_max_calls": settings.daily_max_calls, "shared_ledger_used_before": used,
        "authorized_spend_limit_rub": args.spend_limit_rub, "conservative_planning_estimate_rub": bound,
        "max_prompt_json_utf8_bytes": max(sizes), "price_input_rub_per_million": 15.86,
        "verified_seed_run_usage": prior,
        "price_output_rub_per_million": 61, "driver_sha256": digest(Path(__file__)),
        "regression_gate": "any_new_fp_or_lost_tp_blocks_recommendation",
        "warm_usage": "cumulative_same_extractor_and_same_total_run_call_cap"})
    extractor = LLMExtractor(config, provider_from_env(settings), settings)
    for temperature in ("cold", "warm"):
        target = output / (temperature + ".jsonl")
        report = predict(source, target, config, extractor)
        if prior:
            report["llm_acquisition"] = {k: prior[k] + report["llm"][k]
                if prior[k] is not None and report["llm"].get(k) is not None else None
                for k in ("calls", "attempts", "prompt_tokens", "completion_tokens", "cost")}
            report["llm_acquisition"]["prior_manifest_sha256"] = prior["manifest_sha256"]
            write_json(target.with_suffix(".manifest.json"), report)
    verify_bundle(args.bundle)
    if digest(source) != args.authorized_packet_sha256:
        raise ValueError("authorized_packet_changed")
    usage = extractor.report()
    dump(output / "completion.json", {"cards": len(products), "calls": usage["calls"],
         "attempts": usage["attempts"], "cost_rub_provider_estimate": usage["cost"],
         "provider_estimate_within_authorized_spend": usage["cost"] is not None and usage["cost"] <= args.spend_limit_rub,
         "repeat_values_identical": digest(output / "cold.jsonl") == digest(output / "warm.jsonl"),
         "shared_ledger_used_after": ledger.used(), "billing_invoice_reconciled": False})
    dump(output / "manifest.json", {"artifacts": {p.relative_to(output).as_posix(): digest(p)
         for p in sorted(output.rglob("*")) if p.is_file() and not p.name.startswith(".")}})
    return {k: usage[k] for k in ("calls", "attempts", "cache_hits", "prompt_tokens", "completion_tokens", "cost", "failures", "disabled_reason")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "baseline-run", "budget-ledger", "output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--authorized-packet-sha256", required=True)
    p.add_argument("--authorization-record", required=True, help="Explicit team approval reference, never a secret")
    p.add_argument("--model", default="openai/gpt-oss-120b")
    p.add_argument("--max-calls", default=100, type=int)
    p.add_argument("--spend-limit-rub", required=True, type=float)
    p.add_argument("--cache-seed-run", type=Path, help="Verified earlier bounded run on the exact same packet")
    print(json.dumps(run(p.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
