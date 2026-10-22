# EVAL-012: результаты и границы приёмки

22.10.2026, #168 — реализация доступной части #39.
Claim `e77fada`, протокол до просмотра новых предсказаний `cf26b8b`, producer
`bbb265d3884eaced22aa54842eb9320e6aa11902`. Runtime code SHA-256:
`94e3642e9012c20304b63bece9bb802c29bd6d867997324cd6aa5b6eead4d05a`.
Извлечение/normalizer/verifier и принятие не расширены. Новый score — только
экспериментальный профиль context-v1; fixed-v1 остаётся default.

## Данные и воспроизведение

Использованы только 10 reviewed-v2 development и 20 M2 reviewed development
карточек. Оба источника human-reviewed AI-assisted, independent=false, ранее
участвовали в развитии правил. Старый validation, резерв test, error-selected
model-only review и storage-only 145 положительных проверок не включались.
Тексты, reference, predictions, vectors и family assignments остаются вне Git.

Приватный spec: `outputs/confidence-eval012-20261022/spec.json` в исходном
рабочем каталоге Влада. Input SHA фиксируются в spec до inference. Runner:

```bash
python -m scripts.research.compare_confidence --spec /private/confidence-spec.json --output-dir outputs/confidence-new
```

Выходной каталог должен быть новым. Seed `eval012-context-v1` не перебирался.
Есть union исходных family/group и normalized exact duplicates; near-duplicate
границы наследуются от предшествующего family audit и не объявляются заново
независимо проверенными. После объединения — 29 групп кандидатов из 30 карточек.

Два прогона frozen-1/frozen-2 дали одинаковые bytes report, report.md, обеих
predictions, vectors и freeze. Хеши:

| Артефакт | SHA-256 |
| --- | --- |
| report.json | 51bf3967e7e91f291b8afe0c0b522c4e1d1abe0ae55e77cb1b7276efc61d7fe8 |
| fixed.jsonl | 787d6a0306977a487a00136a9031c5e4b92a2f34c6ac95d4359599d52f2e5f45 |
| context.jsonl | fd779572773e2cdd07472b2097dbe121f6d5b8ed05664fa5f10066befd76294f |
| freeze.json | 2bce507c9501558234514ac931afb22bee1d75f3680c8403a58d674c63f80246 |

Latency хранится отдельно и в byte-repeatability не входит. Локально Python
3.12.6 / Windows 11, последовательный CPU run, 30 карточек: mean fixed 3.37 ms,
context 3.10 ms, p95 6.36/6.51 ms. Это малый шумный замер, не ускорение и не SLA.
Вызовов моделей и стоимости API нет.

## Результаты

Существующий evaluator: 172 judged поля, 107 TP, 0 FP, 13 FN; precision=1.0,
recall=0.89167, F1=0.94273, prediction coverage=0.62209. Шесть неоднозначных
полей исключены. Между fixed/context все значения, units, evidence, rule_id,
reasons, decisions и extraction metrics одинаковы. Это development screening,
не новые независимые метрики качества и не результат контекстного score.

| Slice | Support / группы | Fixed Brier / ECE | Context Brier / ECE |
| --- | --- | --- | --- |
| Весь reviewed development | 107 / 29 | 0.03937 / 0.19579 | 0.05446 / 0.22652 |
| Diagnostic | 32 / 10 | 0.03930 / 0.19531 | 0.05836 / 0.23554 |

Контекстная эвристика **не улучшила** Brier/ECE. Коэффициенты не менялись
после просмотра diagnostic. Учитывая нулевой negative support, эти показатели
не доказывают качество ранжирования ошибок ни старого, ни нового score.
Рекомендация runner: `retain_fixed_context_brier_not_improved`.

Learned comparator: `insufficient_data`, model artifact не выпущен:

| Role | Кандидаты | Группы | Правильные | Ошибочные |
| --- | ---: | ---: | ---: | ---: |
| fit | 60 | 15 | 60 | 0 |
| calibration | 15 | 4 | 15 | 0 |
| diagnostic | 32 | 10 | 32 | 0 |

Пороговый отчёт содержит числители/знаменатели, candidate coverage и retention
правильных значений. Пороги не являются новыми правилами auto_accept. IID-bound
при всех correct — лишь условная диагностика; не учитывает family correlation,
selection/reviewer bias и не заменяет независимую приёмку.

## Проверки

- 539 unittest PASS на чистом producer bbb265d; 14 новых regression tests включены.
- Default synthetic demo 6/6, pip check PASS.
- Живой локальный HTTP и CLI выдали одинаковые ответы. Одинаковый storage=256
  получил 0.830094 без подтверждения и 0.879351 с отдельным ROM evidence.
- Fixed default, abstain/conflict, отсутствие SKU features, hidden HTML,
  duplicate corroboration, отказ от обучения без support, раздельный Platt,
  защиты split/hash/overwrite, deterministic replay, profile hash и прежняя
  storage-pilot область покрыты тестами. Новая suite добавлена в CI Windows/Linux.
- Первый полный run на dirty tree ожидаемо остановился в пяти существующих
  provenance-проверках `prediction_method_not_frozen`; guards не ослаблялись.
  После commit чистый полный run PASS. Первый live smoke использовал неподдержанный
  description-only memory pair; он не принят за PASS и сохранён локально.

## Что остаётся

#39 не закрывается. Нужна разметка ошибочных кандидатов из новых development
семейств и отдельные calibration/diagnostic группы с обоими классами; при
обогащении ошибками учитывать sampling bias. Для независимой оценки остаются
#6/#38. Модель, веса и новый auto_accept не включены в runtime или на ВМ.
Текущий согласованный storage pilot 97% не меняется этой работой. Не обещаются
прирост баллов, вероятностная интерпретация score или подтверждённое улучшение.
