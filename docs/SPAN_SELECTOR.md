# Selector: span ID вместо свободного значения

Opt-in `GOODSAI_LLM_SPAN_SELECTOR=true` при включённом LLM. По умолчанию выключен.
Лимит `GOODSAI_LLM_SELECTOR_MAX_SPANS` — 512, допустимо 1–2048. Строгая политика:
недоступный или усечённый SpanIndex даёт `llm_selector_index_incomplete`, без
model call. Если полный исходный контекст не помещается в context budget,
возвращается `llm_context_budget_exceeded`; тихого усечения нет.

Provider получает доступные spans с field/raw offsets/text и JSON schema с enum
ID и null. Ответ: `{"attributes":[{"attribute":"brand","span_id":"<id>"}]}`.
Свободные value/quote/другие ключи отклоняются. Это **клиентская** проверка:
`server_constrained_decoding=false`, gateway получает обычный JSON mode.
Неизвестный, чужой и устаревший ID отклоняется.

Код разрешает ID на неизменённом source, нормализует только выбранную surface
(число+unit, memory pair, словарный alias, model name) и создаёт Candidate с
исходными field/start/end/text. Candidate проходит общий verifier на полном
оригинале. Неоднозначные значения остаются conflict/abstain, accepted остаётся
review с heuristic score. Формат публичного prediction v0.1 не меняется.

SpanIndex и selector versions, source identity, spans/schema и настройки входят
в exact-cache fingerprint. Cache хранит producer IDs; на hit ID разрешается
и проверяется заново. Переключение selector/free extraction даёт miss.

Перед экспериментом измерьте candidate-set recall существующим
`scripts/research/check_span_index.py` на разрешённом reference. Затем E1 #65:
та же frozen model/validation/normalizer/verifier, per-attribute/macro F1,
semantic FP, invalid/copy rejects, input/output tokens, latency и полная стоимость.
Недоказанный recall ≥98%, допуск F1 или экономия токенов не объявляются keep.
Независимая validation и E1 не заменяются synthetic tests; default route прежний.
