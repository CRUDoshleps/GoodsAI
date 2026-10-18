# Научная и open source опора

Проект использует статьи как основания проверяемых решений. Ссылки не являются
доказательством качества нашей реализации: каждый компонент всё равно проходит
локальное сравнение на зафиксированных данных.

## Решения, которые переносим

| Источник | Идея | Как применяем | Что не переносим вслепую |
| --- | --- | --- | --- |
| [OpenTag, KDD 2018](https://www.amazon.science/publications/opentag-open-attribute-extraction-from-product-profiles) | извлечение атрибутов как sequence tagging, active learning | компактный extractor и выбор сложных примеров на разметку | опубликованные метрики и доменные предположения |
| [MAVE, WSDM 2021](https://github.com/google-research-datasets/MAVE) | evidence spans и крупная схема product attributes | формат reference: значение связано с фрагментом текста | английский датасет как замену российскому gold |
| [OA-Mine, WWW 2022](https://www.amazon.science/publications/oa-mine-open-world-attribute-mining-for-e-commerce-products-with-weak-supervision) | open-world extraction и weak supervision | генерация кандидатов для длинного хвоста и группировка вариантов | слабые метки как независимый test |
| [Ask-and-Verify, EMNLP 2022](https://aclanthology.org/2022.emnlp-industry.9/) | сначала кандидаты, затем отдельная проверка | общий verifier после rules/encoder/LLM | заявленный прирост без нашего эксперимента |
| [FrugalGPT, 2023](https://arxiv.org/abs/2305.05176) | каскад моделей с учётом цены | cost-aware routing и ограничение сильной LLM | конкретные проценты экономии |
| [ExtractGPT](https://github.com/wbsg-uni-mannheim/ExtractGPT) | structured prompts и оценка LLM extraction | JSON schema, exact surface form, сравнение моделей | копирование кода без проверки лицензии файлов и адаптации |
| [RouteLLM](https://github.com/lm-sys/RouteLLM) | обучаемый router между моделями | ориентир для поздней версии router | новая зависимость до появления достаточного routing dataset |

## Open source, который можно использовать

Перед переносом кода нужно проверить LICENSE конкретного commit и записать
атрибуцию. На дату этого документа:

- OA-Mine и ExtractGPT публикуют код под Apache-2.0;
- RouteLLM публикует код под Apache-2.0;
- MAVE полезен как dataset/schema reference и находится в архивном read-only
  репозитории; условия данных проверяются отдельно.

Приоритет — повторить проверяемый **паттерн**, а не копировать чужой pipeline.
Самый практичный паттерн для этого проекта: candidate generation → verifier →
normalizer → calibrated decision.

## Исследовательские гипотезы

### H1. Rules сохраняют высокую точность на частых форматах

Сравнить rules с простым словарным baseline по каждому атрибуту. Ожидаемый
эффект: низкая цена и точные evidence. Риск: низкий recall на редких формах.

### H2. Отдельный verifier уменьшает ложные значения

Набор должен включать «совместимо с Samsung», аксессуар рядом с телефоном,
отрицание, два цвета, несколько объёмов, характеристику упаковки и чужую модель.
Сравниваются precision и число корректных отказов до/после verifier.

### H3. LLM на остатке улучшает recall дешевле полного LLM-run

Один frozen split прогоняется тремя способами: rules, LLM-only и cascade.
Считаются качество, число LLM-вызовов, токены, рубли и latency. Выбор делается
по Pareto frontier, а не по одному F1.

### H4. Малый encoder выгоден на повторяющихся категориях

Encoder оценивается только после независимого gold. Он остаётся в проекте,
если даёт полезный прирост или снижает стоимость LLM при допустимой сложности
поддержки и требованиях к памяти VM.

### H5. Active learning сокращает ручную разметку

Для разметки выбираются конфликты методов, низкая margin, новые значения и
редкие продавцы. Эффект измеряется как прирост качества на фиксированное число
проверенных пар, а не количеством собранных карточек.

## Экспериментальная матрица

| Variant | Rules | Encoder | LLM | Verifier | Цель |
| --- | --- | --- | --- | --- | --- |
| A | да | нет | нет | да | текущий baseline |
| B | да | нет | fast | да | минимальный рабочий гибрид |
| C | да | да | нет | да | локальная стоимость/скорость |
| D | да | да | fast/strong | да | максимальный контролируемый recall |
| E | нет | нет | strong | да | дорогой контрольный LLM-only вариант |

Все варианты получают одинаковый разрешённый текст, категорийную схему и
одинаковый verifier. Prompts и пороги замораживаются до открытия test.

## Формулы

Для пар `(SKU, attribute)`:

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * Precision * Recall / (Precision + Recall)
Coverage  = predicted_pairs / required_pairs
```

Для автоматического принятия:

```text
FalseAcceptRate = wrong_auto_accept / all_auto_accept
ReviewRate      = review_pairs / required_pairs
AbstainRate     = abstain_pairs / required_pairs
```

Стоимость:

```text
Cost_1000 = 1000 * total_inference_cost / processed_cards
LLMShare  = cards_sent_to_llm / processed_cards
```

Пример функции выбора route после калибровки:

```text
Utility(route) = Quality(route)
               - lambda_cost * Cost(route)
               - lambda_latency * P95(route)
               - lambda_risk * FalseAcceptRate(route)
```

Коэффициенты задаёт продуктовая политика. До этого показывается Pareto-таблица,
а не искусственно точный единый score.

## Правила честного вывода

- Development используется для решений и не становится test.
- AI-assisted review явно маркируется; просмотр ответа модели снижает
  независимость разметки.
- Процент без числителя, знаменателя, split и версии кода не публикуется.
- Улучшение общей метрики не скрывает деградацию отдельного обязательного поля.
- Новая категория оценивается отдельно.
- Научная ссылка объясняет дизайн, но результат доказывает наш эксперимент.
