# Конфигурация runtime — CONF-001

Полный профиль по умолчанию — `src/goodsai/baseline.json`. `schema_version=0.1`
задаёт прежний контракт карточки и предсказания; отдельный `config_version=1`
задаёт структуру настроек. Конфигурация не включает LLM, не меняет
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
| `runtime.auto_accept_enabled` | Только `false`: калибровка отсутствует |
| `brands`, `colors` и дополнительные словари | Существующие aliases, subbrands и модификаторы evidence |

Числа в `numeric_bounds` проверяются и при извлечении, и в общем candidate/output
verifier. Слишком большое значение даёт отсутствие кандидата; изменение границ
не приводит к внутренней ошибке всего batch. Scores находятся в `[0, 1]` и не
становятся вероятностями; найденный кандидат по-прежнему получает `review`.

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
по-прежнему требуют реализации и отдельного согласования. Model IDs не выносятся:
модель LLM-fallback задаётся флагом `--llm-model` / `GOODSAI_LLM_MODEL`, encoder в
inference нет; их интерфейс относится к LLM/ML-задачам.

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
