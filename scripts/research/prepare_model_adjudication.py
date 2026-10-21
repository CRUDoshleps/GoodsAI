"""Hash-bound development error review; never independent gold or test inference."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.evaluate import evaluate as score_reference
from goodsai.silver_prepare import verify_bundle
from scripts.research.audit_splits import dump, require, unique_rows, write_rows
from scripts.research.compare_model_stage import compare
from scripts.research.review_m2 import cell, fence, make_label


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_inventory(directory, expected):
    directory = Path(directory).resolve()
    require(digest(directory / "manifest.json") == expected, "comparison_manifest_mismatch")
    manifest = read(directory / "manifest.json")
    require(manifest.get("schema") == "goodsai-frozen-comparison-output-1", "comparison_schema")
    require({"freeze.json", "run_stats.json", "config.json", "changed_pairs.private.jsonl",
             "historical/cold.jsonl", "historical/cold.manifest.json",
             "candidate/cold.jsonl", "candidate/cold.manifest.json"} <= manifest["artifacts"].keys(),
            "incomplete_comparison_inventory")
    for name, checksum in manifest["artifacts"].items():
        path = directory / name
        require(path.resolve().is_relative_to(directory) and not path.is_symlink()
                and path.is_file() and digest(path) == checksum, "comparison_artifact_changed")
    return manifest


def new_output(output):
    output = Path(output).resolve()
    require(output.is_relative_to((ROOT / "outputs").resolve()) and not output.exists(),
            "new_private_output_required")
    return output


def prepare(bundle, comparison, bundle_sha256, comparison_sha256, output):
    bundle, comparison = Path(bundle).resolve(), Path(comparison).resolve()
    require(digest(bundle / "manifest.json") == bundle_sha256, "source_bundle_mismatch")
    manifest = verify_bundle(bundle)
    verify_inventory(comparison, comparison_sha256)
    freeze = read(comparison / "freeze.json")
    require(freeze["bundle_manifest_sha256"] == bundle_sha256, "freeze_bundle_mismatch")
    require(freeze.get("reference_kind") == "catalog_silver"
            and freeze.get("external_calls") == "forbidden", "wrong_comparison_kind")
    stats = read(comparison / "run_stats.json")
    require(stats["freeze"] == freeze and stats.get("evaluation_role") == "development_feedback",
            "comparison_provenance_mismatch")
    require(digest(comparison / "config.json") == freeze["config_file_sha256"], "frozen_config_mismatch")
    for mode, key in (("historical", "baseline_sha"), ("candidate", "candidate_sha")):
        producer = read(comparison / mode / "cold.manifest.json")
        require(producer["git_commit"] == freeze[key] and producer["git_dirty"] is False
                and producer["llm_calls"] == 0
                and producer["input_sha256"] == manifest["artifacts"]["input.jsonl"]
                and producer["output_sha256"] == digest(comparison / mode / "cold.jsonl"),
                "frozen_producer_mismatch")
    members = unique_rows(bundle / "metadata.jsonl")
    protected = {m["family_id"] for m in members.values() if m.get("original_split") == "test_reserved"}
    changes = list(read_jsonl(comparison / "changed_pairs.private.jsonl"))
    selected = [x for x in changes if x["attribute"] == "model" and (x["new_fp"] or x["lost_tp"])]
    require(selected and len({x["sku_id"] for x in selected}) == len(selected), "invalid_selected_changes")
    summary = stats["paired"]["slices"]["attribute:model"]
    require(all(sum(x[k] for x in selected) == summary[k] for k in ("new_fp", "lost_tp")),
            "incomplete_model_disagreements")
    # Gate metadata before interpreting selected source text. No reserve is read.
    for change in selected:
        m = members.get(change["sku_id"], {})
        require(m.get("original_split") in {"development", "validation"}
                and m.get("family_id") not in protected
                and m.get("evaluation_role") == "development_feedback", "protected_or_unknown_membership")
    selected.sort(key=lambda x: (members[x["sku_id"]]["category_id"],
                                0 if x["lost_tp"] else 1, x["sku_id"]))
    output = new_output(output)
    output.mkdir(parents=True)
    sources = {str(bundle / "manifest.json"): bundle_sha256,
               str(comparison / "manifest.json"): comparison_sha256}
    policy = {"version": "eval009-model-review-v1", "source_sha256": sources,
              "baseline_sha": freeze["baseline_sha"], "candidate_sha": freeze["candidate_sha"],
              "selection": "all model new_fp/lost_tp; category, lost_tp-first, lexical SKU",
              "reference_kind": "ai_assisted_development_pending_review",
              "selection_uses_predictions": True, "annotation_source": "title_description_only",
              "independent_reference": False, "human_reviewed_cards": 0,
              "precision": None, "recall": None, "f1": None}
    dump(output / "selection.policy.json", policy)  # Freeze before parsing source text.
    ids = {x["sku_id"]: f"M{i:02d}" for i, x in enumerate(selected, 1)}
    products = {}
    for row in read_jsonl(bundle / "input.jsonl"):
        if row["sku_id"] not in ids:
            continue
        product = Product.from_dict(row)
        require(product.category_id == members[product.sku_id]["category_id"], "category_mismatch")
        require(product.sku_id not in products, "duplicate_selected_input")
        products[product.sku_id] = product.as_dict()
    require(products.keys() == ids.keys(), "selected_source_missing")
    tasks = [products[x["sku_id"]] | {"review_id": ids[x["sku_id"]],
             "split": "development", "original_split": members[x["sku_id"]]["original_split"],
             "family_id": members[x["sku_id"]]["family_id"], "independent_reference": False,
             "annotation_status": "unreviewed", "label_source": "unassigned",
             "attributes": [{"attribute": "model", "status": "unreviewed", "value": None,
                             "unit": None, "evidence": None}]} for x in selected]
    write_rows(output / "development.tasks.jsonl", tasks)
    write_rows(output / "selection.manifest.jsonl", [x | {"review_id": ids[x["sku_id"]],
               "category_id": members[x["sku_id"]]["category_id"],
               "family_id": members[x["sku_id"]]["family_id"]} for x in selected])
    template = {t["review_id"]: {"status": "unreviewed", "note": ""} for t in tasks}
    dump(output / "decisions.blank.json", template)
    dump(output / "selection.summary.json", {"policy": policy, "cards": len(tasks),
         "categories": dict(Counter(t["category_id"] for t in tasks)),
         "artifacts": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}})
    require(digest(bundle / "manifest.json") == bundle_sha256, "source_changed")
    require(manifest == verify_bundle(bundle), "source_changed")
    return {"cards": len(tasks), "human_reviewed_cards": 0, "independent_reference": False}


def draft(selection, decisions, output):
    selection, decisions = Path(selection), Path(decisions)
    summary = read(selection / "selection.summary.json")
    for name, checksum in summary["artifacts"].items():
        require(Path(name).name == name and digest(selection / name) == checksum, "selection_changed")
    tasks = list(read_jsonl(selection / "development.tasks.jsonl"))
    specs = read(decisions)
    require(tasks and set(specs) == {t["review_id"] for t in tasks}, "draft_identity_mismatch")
    rows, text = [], ["# M01 и далее: проверка model", "",
        "AI-assisted development; подтверждённых человеком карточек: 0. P/R/F1: N/A.",
        "Отобраны ВСЕ flagged model new_fp/lost_tp, а не случайный контроль качества.",
        "Проверяется только model. Источник ответа — title/description, не каталог.",
        f"Ответ: `{tasks[0]['review_id']}–{tasks[-1]['review_id']}: подтверждаю`, либо `M03: model=...`, либо `M03: не уверен`.", ""]
    if summary["policy"].get("additional_unassessed_model_changes"):
        text += ["M27 — отдельное дополнение после сравнения исправления: catalog conflict,",
                 "не входит в исходные 26 flagged new_fp/lost_tp. Это post-prediction диагностика.", ""]
    for task in tasks:
        label = make_label(task, "model", specs[task["review_id"]])
        row = task | {"attributes": [label], "annotation_status": "draft", "label_source": "ai_assisted",
                      "annotator": "Codex", "human_review_status": "pending"}
        rows.append(row)
        e = label["evidence"]
        evidence = f"{e['field']} [{e['start']}:{e['end']}]: {e['text']}" if e else "—"
        text += [f"## {task['review_id']} · категория {task['category_id']}",
                 "Заголовок:", fence(task["title"]), "Описание:", fence(task["description"] or "[нет описания]"),
                 "| Поле | Предложение | Evidence | Обоснование |", "| --- | --- | --- | --- |",
                 "| " + " | ".join(map(cell, ["model", label["value"] or label["status"],
                                            evidence, label["annotation_notes"]])) + " |", ""]
    output = new_output(output)
    output.mkdir(parents=True)
    write_rows(output / "development.ai-draft.jsonl", rows)
    (output / "review.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    report = {"cards": len(rows), "reviewed_attributes": ["model"], "human_reviewed_cards": 0,
              "selection_uses_predictions": True, "predictions_used": True,
              "annotation_source": "title_description_only", "independent_reference": False,
              "precision": None, "recall": None, "f1": None,
              "sources": {str(p.resolve()): digest(p) for p in [decisions, selection / "selection.summary.json"]},
              "artifacts": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}}
    dump(output / "draft.manifest.json", report)
    return {"cards": len(rows), "human_reviewed_cards": 0, "independent_reference": False}


def evaluate_models(reviewed, reference_sha256, predictions, config_path, output):
    """Project explicitly reviewed model labels; reuse the existing evaluator."""
    reviewed = Path(reviewed)
    source = reviewed / "development.human-reviewed.jsonl"
    require(digest(source) == reference_sha256, "reviewed_reference_mismatch")
    manifest = read(reviewed / "review.manifest.json")
    require(manifest.get("status") == "ai_assisted_human_reviewed_development"
            and manifest.get("independent_reference") is False
            and manifest.get("pending_pairs") == 0, "confirmed_development_reference_required")
    for name, checksum in manifest["artifacts"].items():
        require(Path(name).name == name and digest(reviewed / name) == checksum, "reviewed_artifact_changed")
    config = load_config(config_path)
    tasks, reference = list(read_jsonl(source)), []
    for task in tasks:
        require(task.get("annotation_status") == "reviewed" and task.get("ai_assisted") is True
                and task.get("independent_reference") is False
                and [a["attribute"] for a in task["attributes"]] == ["model"], "model_only_review_required")
        label = task["attributes"][0]
        require(label.get("human_review_status") == "confirmed", "unconfirmed_model_label")
        # Other fields are explicitly excluded, not silently copied from predictions.
        labels = [label if attr == "model" else {"attribute": attr, "status": "unjudgeable",
                  "value": None, "unit": None, "evidence": None,
                  "label_origin": "not_reviewed_out_of_scope"}
                  for attr in config["categories"][task["category_id"]]]
        reference.append(task | {"attributes": labels, "reviewed_attributes": ["model"],
                                "evaluation_view": "model_only_other_attributes_excluded"})
    ids = {t["sku_id"] for t in tasks}
    require(ids and len(ids) == len(tasks), "duplicate_or_empty_review")
    output = new_output(output)
    output.mkdir(parents=True)
    write_rows(output / "model.reference-view.jsonl", reference)
    metrics, variants, provenance = {}, {}, {}
    input_sha = None
    for spec in predictions:
        name, separator, path = spec.partition("=")
        require(separator and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name)
                and name not in variants, "invalid_or_duplicate_method")
        path = Path(path)
        producer_path = path.with_suffix(".manifest.json")
        producer = read(producer_path)
        require(producer.get("git_dirty") is False and producer.get("llm_calls") == 0
                and producer["output_sha256"] == digest(path), "invalid_frozen_producer")
        input_sha = input_sha or producer["input_sha256"]
        require(producer["input_sha256"] == input_sha, "different_frozen_inputs")
        captured = output / "captured" / name / "predictions.jsonl"
        captured.parent.mkdir(parents=True)
        shutil.copyfile(path, captured)
        shutil.copyfile(producer_path, captured.with_suffix(".manifest.json"))
        all_rows = list(read_predictions(captured))
        require(len(all_rows) == producer["rows"] and len({r["sku_id"] for r in all_rows}) == len(all_rows),
                "invalid_producer_population")
        selected = [r for r in all_rows if r["sku_id"] in ids]
        require({r["sku_id"] for r in selected} == ids, "reviewed_prediction_missing")
        target = output / (name + ".model-subset.jsonl")
        write_rows(target, selected)  # Analysis projection; never forge a producer manifest.
        metrics[name] = score_reference(target, output / "model.reference-view.jsonl", config)
        variants[name] = {r["sku_id"]: r for r in selected}
        provenance[name] = {k: producer.get(k) for k in
                            ("git_commit", "code_sha256", "config_sha256", "input_sha256", "output_sha256")}
    require(len(variants) >= 2, "at_least_two_frozen_methods_required")
    names = list(variants)
    transitions = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    changes = compare(reference, variants, transitions=transitions)
    dump(output / "pair-changes.private.json", {"changes": changes})
    report = {"sample_kind": "error_selected_development", "reference_origin": "ai_assisted_human_reviewed",
              "independent_reference": False, "selection_uses_predictions": True,
              "reviewed_attributes": ["model"], "cards": len(tasks), "metrics": metrics,
              "source_reference_sha256": reference_sha256, "method_provenance": provenance,
              "review_manifest_sha256": digest(reviewed / "review.manifest.json"),
              "human_feedback_sha256": digest(reviewed / "human.feedback.json"),
              "reference_view_sha256": digest(output / "model.reference-view.jsonl"),
              "config_file_sha256": digest(config_path),
              "evaluator_sha256": digest(ROOT / "src/goodsai/evaluate.py"),
              "driver_sha256": digest(Path(__file__)),
              "paired_model_transitions": {a + "->" + b: dict(Counter(
                  c["before_verdict"] + "->" + c["after_verdict"] for c in changes
                  if c["attribute"] == "model" and c["transition"] == a + "->" + b)) for a, b in transitions},
              "limitation": "Only selected model errors; not full-card or catalogue quality. Other fields excluded."}
    dump(output / "metrics.json", report)
    dump(output / "manifest.json", {"artifacts": {p.relative_to(output).as_posix(): digest(p)
         for p in sorted(output.rglob("*")) if p.is_file() and not p.name.startswith(".")}})
    return {"cards": len(tasks), "independent_reference": False,
            "metrics": {name: value.get("metrics", {}).get("micro") for name, value in metrics.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("bundle", "comparison", "output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("bundle-sha256", "comparison-sha256"):
        p.add_argument("--" + name, required=True)
    p = sub.add_parser("draft")
    for name in ("selection", "decisions", "output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p = sub.add_parser("evaluate-models")
    for name in ("reviewed", "config", "output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--reference-sha256", required=True)
    p.add_argument("--prediction", action="append", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.bundle, args.comparison, args.bundle_sha256,
                             args.comparison_sha256, args.output_dir)
        elif args.command == "draft":
            result = draft(args.selection, args.decisions, args.output_dir)
        else:
            result = evaluate_models(args.reviewed, args.reference_sha256,
                                     args.prediction, args.config, args.output_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, "model adjudication: " + type(exc).__name__ + "\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
