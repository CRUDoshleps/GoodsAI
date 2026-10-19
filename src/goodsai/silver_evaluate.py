"""Catalog agreement diagnostics, deliberately separate from manual-gold scoring."""
from collections import Counter, defaultdict
import math
import random

from goodsai.contracts import Product, validate_prediction
from goodsai.silver_prepare import SEED, unique


def fraction(a, b):
    return a / b if b else None


def metrics(count):
    tp, fp, fn = (count.get(k, 0) for k in ("tp", "fp", "fn"))
    return dict(count) | {"tp": tp, "fp": fp, "fn": fn,
        "precision": fraction(tp, tp + fp), "recall": fraction(tp, tp + fn),
        "f1": fraction(2 * tp, 2 * tp + fp + fn),
        "recall_supported": fraction(count.get("tp_supported", 0), count.get("known_supported", 0)),
        "coverage_all_requested": fraction(count.get("predicted", 0), count.get("requested", 0)),
        "assessed_candidate_fraction": fraction(count.get("assessed_candidates", 0), count.get("predicted", 0))}


def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    return values[low] + (values[high] - values[low]) * (pos - low)


def bootstrap(group_counts, repeats=1000, seed=SEED, other=None):
    """Paired delta uses identical group draws; no SKU-level pseudo-replication."""
    if repeats < 100 or repeats > 10000:
        raise ValueError("invalid_bootstrap_repeats")
    keys = sorted(group_counts)
    if other is not None and set(other) != set(keys):
        raise ValueError("paired_family_population_mismatch")
    if len(keys) < 20:
        return {"status": "insufficient_groups", "groups": len(keys), "intervals": None}
    generator = random.Random(seed)
    columns = ("tp", "fp", "fn", "tp_supported", "known_supported")
    matrix = [tuple(group_counts[key].get(col, 0) for col in columns) for key in keys]
    other_matrix = [tuple(other[key].get(col, 0) for col in columns) for key in keys] if other is not None else None
    samples = defaultdict(list)
    for _ in range(repeats):
        indices = generator.choices(range(len(keys)), k=len(keys))
        counts = {col: sum(matrix[i][j] for i in indices) for j, col in enumerate(columns)}
        values = metrics(counts)
        other_values = metrics({col: sum(other_matrix[i][j] for i in indices) for j, col in enumerate(columns)}) if other is not None else None
        for name in ("precision", "recall", "f1", "recall_supported"):
            value = values[name]
            if value is not None and (other_values is None or other_values[name] is not None):
                samples[name].append(value if other_values is None else other_values[name] - value)
    return {"status": "paired_group_bootstrap" if other is not None else "group_bootstrap",
        "groups": len(keys), "repeats": repeats, "confidence_level": .95, "seed": seed,
        "intervals": {name: {"lower": quantile(values, .025), "upper": quantile(values, .975),
                             "valid_replicates": len(values)} for name, values in samples.items()}}


