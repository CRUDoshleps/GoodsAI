"""Offline artifact assembly. Smoke is synthetic; assemble writes a local private bundle."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import zipfile

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import digest, read_jsonl
from goodsai.demo import run_demo
from goodsai.evaluate import evaluate
from goodsai.storage import prediction_snapshot

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ("code", "readme", "eda", "pipeline", "predictions", "presentation")
REFERENCE_KINDS = {"ai_assisted_reviewed_development", "development_feedback", "blind_human_reviewed"}
SHA = re.compile(r"[a-f0-9]{64}\Z")
PUBLIC_DOCS = {"README.md", "pyproject.toml", ".gitignore", "AGENTS.md", "CONTRIBUTING.md", "RESEARCH.md", "TASKS.md", "TECHNICAL_SPEC.md",
               "requirements/clean-run.in", "requirements/clean-run.lock", "docs/CLEAN_RUN.md",
               "docs/PROJECT_STATUS.md", "docs/ARCHITECTURE.md", "docs/DATASET.md", "docs/EVALUATION.md", "docs/RESULTS.md",
               "docs/RELEASES.md", "docs/REQUIREMENTS.md", "docs/RUNBOOK.md", "docs/TASK_MANAGEMENT.md",
               "docs/ARTIFACT_BUNDLE.md", "docs/examples/release-spec.example.json",
               "docs/reviews/2026-10-19_second_run_plan.md", "docs/product-stage/context/case/platform-requirements.md"}


class BuildError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, code, message):
    if not condition:
        raise BuildError(code, message)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def file_record(path, output):
    return {"path": path.relative_to(output).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size}


def new_output(output, root):
    root = root.resolve()
    output = output.resolve()
    allowed = root / "outputs"
    require(allowed.resolve() == allowed and allowed in output.parents, "unsafe_output",
            "Use a new directory under the repository's local outputs/ (no symlink escape).")
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--quiet", str(output)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    require(ignored, "unsafe_output", "Bundle destination must be ignored by Git.")
    # Reserve the directory before writing anything; even an empty existing directory is rejected.
    output.mkdir(parents=True, exist_ok=False)
    return output


def code_hash(root):
    hashed = hashlib.sha256()
    for path in sorted((root / "src/goodsai").glob("*.py")):
        hashed.update(path.name.encode())
        hashed.update(path.read_bytes())
    return hashed.hexdigest()


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_bundle(root, output, result):
    commit = git(root, "rev-parse", "HEAD")
    dirty = bool(git(root, "status", "--porcelain"))
    result["source"] = {"git_commit": commit, "git_dirty": dirty, "code_sha256": code_hash(root)}
    # Include known code roots and bundled synthetic fixtures, never data/, outputs/,
    # product decks or arbitrary JSON files just because they happen to be tracked.
    tracked = git(root, "ls-files", "-z").split("\0")
    allowed = []
    for name in tracked:
        p = Path(name)
        if (name in PUBLIC_DOCS
                or (p.parts and p.parts[0] in {"src", "scripts", "tests"} and p.suffix == ".py")
                or name == "src/goodsai/baseline.json"
                or (name.startswith("src/goodsai/examples/synthetic/") and p.suffix in {".json", ".jsonl"})):
            require(not (root / p).is_symlink(), "source_symlink", "Source archive must not contain symlinks.")
            allowed.append(name)
    require("README.md" in allowed and "pyproject.toml" in allowed, "source_missing", "Source/README is missing.")
    target = output / "public/code.zip"
    target.parent.mkdir(parents=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(allowed):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / name).read_bytes())
    readme = output / "public/README.md"
    shutil.copyfile(root / "README.md", readme)
    result["required_artifacts"]["code"] = {"status": "verified", **file_record(target, output)}
    result["required_artifacts"]["readme"] = {"status": "verified", **file_record(readme, output)}


def entry(spec, name, root, suffixes=None):
    record = spec.get(name)
    require(isinstance(record, dict) and set(record) == {"path", "sha256"}
            and isinstance(record["path"], str) and bool(record["path"])
            and isinstance(record["sha256"], str) and bool(SHA.fullmatch(record["sha256"])),
            "invalid_spec", f"{name} requires path and an explicit SHA-256.")
    path = (root / record["path"]).resolve()
    require(path.is_file(), "missing_artifact", f"Required local artifact is missing: {name}.")
    if suffixes:
        require(path.suffix.lower() in suffixes, "artifact_format", f"Unsupported file type for {name}.")
    require(path.stat().st_size > 0, "empty_artifact", f"Artifact is empty: {name}.")
    require(digest(path) == record["sha256"], "artifact_hash_mismatch", f"SHA-256 differs: {name}.")
    return path


def capture(path, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    require(digest(target) == expected, "artifact_changed", "An artifact changed while it was copied.")
    return target


def index_rows(path):
    rows = {}
    for row in read_jsonl(path):
        sku = row.get("sku_id")
        require(isinstance(sku, str) and bool(sku.strip()) and sku not in rows,
                "duplicate_or_missing_sku", "Rows require unique nonempty SKU identifiers.")
        rows[sku] = row
    require(bool(rows), "empty_batch", "Batch input/predictions must not be empty.")
    return rows


def inspect_pair(input_path, predictions, manifest, config, source, require_clean):
    require(isinstance(manifest, dict), "invalid_prediction_manifest", "Prediction manifest must be an object.")
    require(manifest.get("input_sha256") == digest(input_path)
            and manifest.get("output_sha256") == digest(predictions),
            "prediction_hash_mismatch", "Prediction manifest does not match input/output bytes.")
    require(manifest.get("git_commit") == source["git_commit"]
            and manifest.get("code_sha256") == source["code_sha256"]
            and manifest.get("config_sha256") == config_hash(config),
            "prediction_identity_mismatch", "Predictions belong to another source/configuration.")
    require(not require_clean or manifest.get("git_dirty") is False,
            "dirty_predictions", "Release predictions must come from a clean checkout.")
    require(type(manifest.get("llm_calls")) is int and manifest["llm_calls"] == 0
            and manifest.get("confidence_kind") == "heuristic" and manifest.get("calibrated") is False,
            "unsupported_runtime", "This assembler supports the current rules-only heuristic runtime.")
    inputs, outputs = index_rows(input_path), index_rows(predictions)
    require(inputs.keys() == outputs.keys(), "sku_mismatch", "Input/prediction SKU sets must match exactly.")
    statuses = Counter()
    decisions = Counter()
    reasons = Counter()
    for sku, row in inputs.items():
        predicted = outputs[sku]
        try:
            product = Product.from_dict(row)
        except ValueError:
            require(predicted.get("status") == "invalid_input", "input_status_mismatch",
                    "Invalid input must have an invalid_input result.")
            validate_prediction(predicted, config)
        else:
            expected = "processed" if product.category_id in config["categories"] else "unsupported_category"
            require(predicted.get("status") == expected, "input_status_mismatch",
                    "Prediction status does not match category/input validity.")
            validate_prediction(predicted, config, product)
        require(predicted.get("run_id") == manifest.get("run_id") and bool(predicted.get("run_id")),
                "run_id_mismatch", "All prediction rows must belong to the manifest run.")
        statuses[predicted["status"]] += 1
        for attr in predicted["attributes"]:
            decisions[attr["decision"]] += 1
            codes = attr["reason_codes"]
            require(isinstance(codes, list) and all(code in {"not_found_by_rules", "conflicting_evidence"} for code in codes),
                    "unknown_reason_code", "Unknown reason codes require an assembler update before publication.")
            reasons.update(codes)
    require(type(manifest.get("rows")) is int and manifest["rows"] == len(inputs)
            and manifest.get("status_counts") == dict(statuses),
            "count_mismatch", "Manifest row/status counts differ from predictions.")
    return inputs, {"rows": len(inputs), "status_counts": dict(statuses),
                    "decision_counts": dict(decisions), "reason_counts": dict(reasons),
                    "requested_pairs": sum(decisions.values()), "candidate_pairs": decisions["review"],
                    "candidate_coverage": decisions["review"] / sum(decisions.values()) if decisions else None,
                    "input_sha256": digest(input_path), "predictions_sha256": digest(predictions),
                    "run_id": manifest["run_id"]}


def pipeline(output, config, result):
    config_path = output / "public/pipeline/config.json"
    save(config_path, config)
    descriptor = output / "public/pipeline/descriptor.json"
    save(descriptor, {"schema_version": "0.1", "method": "rules_only", "confidence_kind": "heuristic",
                      "decisions": ["review", "abstain"], "config_sha256": config_hash(config),
                      "source_sha": result["source"]["git_commit"], "code_sha256": result["source"]["code_sha256"],
                      "entrypoint": "python -m goodsai.cli --config public/pipeline/config.json predict",
                      "llm_calls": 0})
    result["required_artifacts"]["pipeline"] = {"status": "verified", **file_record(descriptor, output)}


def quality(spec, root, output, inputs, predictions, config):
    if "reference" not in spec:
        require("metrics" not in spec and "reference_kind" not in spec, "metrics_without_reference",
                "A supplied metrics file requires an explicit reference and provenance.")
        report = evaluate(predictions, None, config)
        origin = {"status": "not_evaluated", "independent_reference": False}
    else:
        kind = spec.get("reference_kind")
        require(kind in REFERENCE_KINDS, "reference_provenance_missing", "Declare reference_kind explicitly.")
        ref = entry(spec, "reference", root, {".jsonl"})
        ref_copy = capture(ref, output / "private/reference.jsonl", spec["reference"]["sha256"])
        labels = index_rows(ref_copy)
        require(labels.keys() <= inputs.keys(), "reference_sku_mismatch", "Reference contains SKU absent from input.")
        for sku, row in labels.items():
            require(row.get("split") not in {"test_reserved", "test"}, "reserved_reference",
                    "This development assembler must not open a reserved test for evaluation.")
            require(row.get("annotation_status") == "reviewed", "reference_unreviewed", "Reference has pending labels.")
            fields = ("schema_version", "sku_id", "category_id", "title", "description", "seller_attributes", "source_flags")
            require(Product.from_dict({k: row[k] for k in fields if k in row}) == Product.from_dict(inputs[sku]),
                    "reference_input_mismatch", "Reference texts/categories differ from prediction input.")
        report = evaluate(predictions, ref_copy, config)
        require(report.get("evaluation_status") == "manual_reference", "reference_not_judgeable",
                "Reference contains no judgeable reviewed pairs.")
        if "metrics" in spec:
            old = entry(spec, "metrics", root, {".json"})
            old_copy = capture(old, output / "private/supplied-metrics.json", spec["metrics"]["sha256"])
            require(json.loads(old_copy.read_text(encoding="utf-8")) == report, "metrics_mismatch",
                    "Supplied metrics differ from evaluation on the captured input/reference.")
        origin = {"status": kind, "independent_reference": kind == "blind_human_reviewed",
                  "provenance_asserted_by_spec": True, "reference_sha256": digest(ref_copy)}
    envelope = {"provenance": origin, "input_sha256": digest(output / "private/input.jsonl"),
                "predictions_sha256": digest(predictions), "config_sha256": config_hash(config),
                "report": report}
    save(output / "public/quality.json", envelope)
    return origin


def finish(output, result):
    # Public report contains fixed messages/counts only, never SKU, input text or file contents.
    result["assembly_exit_code"] = 0 if result["status"] in {"complete", "synthetic_smoke"} else 2
    lines = ["# GoodsAI artifact assembly", "", f"Status: {result['status']}",
             f"Mode: {result['mode']}", "", "Presence/integrity is not scientific quality or release approval.", "",
             "| Artifact | Status |", "| --- | --- |"]
    lines += [f"| {name} | {record['status']} |" for name, record in result["required_artifacts"].items()]
    lines += ["", "Issues:"] + [f"- {item['code']}: {item['message']}" for item in result["issues"]]
    lines += ["", "Private bundles are local only. Approve files explicitly before publishing.",
              "EDA/presentation content and the final API still require human review."]
    if "checks" in result:
        lines += ["", "Batch/smoke checks:", "```json", json.dumps(result["checks"], ensure_ascii=True, indent=2), "```"]
    quality_path = output / "public/quality.json"
    if quality_path.is_file():
        quality_report = json.loads(quality_path.read_text(encoding="utf-8"))
        micro = quality_report["report"].get("metrics", {}).get("micro", {})
        lines += ["", "Quality (see quality.json for per-attribute/category metrics):",
                  "```json", json.dumps({"provenance": quality_report["provenance"],
                  **{key: micro.get(key) for key in ["tp", "fp", "fn", "precision", "recall", "f1"]}},
                  ensure_ascii=True, indent=2), "```"]
    else:
        lines += ["", "Catalogue precision/recall/F1: N/A."]
    report = output / "public/report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result["files"] = [file_record(p, output) for p in sorted(output.rglob("*")) if p.is_file()]
    save(output / "release.manifest.json", result)
    return result


def verify_bundle(output):
    """Verify a transferred bundle without running code or reading paths outside it."""
    output = output.resolve()
    require(not any(p.is_symlink() for p in output.rglob("*")), "bundle_symlink", "Transferred bundles must not contain symlinks.")
    manifest = json.loads((output / "release.manifest.json").read_text(encoding="utf-8"))
    require(isinstance(manifest, dict) and manifest.get("bundle_version") == "1", "invalid_bundle", "Unsupported bundle manifest.")
    require(manifest.get("status") in {"complete", "synthetic_smoke"}, "incomplete_bundle", "Incomplete bundles cannot pass verification.")
    records = manifest.get("files")
    require(isinstance(records, list) and bool(records), "invalid_bundle", "File inventory is missing.")
    seen = set()
    for record in records:
        require(isinstance(record, dict) and isinstance(record.get("path"), str), "invalid_bundle", "Invalid file entry.")
        name = record["path"]
        path = (output / name).resolve()
        require(output in path.parents and name not in seen, "unsafe_bundle_path", "Bundle paths must be unique and remain inside the bundle.")
        require(path.is_file() and record.get("sha256") == digest(path) and record.get("bytes") == path.stat().st_size,
                "bundle_hash_mismatch", "A bundle file is absent or changed.")
        seen.add(name)
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
              and p != output / "release.manifest.json"}
    require(actual == seen, "unexpected_bundle_files", "Bundle inventory differs from the directory contents.")
    artifacts = manifest.get("required_artifacts")
    require(isinstance(artifacts, dict) and set(artifacts) == set(REQUIRED), "invalid_bundle", "Six-artifact matrix is missing.")
    for name, record in artifacts.items():
        require(isinstance(record, dict), "invalid_bundle", "Artifact records must be objects.")
        if manifest["status"] == "complete":
            require(record.get("status") == "verified", "incomplete_bundle", "A required artifact is unverified.")
        if record.get("status") in {"verified", "verified_synthetic"}:
            require(record.get("path") in seen and record["sha256"] == digest(output / record["path"]),
                    "artifact_manifest_mismatch", "An artifact entry differs from the file inventory.")
    return {"status": "verified", "assembly_status": manifest["status"], "files_checked": len(records),
            "release_approval": "not_granted", "note": "Checksums prove integrity, not authenticity or scientific quality."}


def build(output, spec=None, *, root=ROOT, smoke=False):
    root = root.resolve()
    output = new_output(output, root)
    result = {"bundle_version": "1", "mode": "smoke" if smoke else "private",
              "status": "incomplete", "publication": "synthetic_only" if smoke else "local_only",
              "release_approval": "not_granted", "issues": [],
              "required_artifacts": {name: {"status": "missing"} for name in REQUIRED}}
    result["builder"] = {"sha256": digest(Path(__file__)), "python": platform.python_version(), "platform": platform.platform(),
                         "command": "python scripts/release/build_release.py " + ("smoke" if smoke else "assemble"),
                         "tests": "not_run_by_assembler"}
    try:
        source_bundle(root, output, result)
        if smoke:
            require(spec is None, "smoke_external_input", "Smoke does not accept external artifacts or references.")
            demo = run_demo(output / "public/smoke")
            config = load_config(str(root / "src/goodsai/baseline.json"))
            pipeline(output, config, result)
            result["checks"] = {"passed": demo["checks_passed"], "total": demo["checks_total"],
                                "rows": demo["rows"], "llm_calls": demo["llm_calls"]}
            result["required_artifacts"]["predictions"] = {"status": "verified_synthetic",
                                **file_record(output / "public/smoke/predictions.jsonl", output)}
            result["quality"] = {"status": "synthetic_smoke_only", "precision": None, "recall": None, "f1": None}
            result["issues"].append({"code": "not_a_release", "message": "Synthetic smoke has no catalogue EDA/final presentation."})
            result["status"] = "synthetic_smoke"
            return finish(output, result)
        require(isinstance(spec, dict) and spec.get("spec_version") == "1", "invalid_spec", "Use spec_version 1.")
        allowed = {"spec_version", "source_commit", "config", "input", "predictions", "eda", "presentation",
                   "reference", "reference_kind", "metrics"}
        require(not set(spec) - allowed, "invalid_spec", "Unknown release-spec fields.")
        require(spec.get("source_commit") == result["source"]["git_commit"], "source_commit_mismatch",
                "Spec source_commit must equal the current checkout HEAD.")
        require(result["source"]["git_dirty"] is False, "dirty_source", "Private assembly requires a clean checkout.")
        config_path = entry(spec, "config", root, {".json"})
        config_copy = capture(config_path, output / "private/source-config.json", spec["config"]["sha256"])
        config = json.loads(config_copy.read_text(encoding="utf-8"))
        require(config == load_config(str(root / "src/goodsai/baseline.json")), "unsupported_config",
                "Use the versioned rules config; external settings/secrets must not enter the public bundle.")
        pipeline(output, config, result)
        source_input = entry(spec, "input", root, {".jsonl"})
        input_copy = capture(source_input, output / "private/input.jsonl", spec["input"]["sha256"])
        source_predictions = entry(spec, "predictions", root, {".jsonl"})
        with prediction_snapshot(source_predictions):
            manifest_path = source_predictions.with_suffix(".manifest.json")
            require(manifest_path.is_file(), "missing_prediction_manifest", "Predictions require their paired manifest.")
            pred_copy = capture(source_predictions, output / "private/predictions.jsonl", spec["predictions"]["sha256"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            save(pred_copy.with_suffix(".manifest.json"), manifest)
        inputs, result["checks"] = inspect_pair(input_copy, pred_copy, manifest, config, result["source"], True)
        result["required_artifacts"]["predictions"] = {"status": "verified", **file_record(pred_copy, output)}
        result["quality"] = quality(spec, root, output, inputs, pred_copy, config)
        for name, suffixes in [("eda", {".md", ".html", ".pdf"}), ("presentation", {".md", ".pdf", ".pptx"})]:
            source = entry(spec, name, root, suffixes)
            copied = capture(source, output / "private" / (name + source.suffix.lower()), spec[name]["sha256"])
            result["required_artifacts"][name] = {"status": "verified", "content_review": "required",
                                                 **file_record(copied, output)}
        result["status"] = "complete"
    except BuildError as exc:
        result["issues"].append({"code": exc.code, "message": str(exc)})
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        # Do not expose arbitrary parser exceptions or data values in public reports.
        result["issues"].append({"code": "artifact_validation_failed", "message": "Invalid artifact, I/O or Git state; preserve this incomplete bundle."})
    return finish(output, result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    for name in ["smoke", "assemble"]:
        command = commands.add_parser(name)
        command.add_argument("--output-dir", type=Path, required=True)
        if name == "assemble":
            command.add_argument("--spec", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "verify":
            print(json.dumps(verify_bundle(args.bundle), ensure_ascii=True, indent=2))
            return 0
        spec = json.loads(args.spec.read_text(encoding="utf-8")) if args.mode == "assemble" else None
        result = build(args.output_dir, spec, smoke=args.mode == "smoke")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        code = exc.code if isinstance(exc, BuildError) else type(exc).__name__
        print(f"release assembly failed ({code}); use a new ignored outputs/ directory and a valid spec", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "mode": result["mode"],
                      "manifest": str(args.output_dir / "release.manifest.json"), "issues": result["issues"]},
                     ensure_ascii=True, allow_nan=False, indent=2))
    return 0 if result["status"] in {"complete", "synthetic_smoke"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
