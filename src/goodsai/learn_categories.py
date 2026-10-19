"""Build a private opt-in config from an explicitly approved train-only projection.

No pickle, gold/test access, network calls, or implicit dataset discovery.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile

from goodsai.category_registry import clean, decimal_value, template_pattern, validate_registry
from goodsai.config import _read_json, load_config, validate_config
from goodsai.data import digest


def attribute_id(name):
    return "catalog_" + hashlib.sha256(name.casefold().encode()).hexdigest()[:16]


def _string(value, limit=256):
    if not isinstance(value, str) or not value or len(value) > limit or value != clean(value):
        raise ValueError("Invalid train projection string")
    return value


def load_inputs(train, split, traffic):
    paths = [Path(p).resolve(strict=True) for p in (train, split, traffic)]
    if len(set(paths)) != 3:
        raise ValueError("Training inputs must be separate files")
    hashes = [digest(p) for p in paths]
    split_doc = _read_json(paths[1].read_text(encoding="utf-8"))
    if (not isinstance(split_doc, dict) or set(split_doc) != {"schema_version", "train_sha256", "train_sku_ids", "validation_sku_ids", "test_sku_ids"}
            or split_doc["schema_version"] != "goodsai-train-split-1" or split_doc["train_sha256"] != hashes[0]):
        raise ValueError("Approved train projection and split hash are required")
    groups = []
    for key in ("train_sku_ids", "validation_sku_ids", "test_sku_ids"):
        items = split_doc[key]
        if not isinstance(items, list):
            raise ValueError("Split IDs must be lists")
        for item in items:
            _string(item, 128)
        if len(set(items)) != len(items):
            raise ValueError("Duplicate split IDs")
        groups.append(set(items))
    if not groups[0] or any(a & b for a, b in itertools.combinations(groups, 2)):
        raise ValueError("Train, validation and test must be disjoint")
    traffic_doc = _read_json(paths[2].read_text(encoding="utf-8"))
    if (not isinstance(traffic_doc, dict) or set(traffic_doc) != {"schema_version", "scope", "train_sha256", "category_traffic"}
            or traffic_doc["schema_version"] != "goodsai-category-traffic-1" or traffic_doc["scope"] != "train"
            or traffic_doc["train_sha256"] != hashes[0] or not isinstance(traffic_doc["category_traffic"], dict)):
        raise ValueError("Train-only traffic aggregates linked to the train projection are required")
    traffic_counts = traffic_doc["category_traffic"]
    for category, count in traffic_counts.items():
        _string(category, 128)
        if type(count) not in (int, float) or not math.isfinite(count) or count < 0:
            raise ValueError("Traffic must be finite nonnegative counts")
    return paths, hashes, groups[0], traffic_counts


def _projection_rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if len(line) > 2_000_000:
                raise ValueError("Oversized train projection record")
            row = _read_json(line)
            if not isinstance(row, dict):
                raise ValueError("Train projection object required")
            yield row


def rows(path, allowed):
    seen = set()
    for row in _projection_rows(path):
        # Check identity/membership before interpreting any target/text field.
        sku = row.get("sku_id")
        if not isinstance(sku, str) or sku not in allowed or sku in seen:
            raise ValueError("Train projection contains duplicate or non-train SKU")
        seen.add(sku)
        if set(row) != {"sku_id", "category_id", "title", "description", "params"}:
            raise ValueError("Unexpected train projection fields")
        _string(row["category_id"], 128)
        if not isinstance(row["title"], str) or not row["title"].strip() or len(row["title"]) > 32768:
            raise ValueError("Invalid training title")
        if row["description"] is not None and (not isinstance(row["description"], str) or len(row["description"]) > 131072):
            raise ValueError("Invalid training description")
        if not isinstance(row["params"], list) or len(row["params"]) > 512:
            raise ValueError("Invalid training params")
        names = set()
        for param in row["params"]:
            if not isinstance(param, dict) or set(param) != {"name", "value", "unit"}:
                raise ValueError("Invalid training param")
            _string(param["name"], 120)
            _string(param["value"])
            if param["unit"] is not None:
                _string(param["unit"], 32)
            name = param["name"].casefold()
            if name in names:
                raise ValueError("Training params must have unique names per card")
            names.add(name)
        yield row
    if seen != allowed:
        raise ValueError("Train projection is incomplete for the approved split")


def build(train, split, traffic, *, top_k=30, fill_threshold=0.5, min_template_support=3):
    if (type(top_k) is not int or not 1 <= top_k <= 1000
            or type(fill_threshold) not in (int, float) or not 0.5 <= fill_threshold <= 1
            or type(min_template_support) is not int or min_template_support < 3):
        raise ValueError("Invalid learning policy")
    paths, hashes, allowed, traffic_counts = load_inputs(train, split, traffic)
    cards = Counter()
    fields = defaultdict(lambda: defaultdict(lambda: {"names": set(), "units": set(), "values": Counter(), "support": 0, "overflow": False}))
    for row in rows(paths[0], allowed):
        category = row["category_id"]
        cards[category] += 1
        if category not in traffic_counts:
            raise ValueError("Missing traffic for a training category")
        for param in row["params"]:
            item = fields[category][attribute_id(param["name"])]
            item["names"].add(param["name"])
            item["units"].add(param["unit"])
            item["support"] += 1
            value = param["value"]
            if value not in item["values"] and len(item["values"]) >= 1024:
                item["overflow"] = True
            if not item["overflow"]:
                item["values"][value] += 1
    selected = sorted(cards, key=lambda c: (-traffic_counts[c], c))[:top_k]
    registry = {"registry_version": "1", "provenance": {
        "train_sha256": hashes[0], "split_sha256": hashes[1], "traffic_sha256": hashes[2],
        "training_cards": len(allowed), "fill_threshold": fill_threshold,
        "top_k": top_k, "min_template_support": min_template_support}, "categories": {}}
    skipped = Counter()
    for category in selected:
        attributes = {}
        for attribute, item in sorted(fields[category].items()):
            if item["support"] / cards[category] < fill_threshold:
                skipped["below_fill_threshold"] += 1
                continue
            if len(item["units"]) != 1 or item["overflow"]:
                skipped["mixed_units_or_dictionary_overflow"] += 1
                continue
            values = sorted(item["values"])
            try:
                normalized = {decimal_value(v) for v in values}
                kind = "number"
            except ValueError:
                kind = "enum"
                normalized = {clean(v).casefold() for v in values}
            unit = next(iter(item["units"]))
            if kind == "enum" and unit is not None:
                skipped["unparsed_unit_values"] += 1
                continue
            # Case variants have one deterministic canonical spelling.
            canonical = sorted(normalized) if kind == "number" else sorted({min(v for v in values if v.casefold() == n) for n in normalized})
            attributes[attribute] = {"name": min(item["names"]), "kind": kind, "unit": unit,
                                     "values": canonical, "support": item["support"]}
        if not attributes:
            skipped["category_without_eligible_fields"] += 1
            continue
        if len(attributes) > 128:
            raise ValueError("Category exceeds 128 eligible fields; review schema explicitly")
        registry["categories"][category] = {"training_cards": cards[category], "attributes": attributes, "templates": []}
    # Learn positional roles from catalog values on train, not from attribute names.
    observations = Counter()
    votes = defaultdict(Counter)
    from goodsai.text import visible_view
    for row in rows(paths[0], allowed):
        category = row["category_id"]
        entry = registry["categories"].get(category)
        if not entry:
            continue
        specs = entry["attributes"]
        numeric = {}
        for param in row["params"]:
            attribute = attribute_id(param["name"])
            if attribute in specs and specs[attribute]["kind"] == "number":
                numeric[attribute] = (decimal_value(param["value"]), param["unit"])
        text, _ = visible_view(row["title"])
        for unit in sorted({u for _, u in numeric.values() if u is not None}):
            for kind, size in (("pair", 2), ("dimensions", 3)):
                matches = list(template_pattern(kind, unit).finditer(text))
                if not matches:
                    continue
                key = (category, kind, unit)
                observations[key] += 1  # Support counts distinct cards, not repeats.
                orders = set()
                for match in matches:
                    options = [[a for a, (v, u) in numeric.items() if u == unit and v == decimal_value(match[f"n{i}"])] for i in range(size)]
                    if all(options) and all(len(o) == 1 for o in options):
                        order = tuple(o[0] for o in options)
                        if len(set(order)) == size:
                            orders.add(order)
                if len(orders) == 1:
                    votes[key][next(iter(orders))] += 1
    for key, counter in sorted(votes.items()):
        category, kind, unit = key
        order, support = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
        total = observations[key]
        if support >= min_template_support and support / total >= 0.95:
            registry["categories"][category]["templates"].append({"kind": kind, "attributes": list(order), "unit": unit, "support": support, "observations": total})
    if [digest(p) for p in paths] != hashes:
        raise ValueError("Training inputs changed during learning")
    validate_registry(registry)
    config = deepcopy(load_config())
    config["config_version"] = "2"
    config["category_registry"] = registry
    config["dictionary_version"] = "train-registry-" + hashes[0][:12]
    for category, entry in registry["categories"].items():
        config["categories"][category] = list(entry["attributes"])
        config["category_profiles"][category] = "learned"
    validate_config(config)
    summary = {"status": "candidate", "independent_quality": "not_measured", "training_cards": len(allowed),
               "requested_top_k": top_k, "ranked_categories": len(selected), "learned_categories": len(registry["categories"]),
               "top_k_complete": len(registry["categories"]) == top_k,
               "attributes": sum(len(c["attributes"]) for c in registry["categories"].values()),
               "templates": sum(len(c["templates"]) for c in registry["categories"].values()),
               "skipped": dict(sorted(skipped.items())), "provenance": registry["provenance"],
               "llm_calls": 0, "auto_accept_enabled": False}
    return config, summary


def publish(train, split, traffic, output_dir, **policy):
    output = Path(output_dir).resolve()
    sources = [Path(p).resolve() for p in (train, split, traffic)]
    if output.exists() or any(output == p or output in p.parents for p in sources) or "raw" in [p.casefold() for p in output.parts]:
        raise ValueError("Use a new private output directory outside raw inputs")
    config, summary = build(train, split, traffic, **policy)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish a complete directory, never half a config/report pair.
    with tempfile.TemporaryDirectory(prefix=".goodsai-registry-", dir=output.parent) as folder:
        stage = Path(folder) / "ready"
        stage.mkdir(mode=0o700)
        for name, value in (("config.json", config), ("learning_report.json", summary)):
            path = stage / name
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
            path.chmod(0o600)
        stage.rename(output)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("train", "split", "traffic", "output-dir"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--fill-threshold", type=float, default=0.5)
    parser.add_argument("--min-template-support", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        result = publish(args.train, args.split, args.traffic, args.output_dir, top_k=args.top_k,
                         fill_threshold=args.fill_threshold, min_template_support=args.min_template_support)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("goodsai: category_learning_failed: check private train inputs and schema", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
