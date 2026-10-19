"""Prepare a development-only delivery from existing E1/EDA caches; no held-out inference."""
import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import subprocess
import zipfile

from goodsai.cli import predict
from goodsai.contracts import Product, load_config
from goodsai.data import digest, read_jsonl
from goodsai.evaluate import evaluate
from scripts.release import build_release as assembler

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SHA = "2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337"
POLICY = "development-only-unmixed-families-v1"
NAMES = {"761": "Смартфоны", "482": "Чайники"}


def check(condition, code, message):
    assembler.require(condition, code, message)


def read_object(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    check(isinstance(result, dict), "metadata_invalid", "An object metadata document is required.")
    return result


def unique_metadata(path):
    result = {}
    for row in read_jsonl(path):
        sku = row.get("sku_id")
        check(isinstance(sku, str) and sku and sku not in result, "metadata_identity", "Invalid or duplicate metadata identity.")
        check(row.get("split") in {"development", "validation", "test_reserved"}
              and isinstance(row.get("group_id"), str) and bool(row["group_id"]),
              "metadata_split", "Invalid split/group metadata.")
        result[sku] = row
    return result


def select_development(input_path, splits_path, families_path, output):
    """Gate on pre-frozen metadata before Product parsing; never predict protected families."""
    splits, families = unique_metadata(splits_path), unique_metadata(families_path)
    check(splits.keys() == families.keys(), "metadata_identity", "Split/family SKU sets differ.")
    family_splits = defaultdict(set)
    flagged = set()
    for sku, row in families.items():
        family = row.get("family_id")
        check(isinstance(family, str) and bool(family), "metadata_family", "Missing family identity.")
        check((row["group_id"], row["split"]) == (splits[sku]["group_id"], splits[sku]["split"]),
              "metadata_split", "Split/family assignments differ.")
        family_splits[family].add(row["split"])
        if row.get("mixed_split_family"):
            flagged.add(family)
    blocked = flagged | {family for family, values in family_splits.items() if values != {"development"}}
    seen = set()
    categories, excluded = Counter(), Counter()
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in read_jsonl(input_path):
            sku = row.get("sku_id")
            check(sku in families and sku not in seen, "input_identity", "Input SKU is duplicate or absent from metadata.")
            seen.add(sku)
            meta = families[sku]
            if meta["split"] != "development":
                excluded["non_development_split"] += 1
                continue
            if meta["family_id"] in blocked:
                excluded["protected_or_mixed_development_family"] += 1
                continue
            # No metadata/gold/vendor/model is merged into the extractor input.
            product = Product.from_dict(row)
            check(product.category_id == splits[sku].get("category_id"), "input_category", "Input/split category differs.")
            check(product.category_id in NAMES, "input_category", "Unexpected category in the E1 delivery.")
            categories[product.category_id] += 1
            stream.write(json.dumps(product.as_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
    check(seen == families.keys(), "input_identity", "Metadata/input SKU sets differ.")
    check(sum(categories.values()) > 0, "empty_development", "No eligible development cards.")
    return {"policy": POLICY, "source_rows": len(seen), "selected_rows": sum(categories.values()),
            "excluded_rows": sum(excluded.values()), "excluded_reasons": dict(excluded),
            "selected_categories": dict(categories),
            "test_reserved_rows_excluded": sum(row["split"] == "test_reserved" for row in families.values()),
            "test_texts_analysed": False, "test_predictions_generated": False}


def numeric_fields(source, fields):
    result = {}
    for field in fields:
        value = source[field]
        check(type(value) is int and value >= 0, "eda_aggregate_invalid", "A nonnegative integer EDA aggregate is required.")
        result[field] = value
    return result


def safe_eda(profile, joins, parquet, preparation):
    """Explicit aggregate allowlist: never export samples, seller IDs or weak labels."""
    catalog = numeric_fields(joins["catalog"][0], ["n_rows", "unique_ids", "vendors", "models", "sellers",
                            "primary_categories", "min_param_count", "max_param_count", "missing_vendor", "missing_model", "missing_title"])
    check(profile["rows"] == catalog["n_rows"] == catalog["unique_ids"], "eda_rows_mismatch", "Catalog aggregate row counts differ.")
    quantiles = joins["catalog"][0]["param_count_quantiles"]
    check(isinstance(quantiles, list) and len(quantiles) == 3 and all(type(x) is int and x >= 0 for x in quantiles),
          "eda_aggregate_invalid", "Expected p50/p90/p99 parameter quantiles.")
    return {"catalog": catalog, "parameter_count_p50_p90_p99": quantiles,
            "duplicate_parameter_name_rows": numeric_fields(profile["issues"], ["duplicate_param_names_rows"])["duplicate_param_names_rows"],
            "catalog_description_join": numeric_fields(joins["catalog_description_join"][0],
                ["catalog_rows", "matched_catalog_rows", "equal_titles", "differing_titles"]),
            "description_table": numeric_fields(parquet["descriptions"][0], ["n_rows", "unique_ids", "null_descriptions",
                "blank_descriptions", "html_rows", "min_desc_length", "max_desc_length"]),
            "e1_rows": preparation["rows"],
            "e1_categories": {key: numeric_fields(preparation["counts"][key], ["rows", "with_description", "title_only", "title_mismatch"])
                              for key in NAMES}}


def percent(value):
    return "N/A" if value is None else f"{100 * value:.1f}%".replace(".", ",")


def render_eda(eda, selection, fingerprints, report_date):
    c, j, d = eda["catalog"], eda["catalog_description_join"], eda["description_table"]
    lines = ["# EDA: сохранённые результаты и состав development delivery", "", f"Сводка на {report_date}.",
             "Использованы прежние EDA caches и Parquet footer; полный EDA и pickle loading не повторялись.", "",
             "## Каталог", "", "| Показатель | Значение |", "| --- | ---: |",
             f"| Карточки / уникальные SKU | {c['n_rows']} / {c['unique_ids']} |",
             f"| Наблюдаемые категории / продавцы | {c['primary_categories']} / {c['sellers']} |",
             f"| Различные vendor / model (исходные поля) | {c['vendors']} / {c['models']} |",
             f"| Пустой vendor / model / title | {c['missing_vendor']} / {c['missing_model']} / {c['missing_title']} |",
             f"| Параметров на SKU: min / max | {c['min_param_count']} / {c['max_param_count']} |",
             f"| Параметров: p50 / p90 / p99 | {' / '.join(map(str, eda['parameter_count_p50_p90_p99']))} |",
             f"| SKU с повторяющимися названиями параметров | {eda['duplicate_parameter_name_rows']} |", "",
             f"Число карточек каталога — {c['n_rows']}, а {eda['duplicate_parameter_name_rows']} относится к повторяющимся названиям параметров.",
             "Эта ошибка была в сокращённом DATASET.md. Vendor/model/params не являются gold и не передаются extractor.", "",
             "## Описания и join", "", "| Показатель | Значение |", "| --- | ---: |",
             f"| Строки / уникальные SKU таблицы описаний | {d['n_rows']} / {d['unique_ids']} |",
             f"| Null / пустое описание | {d['null_descriptions']} / {d['blank_descriptions']} |",
             f"| Описания с HTML | {d['html_rows']} |",
             f"| Длина описания min / max, символов | {d['min_desc_length']} / {d['max_desc_length']} |",
             f"| Каталог с сопоставленным SKU описания | {j['matched_catalog_rows']} |",
             f"| Совпавшие / различающиеся titles при join | {j['equal_titles']} / {j['differing_titles']} |", "",
             "Число строк таблицы описаний не равно числу карточек каталога. HTML требует сохранения raw offsets;",
             "title mismatch требует provenance, а повтор параметра не доказывает правильность значения.", "",
             "## Подготовленный E1", "", "| Категория | SKU | С description | Title-only | Title mismatch |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for cat, values in eda["e1_categories"].items():
        lines.append(f"| {NAMES[cat]} ({cat}) | {values['rows']} | {values['with_description']} | {values['title_only']} | {values['title_mismatch']} |")
    lines += ["", "## Новый прогноз", "", f"Из {selection['source_rows']} E1 SKU выбрано {selection['selected_rows']} development SKU.",
              f"Исключено {selection['excluded_rows']}: {json.dumps(selection['excluded_reasons'], ensure_ascii=False)}.",
              f"Политика: `{POLICY}`. Закрытые и смешанные семейства не предсказываются.",
              "Это ограниченный batch, не predictions по всему каталогу. Near-duplicate grouping — существующая",
              "лексическая эвристика, не доказательство отсутствия всех семантических дублей.", "",
              "## Происхождение", "", "| Локальный источник | SHA-256 |", "| --- | --- |"]
    lines += [f"| {name} | `{checksum}` |" for name, checksum in fingerprints.items()]
    lines += ["", "Оригинальные raw-файлы не изменялись. Их происхождение унаследовано от прежней проверки;",
              "raw pickle не перечитывался. Примеры карточек, SKU, seller IDs и target params в эту сводку не включены."]
    return "\n".join(lines) + "\n"


def render_slides(summary, report_date):
    micro = summary["metrics"]["metrics"]["micro"]
    selection, batch, eda = summary["selection"], summary["batch"], summary["eda"]
    table = ["| Поле | TP | FP | FN | F1 |", "| --- | ---: | ---: | ---: | ---: |"]
    for key, value in summary["metrics"]["metrics"].items():
        if key.startswith("attribute:"):
            table.append(f"| {key.split(':', 1)[1]} | {value['tp']} | {value['fp']} | {value['fn']} | {percent(value['f1'])} |")
    return f"""# GoodsAI

Технический checkpoint · {report_date}

Rules baseline для смартфонов и чайников.
Code candidate: `{summary['source']['git_commit']}`.

---

# Данные и границы прогноза

- Каталог: {eda['catalog']['n_rows']} SKU. Подготовленный E1: {eda['e1_rows']} SKU.
- Новый batch: **{selection['selected_rows']} development SKU** двух категорий.
- {selection['excluded_rows']} E1 SKU исключены: другие split и защищённые/смешанные семейства.
- Закрытый test не предсказывался. Данные — только title/description; изображения и target params не используются.

Источник: private/eda.md в комплекте, selection policy `{POLICY}`.

---

# Пайплайн

Text-only Product → правила и словари → проверка кандидата → нормализация → проверка конфликта и выхода → JSONL + manifest.

- Значение сопровождается исходным evidence span.
- Конфликт/отсутствие → abstain; найденный кандидат → review.
- Confidence эвристический. Автоматического принятия нет.
- Реальная ML/LLM-ветка пока отсутствует.

Источник: src/goodsai/contracts.py, verify.py, rules.py, model_rules.py.

---

# Оценка на reviewed development

**P {percent(micro['precision'])} · R {percent(micro['recall'])} · F1 {percent(micro['f1'])}**

TP {micro['tp']}, FP {micro['fp']}, FN {micro['fn']} · {summary['metrics']['reviewed_cards']} карточек, {micro['judged']} judged-пар.

AI-assisted human-reviewed M2, использованный при разработке.
Это **не независимый holdout** и не оценка качества всего каталога.
Бывший validation также является development_feedback.

Источник: public/quality.json; frozen reference SHA в release.manifest.json.

---

# Качество по атрибутам

{chr(10).join(table)}

У model в M2 нет judged-примеров с отсутствующей моделью: model-FP на таких случаях не измерен.
Неверное значение вместо present gold = FP+FN; ambiguous исключаются явно.

---

# Работа на batch

- Строк результата: {batch['rows']}, ровно одна на каждую входную карточку.
- Статусы: {json.dumps(batch['status_counts'], ensure_ascii=False)}.
- Измеренные extractor p50/p95: {batch['extractor_p50_ms']:.3f}/{batch['extractor_p95_ms']:.3f} мс.
- Полное локальное время batch: {batch['elapsed_seconds']:.2f} с.
- LLM calls: 0; API-расход: 0 ₽. Денежная стоимость compute не оценивалась.

Windows/Python {batch['python']}; один локальный запуск, без гарантий SLA.
Coverage показывает заполнение кандидатов, а не precision.

---

# Комплект и воспроизведение

Код/README, EDA-сводка, pipeline/config, реальные development predictions,
reviewed-метрики, технические Markdown-слайды и frozen manifest.

Сборка: `python -m scripts.release.prepare_delivery --report-date {report_date} --output-dir outputs/delivery/new-run`

Проверка: `python scripts/release/build_release.py verify --bundle outputs/delivery/new-run/bundle`

Нужны локальные данные и frozen metadata. Private input/gold/predictions не публикуются автоматически.

---

# Ограничения и дальнейшая работа

- Не выполнена независимая blind human-оценка; test остаётся закрытым.
- Поддерживаются две категории; длинный хвост и ноутбуки ещё не закрыты.
- Нет ML/LLM-сравнения, калибровки confidence и auto_accept.
- Дальше: release gate и проверка VM, независимый gold, затем измеряемый модельный эксперимент.

Технический черновик checkpoint; финальные выводы защиты обновляются после независимой оценки.
"""


def prepare(output, report_date, *, root=ROOT):
    import pyarrow.parquet as pq

    date.fromisoformat(report_date)
    check(not assembler.git(root, "status", "--porcelain"), "dirty_source", "Commit the candidate before preparing delivery.")
    output = assembler.new_output(output, root)
    data, eda_root = root / "data", root / "outputs/eda"
    base = data / "gold/e1"
    paths = {"input": data / "processed/e1/pilot.jsonl", "prepare_manifest": data / "processed/e1/prepare_manifest.json",
             "annotation_manifest": base / "annotation_manifest.json", "splits": base / "split_manifest.jsonl",
             "families": base / "m2/v2/family.manifest.jsonl", "selection_summary": base / "m2/v2/selection.summary.json",
             "reference": base / "m2/v2/reviewed/development.human-reviewed.jsonl",
             "catalog_profile": eda_root / "catalog_profile.json", "joins_profile": eda_root / "joins_profile.json",
             "parquet_profile": eda_root / "parquet_profile.json", "opcode_scan": eda_root / "pickle_opcodes.json",
             "projection": eda_root / "catalog_skus.parquet"}
    fingerprints = {name: digest(path) for name, path in paths.items()}
    prep, annotation, frozen = (read_object(paths[name]) for name in ["prepare_manifest", "annotation_manifest", "selection_summary"])
    check(fingerprints["input"] == prep["input_sha256"] == annotation["input_sha256"], "input_hash_mismatch", "Prepared input identity differs.")
    check(fingerprints["families"] == frozen["artifacts"]["family.manifest.jsonl"], "family_hash_mismatch", "Frozen family metadata differs.")
    protected = {name.replace("\\", "/").split("/")[-1]: value for name, value in frozen["protected_sources"].items()}
    check(fingerprints["splits"] == protected["split_manifest.jsonl"] and fingerprints["input"] == protected["pilot.jsonl"],
          "split_hash_mismatch", "Frozen split/input differs.")
    check(fingerprints["reference"] == REFERENCE_SHA, "reference_hash_mismatch", "Use the approved M2 development reference.")
    check(fingerprints["projection"] == prep["projection_sha256"], "projection_hash_mismatch", "Cached projection identity differs.")
    check(read_object(paths["opcode_scan"])["source_sha256"] == prep["source_sha256"]["skus.pkl"],
          "source_hash_mismatch", "Inherited raw source fingerprints differ.")
    selected = output / "development.input.jsonl"
    selection = select_development(paths["input"], paths["splits"], paths["families"], selected)
    check(selection["source_rows"] == prep["rows"] == frozen["input_rows"], "source_row_mismatch", "Preparation metadata row counts differ.")
    chosen_ids = {row["sku_id"] for row in read_jsonl(selected)}
    check(all(row["sku_id"] in chosen_ids for row in read_jsonl(paths["reference"])),
          "reference_not_selected", "Reviewed M2 reference must be within selected development.")
    config = load_config()
    predictions = output / "predictions.jsonl"
    batch = predict(selected, predictions, config)
    metrics = evaluate(predictions, paths["reference"], config)
    check(metrics.get("evaluation_status") == "manual_reference", "reference_unavailable", "Reviewed M2 evaluation is unavailable.")
    profile, joins, parquet = (read_object(paths[name]) for name in ["catalog_profile", "joins_profile", "parquet_profile"])
    aggregate = safe_eda(profile, joins, parquet, prep)
    check(pq.ParquetFile(paths["projection"]).metadata.num_rows == aggregate["catalog"]["n_rows"],
          "eda_footer_mismatch", "Projection footer disagrees with cached EDA.")
    reports = output / "reports"
    reports.mkdir()
    eda_path, deck_path = reports / "eda.md", reports / "technical_slides.md"
    summary = {"source": {key: batch[key] for key in ["git_commit", "git_dirty", "code_sha256", "config_sha256"]},
               "scope": "development_delivery_not_full_catalogue", "selection": selection, "batch": batch,
               "eda": aggregate, "metrics": metrics, "reference_provenance": "ai_assisted_reviewed_development",
               "independent_reference": False, "source_fingerprints": fingerprints}
    eda_path.write_text(render_eda(aggregate, selection, fingerprints, report_date), encoding="utf-8")
    deck_path.write_text(render_slides(summary, report_date), encoding="utf-8")
    assembler.save(reports / "reviewed-metrics.json", metrics)
    spec = {"spec_version": "1", "source_commit": batch["git_commit"], "reference_kind": "ai_assisted_reviewed_development"}
    entries = {"config": root / "src/goodsai/baseline.json", "input": selected, "predictions": predictions,
               "reference": paths["reference"], "eda": eda_path, "presentation": deck_path, "metrics": reports / "reviewed-metrics.json"}
    for key, path in entries.items():
        spec[key] = {"path": str(path.resolve()), "sha256": digest(path)}
    assembler.save(output / "release-spec.json", spec)
    bundle = assembler.build(output / "bundle", spec, root=root)
    check(bundle["status"] == "complete", "bundle_incomplete", "Assembly did not produce a complete bundle; inspect its manifest.")
    verified = assembler.verify_bundle(output / "bundle")
    check(all(digest(paths[name]) == checksum for name, checksum in fingerprints.items()),
          "protected_source_changed", "An inherited source changed during delivery preparation.")
    archive = output / "delivery-bundle.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as target:
        for path in sorted((output / "bundle").rglob("*")):
            if path.is_file():
                target.write(path, path.relative_to(output / "bundle").as_posix())
    summary.update(status="prepared", assembly_status=bundle["status"], verification=verified,
                   report_date=report_date, archive={"sha256": digest(archive), "bytes": archive.stat().st_size},
                   protected_sources_unchanged=True, extractor_received_metadata=False,
                   test_reserve_opened=False, llm_calls=0, presentation_format="markdown_checkpoint_draft")
    assembler.save(output / "preparation.manifest.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-date", required=True, help="Client-local YYYY-MM-DD date for the report")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.output_dir, args.report_date)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        code = exc.code if isinstance(exc, assembler.BuildError) else type(exc).__name__
        print(f"delivery preparation failed ({code}); preserve the new output directory for diagnosis")
        return 2
    print(json.dumps({"status": result["status"], "selected_rows": result["selection"]["selected_rows"],
                      "excluded_rows": result["selection"]["excluded_rows"], "metrics": result["metrics"]["metrics"]["micro"],
                      "source_commit": result["source"]["git_commit"], "archive_sha256": result["archive"]["sha256"]},
                     ensure_ascii=True, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
