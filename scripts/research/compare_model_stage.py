"""Offline A/B/C comparison on an explicitly reviewed split; never opens test.

A: git snapshot; B: frozen current code with only model generation disabled;
C: frozen current code. The experimental override for B is not a runtime option.
All real inputs, frozen packages, predictions and per-card deltas stay in outputs.
"""
import argparse
from collections import Counter
from contextlib import nullcontext
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def rows(path):
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError("Blank JSONL row")
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("Expected JSONL objects")
            yield row


def package_hashes(package):
    package = Path(package)
    return {str(p.relative_to(package)).replace("\\", "/"): sha(p)
            for p in sorted(package.rglob("*")) if p.is_file() and p.suffix in {".py", ".json", ".jsonl"}}


def check_configs(baseline, current, allow_dictionary_changes=False):
    """Keep the output schema fixed; dictionary comparisons require opt-in."""
    if any(current[k] != baseline[k] for k in ["schema_version", "categories"]):
        raise ValueError("Comparison requires the same schema and categories")
    changed = [k for k in ["brands", "colors", "brand_subbrands", "color_modifiers"]
               if current.get(k) != baseline.get(k)]
    if changed and not allow_dictionary_changes:
        raise ValueError("Dictionary/policy differences require --allow-dictionary-changes")
    return changed


def _predict_worker(package_root, variant, input_path, output):
    sys.path.insert(0, str(package_root))
    from goodsai.cli import predict
    from goodsai.contracts import load_config
    from goodsai.rules import Rules
    config = load_config()
    if variant == "B":
        config = config | {"rules_version": config["rules_version"] + ":model-disabled-ablation",
                           "experiment_ablation": "disable_model_generation_only"}
    save(output.parent / "effective_config.json", config)
    # Distinct effective config gives B a distinct run_id despite shared source.
    control = patch.object(Rules, "models", return_value=()) if variant == "B" else nullcontext()
    with control:
        report = predict(input_path, output, config)
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))


def verdict(label, got):
    if label["status"] in {"ambiguous", "unjudgeable"}:
        return "excluded"
    value = (got["value"], got["unit"]) if got and got["value"] is not None else None
    if label["status"] == "present":
        return "TP" if value == (label["value"], label["unit"]) else "FP+FN" if value else "FN"
    return "FP" if value else "TN"


def compare(gold, variants, transitions=(("A", "B"), ("B", "C"), ("A", "C"))):
    """Exact per-pair transitions, retaining excluded pairs without scoring them."""
    changes = []
    for reference in gold:
        sku = reference["sku_id"]
        for label in reference["attributes"]:
            attr = label["attribute"]
            got = {v: next(a for a in by_sku[sku]["attributes"] if a["attribute"] == attr)
                   for v, by_sku in variants.items()}
            for before, after in transitions:
                if got[before] != got[after]:
                    changes.append({"sku_id": sku, "category_id": reference["category_id"],
                                    "attribute": attr, "transition": before + "->" + after,
                                    "gold_status": label["status"], "gold_value": label["value"],
                                    "before_verdict": verdict(label, got[before]),
                                    "after_verdict": verdict(label, got[after]),
                                    "before": got[before], "after": got[after]})
    return changes


