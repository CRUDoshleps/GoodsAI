# Ответы GoodsAI: что они значат и что делать оператору

DOCS-003 / [#101](https://github.com/CRUDoshleps/GoodsAI/issues/101).
Примеры взяты из прогона [QUICKSTART](QUICKSTART.md) на `7aec082`. Контракт —
schema `0.1`, одинаковый для CLI (`predictions.jsonl`) и HTTP (`/predict`).

## Строка ответа

Одна строка на каждую входную карточку. `status` определяет, есть ли атрибуты:

| `status` | Когда | `attributes` | Действие оператора |
| --- | --- | --- | --- |
| `processed` | категория поддерживается, вход валиден | все атрибуты схемы категории, в порядке схемы, каждый ровно один раз | проверить `review`, по `abstain` — см. причины ниже |
| `unsupported_category` | `category_id` не в схеме (штатно поддерживаются `761`, `482`) | `[]` | передать карточку в ручное заполнение или в профиль с этой категорией |
| `invalid_input` | строка нарушает text-only схему (CLI) | `[]`, плюс `input_line` и `reason_codes: ["invalid_text_only_input"]` | исправить строку: убрать лишние поля (`vendor`, `model`, `params`…), проверить типы |

В HTTP невалидный вход — не строка `invalid_input`, а ошибка 422 (см. ниже).

## Атрибут

Каждый атрибут — либо значение с доказательством, либо явный отказ.

```json
{"attribute":"capacity_l","value":"1.7","unit":"L","confidence":0.8,"confidence_kind":"heuristic","decision":"review","method":"rule","rule_id":"capacity_l.explicit.v1","evidence":{"field":"title","start":25,"end":30,"text":"1,7 л"},"reason_codes":[]}
```

```json
{"attribute":"storage_gb","value":null,"unit":null,"confidence":null,"confidence_kind":"heuristic","decision":"abstain","method":"rule","rule_id":null,"evidence":null,"reason_codes":["conflicting_evidence"]}
```

| Поле | Смысл |
| --- | --- |
| `value`, `unit` | каноническое значение (`"1.7"`, `"L"`); число в строке, единица по схеме атрибута |
| `decision` | `review` — найдено значение, нужно подтверждение; `abstain` — значения нет, `reason_codes` объясняет почему. `auto_accept` до калибровки не выдаётся |
| `confidence` | эвристический score источника (правила 0.75–0.85, LLM 0.6), **не вероятность** правильности |
| `method`, `rule_id` | откуда значение: `rule` и id правила, `llm` и версия промпта |
| `evidence` | поле (`title`/`description`), raw offsets `start`/`end` в исходной строке и точный текст `text`. В HTML offsets указывают в исходную строку с тегами, `text` совпадает с ней посимвольно |

Evidence доказывает, что текст есть в карточке, но не гарантирует, что значение
относится к нужному атрибуту — поэтому решение `review`.

## Причины `abstain` и действия

| Код | Значение | Что делать |
| --- | --- | --- |
| `not_found_by_rules` | правила не нашли подходящий фрагмент | если значение есть в тексте — заполнить вручную и сообщить пример (кандидат на правило); если нет — запросить у продавца |
| `conflicting_evidence` | в карточке несколько несовместимых значений (пример: `8/256GB` в title и «128 ГБ» в description) | выбрать верное значение по первоисточнику; конфликт часто означает ошибку продавца |
| `relation_*` | кандидат найден, но отклонён проверкой связи: `relation_accessory_product`, `relation_foreign_entity`, `relation_bundle_item`, `relation_other_object`, `relation_negated`, `relation_nonvisible_evidence`, `relation_name_token`, `relation_material_not_color`, `relation_unknown_color_modifier` | значение относится не к самому товару (аксессуар, совместимость, отрицание, цвет внутри названия). Проверить вручную, не копировать найденное слово автоматически. Подробно: [RELATION_VERIFIER](RELATION_VERIFIER.md) |

### Дополнительные причины при `--llm`

Добавляются к `not_found_by_rules`; решения правил не меняются.

| Код | Значение | Что делать |
| --- | --- | --- |
| `llm_skipped_no_signal` | в тексте нет формы, которую можно было бы подтвердить (числа с единицей, цвета из словаря), вызова не было | как `not_found_by_rules` |
| `llm_not_found` | модель не нашла значение | как `not_found_by_rules` |
| `llm_quote_not_found`, `llm_value_not_in_quote`, `llm_value_not_in_schema`, `llm_uncertain_context`, `llm_foreign_entity`, `llm_failed_verification`, `llm_bad_types` | предложение модели отклонено проверкой: цитаты нет в тексте, значение не выводится из цитаты, не из справочника, рядом отрицание/диапазон, чужой бренд | значение не записывать; при массовых отказах — сообщить LLM-владельцу |
| `conflicting_llm_evidence` | модель предложила несколько разных допустимых значений | выбрать вручную |
| `llm_missing_key`, `llm_auth_failed`, `llm_endpoint_not_allowed` | маршрут не настроен или запрещён политикой, вызов не делался | проверить переменные окружения VM; результат = rules-only |
| `llm_timeout`, `llm_rate_limited`, `llm_server_error`, `llm_network_error`, `llm_deadline_exceeded` | шлюз не ответил вовремя или ответил ошибкой после ограниченных повторов | повторить запуск позже; правила уже отработали |
| `llm_budget_exhausted`, `llm_daily_budget_exhausted`, `llm_budget_ledger_unavailable` | исчерпан бюджет запуска/суток или журнал бюджета недоступен | дождаться следующих суток (МСК) или явно поднять лимит запуска; журнал не удалять вручную |
| `llm_malformed_response`, `llm_malformed_json`, `llm_response_too_large`, `llm_too_many_proposals`, `llm_circuit_open` | ответ шлюза не по схеме или повторяющиеся сбои | результат = rules-only; сообщить LLM-владельцу |
| `llm_blocked_by_data_policy` | карточка помечена как закрытый test, в LLM не отправлялась | ничего, это защита |

Полный список и лимиты — в [LLM](LLM.md#отказы-и-причины).

## Ошибки HTTP API

Формат всегда `{"error":{"code":"…","message":"…"}}`; текст карточки и детали
исключения в ответ и логи не попадают. Фактические ответы прогона:

| HTTP | `code` | Пример `message` | Что делать |
| --- | --- | --- | --- |
| 400 | `invalid_json` | `Body must be a UTF-8 JSON object` | отправить один JSON-объект в UTF-8 |
| 413 | `request_too_large` | `Maximum request body is 128 KiB` (лимит из профиля) | сократить description или поднять лимит в профиле |
| 415 | `unsupported_media_type` | `Use application/json` | заголовок `Content-Type: application/json` |
| 422 | `invalid_product` | `Unknown input fields: text-only input must not contain targets or metadata` | убрать запрещённые поля, проверить обязательные `schema_version`, `sku_id`, `title` |
| 500 | `prediction_failed` | `Extraction failed` | внутренняя ошибка; повторить и сообщить команде, указав время запроса |
| 200 | — | `status: unsupported_category`, `attributes: []` | см. таблицу статусов |

## Exit codes CLI

| Exit | Значение |
| --- | --- |
| 0 | прогноз записан; строки `invalid_input`/`unsupported_category` не делают запуск ошибочным |
| 2 | ошибка запуска: нет входного файла, output совпадает с входом или лежит в `data/raw`, невалидный профиль, `--llm` без модели, output занят другим процессом. Сообщение — одна строка в stderr |
| 3 | только `llm-trace`: живой вызов не удался, причина в stderr |
