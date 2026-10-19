"""ENV-002: isolated, hash-locked synthetic/external batch with a resumable audit trail."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SUPPORTED = {("Linux", "x86_64"), ("Darwin", "arm64"), ("Windows", "AMD64")}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL, text=True).strip()


def destination(path):
    path = path.absolute()
    allowed = ROOT / "outputs"
    if allowed.resolve() != allowed or path.resolve() != path or allowed not in path.parents:
        raise ValueError("Use a non-symlink directory under this checkout's ignored outputs/")
    if subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--quiet", str(path)],
                      capture_output=True).returncode:
        raise ValueError("Output must be ignored by Git")
    return path


@contextmanager
def reserve(output):
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".runner-lock"
    lock.mkdir()  # Cross-process exclusion; never break a possibly live lock.
    try:
        (lock / "owner.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        yield
    finally:
        shutil.rmtree(lock)


def preflight(output, source):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Use CPython 3.12 for this lock")
    if platform.python_implementation() != "CPython" or (platform.system(), platform.machine()) not in SUPPORTED:
        raise ValueError("Unsupported interpreter/OS/architecture; see docs/CLEAN_RUN.md")
    if git("status", "--porcelain"):
        raise ValueError("Commit changes first: clean-run requires a clean checkout")
    git("cat-file", "-e", "5f77d81^{commit}")
    if shutil.disk_usage(output).free < 512 * 1024**2:
        raise ValueError("At least 512 MiB free disk is required")
    with tempfile.TemporaryFile(dir=output) as stream:
        stream.write(b"preflight")
    if not source.is_file():
        raise ValueError("Input file is missing")
    # No provider is required: this profile is rules-only, llm_calls must stay zero.
    return {"git_commit": git("rev-parse", "HEAD"), "input_sha256": sha(source),
            "lock_sha256": sha(ROOT / "requirements/clean-run.lock"),
            "runner_sha256": sha(Path(__file__)),
            "config_file_sha256": sha(ROOT / "src/goodsai/baseline.json"),
            "python": platform.python_version(), "platform": platform.platform(),
            "provider": "disabled_rules_only"}


def verified_cached(output, report, identity):
    if report.get("status") != "passed" or report.get("identity") != identity:
        return False
    records = report.get("files")
    if not records:
        return False
    for name, digest in records.items():
        path = (output / name).resolve()
        if output not in path.parents or not path.is_file() or sha(path) != digest:
            raise ValueError("Completed artifacts changed; preserve this run and choose a new output directory")
    return True


def run(output, source):
    output = destination(output)
    with reserve(output):
        identity = preflight(output, source)
        report_path = output / "report.json"
        if report_path.exists():
            previous = json.loads(report_path.read_text(encoding="utf-8"))
            if verified_cached(output, previous, identity):
                python = output / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                versions = subprocess.check_output([str(python), "-m", "pip", "list", "--format=json"],
                                                   cwd=ROOT, timeout=30, stderr=subprocess.DEVNULL)
                if json.loads(versions) != previous["dependencies"]:
                    raise ValueError("Installed dependencies changed; use a new output directory")
                subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, timeout=30,
                               capture_output=True, check=True)
                return previous
            if previous.get("identity") != identity:
                raise ValueError("Source/environment/input changed; use a new output directory")
        report = {"version": "1", "status": "running", "identity": identity, "stages": [],
                  "quality": {"status": "N/A_no_reference", "precision": None, "recall": None, "f1": None}}
        # Preserve failed attempts. A retry reuses the isolated environment but publishes into a new attempt.
        attempt = 1
        while (output / f"attempt-{attempt:04d}").exists():
            attempt += 1
        work = output / f"attempt-{attempt:04d}"
        work.mkdir()
        report["attempt"] = work.name
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.update(PYTHONNOUSERSITE="1", PYTHONUTF8="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
                   PIP_NO_INPUT="1")
        python = output / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

        def stage(name, command, timeout=180):
            record = {"name": name, "exit_code": None, "status": "running"}
            report["stages"].append(record)
            save(report_path, report)
            started = time.monotonic()
            print(f"clean-run: {name}", flush=True)
            try:
                # Do not persist raw stdout/stderr: an external JSONL may be private.
                result = subprocess.run([str(part) for part in command], cwd=ROOT, env=env,
                                        capture_output=True, timeout=timeout)
                record["exit_code"] = result.returncode
                if result.returncode:
                    raise ValueError("stage_failed")
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                record.update(status="failed", error_kind=type(exc).__name__)
                raise
            finally:
                record["seconds"] = time.monotonic() - started
                save(report_path, report)
            record["status"] = "passed"
            save(report_path, report)

        try:
            if not python.exists():
                stage("create_environment", [sys.executable, "-m", "venv", output / ".venv"])
            stage("install_lock", [python, "-m", "pip", "install", "--require-hashes", "--only-binary=:all:",
                                   "-r", ROOT / "requirements/clean-run.lock"], timeout=600)
            stage("install_project", [python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", ROOT])
            stage("pip_check", [python, "-m", "pip", "check"])
            stage("synthetic_smoke", [python, "-m", "goodsai.demo", "--output-dir", work / "demo"])
            # Snapshot the caller's bytes; check again before accepting the completed run.
            shutil.copyfile(source, work / "input.jsonl")
            if sha(work / "input.jsonl") != identity["input_sha256"]:
                raise ValueError("input_changed")
            stage("external_batch", [python, "-m", "goodsai.cli", "predict", "--input", work / "input.jsonl",
                                     "--output", work / "predictions.jsonl"])
            stage("metrics_without_gold", [python, "-m", "goodsai.cli", "evaluate", "--predictions",
                                           work / "predictions.jsonl", "--output", work / "metrics.json"])
            stage("verify_external_pair", [python, Path(__file__), "--verify-pair", work])
            stage("api_contract", [python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_api.py"])
            stage("artifact_smoke", [python, ROOT / "scripts/release/build_release.py", "smoke",
                                     "--output-dir", work / "bundle"])
            stage("artifact_verify", [python, ROOT / "scripts/release/build_release.py", "verify",
                                      "--bundle", work / "bundle"])
            versions = subprocess.check_output([str(python), "-m", "pip", "list", "--format=json"], cwd=ROOT, env=env)
            report["dependencies"] = json.loads(versions)
            manifest = json.loads((work / "predictions.manifest.json").read_text(encoding="utf-8"))
            report["batch"] = {key: manifest[key] for key in ("rows", "run_id", "status_counts", "llm_calls", "config_sha256")}
            if manifest["llm_calls"] != 0 or sha(source) != identity["input_sha256"]:
                raise ValueError("unexpected_model_calls_or_input_change")
            report["files"] = {p.relative_to(output).as_posix(): sha(p) for p in work.rglob("*")
                               if p.is_file() and not p.name.endswith(".lock")}
            report["status"] = "passed"
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            report.update(status="failed", error_kind=type(exc).__name__,
                          recovery="Fix the named stage/environment/input, then repeat the same command. "
                                   "Failed attempts are preserved; changed input/source needs a new --output-dir.")
        save(report_path, report)
        lines = ["# GoodsAI clean run", "", f"Status: `{report['status']}`", "",
                 f"Source: `{identity['git_commit']}`", "", "Quality: N/A (no reference). Synthetic checks do not measure catalogue quality.", "",
                 "| Stage | Status | Exit |", "| --- | --- | --- |"]
        lines.extend(f"| {s['name']} | {s['status']} | {s['exit_code']} |" for s in report["stages"])
        if report["status"] == "failed":
            lines.extend(["", report["recovery"]])
        (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report


def verify_pair(work):
    from goodsai.contracts import Product, load_config, validate_prediction
    from goodsai.data import read_jsonl
    config = load_config()
    manifest = json.loads((work / "predictions.manifest.json").read_text(encoding="utf-8"))
    count = 0
    from itertools import zip_longest
    for count, (source, prediction) in enumerate(zip_longest(read_jsonl(work / "input.jsonl"),
                                                          read_jsonl(work / "predictions.jsonl")), 1):
        if source is None or prediction is None:
            raise ValueError("pair_count_mismatch")
        try:
            product = Product.from_dict(source)
        except ValueError:
            if prediction["status"] != "invalid_input":
                raise ValueError("invalid_input_mismatch")
            product = None
        validate_prediction(prediction, config, product)
        if prediction["run_id"] != manifest["run_id"]:
            raise ValueError("run_id_mismatch")
    if (count != manifest["rows"] or manifest["input_sha256"] != sha(work / "input.jsonl")
            or manifest["output_sha256"] != sha(work / "predictions.jsonl")):
        raise ValueError("manifest_mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--input", type=Path, default=ROOT / "src/goodsai/examples/synthetic/products.jsonl")
    parser.add_argument("--verify-pair", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.verify_pair:
        verify_pair(args.verify_pair)
        return 0
    if not args.output_dir:
        parser.error("--output-dir is required")
    try:
        result = run(args.output_dir, args.input.resolve())
    except ValueError as exc:
        # These messages are fixed preflight/cache diagnostics, never parser payloads.
        print(f"clean-run preflight: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"clean-run preflight failed ({type(exc).__name__}); see docs/CLEAN_RUN.md", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "report": str(args.output_dir / "report.json")}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
