# Результаты и происхождение измерений

## Аудит защит 21.10.2026: отдельный synthetic протокол

Источник runtime — candidate `2246425690f94499e1df80d3686a1e4cfb34dd4d`,
baseline `7542d00`, seed `20261021`. Это проверка конечных контролей и одного
исправленного пути, **не новый замер P/R/F1 каталога**. Исторические human/silver
таблицы ниже сохраняются со своими producer/reference.

- [Матрица сценариев](SCENARIO_MATRIX.md): 17/17 executable групп, внешний
  CLI/socket HTTP без examples — 103/103 checks. В отчёте остаются 4
  not_implemented, 7 not_verified, 1 unknown; complete_case_evidence=false.
- [Таблица решений](VERIFIER.md#проверяемая-таблица-решений): schema/evidence,
  единицы/роль, отрицания/чужие сущности, конфликты, fresh/cache и review-only.
  В offline JSON сохраняются исполненные test IDs; удаление обязательного
  verifier/config контроля не скрывается зелёным результатом оставшегося suite.
- Найден и воспроизведён обход: LLM мог заполнить основную мощность из
  «Мощность подогрева 300 Вт», которую rules уже отклонял. Общий gate теперь
  применяет те же исключения вспомогательных величин. Ordinary LLM fallback
  «Потребляет 2200 Вт» сохраняется; weights и реальные model API не запускались.
- Существующий `verify_candidates` на тех же 12 synthetic probes: до/после
  12/12, false_values=0, missed_true_facts=0, lost_true_facts=0. Это ограниченная
  проверка отсутствия регрессии rules, не доказательство качества всех карточек.

Команда из корня checkout (новый output-dir):

```bash
.venv/bin/python scripts/release/scenario_matrix.py --seed 20261021 --output-dir outputs/eval010/scenarios-next
.venv/bin/python scripts/release/scenario_matrix.py --verify outputs/eval010/scenarios-next
```

Исходный локальный протокол — `outputs/eval010/scenarios-2246425/`,
source/config/test/artifact hashes — в его `scenario.manifest.json`.
Текущий запуск должен ссылаться на собственный manifest, а не наследовать
identity этого протокола. Отдельная независимая оценка по #6/#38,
актуальный model comparison PR #136 и разбор #137 остаются незавершёнными.
Улучшение баллов организаторов или real precision этим не заявляется.

## Сводка доказательств на 20.10.2026

Runtime/documentation audit: код `1c64463`. Строки ниже относятся к разным
reference и producer; это индекс, а не единая таблица сравнимого качества.
Версия конкретного Gitea checkout записана в submission-manifest. Наличие
исправлений/тестов не заменяет повторную оценку каталога на выбранной версии.

| Доказательство | Версия / набор | Результат | Что этим не доказано |
| --- | --- | --- | --- |
| Внешний CLI/HTTP без packaged examples | synthetic seed `20261020`, протокол интеграции `1c64463`; [runner](../scripts/release/external_acceptance.py) | 83/83 contract checks; воспроизводится командой ниже | P/R/F1 реального каталога |
| Чистая сборка и упаковка | locked clean-run, очищенный checkout интеграции `1c64463` | 11/11 этапов; 433 основных tests и 3 reader в интеграционном протоколе | независимая приёмка этой версии на VM, качество моделей |
| Общий verifier + composition | ARCH-001 runtime `3d3dc49`, freeze baseline `2b0176d`; прежние 40 AI-assisted human-reviewed development | 143 TP / 0 FP / 22 FN, 224 judged / 16 excluded; A→C без дельт | independent human test; перенос на новые категории; оценка нынешнего main на этом reference заново |
| Масштабная catalog-silver диагностика | producer `f33e3fc`, declared baseline `977c5ed`; 3037 cards / 1270 families | agreement F1 75,67%, [неизменённые агрегаты](../reports/metrics.md) и [provenance](../reports/run_stats.json) | независимая precision; значение F1 нынешнего main |
| GLiNER brand prototype | development-эксперимент 19.10 на 80 просмотренных карточках, runtime `c3706d2` | narrow brand variant: 17 новых совпадений reference без новых brand mismatches на этом наборе; [условия](EXPERIMENTAL_GLINER.md) | independent gold и общий benchmark с нынешним LLM/registry |
| LLM + экспериментальные routes | opt-in CLI/API, typed proposals/quotes или span IDs, shared gate, ledger/deadline/cache | интеграция и offline failure tests реализованы | измеренный сравнительный выигрыш на общем frozen reference: N/A |
| Независимая итоговая оценка | закрытый reserve, [HUMAN_GOLD](HUMAN_GOLD.md) | N/A — не завершена | калиброванная probability и безопасный auto_accept |

Малый reviewed development и catalog-silver нельзя объединять в один quality
score. Unknown/conflict/ambiguous не переименовываются в ошибки или успехи.
Временные и стоимостные условия каждого эксперимента находятся в его протоколе;
нулевые API calls у rules не означают нулевую стоимость вычислений.

Свежий EVAL-007 и model comparison сопровождаются отдельными задачами
[#123](https://github.com/CRUDoshleps/GoodsAI/issues/123) и
[#125](https://github.com/CRUDoshleps/GoodsAI/issues/125). В новой silver-диагностике
зарегистрированы новые расхождения и потерянные совпадения `model`
([#137](https://github.com/CRUDoshleps/GoodsAI/issues/137)). Это требует adjudication:
catalog mismatch не равен подтверждённой человеком ошибке, а небольшое улучшение
aggregate F1 не отменяет regression gate. Числа этого прогона здесь не подменяют
исторический отчёт 3037 cards и не объявляются завершённой независимой оценкой.

Проверка своего checkout без приватных данных и без model API (новые каталоги):

```bash
.venv/bin/python -m scripts.release.external_acceptance --seed 20261020 --output-dir outputs/external-next
python3.12 scripts/release/clean_run.py --output-dir outputs/clean-next
.venv/bin/python -m goodsai.demo --output-dir outputs/demo-next
.venv/bin/python -m goodsai.demo --verify-dir outputs/demo-next
```

В PowerShell executable — `.\.venv\Scripts\python.exe`; эквивалент clean-run —
`.\.venv\Scripts\python.exe scripts/release/clean_run.py --output-dir outputs/clean-next`.
`external-next` ожидает 83/83, `clean-next` — passed и 11 этапов, demo — 6/6,
verify — verified. Эти сценарии не открывают test и не измеряют catalog P/R/F1.

## Исторический индекс M1/M2, восстановленный 19.10.2026

Индекс восстановлен 19.10.2026 по отчётам из Git `48b45dc` и локальным
manifest. Это сохранённые результаты, не новый эксперимент. Реальные
карточки, gold и predictions остаются вне Git. Независимый test не оценён.

Дополнение: [реальный development checkpoint 19.10](delivery/2026-10-19/README.md)
воспроизводит 69/0/14 на frozen M2 и содержит новый batch из 2198 разрешённых
development SKU, EDA-сводку, PDF/Markdown-слайды и полный локальный комплект.
Это воспроизведение текущих правил, не новое улучшение и не независимый test.

## Как читать сравнения

M1 извлекает атрибут **model правилами**, без ML/LLM: `method=rule`.
M2 расширил reviewed development, затем по согласованным решениям исправлены
brand/color/memory policies. Все значения — `review`, confidence heuristic;
auto-accepted coverage = 0. Неверный ответ вместо present gold даёт FP+FN.
Ambiguous/unjudgeable исключаются из TP/FP/FN и считаются отдельно.

Обозначения A/B/C локальны для эксперимента. В первом M1 и расширении M2
A — baseline `5f77d81`, B — текущий verifier с отключённой генерацией model,
C — новый runtime. В policy fixes **A уже равен M1 из `5adab92`**, B —
ablation C без model, C — policy fixes. B не является отдельным релизом.

## История на неизменных reference

| Срез | Версия | TP / FP / FN | P / R / F1 |
| --- | --- | --- | --- |
| Старый development, 10 cards / 57 judged | baseline | 18 / 1 / 19 | 94,7 / 48,6 / 64,3% |
| Тот же | первый M1 | 26 / 1 / 11 | 96,3 / 70,3 / 81,3% |
| Тот же | M1 boundary fixes | 26 / 1 / 11 | 96,3 / 70,3 / 81,3% |
| Тот же | M2 policy fixes | 28 / 0 / 9 | 100 / 75,7 / 86,2% |
| Бывший validation, 12 / 67 | baseline | 29 / 1 / 21 | 96,7 / 58,0 / 72,5% |
| Тот же | первый M1 | 35 / 3 / 15 | 92,1 / 70,0 / 79,5% |
| Тот же | M1 boundary fixes | 36 / 1 / 14 | 97,3 / 72,0 / 82,8% |
| Тот же | M2 policy fixes | 39 / 1 / 11 | 97,5 / 78,0 / 86,7% |
| Новый M2 development, 20 / 115 | baseline `5f77d81` | 46 / 3 / 37 | 93,9 / 55,4 / 69,7% |
| Тот же | M1 | 58 / 3 / 25 | 95,1 / 69,9 / 80,6% |
| Тот же | M2 policy fixes | 69 / 0 / 14 | 100 / 83,1 / 90,8% |

**Бывший validation — development_feedback:** его ошибки уже использовали
для исправления правил. Нельзя называть его независимым holdout.
Сравнение строк разных reference не является оценкой прироста качества.
Первый M1 давал новые FP; сохранение этой истории необходимо для честного
объяснения последующих исправлений.

M2: AI-assisted human-reviewed, 20 карточек (10 каждой категории),
120 полей: 83 present / 32 absent / 5 ambiguous, judged 115. Все 120 полей
подтверждены пользователем; это не blind human gold. У model 19 present,
1 ambiguous, **нет judged-негативов**, поэтому model-FP на отсутствующих
моделях этот набор не проверяет.

## M2 после policy fixes

| Атрибут | TP / FP / FN | P / R / F1 |
| --- | --- | --- |
| brand | 20 / 0 / 0 | 100 / 100 / 100% |
| model | 12 / 0 / 7 | 100 / 63,2 / 77,4% |
| storage_gb | 5 / 0 / 1 | 100 / 83,3 / 90,9% |
| ram_gb | 6 / 0 / 0 | 100 / 100 / 100% |
| screen_inches | 3 / 0 / 1 | 100 / 75,0 / 85,7% |
| battery_mah | 1 / 0 / 3 | 100 / 25,0 / 40,0% |
| capacity_l | 2 / 0 / 2 | 100 / 50,0 / 66,7% |
| power_w | 4 / 0 / 0 | 100 / 100 / 100% |
| color | 16 / 0 / 0 | 100 / 100 / 100% |

| Категория | Judged | TP / FP / FN | P / R / F1 |
| --- | ---: | --- | --- |
| Смартфоны 761 | 66 | 41 / 0 / 8 | 100 / 83,7 / 91,1% |
| Чайники 482 | 49 | 28 / 0 / 6 | 100 / 82,4 / 90,3% |

От прежнего M1 на том же M2: 3 FP+FN→TP и 8 FN→TP;
lost_tp=0, new_fp=0. Excluded-with-candidate на ambiguous: 2→0,
эти отказы не засчитаны как TP/TN.
Candidate coverage на judged: 61/115→69/115 (53,0→60,0%);
на всех применимых парах: 63/120→69/120 (52,5→57,5%).
Card coverage: 19/20→20/20. Это не precision и не полнота каталога.

Остаются 14 FN, в том числе 7 model и 3 battery. Precision=100% означает
69 правильных кандидатов в обсуждавшейся development-выборке, не отсутствие
ошибок на всём каталоге. Fairness, traffic weighting и перенос на новые
категории не измерены. Нельзя обещать будущий F1 или баллы организаторов.

## Identity и локальные артефакты

| Артефакт | Путь / SHA-256 |
| --- | --- |
| Frozen M2 reference | `data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl` |
| Reference SHA | `2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337` |
| M1 boundaries code SHA | `3fa9972c690370806c0ad42ad1e90d8174cce920f4c7c33a5dc8d0f2728fee85` |
| M1 config SHA | `974ffffb9f56d30386ea41b456c5d78b1ff72ebbb40cd33ca3779af2c88e3b98` |
| Policy experiment C code SHA | `392747b47cf2d479f0b8b59bce8db9a716b8f3193071eb0573bd021110a2de7c` |
| Policy config SHA | `cb7285cb3b83d2584661d5ec8eb4a315d6581148a5c3b1f7d012a0998db19a2b` |

Code SHA выше относится к frozen рабочим снимкам до commit, не к обещанию
clean-tree. Он учитывает байты Python-файлов, включая переносы строк;
публикационные commits и экспериментальные snapshots нужно различать.
M1 опубликован через PR #10 / merge `c813f31`; M2 policy fixes входят
в `48b45dc`. Ночные docs-only изменения до `0736753` runtime не меняли.

Корень локальных опытов — `outputs/experiments/model-stage/`:

| Опыт | Каталог |
| --- | --- |
| Первый M1 | `m1-development/`, `m1-validation/` |
| M1 исправление границ | `m1-boundaries-development/`, `m1-boundaries-feedback/` |
| Расширение M2 | `m2-reviewed-development-v1/`, `m2-reviewed-development-v1-slices-v2/` |
| Финальные policy fixes | `m2-policy-fixes-v2/`, `m2-policy-fixes-v2-slices/` |
| Регрессия старых срезов | `m2-policy-legacy-development-v2/`, `m2-policy-legacy-feedback-v2/` |

В каждом сравнении: `experiment.manifest.json`, frozen packages/configs,
`A|B|C/predictions.jsonl`, prediction manifests, `metrics.json`, повторы,
pair-deltas и summary. Промежуточные policy `v1` сохранены, но не являются
принятой версией: там обнаруживались потерянный TP и новый FP.
Reference SHA повторно проверен при восстановлении индекса, без запуска predictions.

## Воспроизведение M2

Требуются полный Git clone с `5adab92`, Python >=3.12, установленный пакет,
локальный frozen reference с SHA выше. Сначала проверить SHA:

```bash
.venv/bin/python -c "import hashlib,pathlib; p=pathlib.Path('data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl'); h=hashlib.sha256(p.read_bytes()).hexdigest(); assert h=='2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337', h; print(h)"
.venv/bin/python scripts/research/compare_model_stage.py --gold data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl --split development --baseline-ref 5adab92 --allow-dictionary-changes --repeats 3 --output-dir outputs/experiments/model-stage/m2-policy-reproduction-next
```

В PowerShell заменить `.venv/bin/python` на `.\.venv\Scripts\python.exe`.
Каталог должен быть новым; старые snapshots/reference не изменять.
Runner сам строит text-only `input.jsonl`, предсказывает те же SKU,
сохраняет code/config/input/reference hashes и проверяет reference до/после.
`--allow-dictionary-changes` разрешает только явное сравнение политик при
неизменной схеме. Это не разрешение менять runtime ради воспроизведения.

Для сохранённых M2 slices дополнительно нужен локальный bundle
`data/gold/e1/m2/v2/`:

```bash
.venv/bin/python scripts/research/summarize_m2.py --experiment outputs/experiments/model-stage/m2-policy-reproduction-next --bundle data/gold/e1/m2/v2 --output outputs/experiments/model-stage/m2-policy-reproduction-next-slices
```

Эти приватные команды здесь проверены по CLI и исходникам; повторная оценка
реального reference не выполнялась. Новый code/config может дать другой результат:
его публикуют отдельно, не заменяя исторический отчёт. LLM calls/tokens/API
cost исторических опытов = 0. p50/p95 в старых отчётах — малые локальные batch,
не SLA и не контролируемый benchmark.

## Резерв test и незавершённые задачи

Итоговый резерв — **v2**, 40 карточек из test_reserved (20 каждой категории),
seed `goodsai-m2-selection-20261018-v1`. Резерв v1 не использовать.
Тексты не анализировались и predictions на test не запускались. Сейчас проверены
лишь наличие metadata/blank-файла и агрегаты selection summary; сами задания
не открывались. Человеческая blind-разметка и итоговая независимая оценка впереди.

На дату старого индекса приёмка BASE-001 и split audit ещё ожидалась. Позднее
BASE-001 #21 принят через PR #105 (`71cae4b`), EVAL-002 #7 — через PR #69
(`c49540f`). Эти изменения не пересчитывают исторические таблицы выше.
Независимая человеческая оценка EVAL-001 остаётся отдельной задачей:
selection/quarantine и AI-assisted review не заменяют blind human reference.

## Исходные протоколы в истории

Ссылки закреплены на commit до консолидации, не на изменяющийся main:

- [Первый M1](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/model_stage_results.md).
- [M1 boundary fixes](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/model_boundary_fix_results.md).
- [Подготовка и freeze M2](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_evaluation_preparation.md).
- [M2 до policy fixes](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_evaluation_results.md).
- [M2 policy fixes](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_policy_fixes_results.md).
- [Согласованная политика разметки](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_annotation_policy_v2.md).

Офлайн: `git show 48b45dc:docs/research/<имя_файла>.md`.
