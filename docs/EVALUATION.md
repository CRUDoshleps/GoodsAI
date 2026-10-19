# Оценка качества, стоимости и надёжности

## Единица оценки

Основная единица — пара `(SKU, attribute)`. Для каждой пары gold определяет,
есть ли характеристика, какое значение допустимо и каким текстом оно
подтверждается. `ambiguous` не включается в обычные TP/FP/FN и показывается
отдельно.

## Классификация результата

| Prediction | Gold | Класс |
| --- | --- | --- |
| правильное значение | present | TP |
| неверное значение вместо правильного | present | FP + FN |
| значение при отсутствии характеристики | absent | FP |
| abstain/нет значения | present | FN |
| abstain | absent | TN, отдельно от P/R/F1 |

Exact evidence проверяется программно по исходному полю и offsets. Семантическую
связь с атрибутом основного товара оценивает reviewer; совпавший span сам по себе
её не доказывает. Evaluator сопоставляет canonical value+unit с reviewed reference;
отдельной полной семантической метрики evidence сейчас нет.

## Формулы

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2PR / (P + R)
Coverage  = predicted_required_pairs / all_required_pairs
```

Micro-метрика суммирует пары. Macro сначала считает показатель по полю или
категории и усредняет. Текущий evaluator выдаёт micro, per-attribute/category,
category×attribute и macro_attribute_f1; отдельный macro-category не реализован.
В evaluator candidate coverage считается по **judged** парам. Покрытие по всем
запрошенным парам из prediction manifest показывается отдельно; ambiguous/
unjudgeable и кандидаты на них не исчезают из диагностического отчёта.

Для решений:

```text
AutoAcceptPrecision = correct_auto_accept / all_auto_accept  # N/A сейчас: auto_accept нет
ReviewRate          = review_pairs / required_pairs
AbstainRate         = abstain_pairs / required_pairs
EvidenceExactRate   = exact_evidence / predicted_pairs
```

Для ресурсов:

```text
CostPer1000 = 1000 * inference_cost / cards
LLMShare    = cards_with_llm_call / cards
Throughput  = cards / elapsed_seconds
```

ReviewRate, EvidenceExactRate и CostPer1000 выше — определения для отчётности,
не обещание отдельных готовых полей evaluator. Сейчас вызовов моделей нет,
API-расход равен нулю; стоимость compute в рублях не измерена.

## Обязательные срезы

- категория и атрибут;
- title-only и title+description;
- частые и редкие значения;
- длина текста;
- продавец, если идентификатор допустим только для аналитического slice;
- exact rule, model/LLM и fallback route;
- known и новая категория;
- conflict, ambiguous и корректный abstain.

## Исторические результаты

Все значения ниже получены до независимого test и не являются финальной
оценкой качества каталога.

| Набор | Cards / judged | TP / FP / FN | P / R / F1 | Ограничение |
| --- | ---: | ---: | ---: | --- |
| reviewed-v2, исторический baseline | 12 / 67 | 29 / 1 / 21 | 96,7 / 58,0 / 72,5% | теперь development_feedback, не holdout |
| M2 до policy fixes | 20 / 115 | 58 / 3 / 25 | 95,1 / 69,9 / 80,6% | development, использовался для решений |
| M2 после policy fixes | 20 / 115 | 69 / 0 / 14 | 100 / 83,1 / 90,8% | тот же development, не независимый test |

M2 содержит 120 полей: 83 present, 32 absent, 5 ambiguous. В P/R/F1 входят
115 judged решений. Улучшение после просмотра ошибок показывает, что fixes
работают на этом development, но не оценивает перенос на новые карточки.
Полная последовательность M1/M2, per-attribute/category таблицы, SHA reference,
snapshots и команды — в [RESULTS.md](RESULTS.md). Сам факт
`evaluation_status=manual_reference` не означает независимость: происхождение
AI-assisted и использование для разработки фиксируются отдельно.

## Организаторский прогон 18 октября

По сохранённым скриншотам оценённые технические критерии дали 17,17/20.
Блок качества результата оставался без оценки; продуктовый этап был 10/10,
но платформа не объяснила его включение в общий балл. Основные замечания:

- нет реального ML/LLM route в основном pipeline;
- thresholds и ветви решений недостаточно конфигурируемы;
- готовый predictions-файл и отчёт метрик слабо связаны с README/runtime;
- нужны более явные end-to-end сценарии и release evidence;
- эксплуатационные риски: pickle-import, логи и временные файлы.

Атомарная запись и model rules после этого были улучшены. Интеграция LLM,
независимый gold и полный release artifact остаются открыты.

## Протокол эксперимента

Для независимой разметки используется [human-review protocol](HUMAN_GOLD.md).
Инструменты/пустые формы не являются gold; одиночная разметка и AI-assisted
ответы не заменяют два независимых человеческих ответа с adjudication.

Перед новым независимым sampling проверить [аудит split EVAL-002](SPLIT_AUDIT.md).
Исходный E1 split и validation нельзя объявлять независимым holdout. Аудитор
выпускает отдельный filtered partition + карантин без замены старых данных;
blind reserve проверяется только алгоритмически по metadata/fingerprints.

1. Зафиксировать commit, конфиг, prompts и входные hashes.
2. Зафиксировать split и версию annotation guideline.
3. Выполнить A/B на одинаковых парах и одном verifier.
4. Сохранить raw predictions, manifest, metrics и error table.
5. Посчитать доверительный интервал bootstrap по SKU/groups.
6. Проверить деградации каждого обязательного атрибута.
7. Отдельно показать цену, latency, LLMShare и ошибки API.
8. До просмотра test выбрать финальный вариант и пороги.
9. Открыть test один раз и опубликовать результат без донастройки.

## Release gate для нового метода

До EVAL-001 gate задаётся относительным сравнением:

- нет новых нарушений schema/evidence;
- precision критических полей не падает на validation;
- прирост recall подтверждён списком исправленных FN;
- regressions имеют объяснение и отдельные тесты;
- стоимость и latency измерены;
- отказ LLM не ломает rules route;
- результат воспроизводится из clean environment.

После независимого gold команда фиксирует числовые пороги. Запрещено выбирать
порог по test или объявлять heuristic confidence калиброванной вероятностью.

## Ошибки, которые показываем отдельно

- brand в фразе «совместимо с Samsung»;
- характеристика чехла или комплекта вместо телефона;
- два объёма без понятной роли RAM/storage;
- два несовместимых цвета;
- модель другого товара в описании;
- значение за границами категории;
- формат/единица, которых нет в справочнике;
- значение LLM без точного evidence;
- новая категория;
- пустой или повреждённый вход.

## Reference новых категорий (CONF-003 candidate)

[DONE — feature candidate] В конфиге v2 enum-словарь ограничивает извлечение,
но не допустимый набор human reference. Новое правильное значение из validation
не должно вызывать ошибку evaluator или исчезать из знаменателя recall: если
система его не нашла, это FN. Отдельная normalize_reference сохраняет такое
значение, не расширяя обученный inference-словарь. Numeric canonical form и
единицы по-прежнему проверяются. Default config и прежние категории не меняются.

Явный hash-bound mapper и запуск `goodsai.registry_evaluation` описаны в
[CATEGORY_REGISTRY](CATEGORY_REGISTRY.md). Несопоставленные target labels
становятся unjudgeable; отчёт показывает excluded и judged/requested counts.
P/R/F1 на сопоставленной части не выдаются за полноту всей новой схемы.
Разрешён только весь заранее declared validation split, без train/test SKU.
Pending/silver не переименовываются в reviewed manual. Сам факт успешного
mapping/evaluate не доказывает независимость разметки и не разрешает auto_accept.
