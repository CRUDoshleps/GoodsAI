# EVAL-011: фиксированный shadow-пилот storage_gb

Версия `storage-shadow-1`, seed `goodsai-storage-shadow-20261022-v1`.
Зафиксировано до запуска нового inference и просмотра его результатов.

## Что измеряем

Один атрибут `storage_gb`, категория смартфонов `761`, только правила.
Кандидат остаётся `review`. Проверяем гипотетическую политику принятия:

- обработанная карточка с явным словом «смартфон» или smartphone в title;
- title не обозначает часы, браслет или аксессуар;
- storage_gb имеет review, method=rule, unit=GB, точное evidence, пустые reason_codes;
- источник `memory.context.v1` (явная роль) или `memory.title-pair.v1`
  (согласованная пара RAM/storage с единицей по P09);
- конфликт RAM/storage запрещает выбор. Схему/evidence проверяет действующий
  validate_prediction и общий verifier, правила извлечения не меняются.

Обе формы включены в одну заранее заданную политику. Отдельные срезы форм,
поля цитаты и роли исходного split диагностические, не варианты для подбора
лучшего результата. Общий raw score не становится вероятностью.

## Данные и порядок

1. Проверить SHA/inventory существующего catalog_silver bundle. Только
   original_split development/validation, допустимые роли fit/calibration/
   diagnostic/development_feedback. Reserve не входит в bundle.
2. Записать freeze: protocol/seed, source hashes, identity runtime/config,
   helper/template fingerprints и список прежних exposures. До этого predictions
   не читаются и inference не запускается.
3. Запустить rules-only CLI дважды, проверить идентичность predictions.
4. Отобрать eligible candidates без чтения reference. Выборка: до 300 семей,
   family-uniform hash ranking; внутри семьи одна карточка по независимому hash.
   Исключить всю семью, если metadata.exposed или SKU есть в переданных exposure
   ledgers. Не добирать близкие варианты из той же семьи ради размера.
5. Только после фиксации selection прочитать reference и запустить существующие
   silver evaluator/calibrator. Unknown/conflict не исчезают из coverage.
6. Подготовить HTML и партии по 50 случаев для человеческого аудита.

## Ручная проверка

Человек видит исходный текст, значение и evidence **детерминированных правил**.
Каталожные ответы, correctness, score/порог и предлагаемый auto_accept не показаны.
Это проверка предложений, не слепая независимая разметка. Поля предзаполнены
правилами, статус каждого поля первоначально unreviewed. LLM не используется.

Человек подтверждает/исправляет значение и цитату, либо выбирает absent,
ambiguous/unjudgeable с причиной. AI не подтверждает собственные предположения.
До ответа человека human precision и risk bound = N/A. Ответы импортируются
проверкой package_id, reviewer, набора ID, точного evidence и единиц.

## Метрики и заранее установленная граница

- card-weighted shadow coverage: selected storage / все смартфоны и / найденные storage;
- доля оставшихся review по storage и всем обязательным полям;
- TP/FP/unknown/conflict по catalog_silver отдельно от human correctness;
- human precision на family-balanced выборке: correct / все проверенные;
  unresolved показываются отдельно и считаются ошибками в conservative bound;
- незавершённая партия/выборка не даёт положительной приёмки;
- exploratory one-sided 95% Clopper–Pearson lower bound, цель 0.99;
  299/299 без ошибок достаточно численно только при биномиальных предпосылках.
  Это не гарантия для всех SKU/продавцов и не card-weighted production precision.
- существующие Brier/ECE на silver и raw-score risk/coverage показывают отдельно.
  Для подбора порога по этой audit-выборке данные повторно не используются.

## Условия остановки

Изменился source/tool/runtime hash, нарушен split, кандидаты не воспроизводятся:
остановить run. Недостаточно семей, ошибки/неопределённость или неполный review:
показать причину, auto_accept не включать. Политика не расширяется задним числом.

Даже положительная численная граница в этом development-пилоте не закрывает
независимую calibration/приёмку #6/#38/#39. Runtime, contract v0.1, decisions,
confidence и ВМ неизменны. Публикуются только безопасные агрегаты и synthetic
fixtures; реальный bundle, формы, labels и predictions вне Git.
