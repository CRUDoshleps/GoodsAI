# Проверяемая сборка комплекта

ART-003, этап B после [исправления инструкций](RESULTS.md). Сборщик —
`scripts/release/build_release.py`, Python >=3.12, полный Git clone и
установленный `.[serve,test]`. Запуск из корня checkout. Он не меняет runtime,
не обучает модель, не вызывает LLM и не обновляет VM/Gitea.

## Публичная проверка без данных

PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/release/build_release.py smoke --output-dir outputs/release/smoke-next
.\.venv\Scripts\python.exe scripts/release/build_release.py verify --bundle outputs/release/smoke-next
```

Linux: заменить `.\.venv\Scripts\python.exe` на `.venv/bin/python`.
Нужен новый каталог: существующий, в том числе пустой, не перезаписывается.
Путь сборки должен оставаться в игнорируемом `outputs/` данного clone.

Ожидается `synthetic_smoke`, demo 6/6, rows=6, llm_calls=0; затем `verified`.
Это **не комплект сдачи**: EDA и финальная презентация отсутствуют, P/R/F1 N/A.
Smoke не принимает внешние карточки, gold, EDA или презентацию; исходные
примеры берутся только из пакета. Он совместим с обычным demo, но не заменяет
его и не меняет код ART-002 коллеги.

Создаются:

```text
release.manifest.json       hashes, source identity, статусы шести артефактов
public/code.zip             выбранные tracked code/docs и synthetic fixtures
public/README.md
public/pipeline/            конфиг и descriptor текущего rules runtime
public/smoke/               input, predictions, manifest, demo summary
public/report.md           человекочитаемая сводка
```

Архив содержит рабочие байты файлов (переносы строк влияют на code hash),
не `.git` и не полную Git-историю. Для исторических comparison tests нужен
полный clone, не только `code.zip`. Dirty smoke допустим, но так и помечается;
он не является доказательством чистого релиза.

## Локальный комплект реальных артефактов

1. На чистом release checkout зафиксировать `git rev-parse HEAD` и версию
   Python. Сборщик и producer predictions должны видеть **тот же HEAD**.
2. Подготовить утверждённый text-only input, выполнить реальный batch текущим
   rules CLI. Например, если локальный E1 уже подготовлен:

   ```bash
   .venv/bin/python -m goodsai.cli predict --input data/processed/e1/pilot.jsonl --output outputs/release-inputs/predictions.jsonl
   ```

   Использовать новый prediction path, сохранить `.manifest.json` рядом.
   Это прогноз по предоставленному входу; он не доказывает, что вход содержит
   весь выданный каталог, и не является независимой оценкой.
3. Подготовить существующий EDA-отчёт и реальную техническую презентацию.
   Не повторять полный EDA ради сборки и не переименовывать продуктовые слайды
   в финальные технические. Поддержаны EDA `.md/.html/.pdf`, презентация
   `.md/.pdf/.pptx`. Содержание проверяет человек; формат файла не доказывает
   наличие нужных выводов/метрик.
4. Скопировать [template](examples/release-spec.example.json) в
   `outputs/release-inputs/release-spec.json`, заменить пути, полный HEAD и
   lowercase SHA-256 каждого файла. SHA — отпечатки **утверждённых** файлов;
   не обновлять их автоматически после неизвестного изменения.
5. Выполнить одну команду сборки:

   ```powershell
   .\.venv\Scripts\python.exe scripts/release/build_release.py assemble --spec outputs/release-inputs/release-spec.json --output-dir outputs/release/rc-next
   .\.venv\Scripts\python.exe scripts/release/build_release.py verify --bundle outputs/release/rc-next
   ```

Hash отдельного файла в PowerShell:

```powershell
(Get-FileHash -Algorithm SHA256 outputs/release-inputs/eda.md).Hash.ToLowerInvariant()
```

Пути в spec разрешаются относительно корня repo, абсолютные также допустимы.
Ожидаемые SHA обязательны, пустой или изменённый файл не принимается.
Конфиг должен семантически совпадать с versioned `src/goodsai/baseline.json`:
внешние settings/ключи не копируются в публичную часть. Расширение конфига
и поддержка модельного runtime — отдельная задача.

## Метрики и происхождение reference

Без `reference` и `metrics` сборщик создаёт `quality.json` со статусом
unavailable, P/R/F1 `null`. Состав файлов может быть complete при качестве N/A;
это не разрешение выдавать отсутствие оценки за выполненный gold benchmark.

Для разрешённого reviewed development добавить в spec:

```json
{
  "reference": {"path": "data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl", "sha256": "2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337"},
  "reference_kind": "ai_assisted_reviewed_development"
}
```

Это **дополнение** к полному spec, не отдельный готовый spec. Reference должен
быть reviewed/manual с annotator; допустим subset полного batch, но все его SKU,
тексты и категории должны совпасть с input. Evaluator запускается заново на
локальных captured файлах; правила/extractor заново не вызываются. На стадии
разработки `test`/`test_reserved` запрещены. Реальный резерв сам не выбирается
и не открывается по умолчанию.

Поддержаны `ai_assisted_reviewed_development`, `development_feedback`,
`blind_human_reviewed`. Последний — утверждение provenance автором spec,
не автоматическое доказательство независимости; closed test этим не разрешён.
При `metrics: {path, sha256}` supplied JSON должен точно совпасть с новым
выходом штатного evaluator. Отчёты experiment summary/envelope вместо
`metrics.json` напрямую не подставляются. Без reference supplied metrics
отклоняются. Полные per-attribute/category результаты находятся в quality.json,
краткий TP/FP/FN и P/R/F1 — в report.md.

## Что проверяет сборщик

- Матрицу code, README, EDA, pipeline, predictions, presentation.
- Наличие/непустоту/hash каждого заданного файла; отсутствие перезаписи.
- Current HEAD и clean tree; code/config/input/output hashes producer manifest.
- Ровно один prediction на каждый входной SKU, без пропусков/дубликатов/лишних.
- Схему v0.1, категории/статусы, run_id, counts, raw evidence по исходному тексту.
- Текущий rules-only runtime, heuristic confidence, review/abstain, llm_calls=0.
- Reference identity/provenance и соответствие supplied metrics пересчёту.

Предсказания и manifest копируются под существующей блокировкой snapshot;
чужой active writer или повреждённая пара не превращаются в complete.
Источник input и прочие файлы захватываются с проверкой frozen SHA.

Новые форматы LLM, producer без paired manifest, параметры из другого конфига,
новые reason codes, грязный checkout и source_commit mismatch требуют разбора,
не ослабления проверок ради сборки. Exact evidence не гарантирует смысловую
правильность атрибута. Отдельные latency/cost tests, зависимости/CVE, VM smoke
и проверка официального API здесь не выполняются.

## Статусы и код завершения

| Результат | Exit code | Значение |
| --- | ---: | --- |
| `synthetic_smoke` | 0 | синтетический путь прошёл; шести артефактов нет |
| `complete` | 0 | шесть файлов/компонентов присутствуют и связаны проверками |
| `incomplete` | 2 | manifest/report сохранены с причиной; комплект не готов |
| ошибка spec/output/verify | 2 | отказ без перезаписи существующего каталога |
| `verified` | 0 | файлы после переноса совпадают с manifest |

`complete` и `verified` не подтверждают качество/авторство/одобрение релиза.
`release_approval` всегда `not_granted`; содержание EDA/презентации и канал
сдачи требуют командного review. Manifest не подписан: SHA обнаруживают порчу,
а не намеренную одновременную подмену manifest и файлов.

## Подготовка реального development checkpoint

ART-001 добавляет orchestrator `python -m scripts.release.prepare_delivery`.
Нужны локальные неизменённые caches:

- `data/processed/e1/{pilot.jsonl,prepare_manifest.json}`;
- `data/gold/e1/{annotation_manifest.json,split_manifest.jsonl}`;
- M2 v2 `family.manifest.jsonl`, `selection.summary.json` и reviewed development;
- `outputs/eda/{catalog_profile,joins_profile,parquet_profile,pickle_opcodes}.json`
  и существующая `catalog_skus.parquet`.

На чистом candidate checkout:

```powershell
.\.venv\Scripts\python.exe -m scripts.release.prepare_delivery --report-date 2026-10-19 --output-dir outputs/delivery/checkpoint-next
```

Дата — локальная дата отчёта, при новом checkpoint укажите актуальную.
Исходные SHA сверяются с прежними manifests; проекция проверяется по SHA/footer,
pickle не загружается. Закрытые и смешанные семейства исключаются **до**
Product/predict; используются только unmixed development groups. Source/split/
family metadata не попадают в extractor. Закрытые задания test не открываются.

Выход: `development.input.jsonl`, `predictions.jsonl` и paired manifest,
`reports/{eda.md,technical_slides.md,reviewed-metrics.json}`, `release-spec.json`,
`preparation.manifest.json`, `bundle/` и `delivery-bundle.zip`. Сборка и verify
выполняются внутри команды. Созданный ZIP содержит приватные тексты и reference,
остаётся локально. Publishable агрегаты и Markdown-слайды отбираются отдельно.

EDA-сводка берёт только разрешённые числовые агрегаты из caches, а не samples,
seller IDs или target values. Слайды содержат измеренные результаты и оговорку
AI-assisted development; это технический черновик checkpoint, не финальное
оформление защиты. Исходные данные/старые outputs не перезаписываются.

Producer SHA фиксируется в момент запуска. Если затем публикуются generated
агрегаты новым docs commit, они продолжают ссылаться на исходный code candidate;
это разные identities. Для повторения нужно checkout того SHA либо создать
новый checkpoint на другом чистом HEAD с новыми manifests.

## Публикация и оставшаяся работа

В private-сборке исходный input, predictions, reference, supplied metrics,
EDA и презентация копируются **только** в `private/`. Public содержит код,
versioned конфиг и вычисленные агрегаты. `release.manifest.json` включает
hashes обеих частей. Для полной проверки `verify` нужен весь комплект,
а не только скопированная public-папка.

Сейчас всё создаётся локально в игнорируемом outputs. Влад разрешил при
необходимости включить нужные файлы/данные в Gitea. Для ближайшего прогона
можно отдельно отобрать безопасные EDA-агрегаты, metrics/report и финальные
слайды; приватный input/gold/raw автоматически в Git не добавляются.
Реальный большой predictions-файл передаётся согласованным каналом ART-001.

Финальная техническая презентация и официальный real-data release пока не
созданы этим этапом. В smoke они честно missing. Сборщик готов связать их,
когда файлы будут подготовлены; synthetic fixture в тестах не является заменой.
