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

## Фактически выполнено после поручения создать новую выборку

Владелец попросил самостоятельно создать недостающий набор, затем явно разрешил
расходы шлюза. Исходный historical bundle не объявляется восстановленным.
Существующие `goodsai-audit-20261019` projection/split/family metadata на VM
использованы без изменения исходных файлов. Повторный полный EDA не выполнялся.
Новый audit сохраняет исходное разбиение и карантинирует обнаруженные crossings;
зафиксированы четыре прежних exposure источника (E1 tasks, audit-family dev tasks,
audit-input и batch-input). Exposure inventory не доказывает полноту истории.

Результаты и точные hashes: [public measured report](../../reports/checkpoint_20261020.md).
Private корень на VM: `~/goodsai-checkpoint-20261020-e73a2a0/outputs/evaluation/`:

- `eval-002-20261020-rebuilt`: audit; 10324 исходных metadata rows,
  6980 quarantined, development 2171 / validation 846 / test_reserved 327 eligible;
- `eval-006-silver-20261020-rebuilt`: 2974 input/reference rows, 1250 families,
  40 metadata-only reserve, manifest SHA `fbd0dfd438226f09cdbab8e3bb2d618a215fefb729189094f48fed544777fdae`;
- `eval-007-20261020-rebuilt-comparison`: freeze, f33e3fc/1c64463 cold/warm,
  private error transitions, output manifest; regressions recorded in #137;
- `eval-008-brand-20261020`: existing artifact verified; cold/warm 55 local calls,
  48 added brands, no model failure; tokenizer warnings recorded without retuning;
- `eval-008-llm-20261020`: first bounded batch 100 gateway attempts;
- `eval-008-llm-complete-20261020`: verified immutable cache copy + 23 fresh
  attempts, no remaining budget skips; warm cache adds zero fresh requests;
- `eval-008-comparison-20261020`: same 200 preselected development cards for
  actual rules/LLM/brand, paired deltas, per-attribute/category/rare and usage.

Методы, thresholds и verifier не менялись после predictions. Бюджетное completion
выполнялось до просмотра quality deltas, только по счётчику неотправленных строк.
Итоговый acquisition cost включает первый и второй batch: 2.55063692 RUB,
123 attempts, 45572 input + 29965 output tokens. Счёт шлюза не сверялся. Latency
seeded completion не называется полностью cold latency; этапы показаны отдельно.

Команды actual wrappers (из корня такого checkout; новые output-dir для повторов):

```bash
python scripts/research/run_brand_screening.py --bundle outputs/evaluation/eval-006-silver-20261020-rebuilt --baseline-run outputs/evaluation/eval-007-20261020-rebuilt-comparison --artifact PRIVATE/verified-gliner-assets --output-dir outputs/evaluation/brand-repeat
python scripts/research/run_llm_screening.py --bundle outputs/evaluation/eval-006-silver-20261020-rebuilt --baseline-run outputs/evaluation/eval-007-20261020-rebuilt-comparison --budget-ledger PRIVATE/shared-ledger.json --authorized-packet-sha256 ceb5a79971afbff3a26858351ecc3dd25d68ee6737609b8fc0de434962830d1b --authorization-record OWNER_APPROVAL_REFERENCE --max-calls 100 --spend-limit-rub 30 --output-dir outputs/evaluation/llm-first-repeat
python scripts/research/run_llm_screening.py --bundle outputs/evaluation/eval-006-silver-20261020-rebuilt --baseline-run outputs/evaluation/eval-007-20261020-rebuilt-comparison --budget-ledger PRIVATE/shared-ledger.json --authorized-packet-sha256 ceb5a79971afbff3a26858351ecc3dd25d68ee6737609b8fc0de434962830d1b --authorization-record OWNER_APPROVAL_REFERENCE --max-calls 23 --spend-limit-rub 8 --cache-seed-run outputs/evaluation/llm-first-repeat --output-dir outputs/evaluation/llm-complete-repeat
python scripts/research/run_silver_evaluation.py --bundle outputs/evaluation/eval-006-silver-20261020-rebuilt --output-dir outputs/evaluation/model-comparison-repeat --candidate llm=outputs/evaluation/llm-complete-repeat/cold.jsonl --candidate gliner=outputs/evaluation/brand-repeat/cold.jsonl
```

Gateway credentials — только `GOODSAI_LLM_BASE_URL` / `GOODSAI_LLM_API_KEY` в
окружении. Shared ledger обязателен, 300/day; цена — за 1000 tokens в settings,
не за миллион. Replays требуют действующего разрешения и фактического остатка.
Cache TTL 3600 s: completion выполняется в том же окне; stale/missing entries
не считаются cache hits и могут привести к явно раскрытому budget-limited результату.

CONF-004 draft находится отдельно:
`~/goodsai-conf004-20261020-f0e4bc0/outputs/conf004-real-draft`.
Воспроизведение без inference и без фиктивного traffic:

```bash
python scripts/research/prepare_category_pilot.py --catalog PRIVATE/catalog_skus.parquet --profile PRIVATE/catalog_profile.json --audit PRIVATE/rebuilt-audit --max-per-category 300 --output-dir outputs/conf004-real-draft-repeat
```

Сохранены 900 train rows, прежние validation/test identities в split metadata,
provisional exact-title families и предложенные поля. Near-family/units/mandatory
fields/официальный контракт ещё требуют acceptance. Доступный clicks-файл с hash
`75eb3622…0a87a` не совпал с `f9bc052d…bb22`, поэтому в registry не подставлялись
ни новые counts без provenance, ни равные фиктивные traffic weights. Пилот новых
категорий остаётся BLOCKED; CLI/API inference и качество на них не заявлены.
