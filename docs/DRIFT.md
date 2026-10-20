# Локальная диагностика дрейфа

`goodsai.drift` сравнивает агрегаты с frozen baseline. Не отправляет telemetry
наружу и не меняет route, thresholds извлечения, auto_accept или обучение.

```bash
.venv/bin/python -m goodsai.drift snapshot --input outputs/approved.jsonl --predictions outputs/predictions.jsonl --manifest outputs/predictions.manifest.json --output outputs/baseline.json
.venv/bin/python -m goodsai.drift compare --baseline outputs/baseline.json --current outputs/current.json --policy outputs/drift-policy.json --state outputs/drift-state.json
```

Для следующего окна повторите snapshot в новый current.json. Input/prediction
SKU и paired hashes проверяются до агрегирования. Frozen identity включает
schema/config/runtime policy/producer model+revision; несовместимость останавливает
сравнение, а не выдаётся за data drift. Для конфигурации вне baseline добавьте
`--config` на шаге snapshot. Источники должны быть локальными и разрешёнными.

Policy JSON задаётся явно: `min_support`, `rate_delta`, `js_threshold`,
`persistence`, необязательный `clear_ratio` (0.5). Минимальный support ≥20;
конкретные thresholds нужно заморозить на development/synthetic replay.
Например, тестовый профиль 20/0.15/0.2/2 проверяет механику; это не
универсальные production thresholds и не подтверждение false-alarm rate.

Сохраняются counts и знаменатели по category/attribute: unsupported, abstain,
review, conflict, evidence/provider rejects, доля LLM-результатов. Истинный
routing share берётся только из manifest counters с совпадающим cards_seen;
без этих counters он недоступен, а не подменяется долей принятых LLM-значений.
Категории вне allowlist сгруппированы в __other__; lengths — фиксированная
гистограмма. Тексты, evidence, SKU, произвольные reason strings и credentials
не входят в агрегат. Precision/recall/F1 без reviewed labels — null.

Rates показывают baseline/current numerator/denominator и консервативный
95% Wilson difference interval. Изменения распределений категорий/длин измеряет
JS divergence. Малые cohorts подавляются. Alert требует persistence разных
окон, содержит affected slice, baseline, interval/measure и ручное действие.
Duplicate window не продвигает streak; active alert не дублируется до recovery
ниже hysteresis threshold. State bound к hashes baseline/policy и обновляется
под OS-lock атомарно. Не удаляйте state ради подавления сигнала.

В synthetic replay проверены stationary, unsupported/category shift, рост
abstain, малые группы, policy mismatch, повтор/восстановление и redaction.
Репрезентативный false-alarm rate/задержка и эксплуатационная интеграция OPS-002
не измерены. Сигнал — повод для audit sample, не доказательство падения качества.
