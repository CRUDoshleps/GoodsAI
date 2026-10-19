# EVAL-006: замороженный протокол catalog-silver

Версия `catalog-silver-1`, seed `goodsai-silver-20261019-v1`.
Поручение Владислава: выполнить V0–V4 плана сравнения с attrx; claim `f04abec`,
Issue #91. Baseline: `977c5ed`. Протокол фиксируется **до новых predictions**.

## Границы и источники

Каталожные параметры — шумный reference `catalog_silver`, не human gold.
Ручной evaluator и публичный контракт v0.1 не меняются. Истинность и независимое
качество остаются N/A. Confidence heuristic, решения review/abstain.
auto_accept, внешние вызовы на реальных карточках и deployment не разрешаются.

Каталог — существующий `catalog_skus.parquet` из trusted EDA; descriptions —
разрешённый подготовленный text-only JSONL. Привязка source hashes проверяется.
Подготовка разделяет input/reference/metadata. Seller, vendor/model, params и
traffic никогда не входят в inference input. Raw pickle не используется.

В первой поставке mapping ограничен двумя действующими категориями 761/482.
Он задаётся явно по именам полей, без обучения по predictions. Пустое/неизвестное
поле = unknown; несколько несовместимых нормализованных значений = conflict.
Numeric conversion требует явной единицы из поля или единицы в имени mapping.
Неясные единицы не угадываются. Brand/model из каталога применяются только как
reference. Отличия коммерческого имени и каталожного кода остаются ограничением.

## Разделение и независимость

Переиспользовать проверенный EVAL-002 membership и checksums его источников и
артефактов; не разрывать найденные exact/normalized/near-duplicate семейства.
Старый validation = development_feedback. Quarantine/test_reserved, включая
резерв 40 карточек и их семейства, не материализуются в evaluation input.
Подготовка читает только metadata резерва. Изменившийся input/family/membership
без нового аудита — ошибка. Новые exposure ledgers добавляются явно и хешируются;
их семейства нельзя объявлять независимыми после смены seed.

Внутри допустимых development-групп предлагаются детерминированные роли
fit/calibration/diagnostic (целевые доли 70/10/20 **групп**); исходные назначения
не перезаписываются. Экспонированные группы остаются development независимо
от роли. Это не независимый train/test. Исходный validation показывается отдельно.
При малом числе групп фактические доли отличаются. Seller/brand isolation
проверяется отдельно: пересечения раскрываются, family split не называется
seller-disjoint. Отсутствующий идентификатор не образует общую fake-группу.

Независимая human-оценка требует своего freeze и разметчиков; #6/#38/#39/#40
не закрываются результатами этой задачи. Реальные тексты и labels вне Git.

## Метрики

Единица — SKU × обязательный атрибут. На known reference: совпадение value+unit
= TP; несовпадение = FP+FN; abstain/нет prediction = FN. Unknown/conflict не
получают искусственный FP, но входят в coverage и счётчики неоценённых кандидатов.
P/R/F1 называются agreement with catalog. Указывать assessed candidate fraction,
known/unknown/conflict support и доли ошибок/неподдерживаемых категорий.

Отдельный support matcher использует видимый текст, token boundaries, утверждённые
aliases и numeric unit/role patterns; он не импортирует Extractor и не смотрит
prediction. Результат supported/unsupported/unknown и reason. Это приближение,
не семантический reviewer. `recall_supported = TP_supported / known_supported`;
неподтверждённые и конфликтующие совпадения не удаляются из полного recall.
Доля unknown и пары для ручного development-аудита публикуются отдельно.

Срезы: attribute, category, category×attribute, text availability, seller (только
приватный hash), source/method, frequent/rare reference values; micro и macro.
Публичный report не содержит seller hash или значений товаров, только агрегаты.
Traffic = число строк query_clicks на SKU после полного суммирования; это proxy
наблюдений, не уникальные пользователи. Нельзя использовать max или произвольный
вес. При отсутствии файла — weighted metrics N/A. Нулевой суммарный вес — N/A.
Top-30 выбираются по этой metadata до inference; неподдерживаемые категории
учитываются в universe coverage, но не получают фиктивные predictions/метрики.

CI: 95%, percentile grouped bootstrap, 1000 повторов, фиксированный seed,
resampling целых family-групп. Минимум 20 групп; иначе N/A. Для парных дельт
используются одни и те же группы/веса. Это CI catalog agreement, не human quality.

## Калибровка и сравнение

Offline score: логистическая модель на raw heuristic score, method, attribute,
evidence field и reasons; SKU, каталог, gold и traffic не являются признаками.
Fit и calibration/diagnostic группы не пересекаются. Начальный gate: минимум
200 оценённых кандидатов, 20 групп и 20 примеров каждого класса в fit; отдельные
calibration/diagnostic требуют 10 групп и оба класса. Если gate не выполнен —
`insufficient_data`, не fitted probability. Isotonic/boosting не обязательны.
Для обучаемого extractor нужны отдельные OOF candidates; текущая реализация
rules не обучается. Сравнить Brier, ECE (10 равных bins), reliability и coverage.
Нет независимого human gold → auto_accept остаётся запрещён.

Все iterative runs — development/feedback. Сравниваются идентичные input/reference
и frozen configs. Новые схемы Тимура и LLM PR #90 — только после их готовности;
не копировать их код в evaluator. Реальные model/API расходы без решения команды
не производятся. Можно оценивать уже полученные совместимые prediction manifests.
Отсутствующий вариант = not_run с причиной, не нулевые метрики.

Калибровка неизменных predictions не меняет общий extraction F1. Пороговые
accepted-subset показатели — только shadow policy. Публиковать N/A для независимой
precision; arbitrary threshold не переносится в runtime.

Отклонять публикацию как «улучшение» при утечке/невалидном evidence, росте FP
критических полей или нарушении budgets. Выбор нового default не производится
этим PR. Текущий известный strict RED SOLUTION gate документируется и не скрывается.

## Результаты и воспроизводимость

Новые каталоги результатов создаются без overwrite. Manifest хранит версии,
SHA источников/протокола/mapping/config/code и output hashes, исходные роли и
известные ограничения. Отчёт latency различает первый и прогретый проход,
указывает p50/p95, throughput и окружение; повторный проход должен давать те же
значения. API calls/retries/tokens/cache/cost берутся из проверенного manifest
провайдера, а не оцениваются по числу кандидатов. Compute cost в рублях N/A.

В Git идут код, synthetic tests и только агрегированные reports/metrics.md,
reports/run_stats.json. Полные input/reference/predictions и support-review задания
остаются в outputs. Release использует существующие команды и переданные hashes.
Дедлайн 23.10 17:00 — предположение PDF до подтверждения организаторами.
