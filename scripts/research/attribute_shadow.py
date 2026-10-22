"""Frozen per-attribute shadow audits; no runtime promotion or automatic labels."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from goodsai.attribute_shadow import PROTECTED_FLAGS, Selector, cell_id, default_plan, fingerprint, validate_plan
from goodsai.category_registry import Registry
from goodsai.cli import predict
from goodsai.config import _read_json, load_config
from goodsai.contracts import Product
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.normalize import UNITS
from goodsai.runtime import identity
from goodsai.silver_evaluate import evaluate_rows, fraction
from goodsai.silver_prepare import unique, verify_bundle
from scripts.research.audit_splits import dump, exposure_ids, require, write_rows
from scripts.research.human_gold import TEMPLATE, checked, evidence, seal
from scripts.research.storage_shadow import ROLES, precision_lower, review_html

PROTOCOL = ROOT / "docs/ATTRIBUTE_SHADOW.md"


def read(path):
    return _read_json(Path(path).read_text(encoding="utf-8"))


def tool_hashes():
    files = [Path(__file__), PROTOCOL, TEMPLATE, ROOT / "scripts/research/storage_shadow.py",
             ROOT / "scripts/research/human_gold.py", ROOT / "scripts/research/audit_splits.py"]
    return {str(p.relative_to(ROOT)): digest(p) for p in files}


def unchanged(freeze, config):
    require(all(digest(Path(p)) == h for p, h in freeze["source_hashes"].items()), "source_changed")
    require(tool_hashes() == freeze["tool_hashes"], "tool_changed_after_freeze")
    now = identity(config)
    require(all(now[k] == freeze["runtime"][k] for k in ("code_sha256", "config_sha256")), "runtime_changed_after_freeze")


@contextmanager
def publication(output, sources):
    output = Path(output).resolve()
    require(not output.exists() and "raw" not in {p.casefold() for p in output.parts}
            and all(output != p and p not in output.parents and output not in p.parents for p in sources),
            "new_private_output_outside_sources_required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".attribute-shadow-", dir=output.parent) as folder:
        stage = Path(folder) / "ready"
        stage.mkdir(mode=0o700)
        yield stage
        for p in stage.iterdir():
            if p.is_file():
                p.chmod(0o600)
        stage.rename(output)


def ranked(seed, namespace, value):
    return hashlib.sha256(f"{seed}:{namespace}:{value}".encode()).hexdigest()


def sample(candidates, metadata, seen, policy, seed, seen_families=()):
    blocked = {m["family_id"] for sku, m in metadata.items() if m.get("exposed") or sku in seen}
    blocked.update(seen_families)
    groups = defaultdict(list)
    for row in candidates:
        family = metadata[row["sku_id"]]["family_id"]
        if family not in blocked:
            groups[family].append(row)
    key = cell_id(policy["category_id"], policy["attribute"])
    selected = []
    for family in sorted(groups, key=lambda f: ranked(seed, key + ":family", f))[:policy["audit_families"]]:
        row = min(groups[family], key=lambda r: ranked(seed, key + ":sku", r["sku_id"]))
        selected.append(row | {"family_id": family})
    return selected, len(groups), len(blocked)


def materialize(stage, selected, products, reviewer, plan):
    tasks = []
    for index, row in enumerate(selected, 1):
        product, candidate = products[row["sku_id"]], row["candidate"]
        attr = candidate["attribute"]
        row["task_id"] = f"A{index:05}"
        tasks.append({"task_id": row["task_id"], "policy_id": row["policy_id"],
                      "category_id": product.category_id, "title": product.title,
                      "description": product.description,
                      "proposal": {k: candidate[k] for k in ("value", "unit", "evidence")},
                      "attributes": [{"attribute": attr, "status": "unreviewed", "value": None,
                                      "unit": None, "evidence": None, "notes": ""}]})
    package_id = fingerprint({"plan": plan, "selection": selected, "reviewer": reviewer})
    payload = {"package_id": package_id, "slot": "attribute-shadow", "reviewer_id": reviewer,
               "units": UNITS, "tasks": tasks}
    dump(stage / "tasks.private.json", payload)
    template = {k: deepcopy(v) for k, v in payload.items() if k != "units"}
    template["attestation"] = {"human_only": False, "candidate_checked": False, "exposure_disclosed": False}
    template["tasks"] = [{"task_id": t["task_id"], "attributes": deepcopy(t["attributes"])} for t in tasks]
    dump(stage / "answers.blank.json", template)
    for offset in range(0, len(tasks), plan["batch_size"]):
        page = payload | {"tasks": tasks[offset:offset + plan["batch_size"]]}
        # Each form intentionally has the full package identity. Assess accepts
        # one merged complete answer set; missing tasks never count as success.
        html = review_html(page).replace("роль памяти", "роль характеристики")
        (stage / f"review-{offset // plan['batch_size'] + 1:03}.html").write_text(html, encoding="utf-8")
    # Full form supports one portable answers file, partial work saved/reloaded.
    if tasks:
        (stage / "review.html").write_text(review_html(payload).replace("роль памяти", "роль характеристики"), encoding="utf-8")
    else:
        (stage / "review.html").write_text('<!doctype html><meta charset="utf-8"><p>Нет подходящих непросмотренных семейств.</p>', encoding="utf-8")
    return payload


def markdown(report):
    lines = ["# Per-attribute acceptance shadow", "", "Runtime auto_accept is unchanged. Independent human quality: N/A.",
             "Catalog agreement is noisy development feedback; targets are group precision, not heuristic scores.", "",
             "| Category / attribute | Requested | Candidates | Shadow selected | Audit families | Catalog TP / mismatch / unknown / conflict | Human status |",
             "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for key, value in report["fields"].items():
        c = value["catalog"]
        lines.append(f"| {key} | {value['requested']} | {value['found']} | {value['selected']} | {value['audit_sample_size']} | "
                     f"{c['tp']} / {c['mismatch']} / {c['unknown']} / {c['conflict']} | {value['human_status']} |")
    return "\n".join(lines) + "\n"


def prepare(bundle, plan_path, output, *, seen_paths=(), reviewer):
    require(isinstance(reviewer, str) and reviewer.strip() and len(reviewer) <= 128, "named_reviewer_required")
    bundle, plan_path = Path(bundle).resolve(strict=True), Path(plan_path).resolve(strict=True)
    manifest = verify_bundle(bundle)
    require(manifest.get("protected_text_exported") is False, "protected_population_not_excluded")
    config = load_config()
    require(read(bundle / "policy.json")["config"] == config, "bundle_config_mismatch")
    plan = validate_plan(read(plan_path), config)
    selector = Selector(config, plan)
    seen_paths = [Path(p).resolve(strict=True) for p in seen_paths]
    files = [bundle / "manifest.json", bundle / "input.jsonl", bundle / "reference.jsonl",
             bundle / "metadata.jsonl", bundle / "policy.json", plan_path, *seen_paths]
    require(len(set(files)) == len(files), "repeated_source_path")
    freeze = {"plan": plan, "source_hashes": {str(p): digest(p) for p in files},
              "tool_hashes": tool_hashes(), "runtime": identity(config), "independent_reference": False}
    with publication(output, [bundle, *files]) as stage:
        dump(stage / "freeze.json", freeze)  # Before input/reference/predictions are parsed.
        metadata = unique(read_jsonl(bundle / "metadata.jsonl"))
        roles = defaultdict(set)
        for m in metadata.values():
            require(m.get("original_split") in {"development", "validation"} and m.get("role") in ROLES,
                    "protected_or_unknown_split")
            require(isinstance(m.get("family_id"), str) and bool(m["family_id"]), "missing_family")
            roles[m["family_id"]].add(m["role"])
        require(all(len(v) == 1 for v in roles.values()), "cross_role_family")
        inputs = unique(read_jsonl(bundle / "input.jsonl"))
        require(inputs.keys() == metadata.keys(), "input_metadata_mismatch")
        products = {sku: Product.from_dict(row) for sku, row in inputs.items()}
        require(all(p.category_id == metadata[sku]["category_id"] for sku, p in products.items()), "category_mismatch")
        require(all(not PROTECTED_FLAGS.intersection(flag.casefold() for flag in p.source_flags) for p in products.values()),
                "protected_input_flags")
        seen = set().union(*(exposure_ids(p) for p in seen_paths)) if seen_paths else set()
        seen_families = set()
        for path in seen_paths:
            records = read_jsonl(path) if path.suffix == ".jsonl" else read(path)
            for record in records:
                if "family_id" in record:
                    family = record["family_id"]
                    require(isinstance(family, str) and bool(family.strip()), "invalid_exposure_family")
                    seen_families.add(family)
        cold = predict(bundle / "input.jsonl", stage / "predictions.jsonl", config)
        predict(bundle / "input.jsonl", stage / "repeat.jsonl", config)
        require(digest(stage / "predictions.jsonl") == digest(stage / "repeat.jsonl"), "non_deterministic_predictions")
        predictions = unique(read_predictions(stage / "predictions.jsonl"))
        require(predictions.keys() == products.keys(), "prediction_population_mismatch")
        candidates, exclusions, requested, found = defaultdict(list), defaultdict(Counter), Counter(), Counter()
        for sku, product in products.items():
            row = predictions[sku]
            by_attr = {a["attribute"]: a for a in row["attributes"]}
            for key, reason in selector.select(product, row).items():
                attr = key.split(":", 1)[1]
                requested[key] += 1
                found[key] += int(by_attr.get(attr, {}).get("decision") == "review")
                exclusions[key][reason or "selected"] += 1
                if reason is None:
                    candidates[key].append({"policy_id": key, "sku_id": sku, "candidate": by_attr[attr]})
        selected, fields = [], {}
        for p in plan["policies"]:
            key = cell_id(p["category_id"], p["attribute"])
            sampled, available, blocked = sample(candidates[key], metadata, seen, p, plan["seed"], seen_families)
            selected.extend(sampled)
            fields[key] = {"policy": p, "requested": requested[key], "found": found[key], "selected": len(candidates[key]),
                           "shadow_coverage": fraction(len(candidates[key]), requested[key]),
                           "audit_sample_size": len(sampled), "available_unexposed_families": available,
                           "exposure_blocked_families": blocked, "exclusions": dict(exclusions[key]),
                           "human_status": "pending" if sampled else "no_unexposed_eligible_families",
                           "human_precision": None, "runtime_authorized": False}
        materialize(stage, selected, products, reviewer, plan)
        write_rows(stage / "selection.private.jsonl", selected)  # Selection frozen BEFORE catalog labels are read.
        refs = unique(read_jsonl(bundle / "reference.jsonl"))
        require(refs.keys() == products.keys(), "reference_population_mismatch")
        # Reuse the existing evaluator; it also validates reference fields/schema/support.
        evaluation, _, _ = evaluate_rows(inputs.values(), refs.values(), metadata.values(), predictions.values(), config)
        dump(stage / "catalog.diagnostics.json", evaluation)
        for key, values in candidates.items():
            counts = Counter(tp=0, mismatch=0, unknown=0, conflict=0)
            attr = key.split(":", 1)[1]
            for item in values:
                label = next(a for a in refs[item["sku_id"]]["attributes"] if a["attribute"] == attr)
                candidate = item["candidate"]
                if label["status"] == "known":
                    equal = (label["value"], label["unit"]) == (candidate["value"], candidate["unit"])
                    counts["tp" if equal else "mismatch"] += 1
                else:
                    counts[label["status"]] += 1
            fields[key]["catalog"] = dict(counts)
            fields[key]["catalog_precision"] = fraction(counts["tp"], counts["tp"] + counts["mismatch"])
        for key in fields:
            fields[key].setdefault("catalog", dict(tp=0, mismatch=0, unknown=0, conflict=0))
            fields[key].setdefault("catalog_precision", None)
        report = {"policy_version": plan["policy_version"], "plan_sha256": fingerprint(plan), "fields": fields,
                  "cards": len(products), "audit_tasks": len(selected), "runtime_auto_accept_changed": False,
                  "independent_reference": False, "test_reserved_opened": False, "llm_calls": 0,
                  "repeat_predictions_identical": True, "resources": {k: cold[k] for k in
                    ("elapsed_seconds", "extractor_p50_ms", "extractor_p95_ms", "peak_process_rss_bytes")},
                  "exposure_scope": "supplied_metadata_and_seen_ledgers_only",
                  "limitations": ["Proposal-visible developer audit is not independent calibration.",
                                  "One candidate per family per field; families may repeat across fields.",
                                  "Selection is frozen before reference, targets before predictions.",
                                  "No shadow target authorizes runtime acceptance."]}
        unchanged(freeze, config)
        dump(stage / "diagnostics.json", report)
        (stage / "summary.md").write_text(markdown(report), encoding="utf-8")
        seal(stage, "attribute-shadow")
    return report


def assess(bundle, answers_path, output):
    bundle, answers_path = Path(bundle).resolve(strict=True), Path(answers_path).resolve(strict=True)
    package = checked(bundle, "attribute-shadow")
    freeze = read(bundle / "freeze.json")
    config = load_config()
    unchanged(freeze, config)
    payload, response = read(bundle / "tasks.private.json"), read(answers_path)
    answer_hash = digest(answers_path)
    require(isinstance(response, dict) and set(response) == {"package_id", "slot", "reviewer_id", "attestation", "tasks"}, "answer_fields")
    require(all(response[k] == payload[k] for k in ("package_id", "slot", "reviewer_id")), "answer_identity")
    att = response["attestation"]
    require(isinstance(att, dict) and set(att) == {"human_only", "candidate_checked", "exposure_disclosed"}
            and all(v is True for v in att.values()), "human_attestation_required")
    require(isinstance(response["tasks"], list), "answer_tasks_required")
    tasks = {t["task_id"]: t for t in payload["tasks"]}
    selection = {r["task_id"]: r for r in read_jsonl(bundle / "selection.private.jsonl")}
    counts = {cell_id(p["category_id"], p["attribute"]): Counter(correct=0, incorrect=0, unresolved=0, pending=0)
              for p in freeze["plan"]["policies"]}
    observed, judgments = set(), []
    registry = Registry(config)
    for row in response["tasks"]:
        require(isinstance(row, dict) and set(row) == {"task_id", "attributes"}
                and isinstance(row["task_id"], str) and row["task_id"] in tasks and row["task_id"] not in observed
                and isinstance(row["attributes"], list) and len(row["attributes"]) == 1, "answer_task_identity")
        tid, task = row["task_id"], tasks[row["task_id"]]
        observed.add(tid)
        label = row["attributes"][0]
        require(isinstance(label, dict) and set(label) == {"attribute", "status", "value", "unit", "evidence", "notes"}
                and label["attribute"] == task["attributes"][0]["attribute"] and isinstance(label["notes"], str), "answer_label_fields")
        status = label["status"]
        require(status in {"present", "absent", "ambiguous", "unjudgeable", "unreviewed"}, "answer_status")
        if status == "present":
            require(isinstance(label["value"], str) and bool(label["value"].strip())
                    and label["unit"] == task["proposal"]["unit"], "answer_value_unit")
            label = label | {"evidence": evidence(label, task)}
            value = registry.normalize_reference(task["category_id"], label["attribute"], label["value"], label["unit"])
            outcome = "correct" if value == task["proposal"]["value"] else "incorrect"
        else:
            require(all(label[k] is None for k in ("value", "unit", "evidence")), "nonpresent_fields_not_empty")
            require(status not in {"ambiguous", "unjudgeable"} or bool(label["notes"].strip()), "uncertainty_reason_required")
            outcome = "pending" if status == "unreviewed" else "incorrect" if status == "absent" else "unresolved"
        counts[task["policy_id"]][outcome] += 1
        judgments.append({"task_id": tid, "policy_id": task["policy_id"], "outcome": outcome, "label": label})
    require(observed == tasks.keys(), "incomplete_task_set")
    fields = {}
    policies = freeze["plan"]["policies"]
    for policy in policies:
        key = cell_id(policy["category_id"], policy["attribute"])
        count = counts[key]
        n = sum(count.values())
        complete = n > 0 and count["pending"] == 0
        lower = precision_lower(count["correct"], n) if complete else None
        simultaneous = precision_lower(count["correct"], n, alpha=.05 / len(policies)) if complete else None
        target = policy["target_precision"]
        required = math.ceil(math.log(.05) / math.log(target)) if target < 1 else None
        simultaneous_required = math.ceil(math.log(.05 / len(policies)) / math.log(target)) if target < 1 else None
        fields[key] = {"counts": dict(count), "sample_size": n, "review_complete": complete,
                       "target_precision": target, "human_precision_family_sample": fraction(count["correct"], n) if complete else None,
                       "one_sided_lower_95": lower, "simultaneous_lower_95_bonferroni": simultaneous,
                       "numerical_target_met": lower is not None and lower >= target,
                       "simultaneous_target_met": simultaneous is not None and simultaneous >= target,
                       "minimum_all_correct_families_for_target": required,
                       "minimum_all_correct_families_for_simultaneous_target": simultaneous_required,
                       "status": "no_audit_cases" if not n else "pending" if not complete else
                                 "numerical_target_met_pending_approval" if lower >= target else "insufficient_evidence_for_target",
                       "runtime_authorized": False}
    result = {"policy_version": freeze["plan"]["policy_version"], "plan_sha256": fingerprint(freeze["plan"]),
              "fields": fields, "answers_sha256": answer_hash, "package_manifest_sha256": digest(bundle / "manifest.json"),
              "independent_reference": False, "runtime_auto_accept_changed": False,
              "limitations": ["Binomial bounds require representative independent family observations.",
                              "Targets fixed before inference; do not tune on these answers and relabel prospective.",
                              "Unresolved cases count as failures in the conservative bound.",
                              "Numerical success does not grant runtime authorization."]}
    unchanged(freeze, config)
    require(digest(answers_path) == answer_hash, "answers_changed")
    with publication(output, [bundle, answers_path]) as stage:
        dump(stage / "human.metrics.json", result)
        write_rows(stage / "human.judgments.private.jsonl", judgments)
        write_rows(stage / "exposure.receipt.jsonl", [
            {"sku_id": selection[t]["sku_id"], "family_id": selection[t]["family_id"], "policy_id": selection[t]["policy_id"]}
            for t in sorted(observed)])
        seal(stage, "attribute-shadow-reviewed")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--seen", type=Path, action="append", default=[])
    p.add_argument("--reviewer", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p = sub.add_parser("assess")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--answers", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan = default_plan(load_config())
            args.output.parent.mkdir(parents=True, exist_ok=True)
            dump(args.output, plan)
            args.output.chmod(0o600)
            result = {"status": "plan_created", "policies": len(plan["policies"]), "plan_sha256": fingerprint(plan)}
        elif args.command == "prepare":
            report = prepare(args.bundle, args.plan, args.output_dir, seen_paths=args.seen, reviewer=args.reviewer)
            result = {"status": "shadow_prepared", "fields": len(report["fields"]), "audit_tasks": report["audit_tasks"]}
        else:
            report = assess(args.bundle, args.answers, args.output_dir)
            result = {"status": "human_audit_assessed", "fields": len(report["fields"]), "runtime_authorized": False}
        print(json.dumps(result, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print("goodsai: attribute_shadow_failed: check frozen inputs, plan and human answers", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("goodsai: attribute_shadow_interrupted", file=sys.stderr)
        return 130
    except Exception:
        print("goodsai: attribute_shadow_internal_error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
