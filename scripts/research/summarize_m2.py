"""Postprocess frozen reviewed-development predictions; never runs an extractor.

Writes new slice reports and local diagnostics. Never accepts test references or
changes labels, policies, predictions, runtime or existing experiment artifacts.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.evaluate import metrics


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def index_unique(rows):
    result = {}
    for row in rows:
        if row["sku_id"] in result:
            raise ValueError("Duplicate SKU")
        result[row["sku_id"]] = row
    return result


def aggregate(reference, predictions):
    counts = Counter()
    diagnostics = []
    for row in reference:
        prediction = predictions[row["sku_id"]]
        if prediction["category_id"] != row["category_id"]:
            raise ValueError("Prediction category differs from reference")
        attrs = {a["attribute"]: a for a in prediction["attributes"]}
        any_filled = False
        for label in row["attributes"]:
            attr = label["attribute"]
            got = attrs.get(attr)
            filled = bool(got and got["value"] is not None)
            counts.update(applicable=1, predicted_all=int(filled))
            any_filled |= filled
            status = label["status"]
            if status in {"ambiguous", "unjudgeable"}:
                counts.update(excluded=1, excluded_with_candidate=int(filled))
                outcome = "excluded_candidate" if filled else "excluded_abstention"
            elif status in {"present", "absent"}:
                correct = bool(filled and status == "present"
                               and (got["value"], got["unit"]) == (label["value"], label["unit"]))
                fp, fn = filled and not correct, status == "present" and not correct
                counts.update(judged=1, predicted=int(filled), tp=int(correct), fp=int(fp), fn=int(fn),
                              gold_present=int(status == "present"), gold_absent=int(status == "absent"),
                              false_on_absent=int(filled and status == "absent"))
                outcome = "FP+FN" if fp and fn else "FP" if fp else "FN" if fn else "TP" if correct else "TN"
            else:
                raise ValueError("Reference contains unreviewed label")
            if outcome not in {"TP", "TN"}:
                diagnostics.append({"review_id": row.get("review_id"), "sku_id": row["sku_id"],
                                    "category_id": row["category_id"], "attribute": attr,
                                    "outcome": outcome, "gold_status": status, "gold_value": label["value"],
                                    "prediction": got})
        counts.update(cards=1, cards_with_candidate=int(any_filled))
    result = metrics(counts)
    result.update(judged_fraction=counts["judged"] / counts["applicable"] if counts["applicable"] else None,
                  all_pair_coverage=counts["predicted_all"] / counts["applicable"] if counts["applicable"] else None,
                  all_card_coverage=counts["cards_with_candidate"] / counts["cards"] if counts["cards"] else None)
    return result, diagnostics


def run(experiment, bundle, output):
    experiment, bundle, output = Path(experiment), Path(bundle), Path(output)
    parts = output.resolve().parts
    if any(a.lower() == "data" and b.lower() == "raw" for a, b in zip(parts, parts[1:])):
        raise ValueError("Do not write into data/raw")
    if output.exists():
        raise FileExistsError("Never overwrite a slice report")
    manifest_path = experiment / "experiment.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "completed" or manifest["split"] != "development":
        raise ValueError("Only a completed reviewed development experiment is allowed")
    gold_path = Path(manifest["reference"]["path"])
    if digest(gold_path) != manifest["reference"]["sha256"]:
        raise ValueError("Reference SHA mismatch")
    for name, expected in manifest["artifacts"].items():
        if digest(experiment / name) != expected:
            raise ValueError("Frozen experiment artifact SHA mismatch")
    selection_path = bundle / "selection.manifest.jsonl"
    selection_summary = json.loads((bundle / "selection.summary.json").read_text(encoding="utf-8"))
    if digest(selection_path) != selection_summary["artifacts"][selection_path.name]:
        raise ValueError("Selection SHA mismatch")
    selected = index_unique(r for r in read_jsonl(selection_path) if r["purpose"] == "development")
    reference = list(read_jsonl(gold_path))
    ids = index_unique(reference)
    if ids.keys() != selected.keys():
        raise ValueError("Reference/selected development SKU mismatch")
    cohorts = defaultdict(list)
    for row in reference:
        if row.get("split") != "development" or row.get("annotation_status") != "reviewed" or row.get("label_source") != "manual":
            raise ValueError("Only reviewed manual development is allowed")
        metadata = selected[row["sku_id"]]
        desc = "yes" if bool(row.get("description")) else "no"
        if bool(row.get("description")) != metadata["has_description"]:
            raise ValueError("Description metadata differs from frozen selection")
        keys = ["all", "category:" + row["category_id"], "description:" + desc,
                "category:" + row["category_id"] + ":description:" + desc]
        keys += ["feature:" + feature + ":" + str(present).lower()
                 for feature, present in metadata["features"].items() if feature != "random"]
        for key in keys:
            cohorts[key].append(row)
    protected = {str(p): digest(p) for p in [manifest_path, gold_path, selection_path]}
    reports, diagnostics = {}, []
    for variant in ["A", "B", "C"]:
        predictions = index_unique(read_predictions(experiment / variant / "predictions.jsonl"))
        if predictions.keys() != ids.keys():
            raise ValueError("Prediction/reference SKU mismatch")
        reports[variant] = {}
        for key, rows in sorted(cohorts.items()):
            result, detail = aggregate(rows, predictions)
            reports[variant][key] = result
            if key == "all":
                diagnostics.extend(item | {"variant": variant} for item in detail)
        existing = json.loads((experiment / variant / "metrics.json").read_text(encoding="utf-8"))
        for key in ["tp", "fp", "fn", "judged", "predicted", "gold_present", "gold_absent", "precision", "recall", "f1"]:
            if reports[variant]["all"][key] != existing["metrics"]["micro"][key]:
                raise ValueError("Slice aggregation differs from canonical evaluator")
    for path, old in protected.items():
        if digest(Path(path)) != old:
            raise ValueError("Protected source changed")
    output.mkdir(parents=True, exist_ok=False)
    save(output / "slices.json", {"reference_use": "human_reviewed_ai_assisted_development",
                                "independent_reference": False, "cohorts_overlap": True,
                                "variants": reports})
    (output / "diagnostics.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in diagnostics), encoding="utf-8")
    save(output / "manifest.json", {"status": "completed", "runner_sha256": digest(Path(__file__)),
                                   "protected_sources": protected,
                                   "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()},
                                   "predictions_generated": False, "runtime_changed": False,
                                   "note": "Excluded candidates are diagnostic, not scored TP/FP; features overlap."})
    return {"output": str(output), "C_all": reports["C"]["all"], "cohorts": len(cohorts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.experiment, args.bundle, args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"M2 summary: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
