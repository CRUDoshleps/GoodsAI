# Результаты M1/M2 и происхождение измерений

Индекс восстановлен 19.10.2026 по отчётам из Git `48b45dc` и локальным
manifest. Это сохранённые результаты, не новый эксперимент. Реальные
карточки, gold и predictions остаются вне Git. Независимый test не оценён.

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

BASE-001 уже имеет runtime-реализацию (`model_rules.py`, synthetic tests,
M1 evidence); пометка READY в общей очереди требует решения интегратора.
Задача не объявляется DONE автором и повторная реализация не планируется.
EVAL-001/002 остаются нужны: metadata selection/quarantine не заменяют полный
аудит дублей и независимую human-проверку.

## Исходные протоколы в истории

Ссылки закреплены на commit до консолидации, не на изменяющийся main:

- [Первый M1](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/model_stage_results.md).
- [M1 boundary fixes](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/model_boundary_fix_results.md).
- [Подготовка и freeze M2](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_evaluation_preparation.md).
- [M2 до policy fixes](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_evaluation_results.md).
- [M2 policy fixes](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_policy_fixes_results.md).
- [Согласованная политика разметки](https://github.com/CRUDoshleps/GoodsAI/blob/48b45dc/docs/research/m2_annotation_policy_v2.md).

Офлайн: `git show 48b45dc:docs/research/<имя_файла>.md`.
