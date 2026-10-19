"""Offline guard ablation on reviewed development only; no test/LLM access.

Both methods use the same frozen package/candidates. 'before' bypasses only
RelationVerifier construction/reason in the isolated worker, never in CLI/API runtime.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research.compare_model_stage import compare, package_hashes, rows, save, sha, verdict


def worker(package, variant, source, output):
    sys.path.insert(0, str(package))
    from goodsai.cli import predict
    from goodsai.contracts import load_config
    from goodsai.relation import RelationVerifier
    config = load_config() | {"experiment_ablation": "relation:" + variant}
    if variant == "before":
        with patch.object(RelationVerifier, "__init__", return_value=None), patch.object(RelationVerifier, "reason", return_value=None):
            report = predict(source, output, config)
    else:
        report = predict(source, output, config)
    print(json.dumps(report, ensure_ascii=True))


def run(reference, output, repeats=3):
    from goodsai.contracts import Product, load_config
    from goodsai.data import check_output, read_predictions
    from goodsai.evaluate import evaluate, metrics
    reference, output = Path(reference).resolve(), Path(output).resolve()
    if repeats < 1:
        raise ValueError("Positive repeats required")
    # Read only the explicitly supplied development reference. No automatic
    # globbing over gold or test reserves. Validate before creating artifacts.
    original_hash = sha(reference)
    gold = list(rows(reference))
    if not gold or any(r.get("split") != "development" or r.get("annotation_status") != "reviewed"
                       or r.get("label_source") != "manual" or not r.get("annotator")
                       or not (r.get("group_id") or r.get("family_id")) for r in gold):
        raise ValueError("Only explicitly reviewed development reference with groups is allowed")
    if len({r["sku_id"] for r in gold}) != len(gold):
        raise ValueError("Duplicate reference SKU")
    products = [Product.from_dict({k: r[k] for k in ("schema_version", "sku_id", "category_id", "title",
                                                    "description", "seller_attributes", "source_flags") if k in r}) for r in gold]
    check_output(output, reference)
    if "data" in [part.lower() for part in output.parts]:
        raise ValueError("Experiment outputs must not be under data")
    output.mkdir(parents=True, exist_ok=False)
    package = output / "snapshot" / "goodsai"
    shutil.copytree(ROOT / "src" / "goodsai", package, ignore=shutil.ignore_patterns("__pycache__"))
    hashes = package_hashes(package)
    source = output / "input.jsonl"
    source.write_text("".join(json.dumps(p.as_dict(), ensure_ascii=False) + "\n" for p in products), encoding="utf-8")
    reports, variants = {}, {}
    for variant in ("before", "after"):
        folder = output / variant
        folder.mkdir()
        timings = []
        for repeat in range(repeats):
            target = folder / ("predictions.jsonl" if repeat == 0 else f"repeat-{repeat}.jsonl")
            result = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "_worker",
                                     str(package.parent), variant, str(source), str(target)],
                                    capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
            if result.returncode:
                # Do not echo source text or worker stderr into shared logs.
                (folder / "worker.stderr.txt").write_text(result.stderr, encoding="utf-8")
                raise ValueError(f"{variant} worker failed; inspect private worker.stderr.txt")
            info = json.loads(result.stdout)
            timings.append({k: info[k] for k in ("extractor_p50_ms", "extractor_p95_ms", "peak_process_rss_bytes", "elapsed_seconds")})
            if sha(target) != sha(folder / "predictions.jsonl"):
                raise ValueError("Nondeterministic predictions")
        prediction = folder / "predictions.jsonl"
        values = list(read_predictions(prediction))
        variants[variant] = {r["sku_id"]: r for r in values}
        if set(variants[variant]) != {p.sku_id for p in products} or len(values) != len(products):
            raise ValueError("Prediction/reference identity mismatch")
        score = evaluate(prediction, reference, load_config())
        if score["evaluation_status"] != "manual_reference":
            raise ValueError("No judged reference pairs")
        provenance = {}
        for r in gold:
            for label in r["attributes"]:
                if label["status"] in {"ambiguous", "unjudgeable"}:
                    continue
                got = next(a for a in variants[variant][r["sku_id"]]["attributes"] if a["attribute"] == label["attribute"])
                status = verdict(label, got)
                bucket = provenance.setdefault(label.get("label_origin", "other_reviewed"), Counter())
                bucket.update(judged=1, predicted=int(got["value"] is not None),
                              tp=int(status == "TP"), fp=int(status in {"FP", "FP+FN"}),
                              fn=int(status in {"FN", "FP+FN"}))
        reports[variant] = {"evaluation": score, "timings": timings,
                            "provenance_metrics": {k: metrics(v) for k, v in provenance.items()},
                            "abstention_reasons": info["abstention_reasons"], "predictions_sha256": sha(prediction)}
        save(folder / "report.json", reports[variant])
    changes = compare(gold, variants, (("before", "after"),))
    (output / "pair-deltas.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in changes), encoding="utf-8")
    lost = sum(x["before_verdict"] == "TP" and x["after_verdict"] != "TP" for x in changes)
    new_fp = sum(x["after_verdict"] in {"FP", "FP+FN"} and x["before_verdict"] not in {"FP", "FP+FN"} for x in changes)
    if sha(reference) != original_hash or package_hashes(package) != hashes:
        raise ValueError("Reference or frozen code was modified during comparison")
    summary = {"status": "completed", "split": "development", "independent_reference": False,
               "comparison": "same frozen code; before bypasses relation guard only",
               "reference_sha256": original_hash, "package_hashes": hashes,
               "reference_cards": len(gold), "variants": reports,
               "transitions": dict(Counter(x["before_verdict"] + "->" + x["after_verdict"] for x in changes)),
               "lost_tp": lost, "new_fp": new_fp,
               "regression_gate": "pass" if not lost and not new_fp else "review_required",
               "llm_calls": 0, "api_cost": 0, "repeats": repeats}
    save(output / "comparison.json", summary)
    return summary


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        worker(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    result = run(args.reference, args.output_dir, args.repeats)
    print(json.dumps({k: result[k] for k in ("status", "reference_cards", "lost_tp", "new_fp", "regression_gate")}))


if __name__ == "__main__":
    # Isolated workers start with only their script directory on sys.path.
    sys.path.insert(0, str(ROOT))
    main()
