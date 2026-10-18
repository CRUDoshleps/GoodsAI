"""Reproducible synthetic smoke run through the real batch predictor, not a quality benchmark."""
import argparse
from collections import Counter
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import sys

from goodsai.cli import predict
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import check_output, digest, read_jsonl, write_json


def _destination(output_dir: Path, examples) -> Path:
    output = output_dir.expanduser().resolve()
    check_output(output)
    # Also protect data/raw when launched outside the repository working directory,
    # including symlinks resolved above. The demo never writes under any data/raw.
    if any(a.lower() == "data" and b.lower() == "raw" for a, b in zip(output.parts, output.parts[1:])):
        raise ValueError("Demo output must not be inside data/raw")
    if isinstance(examples, Path):
        source = examples.resolve()
        if output == source or source in output.parents:
            raise ValueError("Demo output must not be inside the packaged examples")
    return output


def _verify(inputs: list[dict], predictions: list[dict], expected: dict, config: dict) -> list[dict]:
    cases = expected["cases"]
    if not len(inputs) == len(predictions) == len(cases):
        raise ValueError("Demo input, output and expectation counts differ")
    checks = []
    for line_no, (source, result, case) in enumerate(zip(inputs, predictions, cases), 1):
        sku = case["sku_id"]
        if source["sku_id"] != sku or result.get("sku_id") != sku or result.get("status") != case["status"]:
            raise ValueError(f"Demo identity/status check failed: {sku}")
        if case["status"] == "invalid_input":
            try:
                Product.from_dict(source)
            except ValueError:
                pass
            else:
                raise ValueError(f"Expected invalid input: {sku}")
            if result.get("reason_codes") != case["reason_codes"] or result.get("input_line") != line_no:
                raise ValueError(f"Demo invalid-input check failed: {sku}")
            validate_prediction(result, config)
        else:
            product = Product.from_dict(source)
            validate_prediction(result, config, product)
        attrs = {a["attribute"]: a for a in result["attributes"]}
        if set(attrs) != set(case["values"]) | set(case["abstentions"]):
            raise ValueError(f"Demo expected attributes differ: {sku}")
        for name, value_unit in case["values"].items():
            attr = attrs[name]
            if ([attr["value"], attr["unit"]] != value_unit or attr["decision"] != "review"
                    or attr["confidence_kind"] != "heuristic" or attr["reason_codes"]):
                raise ValueError(f"Demo value check failed: {sku}/{name}")
        for name, reason in case["abstentions"].items():
            if attrs[name]["decision"] != "abstain" or attrs[name]["reason_codes"] != [reason]:
                raise ValueError(f"Demo abstention check failed: {sku}/{name}")
        checks.append({"sku_id": sku, "status": case["status"], "result": "passed",
                       "checked_attributes": len(attrs)})
    return checks


def run_demo(output_dir: Path) -> dict:
    examples = files("goodsai").joinpath("examples", "synthetic")
    source_bytes = examples.joinpath("products.jsonl").read_bytes()
    expected_bytes = examples.joinpath("expectations.json").read_bytes()
    expected = json.loads(expected_bytes)
    config = load_config()
    output = _destination(output_dir, examples)
    # This reservation prevents two demo processes from sharing atomic_text's
    # fixed temporary filename. Existing directories are never reused or deleted.
    output.mkdir(parents=True, exist_ok=False)
    input_path = output / "input.jsonl"
    prediction_path = output / "predictions.jsonl"
    input_path.write_bytes(source_bytes)
    report = predict(input_path, prediction_path, config)
    inputs = list(read_jsonl(input_path))
    predictions = list(read_jsonl(prediction_path))
    checks = _verify(inputs, predictions, expected, config)
    manifest_path = prediction_path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest != report or report["rows"] != len(inputs)
            or report["input_sha256"] != digest(input_path)
            or report["output_sha256"] != digest(prediction_path)
            or any(row["run_id"] != report["run_id"] for row in predictions)):
        raise ValueError("Demo prediction manifest is inconsistent with artifacts")
    decisions = Counter(a["decision"] for row in predictions for a in row["attributes"])
    artifacts = {path.name: {"path": path.name, "sha256": digest(path), "bytes": path.stat().st_size}
                 for path in [input_path, prediction_path, manifest_path]}
    summary = {
        "demo_version": expected["demo_version"], "origin": expected["origin"],
        "quality_status": "synthetic_smoke_only_not_catalog_quality",
        "checks_passed": len(checks), "checks_total": len(expected["cases"]), "checks": checks,
        "run_id": report["run_id"], "rows": report["rows"],
        "status_counts": report["status_counts"], "decision_counts": dict(decisions),
        "abstention_reasons": report["abstention_reasons"], "llm_calls": report["llm_calls"],
        "identity": {key: report[key] for key in ["version", "code_sha256", "config_sha256", "git_commit",
                     "git_dirty", "python", "platform", "rules_version", "dictionary_version"]},
        "resources": {
            "input": {"package_path": "goodsai/examples/synthetic/products.jsonl",
                      "sha256": hashlib.sha256(source_bytes).hexdigest()},
            "expectations": {"package_path": "goodsai/examples/synthetic/expectations.json",
                             "sha256": hashlib.sha256(expected_bytes).hexdigest()}},
        "artifacts": artifacts}
    # A summary is published only after every check passes. Failed runs keep
    # their new directory for diagnosis; choose another directory for a retry.
    write_json(output / "summary.json", summary)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate and verify synthetic GoodsAI demo artifacts")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/demo"),
                        help="New directory only (default: outputs/demo)")
    args = parser.parse_args(argv)
    try:
        result = run_demo(args.output_dir)
    except FileExistsError:
        print("goodsai demo: output directory already exists; choose a new --output-dir", file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError) as exc:
        print(f"goodsai demo: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
