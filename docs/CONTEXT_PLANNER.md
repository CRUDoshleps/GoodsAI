# Контекст из исходных блоков

Opt-in: `GOODSAI_LLM_CONTEXT_PLANNER=true` при явно включённом LLM. Бюджет
`GOODSAI_LLM_CONTEXT_MAX_CHARS` по умолчанию 16000, допустимо 128–262144.
Это лимит символов, не оценка токенов. По умолчанию прежний route сохранён.

`goodsai.context_planner.plan_context` выделяет title и целые предложения/HTML
блоки description с field/start/end/text в неизменённом оригинале. Пересказа нет.
Для numeric fields сохраняются все обнаруженные mentions и соседние блоки.
Неизвестная проза тоже сохраняется: отсутствие keyword не доказывает отсутствия
опровержения. Удаляются только явно перечисленные нейтральные заголовки.
Brand/model/неизвестная grammar, отрицание, совместимость, microSD, чужой объект,
межфразовая ссылка или несколько mentions переводят план в full-context fallback.
Если необходимый полный/отобранный контекст не помещается, model не вызывается:
поле сохраняет abstain с `llm_context_budget_exceeded`. Тихого усечения нет.

Provider получает только source_blocks и requested schema. Цитаты и semantic
relations проверяются на полном оригинале общим verifier. Версия planner,
политика и budget входят в producer fingerprint; изменение инвалидирует cache.
В manifest есть counts full/reduced/unavailable и original/selected chars;
provider tokens/attempts/cost учитываются прежними счётчиками, включая retries.

Тесты используют вымышленные карточки: HTML/raw offsets, отрицание, microSD,
чужой товар, конфликт и межфразовые ссылки. Тест на удаление нейтральных заголовков
не доказывает ≥25% экономии на репрезентативном long-text slice. E3 из #66
(размеченный support/contradictions, frozen model, recall interval, tokens/cost
включая fallback) остаётся необходимым для решения keep. Никакой общий выигрыш
качества или стоимости не заявляется; strict planner может часто выбирать full.
