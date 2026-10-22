"""Frozen development-only confidence experiment; no external calls or runtime training."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import time

from goodsai.confidence import VERSION, contextual_score, normalized, row_features
from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.data import digest, preparation_directory, read_jsonl, write_json, write_line
from goodsai.evaluate import evaluate
from goodsai.silver_calibration import fit_logistic, logit, reliability, sigmoid
from goodsai.text import visible_view
from goodsai.verify import Extractor
from scripts.release.build_release import code_hash, config_hash

SEED = "eval012-context-v1"
THRESHOLDS = (.5, .75, .8, .85, .9, .95, .97)
ROOT = Path(__file__).resolve().parents[2]
INPUT_FIELDS = ("schema_version", "sku_id", "category_id", "title", "description", "seller_attributes", "source_flags")


def require(value, message):
    if not value:
        raise ValueError(message)


def partition(rows):
    """Union supplied families and normalized text duplicates BEFORE assigning roles."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    keys = {}
    for row in rows:
        family = row.get("family_id") or row.get("group_id")
        require(isinstance(family, str) and family.strip(), "Reviewed input requires a family/group")
        text = "\n".join(normalized(visible_view(row.get(f) or "")[0]) for f in ("title", "description"))
        key = "text:" + hashlib.sha256(text.encode()).hexdigest()
        union("family:" + family, key)
        keys[row["sku_id"]] = key
    result = {}
    for sku, key in keys.items():
        group = find(key)
        bucket = int(hashlib.sha256((SEED + group).encode()).hexdigest(), 16) % 10
        result[sku] = {"group": group, "role": "fit" if bucket < 6 else "calibration" if bucket < 8 else "diagnostic"}
    return result


def summary(pairs, scores):
    if not pairs:
        return {"support": 0, "brier": None, "ece": None, "bins": [], "thresholds": []}
    labels = [int(p["correct"]) for p in pairs]
    measured = reliability(scores, labels)
    for b in measured["bins"]:
        b["observed_correct_rate"] = b.pop("catalog_agreement_rate")
    cutoffs = []
    for threshold in THRESHOLDS:
        selected = [p for p, score in zip(pairs, scores) if score >= threshold]
        correct = sum(p["correct"] for p in selected)
        # Exploratory only; grouped/bias limitations must accompany this bound.
        lower = .05 ** (1 / len(selected)) if selected and correct == len(selected) else None
        cutoffs.append({"threshold": threshold, "selected": len(selected), "correct": correct,
            "errors": len(selected) - correct, "precision": correct / len(selected) if selected else None,
            "candidate_coverage": len(selected) / len(pairs),
            "correct_candidate_retention": correct / sum(labels) if sum(labels) else None,
            "groups": len({p['group'] for p in selected}),
            "all_correct_iid_lower_95": lower, "runtime_acceptance": "forbidden"})
    return {"support": len(pairs), "groups": len({p['group'] for p in pairs}), **measured, "thresholds": cutoffs}


def learned_comparison(pairs):
    parts = {r: [p for p in pairs if p["role"] == r] for r in ("fit", "calibration", "diagnostic")}
    groups = {r: {p["group"] for p in ps} for r, ps in parts.items()}
    require(not any(groups[a] & groups[b] for a, b in (("fit", "calibration"), ("fit", "diagnostic"), ("calibration", "diagnostic"))), "Family leakage")
    support = {r: {"candidates": len(ps), "groups": len(groups[r]),
                   "correct": sum(p["correct"] for p in ps), "incorrect": sum(not p["correct"] for p in ps)} for r, ps in parts.items()}
    enough = (support["fit"]["candidates"] >= 200 and support["fit"]["groups"] >= 20
              and min(support["fit"]["correct"], support["fit"]["incorrect"]) >= 20
              and all(support[r]["groups"] >= 10 and min(support[r]["correct"], support[r]["incorrect"]) > 0 for r in ("calibration", "diagnostic")))
    report = {"support": support, "runtime_use": "forbidden", "independent_reference": False}
    if not enough:
        return report | {"status": "insufficient_data", "reason": "predeclared_class_and_group_support_gate"}, None
    weights = fit_logistic([p["features"] for p in parts["fit"]], [int(p["correct"]) for p in parts["fit"]])
    platt = fit_logistic([{"intercept": 1.0, "logit": logit(weights, p["features"])} for p in parts["calibration"]],
                         [int(p["correct"]) for p in parts["calibration"]])
    diagnostic = parts["diagnostic"]
    fitted = [sigmoid(logit(weights, p["features"])) for p in diagnostic]
    calibrated = [sigmoid(logit(platt, {"intercept": 1.0, "logit": logit(weights, p["features"])})) for p in diagnostic]
    # Per-slice support is reported rather than a pooled score certifying every attribute.
    slices = {}
    for key in sorted({p["category"] + ":" + p["attribute"] for p in pairs}):
        slices[key] = {r: {"count": sum(p["category"] + ":" + p["attribute"] == key for p in ps),
                           "incorrect": sum(p["category"] + ":" + p["attribute"] == key and not p["correct"] for p in ps)} for r, ps in parts.items()}
    return report | {"status": "offline_fitted", "fitted": summary(diagnostic, fitted),
                     "platt": summary(diagnostic, calibrated), "slice_support": slices}, {
        "format": "confidence-offline-1", "weights": weights, "platt": platt, "runtime_use": "forbidden"}


