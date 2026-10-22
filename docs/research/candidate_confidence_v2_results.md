# EVAL-012 v2: пригодный advisory confidence

Продолжение #168 / PR #169 по запросу Владислава: довести score до приемлемого
состояния самостоятельно, без merge. #39 остаётся открытой для независимой
human calibration; этот результат не объявляет её завершённой.

## История и решение

V1 context-v1 сохранил отрицательный результат: 30 reviewed cards, только
положительные кандидаты, Brier ухудшился. Его коэффициенты не подгонялись.
Вместо остановки подготовлен [протокол v2](candidate_confidence_v2_protocol.md)
в commit `9e49b53`, до расчёта нового score на большом development bundle.
Использованы существующие logistic/Platt/reliability, evaluator и atomic
preparation. Новых библиотек, внешних вызовов, расходов или SKU lookup нет.

Пригодность определена для **advisory confidence / review ordering**, не для
human probability и не новых auto_accept. Все четыре заранее заданных gates PASS:
diagnostic Brier ≥10% лучше fixed, ECE не хуже, catalog mismatch capture при
review 10% не хуже, reviewed sanity Brier не хуже fixed+0.005.

## Источники и изоляция

Frozen `eval-006-silver-20261020-rebuilt`, проверены SHA input/reference/metadata
по исходному manifest. Только original_split=development и прежние fit/calibration/
diagnostic. 803 validation/development_feedback карточки исключены; резерв test
не использовался. Из 2 171 selected карточки получено:

| Role | Кандидаты | Семейства | Catalog match | Catalog mismatch |
| --- | ---: | ---: | ---: | ---: |
| fit | 1 875 | 400 | 1 755 | 120 |
| calibration | 310 | 77 | 289 | 21 |
| diagnostic | 3 986 | 127 | 3 822 | 164 |

Семейства и normalized exact duplicates между ролями проверяются до inference;
cross-role components исключались бы целиком (в этом bundle их 0). Near-duplicate
границы наследуются от предыдущего family audit. Unknown/conflict не negative.
SKU/family и catalog targets используются только для splits/labels, не features.
Reference kind — catalog_silver; independent=false во всех стадиях.

Модель — regularized logistic с отдельным Platt fit. Параметры алгоритма не
перебирались по diagnostic. Выбор scopes (≥30 fit-кандидатов) использует только
fit counts. В девяти scopes применяется learned score, остальные сохраняют fixed.
Признаки text-candidate-1 совпадают между runtime и offline; score применяется
после выбора/проверок значения, не отменяет verifier и не изменяет decision.

## Измерения готового runtime score (с fallback)

| Slice | Fixed Brier | Learned Brier | Fixed ECE | Learned ECE |
| --- | ---: | ---: | ---: | ---: |
| Calibration | 0.07599 | 0.05732 | 0.11919 | 0.01187 |
| Diagnostic | 0.06590 | 0.03283 | 0.15501 | 0.03648 |
| Reviewed sanity: 107 correct candidates | 0.03937 | 0.00959 | 0.19579 | 0.06901 |

Diagnostic Brier снизился на 50.18%. Family-macro Brier: 0.05779 → 0.03067.
Парный family bootstrap (1 000 повторов, seed 2212) даёт 95% интервал разности
learned-fixed [-0.03471, -0.02399]. Это условный catalog development interval.

Review budget 10%, с ожидаемым равномерным включением ties: обнаружение catalog
mismatches 12.43% → 89.74%. Не называть это recall реальных ошибок/галлюцинаций.
Из 3 986 diagnostic кандидатов 3 830 (96.09%) имеют поддержанный scope, 156
получают прежний score. Scope coverage не равно качеству на редких категориях.

Обе категории улучшились по proxy Brier: чайники 0.05816 → 0.03534,
смартфоны 0.06626 → 0.03271. Срезы по атрибутам/thresholds и bins в приватном
машиночитаемом report.json. Для screen/capacity и редких rules статистики
недостаточно: fixed fallback видим, успех для них не приписывается.

Reviewed sanity: прежние 30 AI-assisted human-reviewed development карточек,
107 TP / 0 FP / 13 FN, P/R/F1 и все факты/decisions неизменны. Эти карточки
использовались для правил, а ошибочных извлечений в них нет: это не independent
test и не доказательство ранжирования настоящих ошибок.

## Проверка смысла proxy labels

После fit выполнен отдельный AI spot check 12 случайных fit mismatches (seed
2212), без изменения labels/весов/thresholds. Среди них есть parent/subbrand,
model с цветом/памятью в catalog reference, blue/голубой и тёмно-синий/синий,
а также числовое расхождение источников. Многие mismatches не доказывают
неправильность извлечённого значения по согласованной политике. Этот spot check
не выдаётся за human review и не используется как оценка частоты ошибок.

Поэтому смысл learned-v1 ограничен обученной оценкой catalog agreement по
текстовым признакам. Это более обоснованный advisory score, чем ручная константа,
но не human-calibrated probability. Для автоматического принятия по новым
порогам нужны отдельные correctness labels и независимая приёмка #39/#6/#38.

## Исполнение, артефакты и повторение

Runtime producer `b9472b14e1b9a7a674ca5b33a90fa074d971d94f`; uncertainty/report
producer `8a50c5d`. Model profile fingerprint:
`927956a1116e3881429ccdb1f89585cefaebca3de25a2b73136e2744b5b8b444`.
Model.json SHA-256:
`4e8318b9add8a262abad8eebfecd44c82c03927ad2c57ebf9752662c03953ac0`.

Локальные артефакты Влада (вне Git):

- `outputs/confidence-eval012-20261022/silver-v2-final/` — frozen features/splits;
- `human-v2-final/` рядом — reviewed baseline replay;
- `learned-v2-verified/` — model.json, готовый profile.json, report и объяснения;
- `learned-v2-runtime/` — полный replay 2 171 карточки.

Рецепт воспроизведения/запуска — [CONFIDENCE](../CONFIDENCE.md). Manifest SHA
проверяются до fit/export. Model/profile JSON остаются приватными; schema,
finite weights, feature version и fingerprint проверяются до API startup.
API health показывает loaded model/version и human_probability_calibrated=false.

Полный runtime replay: 6 422 confidence изменены, 0 изменений значений, units,
evidence, reasons и decisions. Все известные scores совпали с offline features.
Mean 3.02 ms, p95 7.96 ms на 2 171 карточке локально (Python 3.12.6 / Windows 11),
без модельных API/GPU; это измерение, не SLA.

Две полные сборки model/profile/report/объяснений дали byte-identical артефакты.
Живой HTTP и CLI на настоящем artifact согласованы: storage=256 получил
0.987701 и 0.988993 при дополнительном ROM evidence. Совместный профиль с 97%
storage pilot сохранил auto_accept только в прежней области. Filtered submission
успешно загрузил модель с тем же source fingerprint. ВМ и main не изменяются.

Тесты: 549 полных unittest PASS на runtime producer; ещё добавлен и отдельно
проверен deterministic family-bootstrap regression. CI содержит learned suite
для Windows/Linux. Default pipeline/prediction contract остаются прежними.
