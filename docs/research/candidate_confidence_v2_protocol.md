# EVAL-012 v2: обучаемый advisory score

Продолжение по прямому запросу Владислава 22.10.2026: довести confidence до
приемлемого практически применимого состояния самостоятельно; PR не вливать.
V1 и его отрицательные результаты сохраняются. Изменение подхода фиксируется
до расчёта новых score и выбора модели на большом development bundle.

## Данные

Использовать существующий catalog-silver bundle eval-006-silver-20261020-rebuilt:
только original_split=development, роли fit/calibration/diagnostic. Сохранить
его исходное семейное разбиение. development_feedback/validation и reserve
не использовать. Source hashes проверять по manifest до inference, family и
нормализованные точные дубли между ролями выявлять; связанные группы объединять
или исключать из всех ролей при пересечении, не разрывать.

Silver correctness = совпадение canonical value/unit с known catalog reference;
unknown/conflict не отрицательный класс. Это proxy, не human correctness.
Reference, SKU/family, seller/brand metadata не передавать в feature vector.
Сохранить ранее использованные 30 reviewed development отдельно как sanity check,
не называть их независимыми и не подбирать по ним коэффициенты.

## Модель

Использовать существующие logistic/Platt primitives и text-only признаки v1.
Начальная модель: regularized logistic; отдельная Platt calibration только на
calibration. Более сложные модели не нужны без провала fit-only диагностики.
Параметры/feature changes подбирать только на fit через group cross-validation,
диагностический split не использовать для перебора. V1 heuristic остаётся
comparator, а не основой для нового ручного тюнинга.

## Приемлемость

Для advisory confidence (не auto_accept): на frozen silver diagnostic требуется
снижение Brier не менее 10% относительно fixed, ECE не хуже fixed и доля найденных
catalog mismatches при review 10% кандидатов не ниже fixed. Нужны оба класса,
достаточный class/group support по прежнему gate. Tie handling — ожидаемое
равномерное включение ties, не сортировка по SKU/labels. Показать per-attribute,
category и field slices, число ошибок, ranking и доверительные ограничения.

На reviewed development: value/unit/evidence/decision/P/R/F1 неизменны, Brier
не хуже fixed более чем на 0.005. Это sanity check, не independent calibration.
Не расширять auto_accept и не менять его 97%-цель. Сравнить на синтетических
отрицаниях/несовместимости, HTML, неизвестных scopes, damaged artifacts и CLI/API.

## Runtime

Новый opt-in learned-v1 — эвристическая обученная оценка согласованности с silver,
а не заявленная вероятность правильности. Model artifact JSON без pickle,
schema/finite weights/feature version/source profile fingerprint и SHA обязательны.
Модель/приватный config не коммитить; дать воспроизводимое создание и загрузку.
При неизвестном scope/версии грамматики не применять статистику молча: OOD scope
даёт прежний score, несовместимая модель отклоняется до старта API. Не применять
к LLM/encoder candidates. Score следует после выбора/верификации значения.
Объяснения влияния признаков и область применимости — в диагностике.

Если критерии не выполнены, продолжить работу с новым fit-only исследованием и
отдельным зафиксированным протоколом, не выдавать проход другой метрики за успех.
Не ослаблять определения human review/independence. #39/#6/#38 остаются открыты
для настоящей независимой вероятностной калибровки даже при пригодном advisory score.
