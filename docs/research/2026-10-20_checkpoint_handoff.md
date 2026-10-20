# #123 / #124 / #125: подготовка следующего прогона

Это handoff, не отчёт о новом качестве. Реальные измерения требуют существующих
приватных артефактов; исторические `reports/metrics.md` и `run_stats.json` не
перезаписываются. Independent acceptance #6/#38/#40 не выполнена этой работой.

## Подготовка без inference

Из чистого checkout, Python 3.12 и Git с историческим `f33e3fc`:

```bash
python scripts/research/prepare_checkpoint.py --candidate HEAD --output-dir outputs/checkpoint-20261020-preparation
```

Команда сохраняет private handoff #123 с ожидаемыми hashes из исторического
агрегата, план #124 и план #125. В планах `inference: not_run`, quality/cost N/A,
пустые поля фактической авторизации и глобального остатка. Секреты не принимаются.
Само наличие ключа API или дневного лимита не подтверждает допустимость пакета.

Frozen EVAL-006 manifest ожидается с SHA-256
`c325664d36afe2a9fd73217d9515ffefe81b11bafd7bc736d3b8484eea88d9f6`.
Исторический producer — `f33e3fcd1487a3d82f8ed684ebfaa56d8220f6e4`.
Это provenance прежнего результата, не свежие метрики. Handoff показывает все
ожидаемые hashes audit/catalog/input/exposure/protocol/reserve/traffic.

## #123: одна команда сравнения после получения артефактов

Пример для исходных private paths EVAL-006; пути заменяются только путями тех же
файлов с теми же hashes. Audit дополнительно проверяет исходные пути своей
policy: для перенесённого audit нужны доступные исходные файлы, а не новый split.

```bash
python scripts/research/compare_silver_baseline.py \
  --bundle outputs/evaluation/eval-006-silver-v3 \
  --audit outputs/evaluation/eval-002-20261019-final \
  --bundle-sha256 c325664d36afe2a9fd73217d9515ffefe81b11bafd7bc736d3b8484eea88d9f6 \
  --candidate HEAD \
  --source input=data/processed/e1/pilot.jsonl \
  --source catalog=outputs/eda/catalog.parquet \
  --source protocol=docs/research/silver_evaluation_protocol.md \
  --source reserve=data/gold/e1/m2/v2/test_reserve.blank.jsonl \
  --source exposure_0=data/gold/e1/tasks.jsonl \
  --source exposure_1=data/gold/e1/ai/full.annotations.v4.jsonl \
  --source exposure_2=data/gold/e1/m2/v2/development.tasks.jsonl \
  --source exposure_3=outputs/evaluation/development-review-20261019-v2/development.tasks.jsonl \
  --source traffic=data/raw/query_clicks.parquet \
  --output-dir outputs/evaluation/eval-007-frozen-comparison
```

`catalog` здесь пример пути: нужен фактический файл с hash из handoff. При любом
несовпадении команда прекращает работу до inference. Новые exposure ledgers,
возникшие после подготовки, сначала сверяет ответственный за данные: их нельзя
замолчать или подменить новым разбиением ради результата. Проверка checksums не
доказывает полноту истории доступов. Reserve только хешируется; его карточки и
метки не интерпретируются и не передаются extractor.

До первого prediction пишется `freeze.json`: точные commits, schema/config,
evaluator/support/driver hashes, seed и фиксированный regression gate. Два
detached Git worktree используют общий frozen config, один Python interpreter и
один input. Окружение model-переменных очищено; внешних model-вызовов нет. Первый
и второй вызов идут в одном процессе каждого runtime; значения должны совпасть.
Cold здесь означает первый вызов процесса, не сброс дискового кеша ОС. RSS —
high-water mark процесса. Импорт/создание checkout не входит в extractor latency.
Нормализация effective config старого/нового runtime может различаться: оба hashes
показаны вместе с code hashes; запрошенные категории и reference остаются общими.

Результат: aggregate `metrics.md`/`run_stats.json`, private predictions/manifests,
private пары изменённых ответов без исходных текстов и output manifest с hashes.
Per-attribute/category, coverage, supported recall, unknown/conflict, macro,
rare/traffic/grouped CI вычисляет существующий silver evaluator. Любой new FP,
lost TP либо необработанная карточка блокирует рекомендацию; после реального
выявления регрессии нужен отдельный defect с анализом private пар и агрегатами.
Команда не публикует потенциально чувствительные сведения автоматически.

## #124: отбор до predictions

После handoff #5 можно добавить к подготовке:

```bash
python scripts/research/prepare_checkpoint.py --candidate HEAD \
  --train PRIVATE/train.jsonl --split PRIVATE/train.split.json \
  --traffic PRIVATE/train.traffic.json --min-support 30 \
  --output-dir outputs/checkpoint-with-train-proposal
```

Проверяются существующие строгие форматы `learn_categories`, disjoint SKU и
hash train. Отбор: исключить default категории, минимум 30 train-карточек,
затем traffic/support по убыванию и category ID для разрешения равенства. Первые
три фиксируются предложением. Недостаток категорий явно отражается; замена на
успешные predictions запрещена. Нынешний EVAL-006 train handoff содержит только
две прежние категории и сам по себе не удовлетворяет пилоту новых категорий.

До inference остаются #10/#5/#44, family/source hashes и решение владельца по
реальным названиям, обязательным полям, mapping/units, разнообразию атрибутов и
ноутбукам. Скрипт не может утвердить эти решения. Затем существующий
`python -m goodsai.learn_categories` строит private registry; составляется
отдельный opt-in profile и выполняются existing CLI/API и E1 checks. Default
profile не меняется. Catalog agreement и human quality публикуются раздельно.

## #125: существующие adapters, общий screening

Берётся frozen #123 и исходный `llm_screening.input.jsonl`, одинаковый для всех
режимов, с ровно теми же reference/evaluator/schema/seed. До запуска фиксируются
actual Git/config/model artifact hashes, routing, cache cold/warm, token/deadline
лимиты, общий ledger и разрешение пакета/расходов. Цены из предоставленного
владельцем скриншота: `openai/gpt-oss-120b`, 15.86/61 RUB за миллион input/output
tokens. Это плановые цены, не измеренный расход и не актуальный остаток.

Используются существующие `goodsai.cli` / `goodsai.llm` /
`goodsai.experimental_gliner`, новый adapter не нужен. GLiNER artifact сначала
проверяется `validate_artifact`; наличие файлов не доказывает успешный запуск.
Combined не реализован и не заявляется. У всех фактических predictions должен
быть manifest с input/config/output hashes. Existing `run_silver_evaluation.py
--candidate llm=PRIVATE/predictions.jsonl --candidate gliner=PRIVATE/predictions.jsonl`
сопоставляет их с paired rules на том же full/screening input.

Добавлены per-attribute/category и slices кандидатов, actual producer hashes,
RSS/resources и парные new TP/new FP/lost TP (не только net F1). Private changed
pairs сохраняются отдельно. New FP/lost TP блокируют рекомендацию. Окончательное
keep требует положительного new TP, отсутствия регрессий, проверенного model
artifact, фактического usage/cost и воспроизводимости. Unknown остаётся N/A.
Непроведённый вариант — not_run, LLM без calls/cache hits — route_not_exercised;
budget-limited прогон раскрывает достигнутый объём, отказы и неотправленные строки.

Подготовка, private планы, доступы и полные predictions не включаются в Gitea.
Код остаётся воспроизводимым, внутренний handoff — только в GitHub.
