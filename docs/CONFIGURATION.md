# Конфигурация runtime — CONF-001 / CONF-002

Для opt-in оценки конкретного кандидата доступна
[конфигурация confidence](CONFIDENCE.md): `fixed-v1` (default), исторический
`context-v1` и обучаемый advisory `learned-v1`. Последний требует полной
проверенной model JSON в `runtime.confidence.model`; используйте генератор
`python -m goodsai.confidence --model ... --model-sha256 ... --output ...`.
Он не меняет категории/значения/decisions и не включает новые auto_accept.
При смене extraction profile/source fingerprint модель отклоняется до старта;
при неизвестном scope применяется прежний fixed score.

Полный профиль по умолчанию — `src/goodsai/baseline.json`. `schema_version=0.1`
задаёт прежний контракт карточки и предсказания; отдельный `config_version=1`
задаёт структуру настроек (v2 дополнительно поддерживает registry). Конфигурация не включает LLM, не меняет
единицы, решения, категории или значения scores по умолчанию. Opt-in
LLM-fallback (LLM-003) включается только флагом `--llm` или
`GOODSAI_LLM_ENABLED=1` и проверяет ответы по тем же `numeric_bounds` и
`rule_limits`, что и правила.

## Использование

Из корня проекта скопируйте полный профиль в новый файл и измените нужные поля:

```bash
mkdir -p configs
cp src/goodsai/baseline.json configs/local.json

.venv/bin/python -m goodsai.cli --config configs/local.json predict \
  --input src/goodsai/examples/synthetic/products.jsonl \
  --output outputs/config-check/predictions.jsonl

.venv/bin/python -m goodsai.api --config configs/local.json --host 127.0.0.1 --port 8000
```

В CLI `--config` указывается **перед** подкомандой `predict`/`evaluate`.
Без `--config` используется пакетный профиль. В Python:

```python
from goodsai.contracts import load_config
from goodsai.verify import Extractor
from goodsai.api import create_app

config = load_config("configs/local.json")
extractor = Extractor(config)
app = create_app("configs/local.json")
```

Явно заданный файл является полным профилем, а не overlay. Опечатки, пропущенные
обязательные секции, неизвестные атрибуты/профили, неоднозначные aliases, неверные
типы, NaN/Infinity, повторные JSON-ключи и некорректные диапазоны останавливают
запуск. Ошибка конфигурации обнаруживается до публикации predictions или запуска
HTTP-сервера. Окружение и файлы с ключами не читаются как конфиг автоматически.

## Поля

| Секция | Назначение |
| --- | --- |
| `config_version` | Версия формата настроек, сейчас строка `1` |
| `categories` | Упорядоченные запрашиваемые атрибуты по category ID |
| `category_profiles` | Связь ID с семейством существующих правил: `smartphone` или `kettle` |
| `numeric_bounds` | Положительные `[min, max]` в канонических единицах для шести числовых атрибутов |
| `rule_scores` | Heuristic scores для brand, color, model, memory_pair, memory_context и quantity |
| `rule_limits` | Размеры контекстных окон и отдельные ограничения записи RAM/ROM |
| `runtime.api` | Размер HTTP body, concurrency uvicorn и keep-alive timeout |
| `runtime.llm_enabled` | Только `false`: зарезервировано; конфигурация не включает LLM-fallback, он включается флагом `--llm` / `GOODSAI_LLM_ENABLED=1` (см. [LLM](LLM.md)) |
| `runtime.auto_accept_enabled` | Default `false`; `true` только с явной политикой storage-пилота |
| `runtime.auto_accept` | Опциональный `storage-pilot-97-v1` с target_precision `[0.97,1]`; [scope и запуск](STORAGE_PILOT.md) |
| `runtime.auto_accept_policies` | Политика решения для каждой пары category × attribute: `review` или аудированная политика именно этой ячейки (сейчас только `761/storage_gb` → `storage-pilot-97-v1`). См. «Матрица auto_accept по категориям» ниже |
| `runtime.auto_accept_trial` | Только пробный профиль CONF-008: `silver-trial-v1` и targets `[0.85,1]` для 6 ячеек с catalog-silver evidence; [AUTO_ACCEPT_TRIAL](AUTO_ACCEPT_TRIAL.md) |
| `runtime.review_threshold` | Только `null`: произвольный порог для heuristic score не применяется |
| `runtime.llm` | Полные не-секретные настройки opt-in LLM: model, timeout, retries, budgets, cache, цены |
| `brands`, `colors` и дополнительные словари | Существующие aliases, subbrands и модификаторы evidence |

Числа в `numeric_bounds` проверяются и при извлечении, и в общем candidate/output
verifier. Слишком большое значение даёт отсутствие кандидата; изменение границ
не приводит к внутренней ошибке всего batch. Scores находятся в `[0, 1]` и не
становятся вероятностями; по умолчанию найденный кандидат получает `review`.

