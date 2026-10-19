# LLM-003: evidence-first LLM fallback

Статус: `[DONE]` в ветке `llm/llm-003-evidence-first-fallback`, задача
[LLM-003 #25](https://github.com/CRUDoshleps/GoodsAI/issues/25) в REVIEW.
Маршрут включается только явно. Без флага CLI и API работают как раньше:
только правила, `llm_calls=0`, тот же формат manifest.

## Что делает

Правила всегда запускаются первыми. В LLM уходят только атрибуты карточки с
итогом `not_found_by_rules`, одним запросом на карточку. Найденные правилами
значения и конфликты (`conflicting_evidence`) модели не передаются и не
перезаписываются.

Ответ модели — предложение, а не результат. Значение принимается, только если:

1. ответ — JSON-объект `{"attributes":[{"attribute","value","quote"}]}` без
   других ключей;
2. атрибут был запрошен у модели;
3. `quote` дословно (с точностью до пробелов) есть в видимом тексте title или
   description;
4. значение выводится из цитаты тем же нормализатором, что у правил: число с
   единицей внутри цитаты (`5000 мА*ч` → `5000`, `500 мл` → `0.5`), цвет из
   справочника, бренд или модель как слово из цитаты;
5. перед значением нет признаков диапазона или отрицания (`до`, `от`, `не`,
   `без`), а бренд не стоит после `для` / `совместим`;
6. кандидат проходит `validate_candidate` (диапазоны, единицы, точный raw
   evidence) и строка — `validate_prediction`.

Принятое значение получает `method="llm"`, `decision="review"`,
`confidence_kind="heuristic"`, `confidence=0.6` и `rule_id="llm.llm-fill-v1"`.
`auto_accept` этот маршрут не создаёт. Score не является вероятностью.

Если модель предложила разные допустимые значения одного атрибута, итог —
`abstain` с `conflicting_llm_evidence`.

## Запуск

Endpoint, ключ и модель берутся только из окружения. Шаблон —
[`.env.example`](../.env.example); реальный `.env` в Git не попадает.

```bash
export GOODSAI_LLM_BASE_URL=<OpenAI-совместимый base URL шлюза, с /v1>
export GOODSAI_LLM_API_KEY=<ключ>
export GOODSAI_LLM_MODEL=<имя модели шлюза>

.venv/bin/python -m goodsai.cli predict \
  --input <внешний>.jsonl --output outputs/llm-run/predictions.jsonl \
  --llm --llm-max-calls 100 --llm-cache-dir outputs/llm-cache
```

| Флаг | По умолчанию | Назначение |
| --- | --- | --- |
| `--llm` | выключен | включить маршрут |
| `--llm-model` | `GOODSAI_LLM_MODEL` | имя модели; без него запуск завершается с кодом 2 |
| `--llm-max-calls` | 200 | жёсткий бюджет реальных вызовов за запуск |
| `--llm-cache-dir` | нет | точный кэш запросов; каталог вне Git |
| `--llm-timeout` | 60 с | timeout одного HTTP-запроса |
| `--llm-attempts` | 3 | попыток на запрос вместе с повторами (1–5) |
| `--llm-concurrency` | 2 | одновременных запросов к шлюзу |
| `--llm-price-input-per-1k`, `--llm-price-output-per-1k` | нет | цена за 1000 токенов; без цены стоимость `N/A` |
| `--llm-json-mode` | выключен | попросить `response_format=json_object` |

HTTP API: `GOODSAI_LLM_ENABLED=1`, `GOODSAI_LLM_MODEL`,
`GOODSAI_LLM_MAX_CALLS` (по умолчанию 200) плюс те же переменные endpoint и
ключа. `/health` тогда показывает модель, число вызовов, cache hits и причину
отключения, без URL и ключа. `run_id` ответа — `http-rules-llm-v0`.

`--llm-json-mode` только просит шлюз о JSON. Это не constrained decoding:
структура всегда проверяется на клиенте. Поддержку `response_format` у шлюза
хакатона нужно проверить отдельно.

## Отказы и причины

Сбой провайдера не меняет решений правил. Запрошенные атрибуты остаются
`abstain`, к `not_found_by_rules` добавляется одна причина:

| Причина | Когда | Повтор |
| --- | --- | --- |
| `llm_missing_key` | нет base URL или ключа | нет, маршрут отключается до конца запуска |
| `llm_auth_failed` | HTTP 401/403 | нет, маршрут отключается |
| `llm_rate_limited` | HTTP 429 после всех попыток | да, учитывается `Retry-After` (не больше 30 с) |
| `llm_server_error` | HTTP 5xx после всех попыток | да, пауза 1, 2, 4 с |
| `llm_timeout`, `llm_network_error` | timeout или сеть после всех попыток | да |
| `llm_http_error` | прочие HTTP 4xx | нет |
| `llm_malformed_response` / `llm_malformed_json` | ответ шлюза или модели не по схеме | нет |
| `llm_budget_exhausted` | исчерпан `--llm-max-calls` | вызов не выполняется |
| `llm_circuit_open` | 5 неудачных вызовов подряд | маршрут отключается до конца запуска |

Отклонённые предложения модели дают причину на атрибуте и счётчик в manifest:
`llm_quote_not_found`, `llm_value_not_in_quote`, `llm_value_not_in_schema`,
`llm_uncertain_context`, `llm_foreign_entity`, `llm_span_not_visible`,
`llm_failed_verification`, `llm_bad_types`; `llm_unknown_attribute` и
`llm_unknown_field` — только счётчики. Если модель ничего не нашла —
`llm_not_found`.

Тексты исключений провайдера, тело запроса и ответа в логи и manifest не
пишутся. После запуска с отключённым маршрутом CLI печатает в stderr одну строку
с причиной.

## Учёт в manifest

При `--llm` manifest получает `method_counts` и объект `llm`: модель, версия
промпта, лимиты, `cards_routed`, `calls`, `retries`, `cache_hits`, токены,
`cost` и `cost_status`, `accepted` по атрибутам, `rejected`, `failures`,
`disabled_reason`, время провайдера. Поле `llm_calls` равно реальным вызовам;
cache hit вызовом не считается. Настройки маршрута входят в `run_id`, поэтому
rules-only и LLM-запуски на одном входе различаются.

## Кэш

`--llm-cache-dir` хранит разобранные предложения модели под ключом SHA-256 от
полного запроса: сообщения, модель, версия промпта, параметры генерации и hash
конфигурации. Любое изменение текста, схемы, промпта или модели — промах.
Попадание в кэш снова проходит все проверки из раздела «Что делает»;
испорченная запись считается промахом. Записи содержат цитаты из карточек,
поэтому каталог кэша должен лежать вне Git (например, `outputs/`).

Объединение одновременных одинаковых запросов, TTL и аудит доли повторов —
`[PLAN]` в [LLM-004 #59](https://github.com/CRUDoshleps/GoodsAI/issues/59).

## Проверено и не проверено

- `[DONE]` 27 тестов `tests/test_llm.py` с поддельным провайдером: grounding,
  HTML offsets, отказы 429/502/timeout/401, бюджет, circuit breaker, кэш,
  CLI/API, отсутствие ключа и текста карточки в manifest. Сеть в тестах не
  используется.
- `[DONE]` Без `--llm` вывод и manifest прежние: полный набор тестов и demo 6/6.
- `[PLAN]` Реальный вызов шлюза не выполнялся: по условиям #25 он ждёт решения
  команды о политике данных и бюджете. После решения — один synthetic trace с
  моделью, кандидатом, результатом verifier и фактическим usage.
- `[HYPOTHESIS]` Маршрут поднимает recall на пропусках правил без потери
  precision. Проверка — сравнение rules и rules→LLM на frozen split после
  EVAL-001/EVAL-005; до этого прирост качества не заявляется.
