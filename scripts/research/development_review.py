"""Prepare a new AI-assisted DEVELOPMENT review; keep reserved test unread/unpredicted."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl
from scripts.research.audit_splits import dump, require, unique_rows, verify, write_rows
from scripts.research.prepare_m2 import signals
from scripts.research.review_m2 import make_label, cell, fence

POLICY = {"version": "development-review-20261019-v1", "seed": "goodsai-development-review-20261019-v1",
    "categories": ["761", "482"], "per_description_cell": 5,
    "priority_slots": ["html", "unit_issue", "name_ambiguity", "sparse", "random"],
    "eligibility": "EVAL-002 eligible development, unexposed full family, one SKU per family",
    "numbering": "D21-D40", "predictions_used": False, "independent_reference": False}


def rank(sku):
    return hashlib.sha256((POLICY["seed"] + ":" + sku).encode()).hexdigest()


def select(audit_bundle, output, seen_paths=()):
    audit_bundle, output = Path(audit_bundle).resolve(), Path(output).resolve()
    verify(audit_bundle)
    require(not output.exists(), "new_output_directory_required")
    members_path = audit_bundle / "eligible.split_manifest.jsonl"
    members = unique_rows(members_path)
    sources = json.loads((audit_bundle / "audit.policy.json").read_text(encoding="utf-8"))["sources"]
    paths = [Path(p) for p in sources if Path(p).name == "pilot.jsonl"]
    require(len(paths) == 1, "source_identity_ambiguous")
    source = paths[0]
    protected = {str(p.resolve()): digest(p) for p in
                 [source, members_path, audit_bundle / "audit.summary.json", *map(Path, seen_paths)]}
    output.mkdir(parents=True, exist_ok=False)
    # Frozen before parsing ANY source text; no predictions are imported or used.
    dump(output / "selection.policy.json", POLICY | {"sources": protected})
    blocked = {m["family_id"] for m in members.values() if m["split"] != "development"
               or m["family_exposed"] or m["known_exposure"] or m["quarantine_reasons"]}
    for path in seen_paths:
        for row in read_jsonl(Path(path)):
            require(isinstance(row.get("sku_id"), str), "seen_identity_required")
            if row["sku_id"] in members:
                blocked.add(members[row["sku_id"]]["family_id"])
    eligible = {sku for sku, m in members.items() if m["split"] == "development"
                and m["family_id"] not in blocked}
    products, features = {}, {}
    for row in read_jsonl(source):
        sku = row.get("sku_id")
        if sku not in eligible:
            continue  # Never inspect text/description/signals of protected rows.
        require(sku not in products, "duplicate_eligible_sku")
        product = Product.from_dict(row)
        require(product.category_id == members[sku]["category_id"], "category_mismatch")
        products[sku], features[sku] = product, signals(product)
    require(products.keys() == eligible, "eligible_source_missing")
    chosen, manifest, families = [], [], set()
    config = load_config()
    for cat in POLICY["categories"]:
        for has_description in [True, False]:
            pool = sorted((sku for sku, p in products.items() if p.category_id == cat
                          and bool(p.description) == has_description), key=rank)
            for feature in POLICY["priority_slots"]:
                candidates = [s for s in pool if members[s]["family_id"] not in families]
                preferred = [s for s in candidates if features[s][feature]]
                require(bool(preferred or candidates), "insufficient_unexposed_families")
                sku = (preferred or candidates)[0]
                families.add(members[sku]["family_id"])
                m, p = members[sku], products[sku]
                rid = "D" + str(21 + len(chosen))
                chosen.append(p.as_dict() | {"review_id": rid, "split": "development",
                    "group_id": m["group_id"], "family_id": m["family_id"],
                    "annotation_status": "unreviewed", "label_source": "unassigned", "annotator": None,
                    "independent_reference": False,
                    "attributes": [{"attribute": a, "status": "unreviewed", "value": None,
                                    "unit": None, "evidence": None} for a in config["categories"][cat]]})
                manifest.append({"review_id": rid, "sku_id": sku, "category_id": cat, "split": "development",
                    "family_id": m["family_id"], "has_description": has_description,
                    "requested_feature": feature, "features": features[sku]})
    require(len(chosen) == len(families) == 20, "selection_count_mismatch")
    require(all(digest(Path(p)) == h for p, h in protected.items()), "source_changed")
    write_rows(output / "development.tasks.jsonl", chosen)
    write_rows(output / "selection.manifest.jsonl", manifest)
    summary = {"version": POLICY["version"], "source_sha256": protected,
        "eligible_pool": len(products), "selected_cards": len(chosen), "selected_families": len(families),
        "cells": dict(Counter(r["category_id"] + ":" + str(r["has_description"]) for r in manifest)),
        "test_texts_inspected": False, "predictions_used": False, "independent_reference": False,
        "reference_status": "pending_ai_draft_and_human_review", "precision": None, "recall": None, "f1": None,
        "tool_sha256": digest(Path(__file__)),
        "artifacts": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}}
    dump(output / "selection.summary.json", summary)
    return {k: summary[k] for k in ["eligible_pool", "selected_cards", "selected_families", "cells", "reference_status"]}


def build(bundle, decisions_path, output):
    bundle, decisions_path, output = Path(bundle), Path(decisions_path), Path(output)
    summary = json.loads((bundle / "selection.summary.json").read_text(encoding="utf-8"))
    require(summary["version"] == POLICY["version"], "unknown_selection_version")
    decisions_sha = digest(decisions_path)
    for name, expected in summary["artifacts"].items():
        require(digest(bundle / name) == expected, "selection_artifact_changed")
    for name, expected in summary["source_sha256"].items():
        require(digest(Path(name)) == expected, "selection_source_changed")
    tasks = list(read_jsonl(bundle / "development.tasks.jsonl"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    require(isinstance(decisions, dict) and set(decisions) == {t["review_id"] for t in tasks}, "decision_task_mismatch")
    drafts, text, disputes = [], ["# D21–D40: AI-assisted development review", ""], []
    text += ["Все решения — AI-черновик для проверки Владом. Human-reviewed=0; P/R/F1=N/A.",
             "20 новых карточек, по одной на семейство. Reserve 40 не затронут. Predictions не использовались.",
             "Ответ: `D21: всё верно`; либо `D23: model=..., остальные поля верно`; либо `D25: color — не уверен`.",
             "Проверьте все поля, включая absent/ambiguous. Неуказанные поля пока НЕ считаются подтверждёнными.", ""]
    for task in tasks:
        rid = task["review_id"]
        require(task["split"] == "development" and task["independent_reference"] is False, "development_only")
        attrs = [a["attribute"] for a in task["attributes"]]
        require(set(decisions[rid]) == set(attrs), "decision_attribute_mismatch")
        labels = [make_label(task, a, decisions[rid][a]) for a in attrs]
        row = task | {"attributes": labels, "annotation_status": "draft", "label_source": "ai_assisted",
            "annotator": "Codex", "human_review_status": "pending", "independent_reference": False}
        drafts.append(row)
        text += [f"## {rid} · категория {task['category_id']}", "Заголовок:", fence(task["title"]),
                 "Описание — исходный текст/HTML:", fence(task["description"] or "[нет описания]"),
                 "| Атрибут | Решение | Evidence | Обоснование |", "| --- | --- | --- | --- |"]
        for label in labels:
            e = label["evidence"]
            ev = f"{e['field']} [{e['start']}:{e['end']}]: {e['text']}" if e else "—"
            value = label["status"] + (f": {label['value']} {label['unit'] or ''}" if e else "")
            text.append("| " + " | ".join(map(cell, [label["attribute"], value, ev, label["annotation_notes"]])) + " |")
            if label["needs_discussion"] or label["status"] in {"ambiguous", "unjudgeable"}:
                disputes.append(f"- **{rid} / {label['attribute']}**: {label['annotation_notes']}")
        text += ["", f"Ваш ответ: `{rid}: ...`", ""]
    require(digest(decisions_path) == decisions_sha, "decisions_changed")
    require(not output.exists(), "new_output_directory_required")
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output / "development.ai-draft.jsonl", drafts)
    write_rows(output / "exposure.manifest.jsonl", ({"sku_id": r["sku_id"], "family_id": r["family_id"],
        "review_id": r["review_id"], "split": "development", "exposure": "ai_assisted_annotation",
        "human_review_status": "pending", "independent_reference": False} for r in drafts))
    (output / "development.review.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    (output / "disputes.md").write_text("# Вопросы D21–D40\n\n" + "\n".join(disputes) + "\n", encoding="utf-8")
    result = {"cards": len(drafts), "pairs": sum(len(r["attributes"]) for r in drafts), "human_reviewed_cards": 0,
        "label_statuses": dict(Counter(a["status"] for r in drafts for a in r["attributes"])),
        "independent_reference": False, "predictions_used": False, "precision": None, "recall": None, "f1": None,
        "sources": {str(p.resolve()): digest(p) for p in [bundle / "selection.summary.json", decisions_path]},
        "artifacts": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}}
    dump(output / "draft.manifest.json", result)
    return {k: result[k] for k in ["cards", "pairs", "human_reviewed_cards", "label_statuses", "independent_reference"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("select")
    p.add_argument("--audit-bundle", type=Path, required=True)
    p.add_argument("--seen", type=Path, action="append", default=[])
    p.add_argument("--output-dir", type=Path, required=True)
    p = sub.add_parser("build")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--decisions", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        require((ROOT / "outputs").resolve() in args.output_dir.resolve().parents, "output_must_be_private_outputs")
        result = select(args.audit_bundle, args.output_dir, args.seen) if args.command == "select" else build(args.bundle, args.decisions, args.output_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        code = str(exc) if type(exc) is ValueError and str(exc).replace("_", "").isalnum() else type(exc).__name__
        parser.exit(2, "development review: " + code + "\n")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
