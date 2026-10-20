"""EVAL-007: freeze, run two isolated rules runtimes, score one existing silver bundle.

No source preparation, model calls, threshold fitting or reserve text access.
All outputs (including error identities) must remain private.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/research"))
from audit_splits import verify as verify_audit
from goodsai.contracts import Product
from goodsai.config import LLM_EXTENSIONS
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.silver_comparison import paired_changes
from goodsai.silver_evaluate import bootstrap, evaluate_rows
from goodsai.silver_prepare import SEED, dump, unique, verify_bundle, write_rows
from goodsai.silver_prepare import role as frozen_role


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def private_output(path):
    path = path.absolute()
    if path.is_symlink() or path.exists() or not path.resolve().is_relative_to((ROOT / "outputs").resolve()):
        raise ValueError("new_private_outputs_directory_required")
    path.mkdir(parents=True, mode=0o700)
    return path.resolve()


def check_population(bundle, audit, expected_hash, sources):
    manifest = verify_bundle(bundle)
    if digest(bundle / "manifest.json") != expected_hash:
        raise ValueError("frozen_bundle_hash_mismatch")
    verify_audit(audit)
    if digest(audit / "audit.summary.json") != manifest["source_sha256"]["audit"]:
        raise ValueError("audit_not_bound_to_bundle")
    policy = json.loads((bundle / "policy.json").read_text(encoding="utf-8"))
    # The policy records all actual preparation sources, including exposure ledgers.
    # Never read reserve contents here; the audit verifies its original checksum.
    paths = {name: Path(path) for name, path in sources.items()}
    paths["audit"] = audit / "audit.summary.json"
    if set(paths) != set(policy["sources"]):
        raise ValueError("all_frozen_source_paths_required")
    if policy["sources"] != manifest["source_sha256"]:
        raise ValueError("source_policy_manifest_mismatch")
    for name, checksum in policy["sources"].items():
        if digest(paths[name]) != checksum:
            raise ValueError("preparation_source_changed")
    members = unique(read_jsonl(audit / "membership.jsonl"))
    eligible = unique(read_jsonl(audit / "eligible.split_manifest.jsonl"))
    protected = {m["family_id"] for m in members.values() if m["split"] == "test_reserved"}
    inputs = unique(read_jsonl(bundle / "input.jsonl"))
    refs = unique(read_jsonl(bundle / "reference.jsonl"))
    metas = unique(read_jsonl(bundle / "metadata.jsonl"))
    if inputs.keys() != refs.keys() or inputs.keys() != metas.keys():
        raise ValueError("frozen_population_mismatch")
    for sku, row in inputs.items():
        Product.from_dict(row)
        member, meta = eligible.get(sku), metas[sku]
        if (not member or member["split"] not in {"development", "validation"}
                or member["family_id"] in protected or meta["family_id"] != member["family_id"]
                or meta["original_split"] != member["split"]
                or meta["role"] != frozen_role(member["family_id"], member["split"])
                or meta["evaluation_role"] != "development_feedback"):
            raise ValueError("forbidden_or_mismatched_family")
    # Existing frozen screening must be byte-equivalent to a subset of Product rows.
    screening = unique(read_jsonl(bundle / "llm_screening.input.jsonl"))
    families = set()
    for sku, row in screening.items():
        if row != inputs.get(sku) or metas[sku]["original_split"] != "development":
            raise ValueError("invalid_screening_population")
        family = metas[sku]["family_id"]
        if family in families:
            raise ValueError("duplicate_screening_family")
        families.add(family)
    return policy, list(inputs.values()), list(refs.values()), list(metas.values())




WORKER = """
import json,sys
from pathlib import Path
from goodsai.contracts import load_config
from goodsai.cli import predict
config=load_config(sys.argv[1])
if config.get('runtime',{}).get('llm',{}).get('enabled',False):
    raise ValueError('rules_only_required')