def run(gold_path, output_dir, split="development", baseline_ref="5f77d81", freeze_from=None,
        historical=None, repeats=3, previous_run=None, feedback_reference=False,
        allow_dictionary_changes=False):
    """Never choose rules from labels: this function only freezes/runs/evaluates."""
    if split not in {"development", "validation"} or repeats < 1:
        raise ValueError("Only development/validation and positive repeats are allowed")
    if (split == "validation") != (freeze_from is not None):
        raise ValueError("Validation requires --freeze-from a completed development run; development creates it")
    if feedback_reference and split != "validation":
        raise ValueError("Feedback flag is for the previously inspected validation reference")
    gold_path, output_dir = Path(gold_path).resolve(), Path(output_dir).resolve()
    if any(a.lower() == "data" and b.lower() == "raw" for a, b in zip(output_dir.parts, output_dir.parts[1:])):
        raise ValueError("Output must not be inside data/raw")
    gold_hash = sha(gold_path)
    protected = {str(gold_path): gold_hash}
    if historical:
        historical = Path(historical).resolve()
        protected[str(historical)] = sha(historical)
    previous_manifest = None
    if previous_run:
        previous_run = Path(previous_run).resolve()
        previous_manifest_path = previous_run / "experiment.manifest.json"
        previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
        if (previous_manifest["status"] != "completed" or previous_manifest["split"] != split
                or previous_manifest["reference"]["sha256"] != gold_hash):
            raise ValueError("Previous run must use the same completed reference/split")
        protected[str(previous_manifest_path)] = sha(previous_manifest_path)
        protected[str(previous_run / "C/predictions.jsonl")] = sha(previous_run / "C/predictions.jsonl")
    gold = list(rows(gold_path))
    if not gold:
        raise ValueError("Empty reviewed reference")
    ids, groups = set(), set()
    for row in gold:
        if (row.get("split") != split or row.get("annotation_status") != "reviewed"
                or row.get("label_source") != "manual" or not row.get("group_id")):
            raise ValueError("Expected reviewed manual reference with the requested split/group")
        if row["sku_id"] in ids:
            raise ValueError("Duplicate reference SKU")
        ids.add(row["sku_id"])
        groups.add(row["group_id"])

    output_dir.mkdir(parents=True, exist_ok=False)
    snapshots = output_dir / "snapshots"
    snapshots.mkdir()
    if freeze_from:
        previous = Path(freeze_from).resolve()
        frozen = json.loads((previous / "experiment.manifest.json").read_text(encoding="utf-8"))
        if frozen["split"] != "development" or frozen["status"] != "completed":
            raise ValueError("Freeze source must be a completed development run")
        if ids & set(frozen["sku_ids"]) or groups & set(frozen["group_ids"]):
            raise ValueError("Development/validation SKU or group overlap")
        for variant in ["A", "C"]:
            source = previous / "snapshots" / variant / "src" / "goodsai"
            if package_hashes(source) != frozen["snapshots"][variant]:
                raise ValueError("Frozen package was modified")
            shutil.copytree(source, snapshots / variant / "src" / "goodsai", ignore=shutil.ignore_patterns("__pycache__"))
        baseline_commit = frozen["baseline_commit"]
    else:
        baseline_commit = subprocess.check_output(["git", "rev-parse", "--verify", baseline_ref + "^{commit}"],
                                                  cwd=ROOT, text=True).strip()
        archive = subprocess.check_output(["git", "archive", baseline_commit, "src/goodsai"], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(snapshots / "A", filter="data")
        shutil.copytree(ROOT / "src/goodsai", snapshots / "C/src/goodsai",
                        ignore=shutil.ignore_patterns("__pycache__"))
    packages = {v: snapshots / v / "src" / "goodsai" for v in ["A", "C"]}
    snapshot_hashes = {v: package_hashes(p) for v, p in packages.items()}
    if snapshot_hashes["C"] != package_hashes(ROOT / "src/goodsai"):
        raise ValueError("Working package differs from frozen C; do not tune after validation freeze")

    # Projection is an allowlist. No gold or grouping metadata goes to predict.
    from goodsai.contracts import Product, load_config
    from goodsai.data import read_predictions
    from goodsai.evaluate import evaluate
    from goodsai.runtime import identity
    config = load_config(str(packages["C"] / "baseline.json"))
    baseline_config = json.loads((packages["A"] / "baseline.json").read_text(encoding="utf-8"))
    dictionary_changes = check_configs(baseline_config, config, allow_dictionary_changes)
    inputs = []
    for row in gold:
        inputs.append(Product.from_dict({k: row[k] for k in ["schema_version", "sku_id", "category_id", "title",
                                                            "description", "seller_attributes", "source_flags"] if k in row}).as_dict())
    input_path = output_dir / "input.jsonl"
    input_path.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in inputs), encoding="utf-8")
    metrics, variants, reports, timings = {}, {}, {}, {}
    for v in ["A", "B", "C"]:
        folder = output_dir / v
        folder.mkdir()
        package = packages["A" if v == "A" else "C"]
        timings[v] = []
        for repeat in range(repeats):
            target = folder / ("predictions.jsonl" if not repeat else f"repeat-{repeat}.jsonl")
            started = time.perf_counter()
            result = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "_predict",
                                     str(package.parent), v, str(input_path), str(target)],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            if result.returncode:
                raise ValueError(f"Variant {v} failed (see local worker stderr): {result.stderr}")
            report = json.loads(result.stdout)
            timings[v].append({"process_seconds_including_startup": time.perf_counter() - started,
                               "batch_seconds": report["elapsed_seconds"],
                               "p50_ms": report["extractor_p50_ms"], "p95_ms": report["extractor_p95_ms"],
                               "peak_process_rss_bytes": report["peak_process_rss_bytes"]})
            if not repeat:
                reports[v] = report
            elif sha(target) != sha(folder / "predictions.jsonl"):
                raise ValueError(f"Variant {v} was not byte-deterministic")
        prediction = folder / "predictions.jsonl"
        entries = list(read_predictions(prediction))
        variants[v] = {p["sku_id"]: p for p in entries}
        if len(entries) != len(variants[v]) or set(variants[v]) != ids:
            raise ValueError("Prediction SKU set differs from reference")
        metrics[v] = evaluate(prediction, gold_path, config)
        if metrics[v].get("evaluation_status") != "manual_reference":
            raise ValueError("Reference did not yield judged metrics")
        save(folder / "metrics.json", metrics[v])
    changes = compare(gold, variants)
    (output_dir / "pair-deltas.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False, allow_nan=False) + "\n" for c in changes), encoding="utf-8")
    previous_comparison = None
    if previous_run:
        if sha(input_path) != previous_manifest["input_sha256"]:
            raise ValueError("Previous run used different text-only inputs")
        previous_rows = list(read_predictions(previous_run / "C/predictions.jsonl"))
        old = {r["sku_id"]: r for r in previous_rows}
        if len(old) != len(previous_rows) or set(old) != ids:
            raise ValueError("Previous predictions have a different SKU set")
        previous_metrics = evaluate(previous_run / "C/predictions.jsonl", gold_path, config)
        delta = compare(gold, {"previous_C": old, "C": variants["C"]}, (("previous_C", "C"),))
        (output_dir / "previous-deltas.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False, allow_nan=False) + "\n" for c in delta), encoding="utf-8")
        previous_comparison = {
            "run": str(previous_run), "previous_metrics": previous_metrics,
            "quality_transitions": dict(Counter(c["before_verdict"] + "->" + c["after_verdict"] for c in delta)),
            "lost_tp": sum(c["before_verdict"] == "TP" and c["after_verdict"] != "TP" for c in delta),
            "new_fp": sum(c["after_verdict"] in {"FP", "FP+FN"} and c["before_verdict"] not in {"FP", "FP+FN"} for c in delta)}
    historical_check = None
    if historical:
        old = {r["sku_id"]: r for r in read_predictions(historical) if r["sku_id"] in ids}
        # Runtime identity changed since reviewed-v2. Compare domain results, not run_id.
        same = lambda r: {k: value for k, value in r.items() if k != "run_id"}
        historical_check = set(old) == ids and all(same(old[k]) == same(variants["A"][k]) for k in ids)
        if not historical_check:
            raise ValueError("A differs from historical domain predictions; explain before reporting delta")
    for path, fingerprint in protected.items():
        if sha(path) != fingerprint:
            raise ValueError("A protected source changed during the experiment")
    for v, package in packages.items():
        if package_hashes(package) != snapshot_hashes[v]:
            raise ValueError("Frozen package changed during the experiment")
    unrelated_changes = [c for c in changes if c["transition"] == "A->C" and c["attribute"] != "model"]
    summary = {v: {"micro": metrics[v]["metrics"]["micro"],
                    "model": metrics[v]["metrics"]["attribute:model"],
                    "category": {k: m for k, m in metrics[v]["metrics"].items() if k.startswith("category:")}}
               for v in metrics}
    save(output_dir / "summary.json", {"split": split, "variants": summary,
                                       "reference_use": "development_feedback" if feedback_reference else split,
                                       "previous_comparison": previous_comparison,
                                       "non_model_changes": len(unrelated_changes),
                                       "historical_A_matches": historical_check,
                                       "llm_calls": 0, "llm_tokens": 0, "api_cost_rub": 0,
                                       "latency": timings, "timing_note": "Small split, descriptive only; no SLA"})
    manifest = {"status": "completed", "split": split, "baseline_commit": baseline_commit,
                "allow_dictionary_changes": allow_dictionary_changes, "dictionary_changes": dictionary_changes,
                "reference_use": "development_feedback" if feedback_reference else split,
                "previous_comparison": previous_comparison,
                "reference": {"path": str(gold_path), "sha256": gold_hash},
                "input_sha256": sha(input_path), "sku_ids": sorted(ids), "group_ids": sorted(groups),
                "snapshots": snapshot_hashes, "freeze_from": str(freeze_from) if freeze_from else None,
                "runner_sha256": sha(__file__), "evaluation_identity": identity(config),
                "variant_modes": {"A": "baseline git snapshot", "B": "C with Rules.models disabled; distinct config/run_id",
                                  "C": "frozen current rules"},
                "prediction_reports": reports, "repeats": repeats,
                "protected_sources": protected, "historical_A_matches": historical_check,
                "independent_reference": False,
                "artifacts": {str(p.relative_to(output_dir)).replace("\\", "/"): sha(p)
                              for p in sorted(output_dir.rglob("*")) if p.is_file()
                              and p.suffix in {".json", ".jsonl"}}}
    save(output_dir / "experiment.manifest.json", manifest)
    return {"output_dir": str(output_dir), "split": split, "variants": summary,
            "non_model_changes": len(unrelated_changes), "historical_A_matches": historical_check}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_predict":
        _predict_worker(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "validation"], default="development")
    parser.add_argument("--baseline-ref", default="5f77d81")
    parser.add_argument("--freeze-from", type=Path)
    parser.add_argument("--historical", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--previous-run", type=Path, help="Compare C against a preserved run on the same reference")
    parser.add_argument("--feedback-reference", action="store_true", help="Mark validation used to fix known errors")
    parser.add_argument("--allow-dictionary-changes", action="store_true",
                        help="Explicitly compare approved dictionary/policy changes with an unchanged output schema")
    args = parser.parse_args()
    try:
        result = run(args.gold, args.output_dir, args.split, args.baseline_ref,
                     args.freeze_from, args.historical, args.repeats, args.previous_run, args.feedback_reference,
                     args.allow_dictionary_changes)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"model comparison: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
