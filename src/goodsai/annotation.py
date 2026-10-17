"""Group-aware manifests and blank annotation tasks. No fabricated gold labels."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from goodsai.contracts import Product
from goodsai.data import atomic_text, check_output, digest, read_jsonl, write_json, write_line


def normalized(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold().replace("ё", "е")).strip()


def annotation_tasks(input_path: Path, provenance: Path, eda_sample: Path | None,
                     output: Path, config: dict, per_category_split: int = 30) -> dict:
    check_output(output, input_path, provenance)
    products = {}
    for row in read_jsonl(input_path):
        p = Product.from_dict(row)
        if p.sku_id in products:
            raise ValueError("Duplicate input SKU")
        products[p.sku_id] = p
    metadata = {}
    for row in read_jsonl(provenance):
        if row["sku_id"] in metadata:
            raise ValueError("Duplicate provenance SKU")
        metadata[row["sku_id"]] = row
    if set(metadata) != set(products):
        raise ValueError("Provenance and input SKU sets must match")
    parent = {sku: sku for sku in products}

    def root(sku):
        while parent[sku] != sku:
            parent[sku] = parent[parent[sku]]
            sku = parent[sku]
        return sku

    def union(left, right):
        a, b = sorted([root(left), root(right)])
        parent[b] = a

    keys = {}
    for sku, p in products.items():
        m = metadata[sku]
        model = normalized(m.get("model") or "")
        vendor = normalized(m.get("vendor") or "")
        candidates = [("title", normalized(p.title))]
        if model and model not in {"нет", "не указано", "unknown"} and vendor:
            candidates.append(("family", vendor + "|" + model))
        if p.description:
            candidates.append(("description", hashlib.sha256(normalized(p.description).encode()).hexdigest()))
        for key in candidates:
            if key in keys:
                union(sku, keys[key])
            else:
                keys[key] = sku
    inspected = set()
    if eda_sample is not None:
        inspected = {str(row["sku_id"]) for row in json.loads(eda_sample.read_text(encoding="utf-8"))}
    else:
        # Reproduce the prior EDA's first-200-per-category selection without needing its raw sample export.
        for cat in config["categories"]:
            available = [p for p in products.values() if p.category_id == cat and p.description]
            available.sort(key=lambda p: hashlib.md5((p.sku_id + ":goodsai-eda-v1").encode()).hexdigest())
            inspected.update(p.sku_id for p in available[:200])
    groups = defaultdict(list)
    for sku in products:
        groups[root(sku)].append(sku)
    assignment, group_ids = {}, {}
    for group in groups.values():
        group_id = hashlib.sha256("|".join(sorted(group)).encode()).hexdigest()[:24]
        score = int(hashlib.sha256((config["seed"] + group_id).encode()).hexdigest()[:8], 16) / 2**32
        split = "development" if score < .4 else ("validation" if score < .8 else "test_reserved")
        if inspected.intersection(group):
            split = "development"
        for sku in group:
            assignment[sku], group_ids[sku] = split, group_id
    tasks = []
    selected_groups = set()
    shortfalls = []
    for cat in config["categories"]:
        for split in ["development", "validation"]:
            candidates = sorted((p for p in products.values() if p.category_id == cat and assignment[p.sku_id] == split),
                                key=lambda p: hashlib.sha256((config["seed"] + p.sku_id).encode()).hexdigest())
            chosen = []
            # Half title-only, half title+description where distinct groups are available.
            for has_description, quota in [(True, per_category_split // 2), (False, per_category_split - per_category_split // 2)]:
                taken = 0
                for p in candidates:
                    if bool(p.description) != has_description or group_ids[p.sku_id] in selected_groups:
                        continue
                    chosen.append(p)
                    selected_groups.add(group_ids[p.sku_id])
                    taken += 1
                    if taken >= quota:
                        break
            if len(chosen) < per_category_split:
                shortfalls.append({"category_id": cat, "split": split, "selected": len(chosen), "requested": per_category_split})
            for p in chosen:
                tasks.append(p.as_dict() | {"split": split, "group_id": group_ids[p.sku_id],
                             "annotation_status": "unreviewed", "label_source": "manual", "annotator": None,
                             "attributes": [{"attribute": a, "status": "unreviewed", "value": None,
                                             "unit": None, "evidence": None} for a in config["categories"][cat]]})
    with atomic_text(output / "split_manifest.jsonl") as stream:
        for sku in sorted(products):
            write_line(stream, {"sku_id": sku, "category_id": products[sku].category_id,
                                "group_id": group_ids[sku], "split": assignment[sku]})
    with atomic_text(output / "tasks.jsonl") as stream:
        for task in tasks:
            write_line(stream, task)
    report = {"input_sha256": digest(input_path), "seed": config["seed"], "rows": len(products),
              "groups": len(groups), "largest_group": max(map(len, groups.values()), default=0),
              "split_rows": dict(Counter(assignment.values())), "tasks": len(tasks), "shortfalls": shortfalls,
              "task_counts": dict(Counter(p["category_id"] + ":" + p["split"] for p in tasks)),
              "grouping": "Connected components of normalized title, description and vendor/model; near-duplicate audit still required.",
              "eda_exclusion": "All groups touching supplied EDA sample are development only.",
              "eda_reference": "supplied sample" if eda_sample else "reconstructed deterministic EDA SKU selection",
              "evaluation_status": "No human labels created; test_reserved is not an evaluated test set."}
    write_json(output / "annotation_manifest.json", report)
    return report
