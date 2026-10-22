# EVAL-012: протокол до прогона

22.10.2026, #168; доступная часть #39. Seed `eval012-context-v1`.
Runtime: fixed-v1 против opt-in context-v1. Только уже проверенные и выбранные
rules-кандидаты; не менять value/unit/evidence/rule_id/decision. Никакого
расширения auto_accept, LLM-вызовов или просмотра test reserve.

Признаки фиксируются до просмотра новых результатов: прежний score, атрибут,
категория, rule_id, поле, длина span, явная подпись роли в той же видимой строке,
единица в evidence, согласие прошедших verifier кандидатов из title/description.
Идентичные нормализованные тексты не дают бонуса согласия. Скрытый HTML не даёт
признаков. SKU, family, reference labels и catalog targets не являются признаками.

Контекстная эвристика — экспериментальный comparator, не измеренная вероятность:
logit прежнего score + 0.35 за явную подпись + 0.20 за единицу + 0.40 за согласие;
-0.35 если нет ни подписи, ни единицы. Коэффициенты не подбирать по diagnostic.
Learned comparator переиспользует fit_logistic и отдельный Platt fit. Support gate:
fit >=200 кандидатов, >=20 групп, >=20 положительных и отрицательных;
calibration и diagnostic >=10 групп, оба класса. Недостаточный support даёт N/A.
Группы непересекающиеся, seed/hash распределяет 60/20/20; точные нормализованные
дубли объединяются перед распределением. Распределение и SHA входов сохраняются.

Источники: только уже human-reviewed AI-assisted development. Старый validation,
test reserve, 145 только положительных storage confirmations и error-selected
model-only subset не включать в обучающий benchmark общего confidence.
Reference provenance и exclusions видимы. Unknown/ambiguous не отрицательный класс.

Сравнение: Brier/ECE с support, bins, precision/coverage по заранее заданным
порогам 0.5/0.75/0.8/0.85/0.9/0.95/0.97, attribute/category slices и исходные
P/R/F1 существующего evaluator. Пороги диагностические, не runtime acceptance.
Отдельно latency; детерминированный отчёт не содержит wall-clock времени.
Default fixed-v1 остаётся. При отсутствии улучшения context-v1 остаётся только
экспериментальным opt-in; learned artifact не допускается автоматически в runtime.
Независимая калибровка, перенос на других продавцов/категории и приёмка #39 —
отдельный блокер #6/#38. Смена правил/verifier требует нового сравнения.
