"""Offline EVAL-003 handoff: replay existing human validation and evaluator, never infer."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from goodsai.config import load_config
from goodsai.contracts import Product, validate_prediction
from goodsai.data import digest, preparation_directory, read_jsonl
from goodsai.evaluate import evaluate
from goodsai.storage import prediction_snapshot
from scripts.research import human_gold as human
from scripts.research.compare_model_stage import compare
from scripts.release.build_release import code_hash, config_hash, index_rows

VERSION = "quality-evidence-v1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
RUNS = ("baseline", "hybrid")
INPUT_FIELDS = ("schema_version", "sku_id", "category_id", "title", "description", "seller_attributes", "source_flags")
EVALUATOR_PATH = Path(sys.modules[evaluate.__module__].__file__)


def require(condition, code):
    if not condition:
        raise ValueError(code)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), "object_required")
    return value


def source(item, base):
    require(isinstance(item, dict) and set(item) == {"path", "sha256"}
            and isinstance(item["path"], str) and bool(item["path"])
            and isinstance(item["sha256"], str) and SHA.fullmatch(item["sha256"]), "invalid_artifact_record")
    path = base / item["path"]
    require(path.is_file() and not path.is_symlink(), "artifact_missing_or_symlink")
    require(digest(path) == item["sha256"], "artifact_hash_mismatch")
    return path.resolve()


def capture(item, base, target):
    path = source(item, base)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    require(digest(target) == item["sha256"], "artifact_changed_during_capture")
    return target


def folder_capture(item, base, target, kind):
    path = source(item, base)
    require(path.name == "manifest.json", "sealed_manifest_required")
    before = human.checked(path.parent, kind)
    target.mkdir(parents=True)
    for name in [*before["artifacts"], "manifest.json"]:
        shutil.copyfile(path.parent / name, target / name)
    require(human.checked(target, kind) == before and digest(target / "manifest.json") == item["sha256"],
            "sealed_package_changed")
    return target


def destination(path, root):
    path, allowed = Path(path).resolve(), (root / "outputs").resolve()
    require(allowed == root.resolve() / "outputs" and allowed in path.parents, "output_must_be_private_outputs")
    return path


def template():
    return {"version": VERSION, "purpose": "independent_evaluation", "input": None,
            "reference_package": None, "review_packages": {"A": None, "B": None},
            "runs": [{"name": name, "status": "not_run", "reason": "frozen_predictions_not_supplied"}
                     for name in RUNS]}


def blocked(reasons):
    return {"version": VERSION, "status": "blocked", "blockers": reasons,
            "independent_reference": False, "final_acceptance": "blocked",
            "precision": None, "recall": None, "f1": None,
            "runs": {name: {"status": "not_run", "metrics": None} for name in RUNS},
            "limitations": ["Human gold #6 is required; no inference or test materialization performed.",
                            "Preparation and synthetic checks do not establish independent quality."]}


def finish(folder, report):
    save(folder / "public/report.json", report)
    lines = ["# Quality evidence", "", "Status: " + report["status"],
             "Final acceptance: " + report["final_acceptance"], "",
             "Integrity/recomputed metrics do not authenticate people or prove process independence."]
    for reason in report.get("blockers", []):
        lines.append("- " + reason)
    for name, run in report["runs"].items():
        lines += ["", "## " + name, "Status: " + run["status"]]
        micro = (run.get("evaluation") or {}).get("metrics", {}).get("micro")
        lines.append("Metrics: " + (json.dumps(micro, sort_keys=True) if micro else "N/A"))
    for limitation in report["limitations"]:
        lines.append("- " + limitation)
    (folder / "public/report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    artifacts = {p.relative_to(folder).as_posix(): digest(p) for p in sorted(folder.rglob("*")) if p.is_file()}
    save(folder / "manifest.json", {"version": VERSION, "artifacts": artifacts})
    # Public subset: hashes are not authorization to distribute private artifacts.
    save(folder / "public/integrity.json", {"version": VERSION, "manifest_sha256": digest(folder / "manifest.json"),
                                           "artifacts": artifacts})


def prepare(output, *, root=ROOT):
    output = destination(output, root)
    with preparation_directory(output) as staged:
        save(staged / "evaluation.spec.template.json", template())
        report = blocked(["independent_human_gold_missing", "frozen_predictions_missing"])
        finish(staged, report)
    return report


def human_reference(spec, base, folder):
    ref = folder / "private/human/reference"
    folder_capture(spec["reference_package"], base, ref, "reference")
    packages = {}
    for slot in ("A", "B"):
        packages[slot] = folder_capture(spec["review_packages"][slot], base,
                                       folder / ("private/human/" + slot), "review")
    # Original packages retain origin pointers to the sealed EVAL-001 metadata.
    # Replay validates all human answers/adjudication instead of trusting a boolean in a JSONL.
    freeze = read(ref / "freeze.A.json")
    require(freeze == read(ref / "freeze.B.json"), "human_freezes_differ")
    require(all(freeze.get(k) is True for k in ["approved", "methods_and_thresholds_frozen", "no_test_based_tuning"])
            and isinstance(freeze.get("approved_by"), str) and bool(freeze["approved_by"].strip()),
            "approved_method_freeze_required")
    for slot in ("A", "B"):
        require(read(packages[slot] / "freeze.json") == freeze, "review_package_freeze_mismatch")
        require(read(packages[slot] / "tasks.private.json")["reviewer_id"] == freeze["reviewers"][slot]["id"],
                "reviewer_freeze_mismatch")
    with tempfile.TemporaryDirectory(prefix="quality-human-") as temp:
        temp = Path(temp)
        agreement = human.reconcile(packages["A"], ref / "annotations.A.json", temp / "agreement",
                                    packages["B"], ref / "annotations.B.json")
        human.finalize(packages["A"], ref / "annotations.A.json", packages["B"], ref / "annotations.B.json",
                       ref / "adjudication.signed.json", temp / "reference")
        require(digest(temp / "reference/reference.jsonl") == digest(ref / "reference.jsonl"),
                "reference_replay_mismatch")
    plan = read(ref / "plan.json")
    require(all(freeze.get(k) == plan.get(k) for k in
                ["method_git_sha", "method_tree_sha", "config_sha256", "guideline_sha256"]),
            "freeze_plan_mismatch")
    require(digest(ref / "guidelines.md") == plan["guideline_sha256"], "guideline_hash_mismatch")
    human.verify(plan["audit_bundle"])  # Existing auditor checks metadata/hashes, without parsing test texts.
    require(digest(Path(plan["audit_bundle"]) / "audit.summary.json") == plan["audit_summary_sha256"],
            "human_audit_changed")
    eligible = human.unique_rows(Path(plan["audit_bundle"]) / "eligible.split_manifest.jsonl")
    for row in read_jsonl(ref / "reference.jsonl"):
        member = eligible.get(row["sku_id"], {})
        require(member.get("split") == "test_reserved" and member.get("family_exposed") is False
                and member.get("family_id") == row.get("group_id"), "reference_not_reserved_or_exposed")
    provenance = read(ref / "provenance.json")
    require(provenance.get("reference_sha256") == digest(ref / "reference.jsonl")
            and provenance.get("response_sha256") == agreement["responses"], "human_provenance_mismatch")
    # Agreement summary contains only aggregates, not reviewer IDs or per-card data.
    agreement = {k: agreement[k] for k in ["cards", "pairs", "disagreement_pairs", "agreement", "agreement_slices"]}
    return ref / "reference.jsonl", freeze, agreement


def frozen_code(freeze):
    commit = freeze["method_git_sha"]
    require(isinstance(commit, str) and re.fullmatch(r"[a-f0-9]{40}", commit), "invalid_method_commit")
    require(human.git("rev-parse", commit + ":src/goodsai") == freeze["method_tree_sha"], "method_tree_mismatch")
    archive = subprocess.check_output(["git", "archive", commit, "src/goodsai"], cwd=ROOT,
                                      stderr=subprocess.DEVNULL)
    hashed = hashlib.sha256()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        files = [m for m in stream.getmembers() if m.isfile() and Path(m.name).parent.as_posix() == "src/goodsai"
                 and m.name.endswith(".py")]
        require(bool(files), "method_source_missing")
        for member in sorted(files, key=lambda m: m.name):
            hashed.update(Path(member.name).name.encode())
            hashed.update(stream.extractfile(member).read())
    return hashed.hexdigest()


def evaluate_runs(folder, spec, inputs, reference, freeze):
    products = {sku: Product.from_dict(row) for sku, row in index_rows(inputs).items()}
    gold = index_rows(reference)
    require(products.keys() == gold.keys(), "input_reference_sku_mismatch")
    for sku, product in products.items():
        reference_product = Product.from_dict({k: gold[sku][k] for k in INPUT_FIELDS if k in gold[sku]})
        require(product.as_dict() == reference_product.as_dict(), "input_reference_text_mismatch")
        require(gold[sku].get("independent_reference") is True
                and gold[sku].get("annotation_origin") == "two_independent_humans_with_adjudication",
                "independent_human_origin_required")
    results, variants = {}, {}
    producer_hash = frozen_code(freeze)
    for run in spec["runs"]:
        name = run["name"]
        if run["status"] == "not_run":
            results[name] = {"status": "not_run", "reason": run["reason"], "evaluation": None}
            continue
        run_dir = folder / "private" / name
        config = load_config(run_dir / "config.json")
        manifest = read(run_dir / "predictions.manifest.json")
        semantic_config = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        require(semantic_config == freeze["config_sha256"], "config_not_frozen")
        require(manifest.get("input_sha256") == digest(inputs)
                and manifest.get("output_sha256") == digest(run_dir / "predictions.jsonl")
                and manifest.get("config_sha256") == config_hash(config), "prediction_hash_mismatch")
        require(manifest.get("git_commit") == freeze["method_git_sha"] and manifest.get("git_dirty") is False
                and manifest.get("code_sha256") == producer_hash,
                "prediction_method_not_frozen")
        policy = manifest.get("runtime_policy")
        require(isinstance(policy, dict) and manifest.get("runtime_policy_sha256") == config_hash(policy)
                and manifest.get("effective_config") == {"profile": config, "runtime_policy": policy}
                and manifest.get("effective_config_sha256") == config_hash(manifest["effective_config"]),
                "effective_policy_identity_mismatch")
        require(name != "baseline" or policy.get("llm_enabled") is False, "baseline_must_be_rules_only")
        predictions = index_rows(run_dir / "predictions.jsonl")
        require(predictions.keys() == products.keys(), "prediction_sku_mismatch")
        require(type(manifest.get("rows")) is int and manifest["rows"] == len(products), "prediction_count_mismatch")
        decisions, reasons, statuses = Counter(), Counter(), Counter()
        for sku, row in predictions.items():
            validate_prediction(row, config, products[sku])
            require(row["run_id"] == manifest.get("run_id") and bool(row["run_id"]), "prediction_run_id_mismatch")
            statuses[row["status"]] += 1
            for attr in row["attributes"]:
                require(isinstance(attr.get("reason_codes"), list)
                        and all(isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code)
                                for code in attr["reason_codes"]), "invalid_reason_code")
                require(name != "baseline" or attr.get("method") == "rule", "baseline_must_be_rules_only")
                decisions[attr["decision"]] += 1
                reasons.update(attr["reason_codes"])
        require(dict(statuses) == manifest.get("status_counts"), "prediction_status_count_mismatch")
        report = evaluate(run_dir / "predictions.jsonl", reference, config)
        require(report.get("evaluation_status") == "manual_reference" and report["pending_cards"] == 0
                and report["missing_prediction_cards"] == 0, "reference_not_judgeable")
        results[name] = {"status": "evaluated", "evaluation": report,
                         "status_counts": dict(statuses), "decision_counts": dict(decisions), "reason_counts": dict(reasons),
                         "producer": {k: manifest.get(k) for k in
                                      ["git_commit", "code_sha256", "config_sha256", "runtime_policy_sha256",
                                       "effective_config_sha256", "run_id"]}}
        # The existing comparator expects one attribute per requested field.
        # A failed row is a missing value, never silently excluded or called a successful abstention.
        # This view is only for paired diagnostics; the captured predictions stay unchanged.
        variants[name] = {sku: row if row["attributes"] else row | {"attributes": [
            {"attribute": attr, "value": None, "unit": None, "source_row_status": row["status"]}
            for attr in config["categories"][products[sku].category_id]]} for sku, row in predictions.items()}
    if len(variants) == 2:
        changes = compare(list(gold.values()), variants, transitions=(("baseline", "hybrid"),))
        paired = {"changed_pairs": len(changes),
                  "transitions": dict(Counter(r["before_verdict"] + "->" + r["after_verdict"] for r in changes)),
                  "new_tp": sum(r["before_verdict"] != "TP" and r["after_verdict"] == "TP" for r in changes),
                  "new_fp": sum("FP" not in r["before_verdict"] and "FP" in r["after_verdict"] for r in changes),
                  "lost_tp": sum(r["before_verdict"] == "TP" and r["after_verdict"] != "TP" for r in changes)}
    else:
        changes, paired = [], {"status": "not_run", "reason": "hybrid_predictions_missing"}
    return results, paired, changes


def validate_spec(spec):
    require(set(spec) == {"version", "purpose", "input", "reference_package", "review_packages", "runs"}
            and spec["version"] == VERSION
            and spec["purpose"] in {"independent_evaluation", "synthetic_workflow_check"}, "invalid_spec")
    require(isinstance(spec["review_packages"], dict) and set(spec["review_packages"]) == {"A", "B"}, "invalid_review_packages")
    runs = spec["runs"]
    require(isinstance(runs, list) and len(runs) == 2 and [r.get("name") for r in runs if isinstance(r, dict)] == list(RUNS),
            "baseline_and_hybrid_required")
    for run in runs:
        if run.get("status") == "not_run":
            require(set(run) == {"name", "status", "reason"} and isinstance(run["reason"], str)
                    and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", run["reason"]),
                    "not_run_reason_required")
        else:
            require(set(run) == {"name", "status", "predictions", "manifest", "config"}
                    and run["status"] == "completed", "invalid_run")


def assemble(spec_path, output, *, root=ROOT):
    spec_path = Path(spec_path).resolve()
    spec = read(spec_path)
    validate_spec(spec)
    output = destination(output, root)
    with preparation_directory(output, spec_path) as staged:
        save(staged / "private/evaluation.spec.json", spec)
        if spec["reference_package"] is None:
            require(spec["input"] is None and all(v is None for v in spec["review_packages"].values())
                    and all(r["status"] == "not_run" for r in spec["runs"]), "incomplete_reference_spec")
            report = blocked(["independent_human_gold_missing", "frozen_predictions_missing"])
        else:
            require(spec["runs"][0]["status"] == "completed", "baseline_predictions_required")
            reference, freeze, agreement = human_reference(spec, spec_path.parent, staged)
            inputs = capture(spec["input"], spec_path.parent, staged / "private/input.jsonl")
            for run in spec["runs"]:
                if run["status"] == "not_run":
                    continue
                run_dir = staged / "private" / run["name"]
                # Lock/check the original pair before capturing either file. Recheck explicit hashes too.
                predictions = source(run["predictions"], spec_path.parent)
                with prediction_snapshot(predictions):
                    for key, name in [("predictions", "predictions.jsonl"), ("manifest", "predictions.manifest.json"),
                                      ("config", "config.json")]:
                        capture(run[key], spec_path.parent, run_dir / name)
            runs, paired, changes = evaluate_runs(staged, spec, inputs, reference, freeze)
            save(staged / "private/changed_pairs.json", {"changes": changes})
            report = {"version": VERSION, "purpose": spec["purpose"],
                      "status": "synthetic_workflow_checked" if spec["purpose"] == "synthetic_workflow_check"
                                else "assembled_awaiting_process_review",
                      "final_acceptance": "blocked", "independent_reference": False,
                      "independence_basis": "human_attestations_replayed_not_identity_authentication",
                      "blockers": ["synthetic_only" if spec["purpose"] == "synthetic_workflow_check"
                                   else "independent_human_process_review_required", "model_artifact_freeze_not_verified"],
                      "agreement": agreement, "runs": runs, "paired": paired,
                      "input_sha256": digest(inputs), "reference_sha256": digest(reference),
                      "evaluator_sha256": digest(EVALUATOR_PATH), "evaluation_runtime_sha256": code_hash(ROOT),
                      "tool_sha256": digest(Path(__file__)), "python": platform.python_version(),
                      "limitations": ["Exact evidence is not complete semantic relation validation.",
                                      "Current evaluator has no grouped confidence intervals; small samples are limited.",
                                      "Latency, cost, seller/rare slices require separate measured artifacts; not inferred here.",
                                      "No inference, model API, calibration, auto_accept or new reserve materialization performed."]}
        finish(staged, report)
    return report


def verify(bundle, expected_sha256=None):
    bundle = Path(bundle)
    require(not bundle.is_symlink(), "bundle_symlink")
    manifest_path = bundle / "manifest.json"
    if expected_sha256 is not None:
        require(SHA.fullmatch(expected_sha256) and digest(manifest_path) == expected_sha256, "manifest_hash_mismatch")
    manifest, public = read(manifest_path), read(bundle / "public/integrity.json")
    require(manifest.get("version") == VERSION and public.get("manifest_sha256") == digest(manifest_path)
            and public.get("artifacts") == manifest.get("artifacts"), "bundle_identity_mismatch")
    artifacts = manifest["artifacts"]
    require(isinstance(artifacts, dict), "invalid_inventory")
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    require(not any(p.is_symlink() for p in bundle.rglob("*")), "bundle_symlink")
    require(actual == set(artifacts) | {"manifest.json", "public/integrity.json"}, "bundle_inventory_mismatch")
    for name, checksum in artifacts.items():
        require(isinstance(name, str) and "\\" not in name and not Path(name).is_absolute()
                and ".." not in Path(name).parts and SHA.fullmatch(checksum), "unsafe_artifact_record")
        require(digest(bundle / name) == checksum, "bundle_hash_mismatch")
    report = read(bundle / "public/report.json")
    require(report.get("status") in {"blocked", "synthetic_workflow_checked", "assembled_awaiting_process_review"}
            and report.get("final_acceptance") == "blocked" and report.get("independent_reference") is False,
            "final_acceptance_not_granted")
    if report["status"] != "blocked":
        require(digest(EVALUATOR_PATH) == report["evaluator_sha256"]
                and code_hash(ROOT) == report["evaluation_runtime_sha256"], "evaluator_version_mismatch")
        spec = read(bundle / "private/evaluation.spec.json")
        validate_spec(spec)
        require(report["purpose"] == spec["purpose"] and report["status"] == (
            "synthetic_workflow_checked" if spec["purpose"] == "synthetic_workflow_check"
            else "assembled_awaiting_process_review"), "purpose_mismatch")
        freeze = read(bundle / "private/human/reference/freeze.A.json")
        runs, paired, changes = evaluate_runs(bundle, spec, bundle / "private/input.jsonl",
                                              bundle / "private/human/reference/reference.jsonl", freeze)
        require(runs == report["runs"] and paired == report["paired"]
                and {"changes": changes} == read(bundle / "private/changed_pairs.json"), "recomputed_metrics_mismatch")
    else:
        require(report["independent_reference"] is False and all(report[k] is None for k in ["precision", "recall", "f1"]),
                "blocked_metrics_must_be_unavailable")
    return {"status": "integrity_verified", "evidence_status": report["status"],
            "final_acceptance": "blocked", "independent_reference": False,
            "manifest_sha256": digest(manifest_path), "metrics_recomputed": report["status"] != "blocked"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = commands.add_parser("prepare")
    prepare_cmd.add_argument("--output-dir", type=Path, required=True)
    build_cmd = commands.add_parser("assemble")
    build_cmd.add_argument("--spec", type=Path, required=True)
    build_cmd.add_argument("--output-dir", type=Path, required=True)
    check_cmd = commands.add_parser("verify")
    check_cmd.add_argument("--bundle", type=Path, required=True)
    check_cmd.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.output_dir)
        elif args.command == "assemble":
            result = assemble(args.spec, args.output_dir)
        else:
            result = verify(args.bundle, args.expected_sha256)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        code = str(exc) if type(exc) is ValueError and re.fullmatch(r"[a-z_]+", str(exc)) else "invalid_quality_evidence"
        parser.exit(2, "quality evidence: " + code + "\n")
    # Do not print private paths, labels, SKU, people or per-card deltas.
    print(json.dumps({k: result[k] for k in ["status", "final_acceptance", "independent_reference"]}
                     | {"metrics_recomputed": result.get("metrics_recomputed", False)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
