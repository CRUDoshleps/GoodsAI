# Эксперимент: auto_accept для всех 12 полей (all-fields-unaudited-v1)

**Только ветка `exp/all-fields-auto-accept`. Не для `main`, сдачи, ВМ и production.**

## Что делает

Opt-in профиль включает `auto_accept` для **каждого** настроенного поля:
761 brand, model, storage_gb, ram_gb, screen_inches, battery_mah, color и
482 brand, model, capacity_l, power_w, color. Порога по точности нет: любое
найденное правилами значение без `reason_codes` принимается автоматически.
Значения, evidence и score не меняются, меняется только `decision`.
`abstain` и конфликты остаются `abstain`. LLM-кандидаты не принимаются.

## Чем отличается от остальных политик

| Политика | Основание | Порог |
| --- | --- | --- |
| `storage-pilot-97-v1` (main) | human audit 145/145 | нижняя граница ≥ 0,97 |
| `silver-trial-v1` (#172, draft) | catalog-silver TP/FP | граница ≥ target, target ≥ 0,85 |
| `all-fields-unaudited-v1` (эта ветка) | нет | нет |

По catalog-silver (`reports/run_stats.json`, f33e3fc) это значит автопринятие
полей с нижней границей точности 0,47 (761 model) и без reference вообще
(482 capacity_l). Ожидаемо в каталог уйдут ошибки, которые сейчас ловит review.

## Запуск

```bash
python -m goodsai.experiment_acceptance --output outputs/all-fields.json
python -m goodsai --config outputs/all-fields.json predict --input /private/cards.jsonl --output outputs/all-fields-predictions.jsonl
```

Профиль требует `runtime.auto_accept_experiment = {"policy_version":
"all-fields-unaudited-v1", "acknowledge_unaudited": true}`; без явного
подтверждения конфиг отклоняется. `/health` и manifest показывают
`audited=false`, `production_safe=false`, `evidence_threshold=null`.
Изменённый extraction profile отклоняется. Откат — штатный профиль.

## Для чего полезен

Оценить верхнюю границу автоматизации: сколько review уйдёт при «принимать всё»,
и сравнить на том же наборе с `storage-pilot-97-v1` и `silver-trial-v1`
(`decision_counts` в manifest). Это измерение нагрузки, не качества.
