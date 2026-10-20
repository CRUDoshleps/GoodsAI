# Exact-request cache и аудит повторов

Включение: `--llm --llm-cache-dir outputs/llm-cache`; HTTP использует
`GOODSAI_LLM_CACHE_DIR`. Доступ к provider по-прежнему требует model/key,
разрешённых данных и общего budget ledger. По умолчанию cache не включён.

`GOODSAI_LLM_CACHE_NAMESPACE` разделяет tenants/data-access/provider namespaces.
При смене gateway или прав доступа задайте другой namespace. `GOODSAI_LLM_MODEL_REVISION`
записывает ожидаемую producer revision в ключ; это не подтверждение того, что
удалённый gateway закрепил revision. Для плавающего model действует
`GOODSAI_LLM_CACHE_TTL` (по умолчанию 3600 с, максимум сутки).

Ключ содержит exact title/description с границами полей, category/schema,
source flags, prompt/messages, generation settings, config hash, model/revision
и namespace. SKU исключён: provider его не получает. Любая правка исходного
текста, включая текст за лимитом отправляемого контекста, даёт miss.

Локально хранятся только producer proposals, timestamp и integrity hash.
Цитата относится к exact source identity ключа; offsets восстанавливаются
из оригинала при каждом replay. Решения, auto_accept, API key, endpoint и usage
не переиспользуются. Кэш содержит закрытый текст цитат: каталог должен быть
локальным, вне Git, с правами доступа владельца. Это не публичная telemetry.

Одинаковые активные запросы объединяются внутри процесса и OS-lock между
сотрудничающими процессами с общим cache directory. Ожидание ограничено request
deadline; сбой лидера будит ожидающих с причиной, а не пустым успешным ответом.
Недоступный/повреждённый cache даёт обычный inference. Каждый hit заново проходит
актуальные normalizer/verifier/decision. Budget/concurrency guard provider сохраняются.

Сначала аудит без model calls:

```bash
.venv/bin/python -m goodsai.request_cache --input outputs/approved-cards.jsonl --model checkpoint-name --namespace approved-development
```

Отчёт содержит eligible/unique requests и потенциально избежанные calls;
фактические calls/savings равны нулю. Тексты, SKU и fingerprints не выводятся.
Run manifest отдельно считает calls, attempts, tokens, cache_hits,
singleflight_hits и cache_seconds. Hit не списывает повторный usage; при
неизвестном тарифе cost=null. Сравнивайте без cache, cold и warm на одном
разрешённом frozen потоке; guard #59 требует измеренного сокращения calls ≥10%
и одинаковых финальных результатов. Synthetic regression подтверждает
механику, не репрезентативный keep и не финальное качество.