def evaluate_rows(inputs, references, metadata, predictions, config, repeats=1000):
    products, refs, metas, preds = map(unique, [inputs, references, metadata, predictions])
    if not products or products.keys() != refs.keys() or products.keys() != metas.keys() or preds.keys() - products.keys():
        raise ValueError("silver_population_mismatch")
    all_counts, weighted = Counter(), Counter()
    slices = defaultdict(lambda: defaultdict(Counter))
    groups = defaultdict(Counter)
    weighted_groups = defaultdict(Counter)
    private_pairs = []
    frequency = Counter()
    for sku, reference in refs.items():
        if metas[sku]["role"] == "fit":
            frequency.update((reference["category_id"], a["attribute"], a["value"]) for a in reference["attributes"] if a["status"] == "known")
    traffic_available = all(m.get("traffic") is not None for m in metas.values())
    traffic_missing = any(m.get("traffic") is None for m in metas.values())
    if traffic_missing and any(m.get("traffic") is not None for m in metas.values()):
        raise ValueError("partial_traffic_population")
    missing_cards = error_cards = 0
    for sku, input_row in products.items():
        product = Product.from_dict(input_row)
        ref, meta, pred = refs[sku], metas[sku], preds.get(sku)
        if ref.get("reference_kind") != "catalog_silver" or ref["category_id"] != product.category_id or meta["category_id"] != product.category_id:
            raise ValueError("invalid_silver_reference_identity")
        expected = config["categories"].get(product.category_id, [])
        if [a["attribute"] for a in ref["attributes"]] != expected:
            raise ValueError("incomplete_silver_schema")
        if pred is not None:
            validate_prediction(pred, config, product)
        else:
            missing_cards += 1
        if pred and pred["status"] != "processed":
            error_cards += 1
        values = {a["attribute"]: a for a in pred["attributes"]} if pred else {}
        weight = meta.get("traffic")
        if weight is not None and (type(weight) not in (int, float) or not math.isfinite(weight) or weight < 0):
            raise ValueError("invalid_traffic_weight")
        if not isinstance(meta.get("family_id"), str) or not meta["family_id"]:
            raise ValueError("missing_family")
        for label in ref["attributes"]:
            attr = label["attribute"]
            if label["status"] not in {"known", "unknown", "conflict"} or label["support"]["state"] not in {"supported", "unsupported", "unknown"}:
                raise ValueError("invalid_reference_state")
            if label["status"] == "known" and (not isinstance(label["value"], str) or not label["value"]):
                raise ValueError("invalid_known_reference")
            if label["status"] == "known" and label["support"]["state"] == "supported":
                e = label["support"].get("evidence")
                if not isinstance(e, dict) or e.get("field") not in {"title", "description"}:
                    raise ValueError("invalid_support_evidence")
                raw = getattr(product, e["field"]) or ""
                if type(e.get("start")) is not int or type(e.get("end")) is not int or not 0 <= e["start"] < e["end"] <= len(raw) or raw[e["start"]:e["end"]] != e.get("text"):
                    raise ValueError("invalid_support_evidence")
            if label["status"] != "known" and label["value"] is not None:
                raise ValueError("unresolved_reference_contains_value")
            candidate = values.get(attr)
            filled = candidate is not None and candidate["value"] is not None
            known = label["status"] == "known"
            supported = known and label["support"]["state"] == "supported"
            correct = filled and known and (candidate["value"], candidate["unit"]) == (label["value"], label["unit"])
            count = Counter(requested=1, predicted=int(filled), known=int(known),
                unknown=int(label["status"] == "unknown"), conflict=int(label["status"] == "conflict"),
                assessed_candidates=int(filled and known), unassessed_candidates=int(filled and not known),
                tp=int(correct), fp=int(filled and known and not correct), fn=int(known and not correct),
                known_supported=int(supported), tp_supported=int(correct and supported),
                support_unknown=int(known and label["support"]["state"] == "unknown"),
                support_unsupported=int(known and label["support"]["state"] == "unsupported"),
                mismatched_supported=int(filled and supported and not correct),
                review=int(filled), abstain=int(not filled))
            all_counts.update(count)
            groups[meta["family_id"]].update(count)
            if traffic_available:
                weighted.update({k: v * weight for k, v in count.items()})
                weighted_groups[meta["family_id"]].update({k: v * weight for k, v in count.items()})
            method = candidate["method"] if filled else "abstain"
            category = product.category_id
            keys = {"attribute": attr, "category": category, "category_attribute": category + ":" + attr,
                "role": meta["role"], "text": meta["text_slice"], "method": method,
                "reference_frequency": "unknown" if not known else "frequent" if frequency[(category, attr, label["value"])] >= 5 else "rare"}
            if meta.get("seller"):
                keys["seller_private"] = meta["seller"]
            for dimension, key in keys.items():
                slices[dimension][key].update(count)
            private_pairs.append({"sku_id": sku, "family_id": meta["family_id"], "category_id": category,
                "attribute": attr, "role": meta["role"], "reference_status": label["status"],
                "support": label["support"]["state"], "correct": bool(correct) if filled and known else None,
                "heuristic_score": candidate["confidence"] if filled else None,
                "method": method, "evidence_field": candidate["evidence"]["field"] if filled else None,
                "reason_count": len(candidate["reason_codes"]) if filled else 0,
                "counts": dict(count)})
    report = {"reference_kind": "catalog_silver", "evaluation_role": "development_feedback",
        "quality_claim": "agreement_with_noisy_catalog_not_independent_human_quality",
        "cards": len(products), "missing_prediction_cards": missing_cards, "unprocessed_prediction_cards": error_cards,
        "agreement": metrics(all_counts), "traffic_agreement": metrics(weighted) if traffic_available else None,
        "traffic_status": "available" if traffic_available else "unavailable",
        "per_attribute": {k: metrics(v) for k, v in slices["attribute"].items()},
        "per_category": {k: metrics(v) for k, v in slices["category"].items()},
        "slices": {dim: {k: metrics(v) for k, v in values.items()} for dim, values in slices.items() if dim != "seller_private"},
        "seller_slices": {"known_sellers": len(slices["seller_private"]),
            "groups_under_20_requested_pairs": sum(c["requested"] < 20 for c in slices["seller_private"].values()),
            "macro_f1": _mean(metrics(c)["f1"] for c in slices["seller_private"].values())},
        "macro_attribute_f1": _mean(metrics(c)["f1"] for c in slices["attribute"].values()),
        "macro_category_f1": _mean(metrics(c)["f1"] for c in slices["category"].values()),
        "grouped_ci": bootstrap(groups, repeats=repeats),
        "traffic_grouped_ci": bootstrap(weighted_groups, repeats=repeats) if traffic_available else None,
        "support_status": "lexical_matcher_pending_human_audit",
        "independent_precision": None, "auto_accept": "forbidden"}
    return report, private_pairs, dict(groups)


def _mean(values):
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None
