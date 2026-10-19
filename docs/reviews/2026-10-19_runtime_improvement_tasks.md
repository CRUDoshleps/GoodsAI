# Дополнительные задачи runtime и интерфейса

Команда: tunaIT. Дата: 19 октября 2026 года. Задача: GOV-004 #57.
База аудита: GitHub main `1754970c4e0177fa6d3ef7a2dffa71c9a902cbed`.

Это план работ. Новые функции не реализованы и не дают подтверждённого
прироста качества, скорости или баллов. Оценки effort и критерии keep/drop
предлагаются для эксперимента и фиксируются владельцем до его запуска.

## Что важно закончить прежде всего

1. Независимый human gold и split audit: EVAL-001/002/003.
2. Общий evidence/relation verifier: VER-002.
3. Настоящий model/LLM route и сравнение с baseline: ML-001, LLM-003, EVAL-005.
4. Рабочая review-очередь и чистый запуск: PRODUCT-002, ENV-002.

Эти задачи уже существуют. Новый список не заменяет их и не переносит
незакрытые критерии в другие Issues. Development checkpoint шести артефактов
уже подготовлен; это не независимая оценка и не официальная полная сдача.

## Пробелы текущей версии

| Область | Что подтверждает пробел | Какой результат нужен |
| --- | --- | --- |
| Категория | `Product` допускает null category_id, но `Extractor.predict` выбирает схему только по category_id | Подсказка по тексту с отказом и проверкой неизвестного класса |
| Повторный inference | В `src/goodsai/verify.py` нет model cache; LLM-003 описывает route, API-002 — resume | Сохранение точных model-кандидатов и безопасная инвалидация |
| Словари | `baseline.json` содержит aliases, но текущий API не задаёт операторский workflow их публикации | Draft, проверка влияния, approval и rollback версии |
| Дрейф | Evaluator считает результат запуска; OPS-002 собирает telemetry без контракта сравнения окон | Frozen baseline, диагностика сдвига и понятное действие |
| Очередь | PRODUCT-002 задаёт review и фильтры; ACTIVE-001 — sampling для обучения | Объяснимый порядок решения задач при ограниченном времени оператора |

Чтение README, документа и готового отчёта само по себе не доказывает
качество компонента. Сравнение разных split, разных единиц оценки или
catalog-derived labels не считается подтверждённым улучшением GoodsAI.

## Новые задачи

