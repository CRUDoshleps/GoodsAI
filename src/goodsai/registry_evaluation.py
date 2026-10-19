"""Explicit schema mapping and private validation report for category candidates.

No test set, silver-to-manual promotion, calibration, or external model calls.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from goodsai.category_registry import Registry
from goodsai.cli import predict
from goodsai.config import _read_json, load_config
from goodsai.contracts import Product
from goodsai.data import digest, read_jsonl
from goodsai.evaluate import evaluate
from goodsai.runtime import identity

PRODUCT_KEYS = ("schema_version", "sku_id", "category_id", "title", "description", "seller_attributes", "source_flags")


def config_hash(config):
    return hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validation_ids(split_path, config):
    registry = config.get("category_registry")
    if not registry or digest(split_path) != registry["provenance"]["split_sha256"]:
        raise ValueError("Validation split must match the frozen registry provenance")
    split = _read_json(split_path.read_text(encoding="utf-8"))
    required = {"schema_version", "train_sha256", "train_sku_ids", "validation_sku_ids", "test_sku_ids"}
    if (not isinstance(split, dict) or set(split) != required or split["schema_version"] != "goodsai-train-split-1"
            or split["train_sha256"] != registry["provenance"]["train_sha256"]):
        raise ValueError("Invalid frozen train/validation split")
    groups = []
    for key in ("train_sku_ids", "validation_sku_ids", "test_sku_ids"):
        values = split[key]
        if (not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("Invalid split IDs")
        groups.append(set(values))
    train, validation, test = groups
    if not train or not validation or train & validation or train & test or validation & test:
        raise ValueError("A nonempty disjoint validation split is required")
    return validation


def validate_mapping(mapping, config):
    if (not isinstance(mapping, dict) or set(mapping) != {"mapping_version", "config_sha256", "categories"}
            or mapping["mapping_version"] != "1" or mapping["config_sha256"] != config_hash(config)
            or not isinstance(mapping["categories"], dict)):
        raise ValueError("Explicit mapping bound to the effective config hash is required")
    for category, fields in mapping["categories"].items():
        if category not in config["categories"] or not isinstance(fields, dict):
            raise ValueError("Mapping category is outside configured schemas")
        if (any(not isinstance(k, str) or not k.strip() or not isinstance(v, str)
                or v not in config["categories"][category] for k, v in fields.items())
                or len(set(fields.values())) != len(fields)):
            raise ValueError("Reference mapping must be one-to-one and target configured fields")
    return mapping


def map_reference(rows, products, mapping, config):
    """Rename labels only; missing labels become unjudgeable, never absent."""
    registry = Registry(config)
    mapped, seen, counts = [], set(), Counter()
    for row in rows:
        sku = row.get("sku_id")
        if not isinstance(sku, str) or sku not in products or sku in seen:
            raise ValueError("Reference must cover exactly the selected validation input")
        seen.add(sku)
        if (row.get("split") != "validation" or row.get("annotation_status") != "reviewed"
                or row.get("label_source") != "manual" or not isinstance(row.get("annotator"), str)
                or not row["annotator"].strip() or not (row.get("group_id") or row.get("family_id"))):
            raise ValueError("Only explicitly reviewed manual validation with group provenance is allowed")
        product = Product.from_dict({k: row[k] for k in PRODUCT_KEYS if k in row})
        if product != products[sku]:
            raise ValueError("Reference text/identity must exactly match the frozen input")
        requested = config["categories"].get(product.category_id)
        fields = mapping["categories"].get(product.category_id)
        if not requested or fields is None:
            raise ValueError("Missing explicit category mapping")
        labels = row.get("attributes")
        if not isinstance(labels, list):
            raise ValueError("Reference attributes must be a list")
        by_target, sources = {}, set()
        for label in labels:
            if not isinstance(label, dict):
                raise ValueError("Reference label must be an object")
            source = label.get("attribute")
            if not isinstance(source, str) or not source or source in sources:
                raise ValueError("Duplicate or invalid source label")
            sources.add(source)
            if source not in fields:
                counts["unmapped_source_labels"] += 1
                continue
            target = fields[source]
            status = label.get("status")
            if status not in {"present", "absent", "ambiguous", "unjudgeable"}:
                raise ValueError("Invalid reviewed label status")
            result = {"attribute": target, "status": status, "value": None, "unit": None, "evidence": None}
            if status == "present":
                value, unit, evidence = label.get("value"), label.get("unit"), label.get("evidence")
                if not isinstance(value, str) or not value or unit != registry.unit(product.category_id, target):
                    raise ValueError("Mapped label value/unit disagrees with schema; conversion requires explicit preparation")
                if (not isinstance(evidence, dict) or evidence.get("field") not in {"title", "description"}
                        or type(evidence.get("start")) is not int or type(evidence.get("end")) is not int
                        or not isinstance(evidence.get("text"), str) or not evidence["text"]
                        or not 0 <= evidence["start"] < evidence["end"]
                        or (getattr(product, evidence["field"]) or "")[evidence["start"]:evidence["end"]] != evidence["text"]):
                    raise ValueError("Mapped present label requires exact original evidence")
                result.update(value=registry.normalize_reference(product.category_id, target, value, unit),
                              unit=unit, evidence={k: evidence[k] for k in ("field", "start", "end", "text")})
            elif status == "absent" and any(label.get(k) is not None for k in ("value", "unit", "evidence")):
                raise ValueError("Absent reference must be empty")
            if "label_origin" in label:
                result["label_origin"] = label["label_origin"]
            by_target[target] = result
            counts["mapped_" + status] += 1
        # Typoed/unused mappings fail instead of silently excluding intended labels.
        if set(fields) - sources:
            raise ValueError("Mapping references a label missing from the reference card")
        ordered = []
        for target in requested:
            label = by_target.get(target)
            if label is None:
                counts["unmapped_target_labels"] += 1
                label = {"attribute": target, "status": "unjudgeable", "value": None, "unit": None,
                         "evidence": None, "reason_codes": ["unmapped_reference_attribute"]}
            ordered.append(label)
        result = product.as_dict() | {"split": "validation", "annotation_status": "reviewed", "label_source": "manual",
            "annotator": row["annotator"], "attributes": ordered,
            "schema_mapping": {"mapping_version": "1", "config_sha256": config_hash(config),
                               "independence": "not_verified_by_mapper"}}
        for key in ("group_id", "family_id"):
            if key in row:
                if not isinstance(row[key], str) or not row[key].strip():
                    raise ValueError("Reference group/family identity must be a nonempty string")
                result[key] = row[key]
        mapped.append(result)
    if seen != set(products):
        raise ValueError("Missing validation reference cards")
    return sorted(mapped, key=lambda r: r["sku_id"]), dict(sorted(counts.items()))


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _lines(path, values):
    path.write_text("".join(json.dumps(v, ensure_ascii=False, allow_nan=False) + "\n" for v in values), encoding="utf-8")
    path.chmod(0o600)


def _slices(evaluation, config):
    slices = []
    registry = Registry(config)
    for category, attributes in config["categories"].items():
        for attribute in attributes:
            score = evaluation.get("metrics", {}).get(f"category_attribute:{category}:{attribute}")
            if score:
                slices.append({"category_id": category, "attribute": attribute,
                               "attribute_name": (registry.spec(category, attribute) or {}).get("name", attribute), **score})
    return sorted(slices, key=lambda s: (s["f1"] is None, s["f1"] or 0, -s["fn"], s["category_id"], s["attribute"]))


def _markdown(report):
    micro = report["evaluation"].get("metrics", {}).get("micro", {})
    def percentage(value):
        return "N/A" if value is None else f"{value*100:.1f}%"
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# Category validation diagnostics", "", "Development feedback only; independence is not verified by this tool.",
             "Test reserve, LLM, calibration and auto_accept were not used.", "",
             f"Status: {report['evaluation']['evaluation_status']}; cards: {report['validation_cards']}.",
             f"P/R/F1: {percentage(micro.get('precision'))} / {percentage(micro.get('recall'))} / {percentage(micro.get('f1'))}.",
             f"Judged / requested pairs: {micro.get('judged', 0)} / {report['requested_pairs']}.",
             f"Unmapped target pairs excluded as unjudgeable: {report['mapping_counts'].get('unmapped_target_labels', 0)}.",
             "Unknown train-vocabulary values remain in reference and may count as FN.", "",
             "## Lowest F1 among judged category/attribute slices", "",
             "| Category | Attribute | TP | FP | FN | Judged | F1 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in report["slices"]:
        lines.append(f"| {cell(s['category_id'])} | {cell(s['attribute_name'])} | {s['tp']} | {s['fp']} | {s['fn']} | {s['judged']} | {percentage(s['f1'])} |")
    if not report["slices"]:
        lines.append("| — | No judged labels | — | — | — | 0 | N/A |")
    return "\n".join(lines) + "\n"


def run(config_path, input_path, reference_path, split_path, mapping_path, output_dir):
    paths = [Path(p).resolve(strict=True) for p in (config_path, input_path, reference_path, split_path, mapping_path)]
    output = Path(output_dir).resolve()
    if (len(set(paths)) != len(paths) or output.exists() or any(output == p or output in p.parents for p in paths)
            or "raw" in [p.casefold() for p in output.parts]):
        raise ValueError("Use separate inputs and a new private output directory outside raw data")
    hashes = [digest(p) for p in paths]
    config = load_config(paths[0])
    allowed = validation_ids(paths[3], config)
    mapping = validate_mapping(_read_json(paths[4].read_text(encoding="utf-8")), config)
    products = {}
    for row in read_jsonl(paths[1]):
        sku = row.get("sku_id")
        if not isinstance(sku, str) or sku not in allowed or sku in products:
            raise ValueError("Validation input contains duplicate, train, test or unknown SKU")
        product = Product.from_dict(row)
        if product.category_id not in config["categories"]:
            raise ValueError("Validation category is not configured; declare a different frozen scope explicitly")
        products[sku] = product
    if set(products) != allowed:
        raise ValueError("Validation input must cover the full frozen validation split")
    mapped, counts = map_reference(read_jsonl(paths[2]), products, mapping, config)
    meta = identity(config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".goodsai-evaluation-", dir=output.parent) as folder:
        stage = Path(folder) / "ready"
        stage.mkdir(mode=0o700)
        source, labels = stage / "input.jsonl", stage / "mapped_reference.jsonl"
        _lines(source, [products[k].as_dict() for k in sorted(products)])
        _lines(labels, mapped)
        prediction = stage / "predictions.jsonl"
        manifest = predict(source, prediction, config)
        evaluation = evaluate(prediction, labels, config)
        result = {"diagnostics_version": "1", "status": "candidate_validation_feedback" if evaluation["evaluation_status"] == "manual_reference" else "unavailable", "split": "validation",
            "independent_quality": "not_verified_by_tool", "validation_cards": len(products), "mapping_counts": counts,
            "requested_pairs": sum(len(config["categories"][p.category_id]) for p in products.values()),
            "evaluation": evaluation, "slices": _slices(evaluation, config),
            "identity": {**meta, "source_hashes": dict(zip(("config", "input", "reference", "split", "mapping"), hashes))},
            "run_id": manifest["run_id"], "llm_calls": 0, "auto_accept_enabled": False,
            "resources": {key: manifest[key] for key in ("elapsed_seconds", "cards_per_second_including_io", "extractor_p50_ms", "extractor_p95_ms", "peak_process_rss_bytes")}}
        _save(stage / "report.json", result)
        (stage / "report.md").write_text(_markdown(result), encoding="utf-8")
        (stage / "report.md").chmod(0o600)
        if [digest(p) for p in paths] != hashes or identity(config)["code_sha256"] != meta["code_sha256"]:
            raise ValueError("Frozen inputs or code changed during validation")
        _save(stage / "artifacts.json", {"run_id": manifest["run_id"], "sha256": {p.name: digest(p) for p in sorted(stage.iterdir()) if p.is_file()}})
        stage.rename(output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("config", "input", "reference", "split", "mapping", "output-dir"):
        parser.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args.config, args.input, args.reference, args.split, args.mapping, args.output_dir)
        print(json.dumps({"status": report["status"], "evaluation_status": report["evaluation"]["evaluation_status"],
                          "validation_cards": report["validation_cards"], "independent_quality": report["independent_quality"]}))
        return 0 if report["evaluation"]["evaluation_status"] == "manual_reference" else 2
    except (OSError, ValueError, KeyError, TypeError):
        print("goodsai: registry_evaluation_failed: check frozen validation files and explicit schema mapping", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("goodsai: registry_evaluation_interrupted", file=sys.stderr)
        return 130
    except Exception:
        print("goodsai: registry_evaluation_internal_error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
