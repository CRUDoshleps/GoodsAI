"""Blind human review preparation; never annotates, predicts or opens test in stdout."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl
from goodsai.normalize import UNITS, model_name, numeric
from goodsai.text import visible_span
from scripts.research.audit_splits import dump, require, unique_rows, verify, write_rows

VERSION = "human-e1-v1"
GUIDE = ROOT / "docs/HUMAN_GOLD_GUIDELINES.md"
TEMPLATE = Path(__file__).with_name("human_gold_form.html")
STATUSES = {"present", "absent", "ambiguous", "unjudgeable", "unreviewed"}


def person(value):
    require(isinstance(value, str) and bool(value.strip()), "named_person_required")
    return " ".join(value.casefold().split())


def read(path):
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(result, dict), "object_required")
    return result


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def new_directory(path):
    path = Path(path).resolve()
    require(not path.exists(), "new_output_directory_required")
    path.mkdir(parents=True, exist_ok=False)
    return path


def seal(folder, kind):
    artifacts = {p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file()}
    package_id = hashlib.sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest()
    dump(folder / "manifest.json", {"version": VERSION, "kind": kind, "package_id": package_id, "artifacts": artifacts})
    return package_id


def checked(folder, kind):
    folder = Path(folder)
    manifest = read(folder / "manifest.json")
    require(manifest.get("version") == VERSION and manifest.get("kind") == kind, "package_kind_mismatch")
    require({p.name for p in folder.iterdir()} == set(manifest["artifacts"]) | {"manifest.json"}, "package_inventory_mismatch")
    for name, checksum in manifest["artifacts"].items():
        require(Path(name).name == name and not (folder / name).is_symlink(), "unsafe_artifact")
        require(digest(folder / name) == checksum, "package_hash_mismatch")
    require(hashlib.sha256(json.dumps(manifest["artifacts"], sort_keys=True).encode()).hexdigest()
            == manifest["package_id"], "package_identity_mismatch")
    return manifest


def prepare(audit_bundle, output, method_ref="work/main"):
    verify(audit_bundle)  # Rechecks source SHA, never prints source texts.
    audit_bundle = Path(audit_bundle).resolve()
    report = read(audit_bundle / "audit.summary.json")
    require(report["reserve"]["status"] == "metadata_checks_passed", "reserve_not_safe")
    sources = read(audit_bundle / "audit.policy.json")["sources"]
    reserve_paths = [Path(p) for p in sources if Path(p).name == "test_reserve.blank.jsonl"]
    input_paths = [Path(p) for p in sources if Path(p).name == "pilot.jsonl"]
    require(len(reserve_paths) == len(input_paths) == 1, "source_identity_ambiguous")
    members = unique_rows(audit_bundle / "eligible.split_manifest.jsonl")
    tasks = []
    for row in read_jsonl(reserve_paths[0]):
        sku = row["sku_id"]
        require(sku in members and members[sku]["split"] == "test_reserved"
                and not members[sku]["family_exposed"], "reserve_not_eligible")
        tasks.append({"task_id": row["review_id"], "sku_id": sku, "category_id": row["category_id"],
                      "family_id": members[sku]["family_id"], "attributes": row["attributes"]})
    require(len(tasks) == 40 and Counter(t["category_id"] for t in tasks) == {"761": 20, "482": 20},
            "expected_frozen_40_reserve")
    require(len({t["task_id"] for t in tasks}) == len(tasks), "duplicate_task_id")
    config = load_config()
    schema = {"schema_version": "0.1", "categories": config["categories"], "units": UNITS}
    for task in tasks:
        require([a["attribute"] for a in task["attributes"]] == schema["categories"][task["category_id"]],
                "reserve_schema_mismatch")
        task["attributes"] = [{"attribute": a["attribute"], "status": "unreviewed", "value": None,
                               "unit": None, "evidence": None, "notes": ""} for a in task["attributes"]]
    method_sha = git("rev-parse", method_ref + "^{commit}")
    method_tree = git("rev-parse", method_sha + ":src/goodsai")
    method_config = json.loads(git("show", method_sha + ":src/goodsai/baseline.json"))
    require(method_config == config, "method_config_differs_from_schema_source")
    config_sha = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    output = new_directory(output)
    write_rows(output / "tasks.metadata.jsonl", tasks)
    dump(output / "schema.json", schema)
    (output / "guidelines.md").write_bytes(GUIDE.read_bytes())
    dump(output / "plan.json", {"version": VERSION, "status": "pending_method_freeze_and_humans",
        "audit_bundle": str(audit_bundle), "audit_summary_sha256": digest(audit_bundle / "audit.summary.json"),
        "input_path": str(input_paths[0]), "input_sha256": digest(input_paths[0]),
        "reserve_sha256": digest(reserve_paths[0]), "method_git_sha": method_sha,
        "method_tree_sha": method_tree, "config_sha256": config_sha, "guideline_sha256": digest(GUIDE),
        "cards": len(tasks), "pairs": sum(len(t["attributes"]) for t in tasks),
        "independent_reference": False, "precision": None, "recall": None, "f1": None,
        "text_materialized": False, "predictions_used": False, "tool_sha256": digest(Path(__file__)),
        "form_sha256": digest(TEMPLATE)})
    dump(output / "freeze.template.json", {"approved": False, "approved_by": None,
        "method_git_sha": method_sha, "method_tree_sha": method_tree, "config_sha256": config_sha,
        "guideline_sha256": digest(GUIDE), "methods_and_thresholds_frozen": False,
        "no_test_based_tuning": False,
        "reviewers": {"A": {"id": "vlad", "worked_on_method": True, "seen_prior_development_ai": True},
                      "B": {"id": None}, "C": {"id": None}},
        "note": "A single reviewer cannot close EVAL-001. Do not approve before the method is actually frozen."})
    package_id = seal(output, "metadata")
    return {"status": "metadata_prepared", "cards": len(tasks), "pairs": sum(len(t["attributes"]) for t in tasks),
            "package_id": package_id, "text_materialized": False, "independent_reference": False}


def materialize(bundle, freeze_path, slot, output):
    bundle = Path(bundle)
    meta = checked(bundle, "metadata")
    plan, freeze = read(bundle / "plan.json"), read(freeze_path)
    require(freeze.get("approved") is True and isinstance(freeze.get("approved_by"), str)
            and freeze["approved_by"].strip(), "human_method_freeze_required")
    require(freeze.get("methods_and_thresholds_frozen") is True and freeze.get("no_test_based_tuning") is True,
            "method_not_frozen")
    require(all(freeze.get(k) == plan[k] for k in
                ["method_git_sha", "method_tree_sha", "config_sha256", "guideline_sha256"]), "freeze_identity_mismatch")
    require(git("rev-parse", plan["method_git_sha"] + ":src/goodsai") == plan["method_tree_sha"], "method_tree_mismatch")
    require(digest(Path(__file__)) == plan["tool_sha256"] and digest(TEMPLATE) == plan["form_sha256"], "tool_changed_after_preparation")
    reviewer = freeze.get("reviewers", {}).get(slot, {}).get("id")
    require(slot in {"A", "B"} and isinstance(reviewer, str) and reviewer.strip(), "named_reviewer_required")
    ids = [person(r["id"]) for r in freeze["reviewers"].values() if r.get("id")]
    require(len(ids) == len(set(ids)), "reviewer_identity_reused")
    verify(plan["audit_bundle"])
    require(digest(Path(plan["audit_bundle"]) / "audit.summary.json") == plan["audit_summary_sha256"], "audit_changed")
    source = Path(plan["input_path"])
    require(digest(source) == plan["input_sha256"], "input_hash_mismatch")
    metadata = list(read_jsonl(bundle / "tasks.metadata.jsonl"))
    wanted, products = {t["sku_id"] for t in metadata}, {}
    for row in read_jsonl(source):
        if row.get("sku_id") in wanted:
            require(row["sku_id"] not in products, "duplicate_selected_sku")
            products[row["sku_id"]] = Product.from_dict(row)
    require(products.keys() == wanted, "selected_source_missing")
    require(digest(source) == plan["input_sha256"], "source_changed")
    tasks = []
    for task in metadata:
        product = products[task["sku_id"]]
        require(product.category_id == task["category_id"], "task_category_mismatch")
        tasks.append({"task_id": task["task_id"], "category_id": task["category_id"],
                      "title": product.title, "description": product.description, "attributes": task["attributes"]})
    payload = {"package_id": meta["package_id"], "slot": slot, "reviewer_id": reviewer,
               "units": read(bundle / "schema.json")["units"], "tasks": tasks}
    output = new_directory(output)
    dump(output / "tasks.private.json", payload)
    dump(output / "freeze.json", freeze)
    dump(output / "origin.json", {"metadata_bundle": str(bundle.resolve()), "package_id": meta["package_id"]})
    (output / "guidelines.md").write_bytes((bundle / "guidelines.md").read_bytes())
    data = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    (output / "review.html").write_text(TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", data), encoding="utf-8")
    seal(output, "review")
    return {"status": "human_review_materialized", "cards": len(tasks), "slot": slot,
            "independent_reference": False, "predictions_used": False}


def evidence(label, task):
    e = label.get("evidence")
    require(isinstance(e, dict) and set(e) <= {"field", "text", "start", "end"}, "invalid_evidence")
    require(e.get("field") in {"title", "description"} and isinstance(e.get("text"), str) and e["text"], "quote_required")
    source, quote = task[e["field"]] or "", e["text"]
    positions = [i for i in range(len(source)) if source.startswith(quote, i)]
    start = e.get("start")
    if start is None:
        require(len(positions) == 1, "quote_missing_or_repeated_choose_start")
        start = positions[0]
    require(type(start) is int and start in positions, "evidence_offset_mismatch")
    end = start + len(quote)
    require("end" not in e or e["end"] == end, "evidence_end_mismatch")
    visible_span(source, start, end)
    return {"field": e["field"], "start": start, "end": end, "text": quote}


def answers(package, path, allow_partial=False):
    package = Path(package)
    checked(package, "review")
    payload, response = read(package / "tasks.private.json"), read(path)
    require(set(response) == {"package_id", "slot", "reviewer_id", "attestation", "tasks"}, "unknown_response_fields")
    require(all(response.get(k) == payload[k] for k in ["package_id", "slot", "reviewer_id"]), "response_identity_mismatch")
    attestation = response.get("attestation")
    require(isinstance(attestation, dict) and set(attestation) == {"human_only", "no_predictions_or_ai", "worked_independently"}
            and all(v is True for v in attestation.values()), "human_attestation_required")
    require(isinstance(response.get("tasks"), list), "tasks_list_required")
    expected = {t["task_id"]: t for t in payload["tasks"]}
    result, pending = {}, 0
    for row in response["tasks"]:
        require(isinstance(row, dict) and set(row) == {"task_id", "attributes"}, "invalid_answer_task")
        tid = row["task_id"]
        require(tid in expected and tid not in result, "answer_task_identity_mismatch")
        attrs = row.get("attributes")
        require(isinstance(attrs, list) and all(isinstance(a, dict) for a in attrs) and [a.get("attribute") for a in attrs]
                == [a["attribute"] for a in expected[tid]["attributes"]], "answer_attribute_schema_mismatch")
        clean = []
        for label in attrs:
            require(set(label) == {"attribute", "status", "value", "unit", "evidence", "notes"}, "invalid_label_fields")
            status, attr = label["status"], label["attribute"]
            require(status in STATUSES and isinstance(label["notes"], str), "invalid_label_status")
            if status == "present":
                require(isinstance(label["value"], str) and label["value"].strip(), "present_value_required")
                require(label["unit"] == UNITS.get(attr), "canonical_unit_required")
                if attr in UNITS:
                    require(numeric(attr, label["value"], label["unit"]) == label["value"], "canonical_numeric_required")
                e = evidence(label, expected[tid])
                if attr == "model":
                    visible = visible_span(expected[tid][e["field"]], e["start"], e["end"])
                    require(model_name(visible) == label["value"], "model_minimal_normalization_required")
                label = label | {"evidence": e}
            else:
                require(all(label[k] is None for k in ["value", "unit", "evidence"]), "nonpresent_must_be_empty")
                if status in {"ambiguous", "unjudgeable"}:
                    require(bool(label["notes"].strip()), "uncertainty_reason_required")
                if status == "unreviewed":
                    pending += 1
            clean.append(label)
        result[tid] = clean
    require(result.keys() == expected.keys(), "incomplete_task_set")
    require(allow_partial or pending == 0, "unreviewed_labels_remain")
    return payload, result, pending


def reconcile(package_a, answers_a, output, package_b=None, answers_b=None):
    pa, a, _ = answers(package_a, answers_a)
    require(bool(package_b) == bool(answers_b), "both_second_review_inputs_required")
    output = new_directory(output)
    if package_b is None:
        report = {"status": "single_human_review_complete", "cards": len(a), "pairs": sum(map(len, a.values())),
                  "independent_reference": False, "agreement": None, "precision": None, "recall": None, "f1": None,
                  "next": "Second independent human review and adjudication are required; no gold exported."}
        dump(output / "summary.json", report)
        seal(output, "comparison")
        return report
    pb, b, _ = answers(package_b, answers_b)
    require(pa["package_id"] == pb["package_id"] and pa["slot"] != pb["slot"]
            and person(pa["reviewer_id"]) != person(pb["reviewer_id"]), "independent_reviewer_identity_required")
    disagreements, status_match, value_match, span_match = [], 0, 0, 0
    ca, cb = Counter(), Counter()
    slices = {}
    task_categories = {t["task_id"]: t["category_id"] for t in pa["tasks"]}
    for tid in sorted(a):
        for left, right in zip(a[tid], b[tid]):
            same_status = left["status"] == right["status"]
            same_value = all(left[k] == right[k] for k in ["status", "value", "unit"])
            ca[left["status"]] += 1
            cb[right["status"]] += 1
            status_match += same_status
            value_match += same_value
            span_match += same_value and left["evidence"] == right["evidence"]
            for name in ["attribute:" + left["attribute"], "category:" + task_categories[tid]]:
                counts = slices.setdefault(name, Counter())
                counts.update(pairs=1, status_matches=int(same_status), canonical_matches=int(same_value))
            if not same_value:
                disagreements.append({"task_id": tid, "attribute": left["attribute"], "a": left, "b": right})
    n = sum(ca.values())
    observed = status_match / n
    expected = sum(ca[s] * cb[s] for s in STATUSES) / n**2
    report = {"status": "pending_adjudication" if disagreements else "pending_human_signoff",
        "cards": len(a), "pairs": n, "disagreement_pairs": len(disagreements),
        "agreement": {"status_exact": observed, "canonical_exact": value_match / n,
            "canonical_and_evidence_exact": span_match / n,
            "status_cohen_kappa": (observed-expected)/(1-expected) if expected < 1 else None},
        "agreement_slices": {k: dict(v) | {"canonical_exact": v["canonical_matches"] / v["pairs"]}
                             for k, v in sorted(slices.items())},
        "independent_reference": False, "precision": None, "recall": None, "f1": None,
        "responses": {"A": digest(Path(answers_a)), "B": digest(Path(answers_b))}}
    dump(output / "summary.json", report)
    write_rows(output / "disagreements.private.jsonl", disagreements)
    dump(output / "adjudication.template.json", {"approved": False, "adjudicator": None,
        "response_sha256": report["responses"], "all_labels_checked": False,
        "human_only": False, "no_test_based_tuning": False,
        "decisions": [{"task_id": d["task_id"], "attribute": d["attribute"], "label": None, "reason": ""}
                      for d in disagreements]})
    seal(output, "comparison")
    return report


def finalize(package_a, answers_a, package_b, answers_b, decision_path, output):
    pa, a, _ = answers(package_a, answers_a)
    pb, b, _ = answers(package_b, answers_b)
    require(pa["slot"] == "A" and pb["slot"] == "B" and pa["package_id"] == pb["package_id"]
            and person(pa["reviewer_id"]) != person(pb["reviewer_id"]), "independent_reviewer_identity_required")
    decision = read(decision_path)
    who = decision.get("adjudicator")
    require(isinstance(who, str) and who.strip()
            and person(who) not in {person(pa["reviewer_id"]), person(pb["reviewer_id"])}, "third_human_required")
    require(all(decision.get(k) is True for k in ["approved", "all_labels_checked", "human_only", "no_test_based_tuning"]),
            "human_signoff_required")
    require(decision.get("response_sha256") == {"A": digest(Path(answers_a)), "B": digest(Path(answers_b))}, "signoff_response_mismatch")
    resolved = {}
    for row in decision.get("decisions", []):
        require(isinstance(row, dict), "invalid_adjudication")
        key = row.get("task_id"), row.get("attribute")
        require(key not in resolved and isinstance(row.get("reason"), str) and row["reason"].strip(), "invalid_adjudication")
        resolved[key] = row.get("label")
    needed = {(tid, left["attribute"]) for tid in a for left, right in zip(a[tid], b[tid])
              if any(left[k] != right[k] for k in ["status", "value", "unit"])}
    require(resolved.keys() == needed, "adjudication_incomplete_or_extra")
    # Reuse exactly the same validation path for adjudicated labels.
    combined = read(answers_a)
    for task in combined["tasks"]:
        task["attributes"] = [resolved.get((task["task_id"], label["attribute"]), label) for label in a[task["task_id"]]]
    output = new_directory(output)
    dump(output / "adjudicated.answers.private.json", combined)
    _, labels, _ = answers(package_a, output / "adjudicated.answers.private.json")
    origin = read(Path(package_a) / "origin.json")
    metadata_bundle = Path(origin["metadata_bundle"])
    require(checked(metadata_bundle, "metadata")["package_id"] == pa["package_id"], "origin_identity_mismatch")
    mapping = {t["task_id"]: t for t in read_jsonl(metadata_bundle / "tasks.metadata.jsonl")}
    tasks = {t["task_id"]: t for t in pa["tasks"]}
    result = []
    for tid in sorted(tasks):
        t, m = tasks[tid], mapping[tid]
        result.append({"schema_version": "0.1", "sku_id": m["sku_id"], "category_id": t["category_id"],
            "title": t["title"], "description": t["description"], "seller_attributes": [], "source_flags": [],
            "split": "test_reserved", "group_id": m["family_id"], "review_id": tid,
            "annotation_status": "reviewed", "label_source": "manual", "annotator": who,
            "annotation_origin": "two_independent_humans_with_adjudication", "independent_reference": True,
            "independence_basis": "human_attestations_and_frozen_method_not_identity_authentication",
            "attributes": labels[tid]})
    write_rows(output / "reference.jsonl", result)
    for name, path in [("annotations.A.json", answers_a), ("annotations.B.json", answers_b),
                       ("adjudication.signed.json", decision_path),
                       ("freeze.A.json", Path(package_a) / "freeze.json"),
                       ("freeze.B.json", Path(package_b) / "freeze.json"),
                       ("guidelines.md", metadata_bundle / "guidelines.md"),
                       ("plan.json", metadata_bundle / "plan.json")]:
        (output / name).write_bytes(Path(path).read_bytes())
    dump(output / "provenance.json", {"version": VERSION, "package_id": pa["package_id"],
        "response_sha256": decision["response_sha256"], "decision_sha256": digest(Path(decision_path)),
        "reviewers": [pa["reviewer_id"], pb["reviewer_id"]], "adjudicator": who,
        "freeze_sha256": {"A": digest(Path(package_a) / "freeze.json"), "B": digest(Path(package_b) / "freeze.json")},
        "reference_sha256": digest(output / "reference.jsonl"), "precision": None, "recall": None, "f1": None})
    seal(output, "reference")
    return {"status": "human_reference_assembled", "cards": len(result), "independent_reference": True,
            "basis": "three_human_declarations_require_external_review", "predictions_used": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--audit-bundle", type=Path, required=True)
    p.add_argument("--method-ref", default="work/main")
    p.add_argument("--output-dir", type=Path, required=True)
    p = sub.add_parser("materialize")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--slot", choices=["A", "B"], required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    for command in ["check", "reconcile", "finalize"]:
        p = sub.add_parser(command)
        p.add_argument("--package-a", type=Path, required=True)
        p.add_argument("--answers-a", type=Path, required=True)
        if command != "check":
            p.add_argument("--package-b", type=Path, required=command == "finalize")
            p.add_argument("--answers-b", type=Path, required=command == "finalize")
        if command == "finalize":
            p.add_argument("--decisions", type=Path, required=True)
        if command != "check":
            p.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if hasattr(args, "output_dir"):
            require((ROOT / "outputs").resolve() in args.output_dir.resolve().parents, "output_must_be_private_outputs")
        if args.command == "prepare":
            result = prepare(args.audit_bundle, args.output_dir, args.method_ref)
        elif args.command == "materialize":
            result = materialize(args.bundle, args.freeze, args.slot, args.output_dir)
        elif args.command == "check":
            _, labels, pending = answers(args.package_a, args.answers_a, allow_partial=True)
            result = {"status": "validated", "cards": len(labels), "pending_pairs": pending, "independent_reference": False}
        elif args.command == "reconcile":
            result = reconcile(args.package_a, args.answers_a, args.output_dir, args.package_b, args.answers_b)
        else:
            result = finalize(args.package_a, args.answers_a, args.package_b, args.answers_b, args.decisions, args.output_dir)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        code = str(exc) if type(exc) is ValueError and str(exc).replace("_", "").isalnum() else type(exc).__name__
        parser.exit(2, "human gold: " + code + "\n")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
