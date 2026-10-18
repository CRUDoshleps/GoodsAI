"""Validate offline M2 artifacts and render explicitly authored AI drafts.

No predictions, network access, test text materialization or human-label promotion.
An evidence quote is an author-selected witness, never a guessed label.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl
from goodsai.normalize import UNITS, numeric
from goodsai.runtime import identity
from goodsai.text import visible_span, visible_view


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def records(path):
    return list(read_jsonl(path))


def validate_bundle(bundle):
    bundle = Path(bundle)
    summary = json.loads((bundle / "selection.summary.json").read_text(encoding="utf-8"))
    for name, expected in summary["artifacts"].items():
        if digest(bundle / name) != expected:
            raise ValueError("Selection artifact SHA mismatch: " + name)
    for path, expected in summary["protected_sources"].items():
        if digest(Path(path)) != expected:
            raise ValueError("Protected source SHA mismatch")
    if identity(load_config())["code_sha256"] != summary["runtime_identity"]["code_sha256"]:
        raise ValueError("Frozen runtime changed; create a new protocol, do not silently reevaluate")
    family_rows = records(bundle / "family.manifest.jsonl")
    families = {r["sku_id"]: r for r in family_rows}
    if len(families) != len(family_rows):
        raise ValueError("Duplicate family SKU")
    selected = records(bundle / "selection.manifest.jsonl")
    ids, groups = set(), set()
    for row in selected:
        ref = families[row["sku_id"]]
        expected_split = "development" if row["purpose"] == "development" else "test_reserved"
        if (row["sku_id"] in ids or row["family_id"] in groups
                or row["split"] != expected_split or ref["split"] != expected_split
                or ref["group_id"] != row["group_id"] or ref["family_id"] != row["family_id"]
                or ref["family_exposed"] or ref["mixed_split_family"] or ref["known_exposure"]):
            raise ValueError("Selected overlap/exposure/split violation")
        ids.add(row["sku_id"])
        groups.add(row["family_id"])
    config = load_config()
    for purpose, name in [("development", "development.tasks.jsonl"), ("test", "test_reserve.blank.jsonl")]:
        tasks = records(bundle / name)
        selection = {r["sku_id"]: r for r in selected if r["purpose"] == purpose}
        if len(tasks) != len(selection) or {r["sku_id"] for r in tasks} != selection.keys():
            raise ValueError("Task selection mismatch")
        for i, row in enumerate(tasks, 1):
            selected_row = selection[row["sku_id"]]
            if row["review_id"] != ("D" if purpose == "development" else "T") + f"{i:02d}":
                raise ValueError("Unstable review numbering")
            for key in ["category_id", "group_id", "family_id", "split"]:
                if row[key] != selected_row[key]:
                    raise ValueError("Task metadata mismatch")
            if (row["annotation_status"] != "unreviewed" or row["label_source"] != "unassigned"
                    or row["annotator"] is not None):
                raise ValueError("Blank task promoted to reviewed")
            expected = [{"attribute": a, "status": "unreviewed", "value": None, "unit": None, "evidence": None}
                        for a in config["categories"][row["category_id"]]]
            if row["attributes"] != expected:
                raise ValueError("Blank task has a prefilled answer")
            if purpose == "test":
                allowed = {"review_id", "sku_id", "category_id", "group_id", "family_id", "split",
                           "annotation_status", "label_source", "annotator", "attributes", "text_materialized"}
                if set(row) != allowed or row["text_materialized"] is not False:
                    raise ValueError("Test export must be metadata and blanks only")
            else:
                Product.from_dict({k: row[k] for k in ["schema_version", "sku_id", "category_id", "title",
                                                     "description", "seller_attributes", "source_flags"] if k in row})
    return {"status": "verified", "selection_counts": summary["selected_counts"],
            "runtime_sha256": summary["runtime_identity"]["code_sha256"],
            "new_quality": "N/A: pending human review", "test": "metadata and blanks only"}


def make_label(task, attribute, spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("note"), str) or not spec["note"].strip():
        raise ValueError("Every label needs an explicit explanation")
    status = spec.get("status", "present")
    label = {"attribute": attribute, "status": status, "value": None, "unit": None,
             "evidence": None, "annotation_notes": spec["note"], "needs_discussion": bool(spec.get("discuss", False))}
    if status not in {"present", "absent", "ambiguous", "unjudgeable"}:
        raise ValueError("Invalid draft status")
    if status != "present":
        if set(spec) - {"status", "note", "discuss"}:
            raise ValueError("Non-present label must not have a value or witness")
        return label
    if set(spec) - {"status", "note", "discuss", "value", "unit", "field", "quote", "occurrence"}:
        raise ValueError("Unexpected draft field")
    value, unit, field, quote = spec.get("value"), spec.get("unit"), spec.get("field"), spec.get("quote")
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or field not in {"title", "description"} or not isinstance(quote, str) or not quote
            or unit != UNITS.get(attribute)):
        raise ValueError("Invalid canonical value/unit/witness")
    if attribute in UNITS and numeric(attribute, value, unit) != value:
        raise ValueError("Noncanonical numeric label")
    source = task.get(field) or ""
    occurrences = [m.start() for m in re.finditer(re.escape(quote), source)]
    occurrence = spec.get("occurrence")
    if occurrence is None:
        if len(occurrences) != 1:
            raise ValueError("Witness must occur exactly once or specify occurrence")
        occurrence = 0
    if type(occurrence) is not int or not 0 <= occurrence < len(occurrences):
        raise ValueError("Invalid witness occurrence")
    start = occurrences[occurrence]
    end = start + len(quote)
    visible = visible_span(source, start, end)
    if attribute == "model" and " ".join(visible.split()) != value:
        raise ValueError("Model changes characters/case beyond agreed whitespace normalization")
    label.update(value=value, unit=unit, evidence={"field": field, "start": start, "end": end, "text": quote})
    return label


def fence(value):
    marker = "`" * max(3, max((len(s) for s in re.findall(r"`+", value)), default=0) + 1)
    return marker + "text\n" + value + "\n" + marker


def cell(value):
    # Untrusted raw HTML stays inert in Markdown tables.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\n", " ")


def render(tasks, drafts):
    out = ["# M2: проверка AI-черновика (20 новых development-карточек)",
           "Это AI-assisted черновик, не gold. P/R/F1 до ваших подтверждений — N/A. Предсказания не использованы.",
           "Постоянные номера D01–D20 относятся только к пакету v2; v1 — отклонённый технический отбор.",
           "Проверяйте исходный текст и все атрибуты. absent означает недостаток сведений в тексте.",
           "Ответ: `D01: всё верно`; либо `D03: model=..., остальные верно`; либо `D06: color — не уверен`.",
           "Без подтверждения спорного поля оно останется pending. Внешние знания записываем отдельно."]
    disputes = ["# Вопросы M2", "Все D01–D20 требуют проверки. Здесь — приоритетные вопросы; тексты в development.review.md."]
    for task, row in zip(tasks, drafts):
        rid = row["review_id"]
        out += [f"## {rid} · категория {row['category_id']} · SKU {row['sku_id']}",
                "Заголовок (исходный):", fence(task["title"]), "Описание (исходный HTML):",
                fence(task["description"] or "[описание отсутствует]"),
                "Видимый текст описания:", fence(visible_view(task["description"] or "")[0] or "[нет]")]
        table = ["| Атрибут | Статус / значение | Evidence: поле [start:end], точная цитата | Обоснование |",
                 "| --- | --- | --- | --- |"]
        for a in row["attributes"]:
            e = a["evidence"]
            ev = f"{e['field']} [{e['start']}:{e['end']}]: {e['text']}" if e else "—"
            value = a["status"] + (f": {a['value']} {a['unit'] or ''}" if a["value"] is not None else "")
            table.append("| " + " | ".join(map(cell, [a["attribute"], value, ev, a["annotation_notes"]])) + " |")
            if a["needs_discussion"] or a["status"] in {"ambiguous", "unjudgeable"}:
                disputes.append(f"- **{rid} / {a['attribute']}**: {cell(a['annotation_notes'])}")
        out.append("\n".join(table))
        out.append("Ваш ответ: `" + rid + ": ...`\n")
    return "\n\n".join(out) + "\n", "\n\n".join(disputes) + "\n"


def build(bundle, decisions_path, output):
    bundle, decisions_path, output = Path(bundle), Path(decisions_path), Path(output)
    validate_bundle(bundle)
    if any(a.lower() == "data" and b.lower() == "raw" for a, b in zip(output.resolve().parts, output.resolve().parts[1:])):
        raise ValueError("Do not write into data/raw")
    if output.exists():
        raise ValueError("Never overwrite a draft/review directory")
    tasks = records(bundle / "development.tasks.jsonl")
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if set(decisions) != {t["review_id"] for t in tasks}:
        raise ValueError("Decisions must cover exactly the selected development tasks")
    drafts = []
    config = load_config()
    for task in tasks:
        specs = decisions[task["review_id"]]
        attrs = config["categories"][task["category_id"]]
        if set(specs) != set(attrs):
            raise ValueError("Decisions must cover all requested attributes")
        row = deepcopy(task)
        row.update(annotation_status="ai_draft", label_source="ai", annotator="Codex",
                   human_review_status="pending", independent_reference=False)
        row["attributes"] = [make_label(task, a, specs[a]) for a in attrs]
        drafts.append(row)
    review, disputes = render(tasks, drafts)
    output.mkdir(parents=True, exist_ok=False)
    (output / "development.ai-draft.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in drafts), encoding="utf-8")
    (output / "development.review.md").write_text(review, encoding="utf-8")
    (output / "development.disputes.md").write_text(disputes, encoding="utf-8")
    report = {"reference_status": "ai_assisted_pending_human_review", "independent_reference": False,
              "cards": len(drafts), "labels": sum(len(r["attributes"]) for r in drafts),
              "label_statuses": dict(Counter(a["status"] for r in drafts for a in r["attributes"])),
              "precision": None, "recall": None, "f1": None, "predictions_used": False,
              "sources": {str(p.resolve()): digest(p) for p in [bundle / "selection.summary.json",
                         bundle / "development.tasks.jsonl", decisions_path]},
              "review_tool_sha256": digest(Path(__file__)),
              "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
    save(output / "draft.manifest.json", report)
    return {k: report[k] for k in ["cards", "labels", "label_statuses", "reference_status", "predictions_used"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("audit")
    p.add_argument("--bundle", type=Path, required=True)
    p = sub.add_parser("build")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--decisions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate_bundle(args.bundle) if args.command == "audit" else build(args.bundle, args.decisions, args.output)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"review M2: {type(exc).__name__}: {exc}\n")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