| ID / Issue | P | Результат | Блокер | Effort / риск |
| --- | --- | --- | --- | --- |
| [ML-002 #58](https://github.com/CRUDoshleps/GoodsAI/issues/58) | P1 | Keyword/CPU baseline для category suggestion, unknown/uncertain → отказ | #10, #6, #7, #44 | M / выбор неверной схемы |
| [LLM-004 #59](https://github.com/CRUDoshleps/GoodsAI/issues/59) | P1 | Exact request cache и объединение одновременных дублей, повторная downstream-проверка | #25, #37, #43, #49 | S для аудита, M для cache / stale reuse |
| [PRODUCT-005 #60](https://github.com/CRUDoshleps/GoodsAI/issues/60) | P1 | UI предложений по словарю, impact diff, новая версия и rollback | #44, #37, #50 | M / распространение ошибочного alias |
| [OPS-003 #61](https://github.com/CRUDoshleps/GoodsAI/issues/61) | P1 | Drift report с support, compatible baseline, alert reason и действием | #49, #24; model reasons после #37/#45 | M / ложные сигналы |
| [PRODUCT-006 #62](https://github.com/CRUDoshleps/GoodsAI/issues/62) | P2 | Review priority по severity, age и разрешённым агрегатам спроса | #50, #10, #49 | M / starvation и искажённый приоритет |

S — до одного дня инженерной работы, M — ориентировочно 1–3 дня;
сбор разметки и время участников учитываются отдельно. Все пять задач
созданы без исполнителя и имеют status:blocked. Они не являются claims
на реализацию и не включают внешние вызовы по умолчанию.

### Как проверить полезность

| Задача | Контроль | Измерение и решение |
| --- | --- | --- |
| ML-002 | Переданная категория / keyword baseline | Precision и coverage suggestion, macro-F1, OOD false assignment, downstream ошибки, CPU p95/RSS. Keep только после согласованного quality gate; explicit category не заменяется |
| LLM-004 | Тот же stream без cache | Cold/warm calls, tokens, cost, overhead и полное совпадение value/unit/evidence/decision. Screening: ≥10% меньше cold calls; unsafe hit запрещает включение |
| PRODUCT-005 | Ручная правка конфигурации | Время и ошибки на 20 synthetic словарных правках, воспроизводимость audit и rollback. Небезопасная публикация → оставить только proposals |
| OPS-003 | Стационарный frozen stream | False alarms, обнаружение заданных perturbations и задержка. Без labels нельзя называть proxy shift падением precision |
| PRODUCT-006 | FIFO и severity+age | Корректные обязательные пары/минуту, critical corrections, p90 ожидания и обслуживание редких задач. Demand weighting остаётся только при доказанной пользе |

Ни один из этих экспериментов в GOV-004 не запускался. Предложенные
критерии не являются измеренными метриками. Детальные steps, приёмка,
отрицательные примеры и keep/drop находятся в соответствующих Issues.

## Уточнения существующих задач

| Issue | Добавленная конкретика | Что не меняется |
| --- | --- | --- |
| [ML-001 #16](https://github.com/CRUDoshleps/GoodsAI/issues/16) | Готовый multilingual span baseline до обучения; реальная интеграция; offsets; artifact license/revision, offline load и CPU/RSS | Encoder остаётся только при измеримой пользе; task owner/status сохранены |
| [LLM-003 #25](https://github.com/CRUDoshleps/GoodsAI/issues/25) | Различать fake tests и разрешённый live trace; external JSONL; реальный usage; provider capabilities и причины отказов | Никаких live calls в GOV-004, исходные бюджет/data gates сохранены |
| [EVAL-005 #40](https://github.com/CRUDoshleps/GoodsAI/issues/40) | Пофакторные ablations, extraction/normalization/attachment отдельно, provenance labels, cold/warm и цена ошибки category routing | Frozen validation, blind test без настройки и исходные зависимости |
| [PRODUCT-002 #50](https://github.com/CRUDoshleps/GoodsAI/issues/50) | Настоящий backend и сохранение после reload; конкурирующие candidates; browser offsets и safe HTML; versioned export | Audit и exact evidence обязательны; новая очередь не дублируется |

Это дополнения приёмки, а не заявление о завершении этих функций.
Существующие владельцы, labels, статусы и claims не менялись.

## Границы решений

- Title/description остаются разрешённым источником фактов. Готовые параметры,
  vendor/model, gold и clicks не используются как признаки extractor.
- Category suggestion требует решения SPEC-001; неизвестный класс не
  превращается принудительно в ближайшую поддержанную категорию.
- Любой cache hit заново проходит актуальные normalizer/verifier/decision.
  Близость похожих SKU не разрешает перенос значений.
- Справочники расширяются после review; fuzzy similarity не доказывает alias,
  а неизвестный бренд не становится фактом из памяти модели.
- Click aggregates разрешены только отдельным аналитическим профилем после
  согласования; они меняют очередь человека, а не prediction.
- Heuristic confidence не является вероятностью, автоматический приём
  остаётся выключенным до EVAL-004.
- Не добавляются OCR, изображения, обогащение по аналогам, скрытая загрузка
  данных/моделей, внешняя telemetry и автоматический retrain.
- Код, данные, тестовый резерв, VM, модели и действующая конфигурация в этой
  задаче не меняются. Статусы DONE и merge остаются за интегратором.

## Проверка планирования

- Каждая новая задача имеет ровно один type, priority и status label.
- Новые IDs не пересекаются с TASKS и Issues #35–#54.
- Индекс содержит ссылки на все новые Issues; зависимости не образуют цикла.
- Для каждого улучшения есть контроль, измерение, ограничение и keep/drop.
- В задачах и документах отсутствуют неподтверждённые claims о качестве,
  пользовательские отзывы, тексты реальных карточек и секреты.
- PR #55 и чужие claims не изменялись; возможные пересечения TASKS при merge
  разрешаются с сохранением обоих списков задач.