for name in ('cold','warm'):
    predict(Path(sys.argv[2]),Path(sys.argv[3])/(name+'.jsonl'),config)
"""


def runtime_run(sha, config, input_path, output):
    output.mkdir()
    # Real detached worktrees are essential: identity() resolves Git from cwd.
    with tempfile.TemporaryDirectory(prefix="goodsai-baseline-") as tmp:
        checkout = Path(tmp) / "checkout"
        subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(checkout), sha],
                       check=True, capture_output=True)
        try:
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("GOODSAI_", "OPENAI_"))}
            env.update(PYTHONPATH=str(checkout / "src"), PYTHONDONTWRITEBYTECODE="1",
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            result = subprocess.run([sys.executable, "-c", WORKER, str(config), str(input_path), str(output)],
                                    cwd=checkout, env=env, timeout=3600, capture_output=True)
            if result.returncode:
                # Do not forward arbitrary child output, which could include card content.
                raise ValueError("isolated_runtime_failed_" + sha[:12])
            for name in ("cold", "warm"):
                m = json.loads((output / (name + ".manifest.json")).read_text(encoding="utf-8"))
                if m["git_commit"] != sha or m["git_dirty"] or m["llm_calls"]:
                    raise ValueError("runtime_identity_or_route_mismatch")
            if digest(output / "cold.jsonl") != digest(output / "warm.jsonl"):
                raise ValueError("non_deterministic_runtime")
        finally:
            subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(checkout)],
                           check=True, capture_output=True)


def shared_rules_config(config):
    """Remove only default, unused LLM extensions unknown to historical loaders.

    Both runtimes receive this exact same file; the current loader restores its
    own default extension keys. No category, dictionary or rule value changes.
    """
    result = deepcopy(config)
    llm = result.get("runtime", {}).get("llm", {})
    for key, default in LLM_EXTENSIONS.items():
        if key in llm:
            if llm[key] != default:
                raise ValueError("non_default_llm_extension_in_rules_comparison")
            del llm[key]
    return result


def run(args):
    if not 100 <= args.repeats <= 10000:
        raise ValueError("invalid_bootstrap_repeats")
    bundle, audit = args.bundle.resolve(), args.audit.resolve()
    sources = {}
    for entry in args.source:
        name, sep, path = entry.partition("=")
        if not sep or not name or not path or name in sources or name == "audit":
            raise ValueError("invalid_or_duplicate_source")
        sources[name] = path
    policy, inputs, refs, metas = check_population(bundle, audit, args.bundle_sha256, sources)
    baseline = git("rev-parse", args.baseline + "^{commit}")
    candidate = git("rev-parse", args.candidate + "^{commit}")
    output = private_output(args.output_dir)
    dump(output / "config.json", shared_rules_config(policy["config"]))
    freeze = {"schema": "goodsai-frozen-comparison-1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "baseline_sha": baseline, "candidate_sha": candidate,
              "evaluator_checkout_sha": git("rev-parse", "HEAD"),
              "evaluator_checkout_dirty": bool(git("status", "--porcelain")),
              "bundle_manifest_sha256": args.bundle_sha256,
              "audit_sha256": digest(audit / "audit.summary.json"), "seed": SEED,
              "bootstrap_repeats": args.repeats, "config_file_sha256": digest(output / "config.json"),
              "shared_config_projection": "only_default_unused_llm_extensions_omitted_for_historical_loader",
              "evaluator_sha256": digest(ROOT / "src/goodsai/silver_evaluate.py"),
              "support_matcher_sha256": digest(ROOT / "src/goodsai/silver_support.py"),
              "driver_sha256": digest(Path(__file__)), "external_calls": "forbidden",
              "regression_gate": "any_new_fp_or_lost_tp_blocks_recommendation",
              "reference_kind": "catalog_silver", "independent_quality": None}
    dump(output / "freeze.json", freeze)  # Before either runtime sees any input.
    reports, pairs, groups, resources = {}, {}, {}, {}
    for name, sha in (("historical", baseline), ("candidate", candidate)):
        target = output / name
        runtime_run(sha, output / "config.json", bundle / "input.jsonl", target)
        report, pair, group = evaluate_rows(inputs, refs, metas, read_predictions(target / "cold.jsonl"),
                                           policy["config"], args.repeats)
        reports[name], pairs[name], groups[name] = report, pair, group
        resources[name] = {}
        for temperature in ("cold", "warm"):
            m = json.loads((target / (temperature + ".manifest.json")).read_text(encoding="utf-8"))
            if m["input_sha256"] != digest(bundle / "input.jsonl"):
                raise ValueError("runtime_input_mismatch")
            resources[name][temperature] = {k: m.get(k) for k in (
                "git_commit", "code_sha256", "config_sha256", "python", "platform", "rows", "elapsed_seconds",
                "cards_per_second_including_io", "extractor_p50_ms", "extractor_p95_ms",
                "peak_process_rss_bytes", "invalid_input_rows", "status_counts", "abstention_reasons")}
        write_rows(target / "pair_diagnostics.jsonl", pair)
    changes, private = paired_changes(pairs["historical"], pairs["candidate"])
    write_rows(output / "changed_pairs.private.jsonl", private)
    regression = bool(changes["counts"].get("new_fp") or changes["counts"].get("lost_tp")
                      or reports["candidate"]["missing_prediction_cards"]
                      or reports["candidate"]["unprocessed_prediction_cards"])
    report = {"reference_kind": "catalog_silver", "evaluation_role": "development_feedback",
              "freeze": freeze, "variants": reports, "paired": changes, "resources": resources,
              "compute_cost_rub": None, "independent_quality": None, "auto_accept": "forbidden",
              "paired_grouped_ci": bootstrap(groups["historical"], args.repeats, other=groups["candidate"]),
              "recommendation": "blocked_regression_requires_defect" if regression else "no_observed_regression_on_this_silver_bundle",
              "limitations": ["Catalog agreement is not human quality; unknown/conflict excluded from assessed precision.",
                              "Cold is first call in an isolated process, not an OS page-cache reset.",
                              "Warm shares process; peak RSS is process high-water mark, not per-request memory."]}
    check_population(bundle, audit, args.bundle_sha256, sources)
    dump(output / "run_stats.json", report)
    lines = ["# Frozen catalog agreement / development feedback", "", freeze["created_utc"], "",
             "Independent quality: N/A. Compute cost: N/A. Auto-accept: forbidden.", "",
             "| Runtime | TP | FP | FN | Agreement F1 |", "|---|---:|---:|---:|---:|"]
    for name, r in reports.items():
        a = r["agreement"]
        lines.append(f"| {name} | {a['tp']} | {a['fp']} | {a['fn']} | {a['f1']} |")
    lines += ["", report["recommendation"], "", json.dumps(changes["counts"], sort_keys=True),
              "", "Per-attribute/category, unknown/conflict, coverage, rare slices and CI: run_stats.json.",
              "Paired identities and prediction files are private. Historical reports were not overwritten."]
    (output / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dump(output / "manifest.json", {"schema": "goodsai-frozen-comparison-output-1", "artifacts": {
        p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob("*"))
        if p.is_file() and not p.name.startswith(".")}})
    return {"status": report["recommendation"], "paired": changes["counts"], "cards": len(inputs)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", required=True, type=Path)
    p.add_argument("--audit", required=True, type=Path)
    p.add_argument("--bundle-sha256", required=True)
    p.add_argument("--source", action="append", default=[], metavar="NAME=PATH",
                   help="Every original policy source except audit; includes exposure ledgers")
    p.add_argument("--baseline", default="f33e3fcd1487a3d82f8ed684ebfaa56d8220f6e4")
    p.add_argument("--candidate", required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--repeats", default=1000, type=int)
    args = p.parse_args()
    print(json.dumps(run(args), sort_keys=True))


if __name__ == "__main__":
    main()
