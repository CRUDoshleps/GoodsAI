"""Offline M2 sampling, family quarantine and draft review; never predicts.

Test texts are processed only by deterministic fingerprinting/sampling. Test
exports contain metadata/blank labels only. No extractor or model is imported.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl
from goodsai.runtime import identity
from goodsai.text import visible_view

POLICY = {
    "version": "goodsai-m2-v2", "seed": "goodsai-m2-selection-20261018-v1",
    "categories": ["761", "482"], "development_per_cell": 5, "test_per_cell": 10,
    "cells": "category x description presence", "title_jaccard": 0.90,
    "description_jaccard": 0.90, "description_shingle_words": 5,
    "priority_slots": ["name_ambiguity", "unit_issue", "html", "sparse", "random"],
    "exclude": "Known exposure, its connected family, or any mixed-split family; one SKU per family",
    "family": "Original groups + exact visible text + title skeleton (parenthesized codes removed) + thresholded near title/description",
    "test_visibility": "metadata_and_blank_labels_only",
    "selection_uses_predictions": False, "quality_before_human_review": None,
}


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def jsonl(path, items):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for item in items:
            stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")


def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalized(value):
    visible, _ = visible_view(value or "")
    return re.sub(r"\W+", " ", visible.casefold().replace("ё", "е")).strip()


def source_hashes(paths):
    return {str(Path(p).resolve()): digest(Path(p)) for p in paths}


def freeze(bundle):
    bundle = Path(bundle).resolve()
    if any(a.lower() == "data" and b.lower() == "raw" for a, b in zip(bundle.parts, bundle.parts[1:])):
        raise ValueError("Do not write into data/raw")
    bundle.mkdir(parents=True, exist_ok=False)
    config = load_config()
    dump(bundle / "selection.policy.json", POLICY | {"frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                                                   "runtime_identity": identity(config)})
    return {"status": "policy_frozen", "seed": POLICY["seed"]}


class Families:
    def __init__(self, ids):
        self.parent = {sku: sku for sku in ids}
        self.edges = []

    def root(self, sku):
        while self.parent[sku] != sku:
            self.parent[sku] = self.parent[self.parent[sku]]
            sku = self.parent[sku]
        return sku

    def union(self, a, b, reason, score=None):
        left, right = sorted((self.root(a), self.root(b)))
        if left != right:
            self.parent[right] = left
            self.edges.append({"left": a, "right": b, "reason": reason, "similarity": score})


def near_join(documents, threshold, families, reason):
    """Exact Jaccard join of supplied sets using a shared frequency prefix filter.

    Every set is ordered in one global order. Similar sets must intersect in
    prefixes of length |S|-ceil(t*|S|)+1; length bounds prune impossible pairs.
    Fingerprint similarity is not a guarantee of semantic family detection.
    """
    documents = {sku: tokens for sku, tokens in documents.items() if tokens}
    frequency = Counter(token for tokens in documents.values() for token in tokens)
    index = defaultdict(list)
    tested = 0
    for sku in sorted(documents, key=lambda s: (len(documents[s]), s)):
        tokens = documents[sku]
        prefix = sorted(tokens, key=lambda t: (frequency[t], t))[:len(tokens) - math.ceil(threshold * len(tokens)) + 1]
        candidates = {other for token in prefix for other in index[token]}
        for other in sorted(candidates):
            old = documents[other]
            if len(old) < threshold * len(tokens) or families.root(sku) == families.root(other):
                continue
            tested += 1
            score = len(old & tokens) / len(old | tokens)
            if score >= threshold:
                families.union(sku, other, reason, score)
        for token in prefix:
            index[token].append(sku)
    return tested


def skeleton(title, config):
    text = visible_view(title)[0].casefold().replace("ё", "е")
    # Seller/region codes must not separate variants of one commercial family.
    # Removing all parentheses is deliberately conservative: false joins quarantine
    # a family rather than allowing a plausible relative into independent test.
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\d+(?:\s*[/+]\s*\d+)?\s*(?:gb|гб|tb|тб|мл|литр\w*|л|квт|вт|mah|мач|дюйм\w*)(?!\w)", " ", text)
    text = re.sub(r"\b\d+\s*[/+]\s*\d+\b", " ", text)
    text = re.sub(r"\b(?:4g|5g|lte|восстановленный|рабочий|новый)\b", " ", text)
    for aliases in config["colors"].values():
        for alias in sorted(aliases, key=len, reverse=True):
            text = re.sub(r"(?<!\w)" + re.escape(alias.casefold().replace("ё", "е")) + r"(?!\w)", " ", text)
    return re.sub(r"\W+", " ", text).strip()


def signals(product):
    title, _ = visible_view(product.title)
    joined = title + " " + (product.description or "")
    return {
        "name_ambiguity": bool(re.search(r"\b[A-Za-z]+\s+[A-Za-z]+\s+[A-Za-z]*\d", title)
                               or len(re.findall(r"\b[A-Za-zА-Яа-я]+[-\w]*\d[-\w]*\b", title)) > 1),
        "unit_issue": bool(re.search(r"\b\d{1,3}\s*[/+]\s*\d{2,4}(?!\d|\s*(?:GB|ГБ))", joined, re.I)
                           or re.search(r"\b\d+\s*(?:TB|ТБ|кг|kg)\b", joined, re.I)),
        "html": bool(re.search(r"<[^>]+>", joined)),
        "sparse": len(re.findall(r"\d+\s*(?:GB|ГБ|mAh|мАч|Вт|л|дюйм)", joined, re.I)) < 2,
        "random": True,
    }


def blank_labels(config, category):
    return [{"attribute": a, "status": "unreviewed", "value": None, "unit": None, "evidence": None}
            for a in config["categories"][category]]


def select(bundle, input_path, split_path, seen_paths, eda_sample=None):
    bundle, input_path, split_path = Path(bundle).resolve(), Path(input_path), Path(split_path)
    policy_path = bundle / "selection.policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if any(policy[k] != v for k, v in POLICY.items()):
        raise ValueError("Selection policy differs from the frozen version")
    if any(p.name != "selection.policy.json" for p in bundle.iterdir()):
        raise ValueError("Selection output must contain only the frozen policy; never overwrite a run")
    config = load_config()
    if identity(config)["code_sha256"] != policy["runtime_identity"]["code_sha256"]:
        raise ValueError("Runtime changed after policy freeze")
    protected = source_hashes([input_path, split_path, policy_path, *seen_paths, *([eda_sample] if eda_sample else [])])
    products, metadata = {}, {}
    for row in read_jsonl(input_path):
        p = Product.from_dict(row)
        if p.sku_id in products:
            raise ValueError("Duplicate input SKU")
        products[p.sku_id] = p
    for row in read_jsonl(split_path):
        if row["sku_id"] in metadata or row.get("split") not in {"development", "validation", "test_reserved"}:
            raise ValueError("Invalid split metadata")
        metadata[row["sku_id"]] = row
    if products.keys() != metadata.keys():
        raise ValueError("Input/split SKU mismatch")
    by_group = defaultdict(set)
    for sku, row in metadata.items():
        if row["category_id"] != products[sku].category_id or not row.get("group_id"):
            raise ValueError("Category/group mismatch")
        by_group[row["group_id"]].add(row["split"])
    if any(len(s) != 1 for s in by_group.values()):
        raise ValueError("Original group crosses splits")
    seen = set()
    for path in seen_paths:
        seen.update(row["sku_id"] for row in read_jsonl(Path(path)))
    if eda_sample:
        sample = json.loads(Path(eda_sample).read_text(encoding="utf-8"))
        if not isinstance(sample, list):
            raise ValueError("EDA exposure sample must be a list")
        seen.update(str(row["sku_id"]) for row in sample)
    # Reproduce the explicitly recorded E1 EDA exposure, even if export is absent.
    for cat in POLICY["categories"]:
        candidates = sorted((p for p in products.values() if p.category_id == cat and p.description),
                            key=lambda p: hashlib.md5((p.sku_id + ":goodsai-eda-v1").encode()).hexdigest())
        seen.update(p.sku_id for p in candidates[:200])
    seen &= products.keys()
    families = Families(products)
    keys = {}
    title_sets, desc_sets = {}, {}
    for sku, p in products.items():
        title = normalized(p.title)
        desc = normalized(p.description)
        core = skeleton(p.title, config)
        candidates = [("original_group", metadata[sku]["group_id"]), ("exact_title", title)]
        if desc:
            candidates.append(("exact_description", desc))
        if len(core.split()) >= 3:
            candidates.append(("title_skeleton", p.category_id + ":" + core))
        for reason, key in candidates:
            pair = (reason, key)
            if pair in keys:
                families.union(sku, keys[pair], reason)
            else:
                keys[pair] = sku
        title_sets[sku] = {title[i:i+3] for i in range(max(0, len(title)-2))}
        words = desc.split()
        n = POLICY["description_shingle_words"]
        desc_sets[sku] = {" ".join(words[i:i+n]) for i in range(max(0, len(words)-n+1))}
    tested_title = near_join(title_sets, POLICY["title_jaccard"], families, "near_title")
    tested_desc = near_join(desc_sets, POLICY["description_jaccard"], families, "near_description")
    groups = defaultdict(list)
    for sku in products:
        groups[families.root(sku)].append(sku)
    family_id, exposed, mixed = {}, set(), set()
    for group in groups.values():
        fid = fingerprint("|".join(sorted(group)))[:24]
        for sku in group:
            family_id[sku] = fid
        if seen.intersection(group):
            exposed.add(fid)
        if len({metadata[sku]["split"] for sku in group}) > 1:
            mixed.add(fid)
    eligible = {sku for sku in products if family_id[sku] not in exposed | mixed}
    selected, selections, selected_families = {}, [], set()
    shortfalls = []
    for purpose, split, quota in [("development", "development", POLICY["development_per_cell"]),
                                   ("test", "test_reserved", POLICY["test_per_cell"])]:
        selected[purpose] = []
        for cat in POLICY["categories"]:
            for has_desc in [True, False]:
                candidates = [sku for sku in eligible if products[sku].category_id == cat
                              and metadata[sku]["split"] == split and bool(products[sku].description) == has_desc]
                candidates.sort(key=lambda sku: fingerprint(POLICY["seed"] + ":" + purpose + ":" + sku))
                for slot in range(quota):
                    feature = POLICY["priority_slots"][slot] if purpose == "development" else "random"
                    available = [sku for sku in candidates if family_id[sku] not in selected_families]
                    preferred = [sku for sku in available if signals(products[sku])[feature]]
                    chosen = (preferred or available)
                    if not chosen:
                        shortfalls.append({"purpose": purpose, "category_id": cat, "has_description": has_desc,
                                           "missing": quota - slot})
                        break
                    sku = chosen[0]
                    selected[purpose].append(sku)
                    selected_families.add(family_id[sku])
                    selections.append({"purpose": purpose, "sku_id": sku, "category_id": cat,
                                       "group_id": metadata[sku]["group_id"], "family_id": family_id[sku],
                                       "split": split, "has_description": has_desc,
                                       "requested_feature": feature, "features": signals(products[sku])})
    dev_tasks, test_blank = [], []
    for purpose, skus in selected.items():
        for i, sku in enumerate(skus, 1):
            p = products[sku]
            record = {"review_id": ("D" if purpose == "development" else "T") + f"{i:02d}",
                      "sku_id": sku, "category_id": p.category_id, "group_id": metadata[sku]["group_id"],
                      "family_id": family_id[sku], "split": metadata[sku]["split"],
                      "annotation_status": "unreviewed", "label_source": "unassigned", "annotator": None,
                      "attributes": blank_labels(config, p.category_id)}
            if purpose == "development":
                dev_tasks.append(p.as_dict() | record)
            else:
                test_blank.append(record | {"text_materialized": False})
    jsonl(bundle / "development.tasks.jsonl", dev_tasks)
    jsonl(bundle / "test_reserve.blank.jsonl", test_blank)
    jsonl(bundle / "selection.manifest.jsonl", selections)
    jsonl(bundle / "family.manifest.jsonl", ({"sku_id": sku, "group_id": metadata[sku]["group_id"],
          "family_id": family_id[sku], "split": metadata[sku]["split"],
          "known_exposure": sku in seen, "family_exposed": family_id[sku] in exposed,
          "mixed_split_family": family_id[sku] in mixed} for sku in sorted(products)))
    jsonl(bundle / "audit.edges.jsonl", families.edges)
    assert not {family_id[s] for s in selected["development"]} & {family_id[s] for s in selected["test"]}
    for path, old_hash in protected.items():
        if digest(Path(path)) != old_hash:
            raise ValueError("Protected source changed")
    report = {"version": POLICY["version"], "policy_sha256": digest(policy_path),
              "input_rows": len(products), "known_exposure_rows": len(seen), "audited_families": len(groups),
              "mixed_split_families_quarantined": len(mixed), "exposed_families_quarantined": len(exposed),
              "eligible_rows": len(eligible), "near_pairs_tested": {"title": tested_title, "description": tested_desc},
              "edge_counts": dict(Counter(e["reason"] for e in families.edges)),
              "selected_counts": {k: len(v) for k, v in selected.items()}, "shortfalls": shortfalls,
              "reference_status": "pending_human_review", "precision": None, "recall": None, "f1": None,
              "test_status": "reserved_metadata_only_not_annotated_or_predicted", "independent_reference": False,
              "protected_sources": protected, "runtime_identity": policy["runtime_identity"],
              "tool_sha256": digest(Path(__file__)),
              "limitations": "Lexical families are conservative, not semantic proof; filtered purposive samples are not catalogue-representative.",
              "artifacts": {p.name: digest(p) for p in bundle.iterdir() if p.is_file()}}
    dump(bundle / "selection.summary.json", report)
    return {k: report[k] for k in ["selected_counts", "shortfalls", "known_exposure_rows", "audited_families",
                                 "mixed_split_families_quarantined", "eligible_rows", "reference_status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--bundle", type=Path, required=True)
    p = sub.add_parser("select")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--split-manifest", type=Path, required=True)
    p.add_argument("--seen", type=Path, action="append", required=True)
    p.add_argument("--eda-sample", type=Path)
    args = parser.parse_args()
    try:
        result = freeze(args.bundle) if args.command == "freeze" else select(
            args.bundle, args.input, args.split_manifest, args.seen, args.eda_sample)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"prepare M2: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
