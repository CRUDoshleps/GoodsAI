# GoodsAI

Извлечение характеристик товара из названия и описания с точным evidence.
Поддерживаются смартфоны (`761`) и чайники (`482`). CLI и HTTP API возвращают
нормализованные значения, исходные offsets и решения `review` / `abstain`.
По умолчанию работают правила; LLM-fallback включается явно и требует ключа.

Это репозиторий сдачи. Исходный GitHub commit и SHA-256 опубликованных файлов
указаны в [submission-manifest.json](../../submission-manifest.json).

## Проверено и измерено

| Проверка / reference | Результат | Версия и граница вывода |
| --- | --- | --- |
| Общий QA-002 прогон | 499 unit/integration, 3 reader, 11 property tests PASS | source `75d2821`; [протокол и ограничения](../../reports/qa002_20261021.md) |
| Внешний JSONL → CLI/HTTP без packaged examples | 83/83 synthetic contract checks | протокол кода `1c64463`, seed `20261020`; не catalog P/R/F1 |
| 40 AI-assisted human-reviewed development | 143 TP / 0 FP / 22 FN | snapshot `3d3dc49`; не independent test и не новый замер нынешнего main |
| 3037 catalog-silver cards | agreement F1 75,67% | producer `f33e3fc`, исторический отчёт; не human precision |
| Независимый human test и общий актуальный model benchmark | N/A | приёмка не завершена; auto_accept по умолчанию выключен |