def markdown(report):
    lines = ["# Candidate confidence comparison", "",
        "AI-assisted human-reviewed development; independent_reference=false.",
        "Synthetic tests and catalog quality are separate. No acceptance thresholds enabled.", "",
        "| Variant | Slice | Candidates | Groups | Brier | ECE |",
        "| --- | --- | ---: | ---: | ---: | ---: |"]
    for variant, slices in report['variants'].items():
        for name, s in slices.items():
            lines.append(f"| {variant} | {name} | {s['support']} | {s.get('groups', 0)} | {s['brier']} | {s['ece']} |")
    lines += ["", "Learned comparator: " + report['learned']['status'],
              "Recommendation: " + report['recommendation'], ""]
    lines.extend("- " + note for note in report['limitations'])
    return "\n".join(lines) + "\n"


def run(spec_path, output):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    require(spec.get("version") == "confidence-experiment-1" and spec.get("seed") == SEED
            and spec.get("reference_origin") == "ai_assisted_human_reviewed_development"
            and spec.get("independent_reference") is False, "Explicit development provenance required")
    records, inputs, seen = [], [], set()
    for item in spec["references"]:
        path = (spec_path.parent / item["path"]).resolve()
        require(digest(path) == item["sha256"], "Reference hash mismatch")
        inputs.append(path)
        for row in read_jsonl(path):
            require(row.get("split") == "development" and row.get("annotation_status") == "reviewed"
                    and row.get("label_source") == "manual" and row.get("human_review_status") in {"confirmed", "reviewed"}
                    and row.get("independent_reference") is False, "Only explicitly confirmed development allowed")
            require(row["sku_id"] not in seen, "Duplicate reference SKU")
            seen.add(row["sku_id"])
            records.append(row)
    require(records, "Empty reference")
    assignments = partition(records)
    base = load_config()
    context = deepcopy(base)
    context["runtime"]["confidence"] = {"version": VERSION}
    before, after = Extractor(base), Extractor(context)
    pairs, exclusions = [], defaultdict(int)
    latencies = {"fixed_ms": [], "context_ms": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    with preparation_directory(output, spec_path, *inputs) as stage:
        write_json(stage / "freeze.json", {"spec_sha256": digest(spec_path), "seed": SEED,
                   "references": [x["sha256"] for x in spec["references"]], "assignments": assignments,
                   "code_sha256": code_hash(ROOT), "config_sha256": config_hash(base),
                   "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
        reference = stage / "reference.private.jsonl"
        with reference.open("w", encoding="utf-8") as refs, (stage / "fixed.jsonl").open("w", encoding="utf-8") as f, (stage / "context.jsonl").open("w", encoding="utf-8") as c:
            for row in records:
                product = Product.from_dict({k: row[k] for k in INPUT_FIELDS if k in row})
                start = time.perf_counter(); old = before.predict(product); latencies["fixed_ms"].append((time.perf_counter() - start) * 1000)
                start = time.perf_counter(); new = after.predict(product); latencies["context_ms"].append((time.perf_counter() - start) * 1000)
                stripped = deepcopy(new)
                for a, b in zip(old["attributes"], stripped["attributes"]):
                    b["confidence"] = a["confidence"]
                require(old == stripped, "Scoring changed values/evidence/decisions")
                grouped = defaultdict(list)
                gate = before.gate_factory.create(product)
                for candidate in before.rules.candidates(product):
                    if gate.reason(candidate) is None:
                        grouped[candidate.attribute].append(candidate)
                vectors = row_features(product, old, grouped)
                labels = {a["attribute"]: a for a in row["attributes"]}
                for a in old["attributes"]:
                    label = labels.get(a["attribute"], {})
                    if label.get("status") not in {"present", "absent"} or a["value"] is None:
                        exclusions[label.get("status", "missing") if a["value"] is not None else "abstain"] += 1
                        continue
                    pairs.append({"attribute": a["attribute"], "category": product.category_id,
                        **assignments[product.sku_id], "correct": label["status"] == "present" and (a["value"], a["unit"]) == (label["value"], label.get("unit")),
                        "features": vectors[a["attribute"]], "fixed": a["confidence"], "context": contextual_score(vectors[a["attribute"]])})
                write_line(refs, row); write_line(f, old); write_line(c, new)
        metrics = evaluate(stage / "fixed.jsonl", reference, base)
        # Existing evaluator validates exact source evidence, canonical labels and all requested fields.
        context_metrics = evaluate(stage / "context.jsonl", reference, context)
        require(metrics.get("evaluation_status") == "manual_reference", "No judged reviewed labels")
        require(metrics["metrics"] == context_metrics["metrics"], "Extraction metrics changed")
        report = {"version": "confidence-comparison-1", "cards": len(records), "candidates": len(pairs),
            "reference_origin": spec["reference_origin"], "independent_reference": False,
            "runtime_acceptance": "unchanged_no_new_thresholds", "exclusions": dict(exclusions),
            "values_evidence_decisions_unchanged": True, "extraction_metrics": metrics, "variants": {}, "slices": {}}
        for version in ("fixed", "context"):
            report["variants"][version] = {"reviewed_development_all": summary(pairs, [p[version] for p in pairs]),
                "diagnostic": summary([p for p in pairs if p["role"] == "diagnostic"], [p[version] for p in pairs if p["role"] == "diagnostic"])}
        for dimension in ("attribute", "category"):
            for value in sorted({p[dimension] for p in pairs}):
                subset = [p for p in pairs if p[dimension] == value]
                report["slices"][dimension + ":" + value] = {v: summary(subset, [p[v] for p in subset]) for v in ("fixed", "context")}
        report["learned"], model = learned_comparison(pairs)
        fixed_diag = report["variants"]["fixed"]["diagnostic"]
        context_diag = report["variants"]["context"]["diagnostic"]
        report["context_brier_improved"] = (context_diag["brier"] < fixed_diag["brier"]
                                             if fixed_diag["brier"] is not None else None)
        report["recommendation"] = ("retain_fixed_context_brier_not_improved"
                                    if report["context_brier_improved"] is not True
                                    else "experimental_only_pending_independent_validation")
        report["limitations"] = ["Reviewed development was previously used for rule development; not independent.",
            "Candidate correctness excludes abstentions; extraction P/R/F1 separately includes missing values.",
            "No wrong candidates means error ranking and calibration cannot be established.",
            "Thresholds are descriptive, not authorizations; IID bounds ignore correlated pairs and selection bias.",
            "Family metadata and normalized exact duplicates constrain splits; near-duplicate families require upstream audit."]
        write_json(stage / "report.json", report)
        (stage / "report.md").write_text(markdown(report), encoding="utf-8", newline="\n")
        if model:
            model["provenance"] = {"freeze_sha256": digest(stage / "freeze.json"), "spec_sha256": digest(spec_path)}
            write_json(stage / "model.offline.json", model)
        write_json(stage / "pairs.private.json", {"pairs": pairs})
        write_json(stage / "latency.json", {"environment": "local_cpu_sequential_no_model_calls", "model_calls": 0, "model_cost": 0,
                   **{k: {"n": len(v), "mean": sum(v) / len(v), "p95": sorted(v)[min(len(v)-1, int(.95 * len(v)))]} for k, v in latencies.items()}})
        require(all(digest(p) == item["sha256"] for p, item in zip(inputs, spec["references"])), "Reference changed during run")
        write_json(stage / "manifest.json", {"status": "complete", "files_sha256": {p.name: digest(p) for p in sorted(stage.iterdir())}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.spec, args.output_dir)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, "Confidence comparison failed: " + type(exc).__name__ + "\n")
    print(json.dumps({"cards": report["cards"], "candidates": report["candidates"], "learned_status": report["learned"]["status"]}))


if __name__ == "__main__":
    main()
