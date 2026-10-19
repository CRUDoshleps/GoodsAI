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
from goodsai.data import check_output, digest, read_jsonl, read_predictions, write_json
from goodsai.evaluate import evaluate

KIT_FILES = {"input.jsonl", "predictions.jsonl", "predictions.manifest.json",
             "summary.json", "metrics.json", "report.md"}


def verify_demo_kit(output: Path) -> dict:
    output = output.resolve()
    manifest = json.loads((output / "artifacts.json").read_text(encoding="utf-8"))
    if (not isinstance(manifest,dict) or not isinstance(manifest.get('files'),dict)
            or not isinstance(manifest.get('run_id'),str) or not manifest['run_id']
            or manifest.get("scope") != "synthetic_smoke_only_not_catalog_quality"
            or set(manifest.get("files", {})) != KIT_FILES):
        raise ValueError("Invalid demo kit manifest")
    for name, record in manifest["files"].items():
        if (not isinstance(record,dict) or set(record)!={'sha256','bytes'}
                or not isinstance(record['sha256'],str) or len(record['sha256'])!=64
                or any(c not in '0123456789abcdef' for c in record['sha256'])
                or type(record['bytes']) is not int or record['bytes']<0):
            raise ValueError('Invalid demo kit file record')
        path = output / name
        if (path.is_symlink() or not path.is_file() or digest(path) != record.get("sha256")
                or path.stat().st_size != record.get("bytes")):
            raise ValueError("Demo kit artifact mismatch")
    for name in ("summary.json", "metrics.json", "predictions.manifest.json"):
        if json.loads((output/name).read_text(encoding="utf-8")).get("run_id") != manifest.get("run_id"):
            raise ValueError("Demo kit run identity mismatch")
    return {"status":"verified", "scope":manifest["scope"], "run_id":manifest["run_id"],
            "verified_files":len(KIT_FILES)}


def _finish_kit(output, summary, predictions, config):
    decisions = summary["decision_counts"]
    requested = sum(decisions.values())
    metric = {"scope":summary["quality_status"], "run_id":summary["run_id"],
              "synthetic_checks":{"passed":summary["checks_passed"],"total":summary["checks_total"]},
              "requested_pairs":requested,"review_pairs":decisions.get("review",0),
              "abstain_pairs":decisions.get("abstain",0),
              "candidate_coverage":decisions.get("review",0)/requested if requested else None,
              "quality":evaluate(output/"predictions.jsonl",None,config),
              "llm_calls":summary["llm_calls"],"api_cost_rub":0,"compute_cost_rub":None}
    write_json(output/"metrics.json",metric)
    lines = ["# GoodsAI: synthetic demo", "", "Contract smoke only. Catalogue precision/recall/F1: N/A.",
             "", f"Run ID: `{summary['run_id']}`", "",
             f"Checks: {summary['checks_passed']}/{summary['checks_total']}. "
             f"Review: {metric['review_pairs']}/{requested}. Abstain: {metric['abstain_pairs']}/{requested}.",
             "API calls/cost: 0 / 0 RUB. Compute cost: N/A (not measured).", "",
             "| Case | Attribute | Value / unit | Decision | Evidence location / reason |",
             "| --- | --- | --- | --- | --- |"]
    def cell(value):
        return str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n',' ')
    for row in predictions:
        if not row['attributes']:
            lines.append(f"| {cell(row['sku_id'])} | — | — | {cell(row['status'])} | — |")
        for attr in row['attributes']:
            evidence = attr['evidence']
            location = (f"{evidence['field']}[{evidence['start']}:{evidence['end']}]" if evidence
                        else ', '.join(attr['reason_codes']))
            value = (attr['value']+' '+(attr['unit'] or '')).strip() if attr['value'] is not None else '—'
            lines.append('| '+' | '.join(cell(v) for v in [row['sku_id'],attr['attribute'],value,attr['decision'],location])+' |')
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in ('metrics.json','report.md'):
        path=output/name
        summary['artifacts'][name]={'path':name,'sha256':digest(path),'bytes':path.stat().st_size}
    write_json(output/"summary.json",summary)
    write_json(output/'artifacts.json',{"scope":summary['quality_status'],"run_id":summary['run_id'],
               "files":{name:{"sha256":digest(output/name),"bytes":(output/name).stat().st_size}
                        for name in sorted(KIT_FILES)}})
    verify_demo_kit(output)


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
    # The demo reserves an entirely new artifact directory; general writers also
    # have their own destination locks and recoverable pair publication.
    output.mkdir(parents=True, exist_ok=False)
    input_path = output / "input.jsonl"
    prediction_path = output / "predictions.jsonl"
    input_path.write_bytes(source_bytes)
    report = predict(input_path, prediction_path, config)
    inputs = list(read_jsonl(input_path))
    predictions = list(read_predictions(prediction_path))
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
    _finish_kit(output, summary, predictions, config)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate and verify synthetic GoodsAI demo artifacts")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--output-dir", type=Path, default=None,
                        help="New directory only (default: outputs/demo)")
    group.add_argument("--verify-dir",type=Path,help="Verify an existing synthetic demo kit")
    args = parser.parse_args(argv)
    try:
        result = verify_demo_kit(args.verify_dir) if args.verify_dir else run_demo(args.output_dir or Path('outputs/demo'))
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
