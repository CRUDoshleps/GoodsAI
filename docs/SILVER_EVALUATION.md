# EVAL-006: оценка по каталогу и offline-калибровка

Инструменты работают локально, без LLM-запросов и изменения runtime. Сохраняются
контракт 0.1, heuristic confidence и review/abstain. Каталог — приблизительный
эталон: отчёт измеряет согласованность с ним, а не независимое качество.

Протокол фиксируется до новых predictions:
[silver_evaluation_protocol.md](research/silver_evaluation_protocol.md).
Источник задачи — [EVAL-006 #91](https://github.com/CRUDoshleps/GoodsAI/issues/91).

## Подготовка данных

Из корня checkout, Python 3.12 с зависимостями проекта. Нужны существующий кеш
EDA, text-only pilot и проверенный EVAL-002 audit. Старые файлы не меняются;
output-dir должен быть новым и находиться в `outputs/`.

```bash
python scripts/research/prepare_silver_reference.py --audit outputs/evaluation/eval-002-20261019-final --exposure-source data/gold/e1/tasks.jsonl --exposure-source data/gold/e1/ai/full.annotations.v4.jsonl --exposure-source data/gold/e1/m2/v2/development.tasks.jsonl --exposure-source outputs/evaluation/development-review-20261019-v2/development.tasks.jsonl --traffic data/raw/query_clicks.parquet --output-dir outputs/evaluation/eval-006-silver-v3
```

Пути exposure-source — использованные в текущем локальном эксперименте.
При новых экспериментах добавить все новые exposure ledgers. Скрипт не
доказывает полноту истории наблюдений. Без traffic-файла убрать `--traffic`:
веса, top-30 и traffic-метрики будут N/A, не заменены частотой SKU.

Подготовка проверяет audit/source hashes и семейства; исключает quarantine,
test_reserved и защищённые семейства; исключает новые exposed validation-family.
Старый validation остаётся feedback. Development делится по hash family на
fit/calibration/diagnostic: это роли эксперимента, а не независимый test.

Приватные результаты:

- `input.jsonl`: только допустимые поля Product;
- `reference.jsonl`: catalog_silver с происхождением, unknown/conflict и support;
- `metadata.jsonl`: family, роль, seller/brand и traffic только для аналитики;
- `policy.json`, `manifest.json`: версии, config, hashes, исключения и охват;
- `support_review.blank.jsonl`: фиксированные S001… задания для проверки matcher;
- `llm_screening.input.jsonl`: до 200 development-карточек, одна на семейство,
  с чередованием категорий; выбор не использует predictions;
- `train.jsonl`, `train.split.json`, при наличии traffic — `train.traffic.json`:
  handoff для train-only registry Тимура. Только fit, без validation/test-текстов.

Резерв 40 карточек не открывается. Исходные split, gold и predictions сохраняются.
Top-30 по metadata не означает 30 runtime-схем. EDA-кеш не содержит params для
всех категорий; расширение реальной train-выгрузки требует отдельной подготовки,
без повторного полного EDA. Нынешний train handoff ограничен двумя категориями.

## Одна команда для отчёта

```bash
python scripts/research/run_silver_evaluation.py --bundle outputs/evaluation/eval-006-silver-v3 --output-dir outputs/evaluation/eval-006-baseline-v3
```

Команда выполняет rules prediction дважды, проверяет идентичность, считает
agreement P/R/F1, supported recall, coverage, unknown/conflict, macro/slices,
traffic-метрики и 95% grouped bootstrap CI. Затем запускает offline logistic +
Platt только при заранее установленном gate объёма/классов/групп.

`metrics.md` и `run_stats.json` — агрегаты для передачи release. Полные predictions,
пары ошибок, family counts, support задания и модель остаются приватными.
Manifest связывает hashes. В Git допустимы только проверенные агрегаты, код
и synthetic tests.

Unknown не считается absent/FP. Wrong known value даёт FP+FN. Каталожная ошибка
или различие коммерческого имени и технического кода могут дать mismatch.
Support matcher не использует extractor, но остаётся лексическим приближением;
его human-аудит ещё требуется. `unsupported` означает отсутствие совпадения
по matcher, не доказанное отсутствие факта в тексте.

Traffic — число строк наблюдений на SKU. CI ресемплирует семейства; при менее
20 групп N/A. Seller/brand crossings раскрываются, seller-disjoint не заявляется.
Малые seller-срезы агрегируются без публикации идентификаторов.

## Подключение результатов коллег

После готовности веток/PR получить predictions на frozen input или screening
subset. Реальные карточки нельзя посылать шлюзу без решения команды о данных
и бюджете. PR #90 существует как opt-in route; этот PR его не сливает.

```bash
python scripts/research/run_silver_evaluation.py --bundle outputs/evaluation/eval-006-silver-v3 --output-dir outputs/evaluation/eval-006-comparison-v1 --candidate llm=outputs/approved-llm-run/predictions.jsonl
```

Для другого конфига добавить `--candidate-config registry=path/config.json`.
Candidate manifest должен совпадать по input/config SHA. Для сравниваемых категорий
порядок обязательных полей должен сохраняться. Расширение вне этой выборки не
выдаётся за измеренный прирост. `control` — проверка воспроизводимости, не ML.
LLM без calls/cache hits получает `route_not_exercised`, не полноценный эксперимент.

Без prediction manifest варианты registry/gliner/llm имеют `not_run` с причиной.
Screening показывается со своим числом карточек и paired rules baseline.
Парные дельты используют одинаковые family draws. Calls/retries/tokens/cache/cost
берутся из provider manifest; нет цены/trace — N/A. Prompt/URL/key не копируются.

## Калибровка и приёмка

Offline scorer получает только inference-признаки. Unknown labels не становятся
отрицательными примерами. Fit/calibration/diagnostic disjoint по family.
Для обучаемого extractor нужны OOF candidates: автоматический fit этой версии
предназначен для необучаемого rules baseline.

Отчёт разделяет raw heuristic, fitted logistic и Platt. Улучшение относительно
heuristic не означает, что Platt лучше logistic. Истинная вероятность правильности
не доказана. Runtime confidence/decision не меняются, auto_accept запрещён.
Shadow 0,95 — заранее фиксированная иллюстрация, не подобранная runtime policy.

```bash
python -m unittest discover -s tests -p test_silver_evaluation.py -v
python -m unittest discover -s tests -v
```

Нужен review аналитика/архитектора, затем человеческий аудит support и независимая
оценка. EVAL-001/003/004/005 сохраняют блокеры. Сравнение новых методов ожидает
frozen артефактов коллег и разрешения на реальные вызовы.