Происхождение и воспроизведение: [RESULTS](../../docs/RESULTS.md).
Последний измеренный quality snapshot (`9ebba1d`): [атрибуты и категории](../../reports/quality_20261021.md)
и [машиночитаемые агрегаты](../../reports/quality_20261021.json). Catalog-silver и
AI-assisted reviewed model regressions показаны отдельно; независимая оценка — N/A.
В [storage shadow-пилоте](../../reports/storage_shadow_20261022.md) человек
подтвердил 145/145 предложений правил. Условная нижняя 95%-граница 97,955%
не достигает выбранных 99%. Это development-аудит, не independent calibration.
После аудита согласован [ограниченный opt-in auto_accept с целью 97%](../../docs/STORAGE_PILOT.md)
только для накопителя смартфонов. Default остаётся review/abstain; при цели
99% пилот также возвращает review. Confidence остаётся эвристическим.
Корректные значения, конфликты и безопасные отказы:
[таблица решений verifier](../../docs/VERIFIER.md#проверяемая-таблица-решений).
`review` требует проверки перед публикацией в каталог; confidence эвристический,
не вероятность. [Обучаемый advisory score](../../docs/CONFIDENCE.md) доступен
как opt-in для приоритизации review: catalog-proxy Brier 0.06590 → 0.03283,
reviewed sanity Brier 0.03937 → 0.00959. Это не независимая human calibration
и не основание для новых порогов auto_accept; default fixed-v1 сохраняется.
Независимо от выбранного score,
auto_accept по умолчанию выключен; узкое исключение пилота описано выше.
Расхождения `model` разобраны в [#137](https://github.com/CRUDoshleps/GoodsAI/issues/137)
по подтверждённой AI-assisted разметке; QA parser fix не сопровождается новым
замером каталога. [Команды общего QA-прогона](../../docs/QA_ACCEPTANCE.md).
[Требования → реализация → оставшийся долг](../../docs/REQUIREMENTS.md).

Рабочая политика команды — [SPEC-001: spec-team-v1](../../TECHNICAL_SPEC.md#0-действующая-политика-команды--spec-001).
Она сохраняет JSON v0.1 и разделяет требования кейса, ограничения E1 и условия
будущей приёмки. Официальные endpoints пока не объявлены.

[Матрица сценариев](../../docs/SCENARIO_MATRIX.md): внешний CLI/HTTP без packaged
examples, offline verifier/LLM и отдельный smoke; пробелы видны в общем отчёте.
После установки зависимостей запустите:

```bash
.venv/bin/python scripts/release/scenario_matrix.py --seed 20261020 --output-dir outputs/scenarios-check
```

PowerShell: замените `.venv/bin/python` на `.\.venv\Scripts\python.exe`.
Отчёт — `outputs/scenarios-check/report.md`. PASS относится к synthetic
доказательствам реализованных сценариев, не ко всему кейсу или качеству каталога.

## Быстрый запуск

Требуется Python 3.12+. Клонируйте с полной историей: comparison tests используют
исторический baseline. Из корня этого checkout (Linux/macOS):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m pip check
mkdir -p outputs
cat > outputs/my-card.jsonl <<'JSON'
{"schema_version":"0.1","sku_id":"my-phone","category_id":"761","title":"Смартфон Samsung Orbit X73 12/512GB белый","description":"Экран 6,4 дюйма. Аккумулятор 4600 мАч."}
JSON
.venv/bin/python -m goodsai.cli predict --input outputs/my-card.jsonl --output outputs/my-predictions.jsonl
```

Ожидаются `processed`, Samsung, Orbit X73, 12 GB RAM, 512 GB storage,
6.4 inch, 4600 mAh, белый; все найденные значения имеют `decision=review`.
Predictions и paired manifest записываются в `outputs/`.
Можно заменить название и описание своими текстами. Готовые vendor/model/params
во входе запрещены.

Фрагмент результата для этого ввода:

```json
{"attribute":"brand","value":"Samsung","unit":null,"confidence":0.85,"confidence_kind":"heuristic","decision":"review","method":"rule","rule_id":"brand.explicit-title.v1","evidence":{"field":"title","start":9,"end":16,"text":"Samsung"},"reason_codes":[]}
```

| Ответ | Действие оператора |
| --- | --- |
| `review` | проверить значение по выделенному evidence; score — эвристика, не вероятность |
| `abstain` | прочитать reason: отсутствие факта или конфликт; не заполнять догадкой |
| HTTP 422 / CLI `invalid_input` | исправить схему/типы своего ввода, затем повторить |

Полный сценарий, команды PowerShell, проверка manifest и отрицательные примеры:
[QUICKSTART](../../docs/QUICKSTART.md). Ответы и действия оператора:
[RESPONSES](../../docs/RESPONSES.md).

HTTP API:

```bash
.venv/bin/python -m goodsai.api
# GET http://127.0.0.1:8000/health
# POST http://127.0.0.1:8000/predict ; Swagger: /docs
```

## Проверка

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
.venv/bin/python scripts/release/external_acceptance.py --help
.venv/bin/python -m goodsai.demo --output-dir outputs/demo-first-run
.venv/bin/python scripts/release/build_release.py smoke --output-dir outputs/release/smoke-first
.venv/bin/python scripts/release/build_release.py verify --bundle outputs/release/smoke-first
```

На Windows используйте `.\.venv\Scripts\python.exe` и `$env:PYTHONUTF8='1'`.
Smoke проверяет упаковку на синтетике, а не качество реального каталога.
Исполняемые инструменты подготовки/оценки в `scripts/research/` нужны тестам
и воспроизведению; входные датасеты и приватные результаты в Git не входят.

## Документация и материалы сдачи

Подготовка выданных данных описана в [DATASET](../../docs/DATASET.md).
`inventory --profile text-only` требует только `skus.pkl` и `sku_desc.parquet`;
clicks обязательны только для `--profile analytics`. `prepare` использует
готовую доверенную Parquet-проекцию и проверенные SHA-256, не загружает pickle.
Оба инструмента запрещают перезапись существующих результатов.
Полный handoff подготовки с существующим frozen EVAL-002 аудитом:

```bash
.venv/bin/python scripts/research/prepare_dataset.py --inventory data/processed/source_inventory.json --split-audit outputs/evaluation/eval-002-20261019-final --output-dir data/processed/data001-next
```

Путь аудита зависит от вашего приватного окружения. Команда сохраняет прежние
группы и карантин; данные/reserve не публикуются, независимый test не создаётся.
Без повторной подготовки: замените `--output-dir ...` на `--verify data/processed/data001-next`.

- [Технический контракт](../../TECHNICAL_SPEC.md), [архитектура](../../docs/ARCHITECTURE.md).
- [Конфигурация](../../docs/CONFIGURATION.md), [production-пример](../../configs/production.example.json).
- [Эксплуатация](../../docs/RUNBOOK.md), [LLM: opt-in, бюджет, fallback](../../docs/LLM.md).
- [Общий verifier](../../docs/VERIFIER.md): evidence, нормализация, связь с товаром и причины отказа.
- [Оценка](../../docs/EVALUATION.md), [результаты и provenance](../../docs/RESULTS.md).
- Подготовка independent quality-пакета без открытия reserve:
  `.venv/bin/python scripts/research/quality_evidence.py prepare --output-dir outputs/evaluation/quality-plan-next`.
  Без human gold статус blocked, метрики N/A; сборка/verify по frozen hashes —
  в [протоколе оценки](../../docs/EVALUATION.md#подготовка-воспроизводимого-human-quality-пакета).
- [Silver-метрики](../../reports/metrics.md), [статистика прогона](../../reports/run_stats.json).
- [Checkpoint: EDA, метрики, PDF-презентация](../../docs/delivery/2026-10-19/README.md).
- [Сборка и проверка шести артефактов](../../docs/ARTIFACT_BUNDLE.md).

## Инструменты оператора и диагностики

- [Консоль словарей](../../docs/DICTIONARY_CONSOLE.md): `python -m goodsai.dictionary_app`
  на `127.0.0.1:8001`; draft → impact → review → owner publish/rollback,
  отдельные ключи ролей и явно выбранный профиль для следующего run.
- [Приоритет проверки](../../docs/REVIEW_PRIORITY.md): `python -m goodsai.review_priority --help`;
  severity/age, квоты старых/редких задач, объяснение порядка и audit сессий.
- [Дрейф](../../docs/DRIFT.md): `python -m goodsai.drift --help`; локальные агрегаты,
  frozen baseline, min support и hysteresis. Без reviewed labels F1 недоступен.
- [Exact cache](../../docs/EXACT_CACHE.md): аудит повторов без model calls,
  TTL/namespace и single-flight; cache включается отдельно.
- [Span selector](../../docs/SPAN_SELECTOR.md) и [source context planner](../../docs/CONTEXT_PLANNER.md)
  — экспериментальные opt-in режимы LLM, по умолчанию выключены.

Компоненты проверены на синтетике. Репрезентативные E1/E3/cache keep gates,
независимая validation, human UX benchmark и подключение к общей review-очереди
остаются отдельной приёмкой; измеренный выигрыш качества/времени не заявляется.

## Ограничения

По умолчанию две категории и `auto_accept` off; отдельный opt-in storage pilot
описан выше. Confidence — эвристика, независимая калибровка не завершена.
Development и silver-метрики не являются независимым human test.
Сравнительное качество LLM и encoder на реальном каталоге не подтверждено.
Реальные данные, gold, predictions, модели и секреты предоставляются отдельно
по согласованному процессу; в Git их нет.