`runtime.api.max_body_bytes`, `limit_concurrency` и `timeout_keep_alive_seconds`
должны быть положительными целыми. Body limit действует внутри приложения,
concurrency/keep-alive — при запуске через `python -m goodsai.api`. При запуске
приложения через сторонний ASGI-сервер параметры сервера задаёт его владелец.

## Инвентаризация и границы задачи

Из кода перенесены прежние значения:

- `normalize.py`: диапазоны шести числовых атрибутов;
- `rules.py`: scores `0.85`, `0.75`, `0.8`; окна поиска и контекста; RAM/ROM limits;
- `api.py`: body `131072` bytes, concurrency `32`, keep-alive `5` seconds;
- `rules.py`/`model_rules.py`: выбор семейства правил теперь использует
  `category_profiles`, а не сравнение category ID в orchestration-коде.

Число `1000` в переводе ml→L/kW→W — определение единицы, а не настраиваемый порог.
Грамматика модели, регулярные выражения, скрытые HTML-теги и canonical unit names
остаются кодом технического контракта. Новые алгоритмы, единицы и типы атрибутов
по-прежнему требуют реализации и отдельного согласования. В исходном CONF-001
model ID задавался отдельно. CONF-002 добавляет `runtime.llm.model` с
переопределением через `GOODSAI_LLM_MODEL` / `--llm-model`; encoder в основном inference нет.

Новый category ID можно привязать к существующему семейству и подмножеству его
атрибутов без изменения orchestration. Это не означает поддержку произвольного
нового типа товара. Изменение production-категорий, границ и scores согласует
архитектор; для него нужны версия профиля и regression/evaluation evidence.
CONF-001 сохраняет прежние production-параметры.

## Совместимость и воспроизводимость

Старые JSON-профили без `config_version` явно мигрируются в v1: к прежним словарям
и схемам добавляются текущие default-параметры. Это поддерживает legacy категории
`761`/`482`. Для других ID нужен полный v1-профиль с `category_profiles`.
Частично заполненный v1-профиль не получает недостающие настройки молча.
Исключение совместимости CONF-002: у прежнего v1/v2 без `runtime.llm` и/или
`runtime.review_threshold` эти новые поля дополняются пакетными defaults и `null`.
Если секция `runtime.llm` уже указана, она обязана быть полной: неизвестные и
пропущенные ключи отклоняются. Версия карточки/предсказания остаётся `0.1`.

Исследовательский ключ `experiment_ablation=disable_model_generation_only`
сохранён для существующего offline A/B/C-инструмента. Он не является новым
публичным model router и сам по себе ничего не включает.

Manifest уже содержит `config_sha256`: он рассчитывается по **эффективному**
валидированному профилю, включая параметры после legacy migration. Смена scores,
окон или API limits меняет hash и run ID. `code_sha256` также изменяется из-за
реализации CONF-001. Поэтому идентификаторы новых запусков отличаются от старых,
даже когда извлечённые значения/evidence/решения совпадают. Старые frozen bundles
остаются связанными со своими producer SHA; их отчёты не перезаписываются.

## Проверки

