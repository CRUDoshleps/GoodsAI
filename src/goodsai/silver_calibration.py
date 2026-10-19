"""Offline-only logistic candidate scoring and Platt calibration (no pickle).

Reference labels can be noisy. Scores are diagnostics, not runtime probabilities.
Unknown catalog labels are never negative training examples.
"""
import math


def sigmoid(value):
    return 1 / (1 + math.exp(-max(-35, min(35, value))))


def features(pair):
    return {"intercept": 1.0, "score": pair["heuristic_score"],
            "reason_count": min(pair["reason_count"], 10) / 10,
            "attribute=" + pair["attribute"]: 1.0, "method=" + pair["method"]: 1.0,
            "field=" + str(pair["evidence_field"]): 1.0}


def fit_logistic(vectors, labels, iterations=400):
    names = sorted({name for vector in vectors for name in vector})
    weights = dict.fromkeys(names, 0.0)
    for _ in range(iterations):
        gradient = dict.fromkeys(names, 0.0)
        for vector, label in zip(vectors, labels):
            error = sigmoid(sum(weights[k] * v for k, v in vector.items())) - label
            for key, value in vector.items():
                gradient[key] += error * value / len(labels)
        for key in names:
            gradient[key] += .001 * weights[key] if key != "intercept" else 0
            weights[key] -= .3 * gradient[key]
    return weights


def logit(weights, vector):
    return sum(weights.get(key, 0) * value for key, value in vector.items())


def reliability(scores, labels):
    if not scores:
        return {"brier": None, "ece": None, "bins": []}
    bins = []
    for index in range(10):
        selected = [(p, y) for p, y in zip(scores, labels) if min(int(p * 10), 9) == index]
        n = len(selected)
        bins.append({"lower": index / 10, "upper": (index + 1) / 10, "count": n,
            "mean_score": sum(p for p, _ in selected) / n if n else None,
            "catalog_agreement_rate": sum(y for _, y in selected) / n if n else None})
    return {"brier": sum((p - y) ** 2 for p, y in zip(scores, labels)) / len(scores),
        "ece": sum(b["count"] * abs(b["mean_score"] - b["catalog_agreement_rate"]) for b in bins if b["count"]) / len(scores),
        "bins": bins}


def calibrate(pairs):
    partitions = {role: [p for p in pairs if p["role"] == role and p["correct"] is not None] for role in ["fit", "calibration", "diagnostic"]}
    groups = {role: {p["family_id"] for p in rows} for role, rows in partitions.items()}
    if any(groups[a] & groups[b] for a, b in [("fit", "calibration"), ("fit", "diagnostic"), ("calibration", "diagnostic")]):
        raise ValueError("calibration_family_leakage")
    support = {role: {"pairs": len(rows), "groups": len(groups[role]),
                     "positive": sum(p["correct"] for p in rows), "negative": sum(not p["correct"] for p in rows)} for role, rows in partitions.items()}
    enough = (support["fit"]["pairs"] >= 200 and support["fit"]["groups"] >= 20
        and min(support["fit"]["positive"], support["fit"]["negative"]) >= 20
        and all(support[role]["groups"] >= 10 and support[role]["positive"] > 0 and support[role]["negative"] > 0 for role in ["calibration", "diagnostic"]))
    base = {"reference_kind": "catalog_silver", "support": support, "auto_accept": "forbidden",
            "independent_probability_quality": None, "runtime_changed": False,
            "scope": "rules_only_inference_features_no_targets", "threshold": None}
    if not enough:
        return base | {"status": "insufficient_data", "reason": "predeclared_class_and_group_support_gate"}, None
    train = partitions["fit"]
    weights = fit_logistic([features(p) for p in train], [int(p["correct"]) for p in train])
    cal = partitions["calibration"]
    platt = fit_logistic([{"intercept": 1.0, "logit": logit(weights, features(p))} for p in cal], [int(p["correct"]) for p in cal])
    diagnostic = partitions["diagnostic"]
    labels = [int(p["correct"]) for p in diagnostic]
    raw = reliability([p["heuristic_score"] for p in diagnostic], labels)
    fitted = reliability([sigmoid(logit(weights, features(p))) for p in diagnostic], labels)
    calibrated = reliability([sigmoid(logit(platt, {"intercept": 1.0, "logit": logit(weights, features(p))})) for p in diagnostic], labels)
    improved = calibrated["brier"] < raw["brier"]
    report = base | {"status": "offline_fitted", "method": "logistic_then_platt_separate_groups",
        "diagnostic_raw": raw, "diagnostic_fitted": fitted, "diagnostic_calibrated": calibrated,
        "brier_improved_over_heuristic": improved,
        "recommendation": "shadow_only_pending_human_validation" if improved else "retain_heuristic_no_measured_brier_gain",
        "shadow_at_0_95": {"selection": "fixed_exploratory_not_runtime_threshold",
            "coverage": sum(sigmoid(logit(platt, {"intercept": 1.0, "logit": logit(weights, features(p))})) >= .95 for p in diagnostic) / len(diagnostic),
            "independent_precision": None}}
    model = {"format": "goodsai-offline-silver-logistic-1", "weights": weights, "platt": platt,
             "runtime_use": "forbidden_without_independent_review_and_contract_approval"}
    return report, model
