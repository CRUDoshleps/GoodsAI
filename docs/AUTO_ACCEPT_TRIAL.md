# CONF-008: пробный auto_accept для всех 12 полей с порогом (silver-trial-v1)

**Статус: пробная ветка, не для production.** Это opt-in профиль поверх
[матрицы CONF-007](CONFIGURATION.md#матрица-auto_accept-по-категориям-conf-007).
Штатный профиль не меняется: `auto_accept_enabled=false`, всё `review`/`abstain`.

## Какие поля и почему

Основание — сохранённое catalog-silver согласие правил с каталогом
(`reports/run_stats.json`, `slices.category_attribute`, producer `f33e3fc`,
3037 development-карточек / 1270 семейств). Для каждой ячейки посчитана
односторонняя нижняя 95%-граница Clopper–Pearson по TP/(TP+FP).

| Ячейка | TP / (TP+FP) | Нижняя граница | Target в пробном профиле |
| --- | ---: | ---: | ---: |
| 482 brand | 610 / 610 | 0,9951 | 0,99 |
| 761 ram_gb | 1581 / 1585 | 0,9942 | 0,99 |
| 761 battery_mah | 122 / 125 | 0,9391 | 0,93 |
| 761 color | 1138 / 1223 | 0,9173 | 0,91 |
| 761 brand | 1714 / 1870 | 0,9053 | 0,90 |
| 482 color | 136 / 147 | 0,8792 | 0,87 |
| 482 power_w | 97 / 106 | 0,8565 | 0,85 |
| 482 model | 470 / 553 | 0,8226 | 0,85 — неактивно |
| 761 screen_inches | 12 / 12 | 0,7791 | 0,85 — неактивно |
| 761 model | 83 / 155 | 0,4663 | 0,85 — неактивно |
| 482 capacity_l | 0 / 0 | — | 0,85 — нет reference |

Пробный профиль привязывает к политике **все 12 полей** (11 через
`silver-trial-v1` и `761 storage_gb` через CONF-005, human audit 145/145).
Поле срабатывает, только если его нижняя граница не ниже target, а минимальный
target — 0,85. Сейчас активны 8 из 12: storage, ram, battery, color и brand
смартфона, brand, color и power_w чайника. 761 model, screen_inches и 482 model
остаются `review` с причиной `evidence_below_target`, 482 capacity_l — с
`no_evidence`. Они включатся сами, когда в `EVIDENCE` появятся данные с
границей ≥ 0,85. Опускать порог ниже 0,85 конфиг не позволяет.
У power_w оценено только 27% кандидатов, поэтому его граница — самая хрупкая из активных.

## Ограничения, которые нельзя опускать

- Catalog-silver — шумная ссылка, не human gold. Unknown/conflict исключены,
  совпадение с каталогом не доказывает правильность, а расхождение может быть
  ошибкой каталога.
- Числа получены на историческом producer `f33e3fc`; правила с тех пор менялись.
  Это описание прошлого прогона, не гарантия текущего.
- Targets выбраны после просмотра чисел; это решение о риске пробы, не
  заранее зафиксированный эксперимент. Пять активных targets ниже 97% (цели CONF-005).
- Независимая калибровка (#6/#38/#39) не завершена; `human_audit=false`,
  `independent_reference=false` видны в `/health` и manifest.

## Как работает

Ячейка активна, только если одновременно:

1. `runtime.auto_accept_enabled=true`;
2. `runtime.auto_accept_policies[category][attribute]="silver-trial-v1"`;
3. `runtime.auto_accept_trial.targets[category][attribute]` задан (`[0.85, 1]`);
4. зафиксированная нижняя граница ≥ target.

Принимается только кандидат `method=rule` без `reason_codes`; значение, unit,
evidence и score не меняются, меняется только `decision`. При проверке с исходным
Product значение заново выводится из правил и verifier: подделанный rule_id,
чужое значение/цитата или конфликт значений отклоняются. LLM-кандидаты не
принимаются. Политика trial без target, target без ячейки, ячейка без evidence,
неизвестная версия и изменённый extraction profile отклоняются до inference.

## Запуск

```bash
python -m goodsai.trial_acceptance --output outputs/trial-silver.json
python -m goodsai --config outputs/trial-silver.json predict --input /private/cards.jsonl --output outputs/trial-predictions.jsonl
python -m goodsai.api --config outputs/trial-silver.json --host 127.0.0.1 --port 8000
```

`--without-storage-pilot` оставляет `761 storage_gb` в review. Генератор не
перезаписывает существующий файл. Отключить одну ячейку — поставить ей
`review` и убрать её target; всё сразу — `auto_accept_enabled=false` или
штатный профиль.

## Что нужно перед переходом из пробы

Shadow-аудит человеком по CONF-006 для каждой ячейки, новая версия политики
вместо `silver-trial-v1` и решение архитектора с обновлением `TECHNICAL_SPEC.md`.