```bash
.venv/bin/python -m unittest discover -s tests -p test_config.py -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Новые проверки используют только синтетику: применение scores/bounds/windows,
ошибки конфига до output/listen, legacy migration, reusable category profile,
config hash в manifest и CLI/API parity с одним внешним профилем. Они не
измеряют precision/recall на реальных товарах. Реальные данные, test reserve,
внешние модели и VM в CONF-001 не используются.

## Opt-in v2 registry

[DONE — feature candidate] Помимо полного v1 принимается v2 с обязательным
`category_registry` версии 1 и `category_profiles[id]="learned"`. Порядок выдачи задаётся списком
config.categories; множество атрибутов должно точно совпадать с registry. Неизвестные поля,
невалидные словари/единицы и недостаточно поддержанные templates отклоняются.
Default baseline остаётся v1. Контракт, команды и ограничения:
[CATEGORY_REGISTRY](CATEGORY_REGISTRY.md). Это не полная CONF-002, не
калибровка и не подтверждение качества новых категорий.

## CONF-002: единый resolver и production-пример

Для CLI и API работает один `goodsai.policy.resolve_runtime_policy`:

1. Пакетный `goodsai/baseline.json` либо полный явно выбранный `--config`.
2. Разрешённые переменные `GOODSAI_LLM_*` (таблица ниже).
3. Явно переданные CLI-флаги. Отсутствующий флаг не затирает профиль; `0` и
   `false` являются значениями, а не отсутствием настройки.

Это совместимое расширение существующего loader, без второго файла LLM-конфига.
Отдельный формат/overlay потребовал бы ещё одной миграции и правил объединения;
дублирование настроек в CLI и API оставляло бы текущие расхождения.

LLM включается только через `predict --llm` либо `GOODSAI_LLM_ENABLED=1` в API.
Переменная `ENABLED` сама по себе не включает CLI; `llm-trace` — явный opt-in,
который ограничивает `max_calls` до `min(1, configured_limit)`, не повышая нулевой
бюджет. Поле профиля `runtime.llm_enabled` остаётся зарезервированным `false`.
Boolean env принимает `0/1/false/true` без учёта регистра. `.env` автоматически
не загружается, никакие model calls при чтении профиля не выполняются.

| Поле `runtime.llm` | Env | CLI `predict` | Пакетный default |
| --- | --- | --- | --- |
| `model` | `GOODSAI_LLM_MODEL` | `--llm-model` | `null`; при opt-in обязателен |
| `max_calls` | `GOODSAI_LLM_MAX_CALLS` | `--llm-max-calls` | 100 |
| `daily_max_calls` | `GOODSAI_LLM_DAILY_MAX_CALLS` | `--llm-daily-max-calls` | 300 физических HTTP-попыток в сутки |
| `timeout_seconds` | `GOODSAI_LLM_TIMEOUT` | `--llm-timeout` | 60 |
| `max_attempts` | `GOODSAI_LLM_ATTEMPTS` | `--llm-attempts` | 3 |
| `max_tokens` | `GOODSAI_LLM_MAX_TOKENS` | `--llm-max-tokens` | 2048 |
| `concurrency` | `GOODSAI_LLM_CONCURRENCY` | `--llm-concurrency` | 2 |
| `circuit_breaker` | `GOODSAI_LLM_CIRCUIT_BREAKER` | `--llm-circuit-breaker` | 5 |
| `json_mode` | `GOODSAI_LLM_JSON_MODE` | `--llm-json-mode` / `--no-llm-json-mode` | false |
| `price_input_per_1k` | `GOODSAI_LLM_PRICE_INPUT_PER_1K` | `--llm-price-input-per-1k` | null |
| `price_output_per_1k` | `GOODSAI_LLM_PRICE_OUTPUT_PER_1K` | `--llm-price-output-per-1k` | null |
| `cache_dir` | `GOODSAI_LLM_CACHE_DIR` | `--llm-cache-dir` | null |
| `budget_ledger` | `GOODSAI_LLM_BUDGET_FILE` | `--llm-budget-file` | outputs/llm-budget/ledger.json |
| `request_deadline_seconds` | `GOODSAI_LLM_REQUEST_DEADLINE` | `--llm-deadline` | 120 |
| `max_response_bytes` | `GOODSAI_LLM_MAX_RESPONSE_BYTES` | `--llm-max-response-bytes` | 1048576 |
| `max_proposals` | `GOODSAI_LLM_MAX_PROPOSALS` | `--llm-max-proposals` | 32 |

Указанные цены — за 1000 токенов, в одной выбранной единице стоимости; без обеих
цен cost остаётся N/A. Unknown `GOODSAI_LLM_*` и неизвестные ключи JSON,
неверные типы/диапазоны, NaN/Infinity и дубликаты ключей дают ошибку до
output/listen, включая выключенный LLM. Значения env не печатаются в ошибках.
Base URL и ключ разрешены только в `GOODSAI_LLM_BASE_URL` / `GOODSAI_LLM_API_KEY`:
они не входят в профиль, effective policy и hashes. Неизвестные параметры не
игнорируются. Модель обязательна только при opt-in; отсутствие ключа сохраняет
прежний fallback `llm_missing_key`, а не включает другой провайдер.

Полный безопасный профиль: [configs/production.example.json](../configs/production.example.json).
Он сохраняет категории, scores, ограничения и выключенный маршрут; не содержит
ключа, URL, реальных данных или придуманной цены. После создания своего JSONL
по README:

```bash
.venv/bin/python -m goodsai.cli --config configs/production.example.json predict --input outputs/my-card.jsonl --output outputs/config-predictions.jsonl
.venv/bin/python -m goodsai.api --config configs/production.example.json --host 0.0.0.0 --port 8000
```

В PowerShell замените executable на `.\.venv\Scripts\python.exe`. Для opt-in
задайте разрешённый model ID в профиле или env, секреты — в окружении VM,
добавьте CLI `--llm` либо API `GOODSAI_LLM_ENABLED=1`. Новая конфигурация
читается при запуске; горячая перезагрузка не предусмотрена. CLI/API требуют
общий journal при opt-in; `budget_ledger=null` тогда отклоняется. Низкоуровневый
`LLMSettings` сохраняет прежнюю возможность `None` для изолированных library tests;
это не способ запуска production CLI/API без дневного журнала.

## Решения, audit и пределы

Для heuristic score нет откалиброванного порога: `runtime.review_threshold=null`,
`runtime.auto_accept_enabled=false` — политика по умолчанию.
Любой числовой review threshold и голый флаг auto-accept без политики отклоняются.
Кандидат с evidence проходит verifier и получает `review`; отсутствие/конфликт
остаётся `abstain`. Ни scores, ни единицы, ни result v0.1 не изменены.
Числовую политику принятия можно добавить только после отдельного решения
архитектора и калибровки; наличие ключа `review_threshold` её не реализует.

Согласованное Владиславом 22.10.2026 исключение: [CONF-005 storage pilot](STORAGE_PILOT.md).
Оно допускает opt-in auto_accept только для двух проверенных форм storage_gb
смартфонов. Цель precision 97% выбрана после аудита, confidence остаётся heuristic;
пилот не завершает независимую калибровку и не меняет default config.

### Матрица auto_accept по категориям (CONF-007)

`runtime.auto_accept_policies` перечисляет все настроенные категории и их
атрибуты. Значение ячейки — `review` либо политика, аудит которой проведён
именно для этой пары category × attribute. Штатный профиль:

```json
"auto_accept_policies": {
  "761": {"brand": "review", "model": "review", "storage_gb": "storage-pilot-97-v1",
          "ram_gb": "review", "screen_inches": "review", "battery_mah": "review", "color": "review"},
  "482": {"brand": "review", "model": "review", "capacity_l": "review", "power_w": "review", "color": "review"}
}
```

Ячейка только привязывает политику; включает её по-прежнему
`runtime.auto_accept_enabled=true` вместе с `runtime.auto_accept`. Поэтому по
умолчанию auto_accept выключен во всех категориях. Правила валидации:

- политика в ячейке без завершённого аудита (любой атрибут чайника 482, любое
  поле смартфона кроме `storage_gb`, неизвестная версия) отклоняется до inference;
- `auto_accept_enabled=true` без ни одной привязанной ячейки отклоняется;
- `storage_gb: "review"` при выключенном флаге — штатный способ закрепить
  отказ от пилота в профиле;
- отсутствующая ячейка и категории, добавленные registry, работают как `review`;
- профиль без секции (созданный до CONF-007) получает штатную матрицу и ведёт
  себя как раньше.

Эффективная матрица по всем категориям входит в `runtime_policy` (и его hash)
и в ответ `/health` как `auto_accept_policies`. Новая ячейка появляется только
после отдельного аудита (CONF-006), решения архитектора и записи в
`AUDITED_POLICIES` в `src/goodsai/storage_acceptance.py`.

Пробная ветка CONF-008 дополнительно разрешает в шести ячейках значение
`silver-trial-v1` (761 ram_gb/battery_mah/color/brand, 482 brand/color) вместе
с `runtime.auto_accept_trial`; это catalog-silver проба, не аудит —
см. [AUTO_ACCEPT_TRIAL](AUTO_ACCEPT_TRIAL.md).

Manifest содержит:

- `config_sha256` — по-прежнему hash валидированного базового профиля;
- `runtime_policy` и `runtime_policy_sha256` — фактически разрешённые настройки,
  включая enable, цены, пути cache/journal и фиксированную политику решений;
- `effective_config={profile,runtime_policy}` и `effective_config_sha256` —
  снимок профиля и применённых overrides, без credentials.

Batch run ID учитывает code hash, вход и effective config hash. Изменение timeout,
бюджета или цен отражается в provenance; смена ключа не меняет policy hash.
Полные settings включены в manifest и при rules-only запуске. У API те же
hashes доступны в `/health`; сам prediction сохраняет прежний временный run ID,
а состояние приложения содержит `goodsai_runtime`. Это не новый официальный
API организаторов. Старые predictions/reports не перезаписываются; frozen
артефакты проверяются со своим producer SHA, новые идентификаторы отличаются.

CONF-002 конфигурирует существующие возможности. Byte/depth/proposal limits,
общий deadline и бюджет физических HTTP attempts остаются [#100](https://github.com/CRUDoshleps/GoodsAI/issues/100).
Текущие `max_calls`/daily ledger считают логические операции; retries отражаются
отдельно и не объявляются полностью ограниченными этими счётчиками.

Проверка дополнения (синтетика, без внешних API):

```bash
.venv/bin/python -m unittest discover -s tests -p test_runtime_policy.py -v
```

12 tests проверяют миграцию, precedence, fail-fast, запрет auto_accept, отсутствие
секретов в metadata, CLI/API policy/hash parity, сохранение прежней пары при
ошибке, нулевой trace budget и настоящий CLI/socket API с production-примером.
Каталоговое качество и прирост баллов этим не измеряются.
