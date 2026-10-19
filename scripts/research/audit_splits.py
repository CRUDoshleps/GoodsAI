"""Offline E1 split audit: deterministic fingerprints, never inference or test inspection.

Only aggregate counts leave stdout. Identifiers/edges remain in a new private
output directory. Existing assignments, labels and reserves are never rewritten.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from goodsai.data import digest, read_jsonl
from scripts.research.prepare_m2 import Families, normalized

SPLITS = {"development", "validation", "test_reserved"}
POLICY = {
    "version": "eval-002-quarantine-v1",
    "normalization": "NFKC + M2 visible HTML/casefold/yo/nonword normalization",
    "title_jaccard": 0.90,
    "description_jaccard": 0.90,
    "title_shingle_chars": 3,
    "description_shingle_words": 5,
    "max_comparisons_per_field": 5_000_000,
    "family_links": "original groups + frozen M2 families + exact/normalized/near text",
    "empty_text": "excluded from duplicate keys and near joins",
    "mixed_family": "quarantine entire component; do not reassign or resample test",
    "exposed_test_family": "quarantine entire component",
    "validation_role": "development_feedback, never independent holdout",
    "test_access": "automated fingerprints and metadata only; no text export or inference",
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def dump(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, allow_nan=False, indent=2)
        stream.write("\n")


def write_rows(path, rows):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True, allow_nan=False, sort_keys=True) + "\n")


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def norm(value):
    return normalized(unicodedata.normalize("NFKC", value))


def unique_rows(path, allow_empty=False):
    result = {}
    for row in read_jsonl(path):
        sku = row.get("sku_id")
        require(isinstance(sku, str) and bool(sku) and sku not in result, "duplicate_or_invalid_sku")
        result[sku] = row
    require(bool(result) or allow_empty, "empty_metadata")
    return result


def near_pairs(documents, threshold, stats, max_comparisons):
    """Complete threshold Jaccard join using a global frequency-prefix filter.

    Unlike M2's component builder, this also checks pairs already connected by
    another link. Therefore per-detector crossing counts are not hidden by DSU.
    Exceeding the fixed budget aborts the audit, never returns a partial pass.
    """
    documents = {sku: tokens for sku, tokens in documents.items() if tokens}
    frequency = Counter(t for tokens in documents.values() for t in tokens)
    index = defaultdict(list)
    stats.update(comparisons=0, matches=0)
    for sku in sorted(documents, key=lambda s: (len(documents[s]), s)):
        tokens = documents[sku]
        size = len(tokens) - math.ceil(threshold * len(tokens)) + 1
        prefix = sorted(tokens, key=lambda t: (frequency[t], t))[:size]
        candidates = {other for token in prefix for other in index[token]}
        for other in sorted(candidates):
            old = documents[other]
            if len(old) < threshold * len(tokens):
                continue
            stats["comparisons"] += 1
            require(stats["comparisons"] <= max_comparisons, "near_join_budget_exceeded")
            score = len(old & tokens) / len(old | tokens)
            if score >= threshold:
                stats["matches"] += 1
                yield other, sku, score
        for token in prefix:
            index[token].append(sku)


def exposure_ids(path):
    # Only identity is consumed, never labels/values or model predictions.
    if path.suffix == ".jsonl":
        rows = read_jsonl(path)
    else:
        rows = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(rows, list), "exposure_list_required")
    result = set()
    for row in rows:
        require(isinstance(row, dict), "exposure_row_required")
        sku = row.get("sku_id")
        require(isinstance(sku, (str, int)) and not isinstance(sku, bool), "exposure_identity_required")
        result.add(str(sku))
    return result


def audit(input_path, split_path, family_path, summary_path, reserve_path, exposure_paths, output):
    paths = [Path(p).resolve() for p in
             [input_path, split_path, family_path, summary_path, reserve_path, *exposure_paths]]
    require(len(set(paths)) == len(paths), "repeated_source_path")
    output = Path(output).resolve()
    require(not output.exists() and not any(output == p or output in p.parents for p in paths),
            "new_output_directory_required")
    protected = {str(p): digest(p) for p in paths}
    producer_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    producer_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    output.mkdir(parents=True, exist_ok=False)
    # Freeze the complete policy and source hashes BEFORE reading texts or joins.
    dump(output / "audit.policy.json", POLICY | {"sources": protected})
    splits, old_families = unique_rows(Path(split_path)), unique_rows(Path(family_path))
    require(splits.keys() == old_families.keys(), "split_family_identity_mismatch")
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    require(summary["artifacts"][Path(family_path).name] == digest(Path(family_path)), "frozen_family_hash_mismatch")
    require(summary["artifacts"][Path(reserve_path).name] == digest(Path(reserve_path)), "frozen_reserve_hash_mismatch")
    expected = {Path(k.replace("\\", "/")).name: v for k, v in summary["protected_sources"].items()}
    require(expected.get(Path(input_path).name) == digest(Path(input_path)), "frozen_input_hash_mismatch")
    require(expected.get(Path(split_path).name) == digest(Path(split_path)), "frozen_split_hash_mismatch")

    components = Families(splits)
    buckets = defaultdict(lambda: defaultdict(list))
    title_sets, description_sets, fingerprints = {}, {}, []
    categories, known = {}, set()
    for sku, row in splits.items():
        family = old_families[sku]
        require(row.get("split") in SPLITS and isinstance(row.get("group_id"), str) and row["group_id"],
                "invalid_split_group")
        require(isinstance(row.get("category_id"), str) and row["category_id"], "invalid_category")
        require(all(family.get(k) == row[k] for k in ["group_id", "split"]), "frozen_assignment_mismatch")
        require(isinstance(family.get("family_id"), str) and family["family_id"], "invalid_family")
        require(all(type(family.get(k)) is bool for k in
                    ["known_exposure", "family_exposed", "mixed_split_family"]), "invalid_exposure_flags")
        if family["known_exposure"]:
            known.add(sku)
        categories[sku] = row["category_id"]
        buckets["original_group"][row["group_id"]].append(sku)
        buckets["m2_family"][family["family_id"]].append(sku)
    require(len(known) == summary["known_exposure_rows"], "frozen_exposure_count_mismatch")
    exposure_counts = []
    for path in exposure_paths:
        ids = exposure_ids(Path(path))
        require(ids <= splits.keys(), "exposure_outside_input")
        known.update(ids)
        exposure_counts.append({"file": Path(path).name, "rows": len(ids), "sha256": digest(Path(path))})

    seen = set()
    for row in read_jsonl(Path(input_path)):
        sku = row.get("sku_id")
        require(sku in splits and sku not in seen, "input_identity_mismatch")
        require(row.get("category_id") == categories[sku], "input_category_mismatch")
        # The auditor consumes only allowed text fields and identities; no
        # target/provenance, gold labels, extractor or model is consulted.
        title, description = row.get("title"), row.get("description")
        require(isinstance(title, str) and (description is None or isinstance(description, str)), "invalid_text")
        require(not row.get("seller_attributes"), "unsupported_seller_attributes")
        seen.add(sku)
        raw = (title, description or "")
        clean = tuple(norm(v) for v in raw)
        record = {"sku_id": sku}
        for prefix, values in [("raw", raw), ("normalized", clean)]:
            for field, value in zip(["title", "description"], values):
                if value.strip():
                    key = sha(value)
                    buckets[prefix + "_" + field][key].append(sku)
                    record[prefix + "_" + field + "_sha256"] = key
            # Preserve field boundaries; empty products are not duplicate proof.
            if any(v.strip() for v in values):
                key = sha(json.dumps(values, ensure_ascii=True))
                buckets[prefix + "_card"][key].append(sku)
                record[prefix + "_card_sha256"] = key
        title_sets[sku] = {sha(clean[0][i:i+3]) for i in range(max(0, len(clean[0])-2))}
        words = clean[1].split()
        description_sets[sku] = {sha(" ".join(words[i:i+5])) for i in range(max(0, len(words)-4))}
        fingerprints.append(record)
    require(seen == splits.keys(), "input_metadata_identity_mismatch")
    diagnostics, violation_rows = {}, []
    for detector, groups in sorted(buckets.items()):
        duplicates = [sorted(items) for items in groups.values() if len(items) > 1]
        crossings = [items for items in duplicates if len({splits[s]["split"] for s in items}) > 1]
        diagnostics[detector] = {"duplicate_groups": len(duplicates),
                                 "cross_split_groups": len(crossings),
                                 "cross_split_rows": sum(map(len, crossings))}
        for items in duplicates:
            for sku in items[1:]:
                components.union(items[0], sku, detector)
        for items in crossings:
            violation_rows.append({"detector": detector, "members": items,
                                   "splits": sorted({splits[s]["split"] for s in items})})
    near_stats = {}
    for detector, documents in [("near_title", title_sets), ("near_description", description_sets)]:
        stats, crossing_rows = {}, set()
        crosses = 0
        for left, right, score in near_pairs(documents, POLICY[detector.replace("near_", "") + "_jaccard"],
                                             stats, POLICY["max_comparisons_per_field"]):
            components.union(left, right, detector, score)
            if splits[left]["split"] != splits[right]["split"]:
                crosses += 1
                crossing_rows.update([left, right])
                violation_rows.append({"detector": detector, "members": [left, right], "similarity": score})
        near_stats[detector] = stats | {"cross_split_pairs": crosses, "cross_split_rows": len(crossing_rows)}

    groups = defaultdict(list)
    for sku in sorted(splits):
        groups[components.root(sku)].append(sku)
    membership, eligible, quarantined = {}, [], []
    contaminated_families, exposed_test_families = 0, 0
    for members in groups.values():
        family_id = sha(json.dumps(members, ensure_ascii=True))[:24]
        assignments = {splits[s]["split"] for s in members}
        mixed, exposed = len(assignments) > 1, bool(known.intersection(members))
        contaminated_families += mixed
        exposed_test_families += exposed and "test_reserved" in assignments
        reasons = (["mixed_split_family"] if mixed else []) + (
            ["exposed_test_family"] if exposed and "test_reserved" in assignments else [])
        for sku in members:
            # Same split values as E1; excluded components have a separate ledger.
            record = splits[sku] | {"original_group_id": splits[sku]["group_id"],
                "group_id": family_id, "family_id": family_id, "known_exposure": sku in known,
                "family_exposed": exposed, "audit_version": POLICY["version"],
                "evaluation_role": "independent_reserve_candidate" if assignments == {"test_reserved"}
                    and not reasons else "development_feedback"}
            membership[sku] = record | {"quarantine_reasons": reasons}
            (quarantined if reasons else eligible).append(membership[sku])
    reserve = unique_rows(Path(reserve_path))
    reserve_issues = []
    for sku, row in reserve.items():
        require(sku in splits, "reserve_outside_input")
        require(not any(k in row for k in ["title", "description", "predictions", "vendor", "model"]),
                "reserve_must_be_metadata_only")
        require(row.get("text_materialized") is False, "reserve_text_materialized")
        require(row.get("split") == splits[sku]["split"] == "test_reserved", "reserve_split_mismatch")
        require(row.get("family_id") == old_families[sku]["family_id"], "reserve_family_mismatch")
        require(row.get("group_id") == splits[sku]["group_id"]
                and row.get("category_id") == categories[sku], "reserve_metadata_mismatch")
        require(all(a.get("status") == "unreviewed" and a.get("value") is None
                    and a.get("evidence") is None for a in row.get("attributes", [])), "reserve_not_blank")
        if membership[sku]["quarantine_reasons"]:
            reserve_issues.append({"sku_id": sku, "reasons": membership[sku]["quarantine_reasons"]})
    reserve_families = [membership[s]["family_id"] for s in reserve]
    repeated = {fid for fid, count in Counter(reserve_families).items() if count > 1}
    for sku in reserve:
        if membership[sku]["family_id"] in repeated:
            reserve_issues.append({"sku_id": sku, "reasons": ["reserve_family_repeated"]})
    # Every detected equality/near edge is contained in a single component.
    # Removing complete mixed/exposed components leaves no detected crossings.
    for members in groups.values():
        kept = [s for s in members if not membership[s]["quarantine_reasons"]]
        require(len({splits[s]["split"] for s in kept}) <= 1, "corrected_family_crossing")
        require(not (known.intersection(members) and any(splits[s]["split"] == "test_reserved" for s in kept)),
                "corrected_exposure_crossing")
    for path, before in protected.items():
        require(digest(Path(path)) == before, "source_changed_during_audit")
    for filename, rows in [
        ("fingerprints.jsonl", sorted(fingerprints, key=lambda r: r["sku_id"])),
        ("violations.jsonl", violation_rows), ("family.edges.jsonl", components.edges),
        ("membership.jsonl", [membership[s] for s in sorted(membership)]),
        ("eligible.split_manifest.jsonl", sorted(eligible, key=lambda r: r["sku_id"])),
        ("quarantine.manifest.jsonl", sorted(quarantined, key=lambda r: r["sku_id"])),
        ("reserve.violations.jsonl", reserve_issues)]:
        write_rows(output / filename, rows)
    report = {
        "version": POLICY["version"], "rows": len(splits), "original_split_counts": dict(Counter(r["split"] for r in splits.values())),
        "known_exposure_rows": len(known), "exposure_sources": exposure_counts,
        "family_components": len(groups), "mixed_split_components": contaminated_families,
        "exposed_test_components": exposed_test_families, "detectors": diagnostics, "near_join": near_stats,
        "corrected": {"eligible_rows": len(eligible), "quarantined_rows": len(quarantined),
            "split_counts": dict(Counter(r["split"] for r in eligible)),
            "category_split_counts": dict(Counter(r["category_id"] + ":" + r["split"] for r in eligible)),
            "detected_cross_split_components": 0, "exposed_test_components": 0},
        "reserve": {"rows": len(reserve), "unique_families": len(set(reserve_families)),
            "invalid_rows": len({r["sku_id"] for r in reserve_issues}), "status": "quarantine_required" if reserve_issues else "metadata_checks_passed",
            "text_exported": False, "predictions_generated": False,
            "blank_labels_validated": True, "gold_labels_read": False},
        "status": "corrected_partition_emitted" if quarantined else "no_detected_crossings",
        "sources": [{"file": p.name, "sha256": protected[str(p)]} for p in paths],
        "producer": {"git_sha": producer_sha, "git_dirty": producer_dirty,
                     "python": platform.python_version(), "os": platform.system()},
        "tool_sha256": digest(Path(__file__)), "normalizer_tool_sha256": digest(ROOT / "scripts/research/prepare_m2.py"),
        "visible_text_tool_sha256": digest(ROOT / "src/goodsai/text.py"),
        "limitations": ["Lexical matches are conservative candidate families, not semantic confirmation.",
            "No absence of all semantic duplicates is claimed below the fixed similarity threshold.",
            "Exposure inventory is recorded, not proof of all historical human accesses.",
            "Validation is development feedback. Candidate reserve is not human gold or measured quality.",
            "Versioned filtered partition does not replace old split or alter previous results."],
        "artifacts": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    dump(output / "audit.summary.json", report)
    return report


def verify(bundle):
    """Check immutable sources, checksums and disjointness without reopening text."""
    bundle = Path(bundle)
    report = json.loads((bundle / "audit.summary.json").read_text(encoding="utf-8"))
    require(report.get("version") == POLICY["version"], "unknown_audit_version")
    expected_files = set(report["artifacts"]) | {"audit.summary.json"}
    require({p.name for p in bundle.iterdir()} == expected_files, "artifact_inventory_mismatch")
    for name, checksum in report["artifacts"].items():
        require(Path(name).name == name and not (bundle / name).is_symlink(), "invalid_artifact_path")
        require(digest(bundle / name) == checksum, "artifact_hash_mismatch")
    policy = json.loads((bundle / "audit.policy.json").read_text(encoding="utf-8"))
    require(all(policy[k] == v for k, v in POLICY.items()), "audit_policy_mismatch")
    for name, checksum in policy["sources"].items():
        require(digest(Path(name)) == checksum, "source_hash_mismatch")
    members = unique_rows(bundle / "membership.jsonl")
    eligible = unique_rows(bundle / "eligible.split_manifest.jsonl", allow_empty=True)
    excluded = unique_rows(bundle / "quarantine.manifest.jsonl", allow_empty=True)
    require(not eligible.keys() & excluded.keys() and eligible.keys() | excluded.keys() == members.keys(),
            "partition_identity_mismatch")
    require(len(members) == report["rows"] and len(excluded) == report["corrected"]["quarantined_rows"],
            "partition_count_mismatch")
    family_splits, exposure = defaultdict(set), defaultdict(bool)
    for sku, record in members.items():
        require(record == (eligible.get(sku) or excluded.get(sku)), "partition_metadata_mismatch")
        require(bool(record["quarantine_reasons"]) == (sku in excluded), "quarantine_mismatch")
        require(record["split"] in SPLITS, "invalid_split")
        if sku in eligible:
            family_splits[record["family_id"]].add(record["split"])
            exposure[record["family_id"]] |= record["family_exposed"]
    require(all(len(values) == 1 for values in family_splits.values()), "eligible_family_crosses_splits")
    require(all(values != {"test_reserved"} or not exposure[family]
                for family, values in family_splits.items()), "eligible_test_exposed")
    require(dict(Counter(r["split"] for r in eligible.values())) == report["corrected"]["split_counts"],
            "split_counts_mismatch")
    # Cross-check all saved union edges independently of the builder's DSU.
    for edge in read_jsonl(bundle / "family.edges.jsonl"):
        require(members[edge["left"]]["family_id"] == members[edge["right"]]["family_id"], "broken_component_edge")
    for violation in read_jsonl(bundle / "violations.jsonl"):
        require(len({members[s]["family_id"] for s in violation["members"]}) == 1, "broken_violation_component")
    return {"status": "verified", "rows": len(members), "eligible_rows": len(eligible),
            "quarantined_rows": len(excluded), "sources_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/processed/e1/pilot.jsonl")
    parser.add_argument("--split", type=Path, default=ROOT / "data/gold/e1/split_manifest.jsonl")
    base = ROOT / "data/gold/e1/m2/v2"
    parser.add_argument("--families", type=Path, default=base / "family.manifest.jsonl")
    parser.add_argument("--m2-summary", type=Path, default=base / "selection.summary.json")
    parser.add_argument("--reserve", type=Path, default=base / "test_reserve.blank.jsonl")
    parser.add_argument("--exposure-source", type=Path, action="append")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-bundle", type=Path)
    args = parser.parse_args()
    exposures = args.exposure_source if args.exposure_source is not None else [
        ROOT / "data/gold/e1/tasks.jsonl", ROOT / "data/gold/e1/ai/full.annotations.v4.jsonl",
        ROOT / "data/gold/e1/m2/v1/development.tasks.jsonl", base / "development.tasks.jsonl"]
    try:
        require(bool(args.output_dir) != bool(args.verify_bundle), "choose_output_or_verify")
        if args.verify_bundle:
            result = verify(args.verify_bundle)
        else:
            require((ROOT / "outputs").resolve() in args.output_dir.resolve().parents, "output_must_be_private_outputs")
            result = audit(args.input, args.split, args.families, args.m2_summary, args.reserve, exposures, args.output_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Exception messages may contain paths or user data: expose only type.
        code = str(exc) if type(exc) is ValueError and str(exc).replace("_", "").isalnum() else type(exc).__name__
        parser.exit(2, "split audit failed: " + code + "\n")
    print(json.dumps(result if args.verify_bundle else {key: result[key] for key in
        ["status", "rows", "mixed_split_components", "corrected", "reserve"]}, indent=2))


if __name__ == "__main__":
    main()
