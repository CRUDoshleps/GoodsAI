"""Manual-reference evaluation. Catalog weak labels are deliberately not accepted as gold."""
from collections import Counter, defaultdict
from pathlib import Path

from goodsai.contracts import Product, validate_prediction
from goodsai.data import read_jsonl, read_predictions
from goodsai.normalize import UNITS, numeric


def ratio(a, b):
    return a / b if b else None


def metrics(c: Counter) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    return dict(c) | {"tp": tp, "fp": fp, "fn": fn,
                      "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
                      "f1": ratio(2 * tp, 2 * tp + fp + fn),
                      "prediction_coverage": ratio(c["predicted"], c["judged"]),
                      "correct_coverage": ratio(tp, c["judged"]),
                      "false_value_rate": ratio(fp, tp + fp)}


def evaluate(predictions: Path, gold: Path | None, config: dict) -> dict:
    if gold is None or not gold.exists():
        return {"evaluation_status": "unavailable", "reason": "manual_gold_missing",
                "precision": None, "recall": None, "f1": None,
                "note": "N/A: no independent manual labels; extraction coverage is not accuracy."}
    pred = {}
    for row in read_predictions(predictions):
        validate_prediction(row, config)
        if row["sku_id"] in pred:
            raise ValueError("Duplicate prediction SKU")
        pred[row["sku_id"]] = row
    counts = defaultdict(Counter)
    score_bins = defaultdict(Counter)
    seen = set()
    pending = excluded = reviewed = missing = invalid = 0
    cards_any = cards_all = 0
    for row in read_jsonl(gold):
        sku = row.get("sku_id")
        if not isinstance(sku, str) or not sku or sku in seen:
            raise ValueError("Invalid or duplicate gold SKU")
        seen.add(sku)
        if row.get("annotation_status") != "reviewed":
            pending += 1
            continue
        if row.get("label_source") != "manual" or not isinstance(row.get("annotator"), str) or not row["annotator"].strip():
            raise ValueError("Reviewed gold requires a manual source and annotator")
        product = Product.from_dict({k: row[k] for k in ["schema_version", "sku_id", "category_id", "title", "description", "seller_attributes", "source_flags"] if k in row})
        requested = config["categories"].get(product.category_id)
        labels = row.get("attributes", [])
        if not requested or [a.get("attribute") for a in labels] != requested:
            raise ValueError("Gold must explicitly label every requested attribute in schema order")
        output = pred.get(sku)
        reviewed += 1
        if output:
            validate_prediction(output, config, product)
            invalid += output["status"] != "processed"
        else:
            missing += 1
        by_attr = {a["attribute"]: a for a in output["attributes"]} if output else {}
        filled = 0
        judged_card = 0
        for label in labels:
            status = label.get("status")
            attr = label["attribute"]
            if status in {"ambiguous", "unjudgeable"}:
                excluded += 1
                continue
            if status not in {"present", "absent"}:
                raise ValueError("Reviewed gold contains an unreviewed attribute")
            if status == "present":
                if not isinstance(label.get("value"), str) or not label["value"]:
                    raise ValueError("Present gold requires a canonical value")
                if label.get("unit") != UNITS.get(attr):
                    raise ValueError("Gold unit does not match category schema")
                if attr in UNITS and numeric(attr, label["value"], label["unit"], config.get("numeric_bounds")) != label["value"]:
                    raise ValueError("Gold numeric value is not canonical")
                evidence = label.get("evidence") or {}
                if (evidence.get("field") not in {"title", "description"}
                        or type(evidence.get("start")) is not int or type(evidence.get("end")) is not int
                        or not 0 <= evidence["start"] < evidence["end"]
                        or not evidence.get("text")
                        or (getattr(product, evidence["field"]) or "")[evidence["start"]:evidence["end"]] != evidence["text"]):
                    raise ValueError("Present manual gold requires exact evidence in the permitted input")
            elif any(label.get(k) is not None for k in ["value", "unit", "evidence"]):
                raise ValueError("Absent gold must not contain a value or evidence")
            got = by_attr.get(attr)
            predicted = bool(got and got.get("value") is not None)
            correct = bool(predicted and status == "present"
                           and (got["value"], got["unit"]) == (label["value"], label.get("unit")))
            delta = Counter(judged=1, predicted=int(predicted), tp=int(correct),
                            fp=int(predicted and not correct), fn=int(status == "present" and not correct),
                            gold_present=int(status == "present"), gold_absent=int(status == "absent"),
                            false_on_absent=int(predicted and status == "absent"))
            for key in ["micro", "attribute:" + attr, "category:" + product.category_id,
                        "category_attribute:" + product.category_id + ":" + attr]:
                counts[key].update(delta)
            if predicted:
                key = f"{int(got['confidence']*10)/10:.1f}"
                score_bins[key].update(predicted=1, correct=int(correct))
            filled += int(predicted)
            judged_card += 1
        cards_any += filled > 0
        cards_all += filled == judged_card and judged_card > 0
    if not reviewed or not counts["micro"]["judged"]:
        return {"evaluation_status": "unavailable", "reason": "no_judged_manual_labels",
                "pending_cards": pending, "excluded_pairs": excluded,
                "precision": None, "recall": None, "f1": None}
    report = {k: metrics(v) for k, v in sorted(counts.items())}
    f1s = [r["f1"] for k, r in report.items() if k.startswith("attribute:") and r["f1"] is not None]
    return {"evaluation_status": "manual_reference", "reviewed_cards": reviewed,
            "pending_cards": pending, "excluded_pairs": excluded, "missing_prediction_cards": missing,
            "unprocessed_prediction_cards": invalid, "metrics": report,
            "macro_attribute_f1": sum(f1s) / len(f1s) if f1s else None,
            "card_coverage": ratio(cards_any, reviewed), "complete_judged_card_coverage": ratio(cards_all, reviewed),
            "heuristic_score_bins": {k: dict(v) | {"precision": ratio(v["correct"], v["predicted"])}
                                     for k, v in sorted(score_bins.items())},
            "calibration_status": "not_calibrated", "normalization": "Exact canonical value and unit comparison; no separate span-conditioned metric yet.",
            "uncertainty": "Confidence intervals not implemented in E1; small manual sets require cautious interpretation."}
