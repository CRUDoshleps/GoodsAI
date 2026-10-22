# Контекст: auto_accept по категориям (CONF-007, CONF-008)

Сводка работы 22.10.2026 (timur0o31 + Claude) для людей и агентов, которые
продолжат тему автоматического принятия. Детали — в ссылках ниже; этот файл
описывает, что сделано, где лежит и что ещё не доказано.

## Исходное состояние (main `b06fbfd`)

- `runtime.auto_accept_enabled=false`, все найденные значения — `review`.
- Единственное исключение — CONF-005 `storage-pilot-97-v1`: только 761
  (смартфоны) / `storage_gb`, human audit 145/145, нижняя граница 97,955%.
- `AGENTS.md` и `TECHNICAL_SPEC.md` P03: вне пилота auto_accept запрещён до
  независимой калибровки; изменение решений требует решения архитектора.
- Категории runtime: 761 (7 атрибутов) и 482 чайники (5 атрибутов) — 12 ячеек.
- Параллельно идёт CONF-006 (`codex/conf-006-attribute-shadow`): per-attribute
  shadow-аудит для всех 12 ячеек; runtime он не включает.

## CONF-007 — матрица политик, default off

PR [#171](https://github.com/CRUDoshleps/GoodsAI/pull/171), ветка
`conf/conf-007-category-auto-accept`, база `main`.

- `runtime.auto_accept_policies[category][attribute]` — для всех 12 ячеек:
  `review` или аудированная политика именно этой ячейки.
- В `baseline.json` и `configs/production.example.json` матрица прописана явно:
  `761/storage_gb = storage-pilot-97-v1`, остальные 11 — `review`.
- Ячейка только привязывает политику; включает её глобальный флаг.
- Флаг без привязанной ячейки и политика в неаудированной ячейке отклоняются.
- Профили без секции получают штатную матрицу (поведение прежнее).
- Эффективная матрица — в runtime policy hash и `/health`.
- Код: `src/goodsai/storage_acceptance.py` (`AUDITED_POLICIES`,
  `validate_cell_policies`, `effective_cell_policies`, `bound_cells`),
  `config.py`, `policy.py`, `api.py`. Тесты: `CategoryPolicyMatrixTests` в
  `tests/test_storage_acceptance.py`. Док: `docs/CONFIGURATION.md`.

## CONF-008 — пробный auto_accept для всех 12 полей с порогом

Draft PR [#172](https://github.com/CRUDoshleps/GoodsAI/pull/172), ветка
`conf/conf-008-silver-trial-auto-accept`, база — ветка CONF-007 (после merge
#171 переключить на `main`).

- Политика `silver-trial-v1` (`src/goodsai/trial_acceptance.py`), секция
  `runtime.auto_accept_trial` с per-cell target `[0.85, 1]`.
- Основание — catalog-silver TP/FP из `reports/run_stats.json`
  (`slices.category_attribute`, producer `f33e3fc`), нижняя 95%-граница
  Clopper–Pearson:

| Ячейка | TP/(TP+FP) | Граница | Target |
| --- | ---: | ---: | ---: |
| 482 brand | 610/610 | 0,9951 | 0,99 |
| 761 ram_gb | 1581/1585 | 0,9942 | 0,99 |
| 761 battery_mah | 122/125 | 0,9391 | 0,93 |
| 761 color | 1138/1223 | 0,9173 | 0,91 |
| 761 brand | 1714/1870 | 0,9053 | 0,90 |
| 482 color | 136/147 | 0,8792 | 0,87 |
| 482 power_w | 97/106 | 0,8565 | 0,85 |
| 482 model | 470/553 | 0,8226 | 0,85 (неактивно) |
| 761 screen_inches | 12/12 | 0,7791 | 0,85 (неактивно) |
| 761 model | 83/155 | 0,4663 | 0,85 (неактивно) |
| 482 capacity_l | 0/0 | — | 0,85 (нет reference) |

- Расширено до 12 полей (решение 22.10.2026): пробный профиль привязывает все
  12 ячеек, но поле срабатывает только при границе ≥ target (минимум 0,85).
  Активны 8 из 12 (storage + 7 trial). 761 model, 761 screen_inches,
  482 model — `evidence_below_target`; 482 capacity_l — `no_evidence`.
  У power_w оценено лишь 27% кандидатов — самая хрупкая активная ячейка.
- Принимаются только `method=rule` без `reason_codes`; значение заново выводится
  из правил и verifier; LLM не принимается; изменённый extraction profile
  отклоняется.
- Профиль: `python -m goodsai.trial_acceptance --output outputs/trial-silver.json`
  (`--without-storage-pilot` — без storage). Default не меняется.
- Тесты: `tests/test_trial_acceptance.py` (12). Док: `docs/AUTO_ACCEPT_TRIAL.md`.
- Хронология ветки: сначала 6 полей (`be9c1f3`), затем все 12 с порогом.

## Что не доказано

- Catalog-silver — шумная ссылка, не human gold; числа описывают исторический
  producer `f33e3fc`, правила с тех пор менялись.
- Targets выбраны после чисел; пять из семи активных trial-ячеек ниже 97% цели CONF-005.
- Независимая калибровка #6/#38/#39 открыта; `human_audit=false`,
  `independent_reference=false` в `/health`.
- Проверки: 554 tests локально; 12 падений есть и на `main` — в среде не было
  fastapi/pyarrow/hypothesis (PyPI недоступен). HTTP-путь проверит CI.

## Как продолжать

1. Новая ячейка в штатном режиме: shadow-аудит CONF-006 → новая версия политики
   → запись в `AUDITED_POLICIES` → решение архитектора и `TECHNICAL_SPEC.md`.
2. Включить неактивную пробную ячейку: обновить её TP/FP в `EVIDENCE` из нового
   отчёта (`trial_acceptance.py`) и тест сверки; при границе ≥ 0,85 она включится.
   Порог ниже 0,85 не допускается.
3. Не включать auto_accept в default-профиле и на ВМ без решения команды.
