# Предлагаемый контракт и политика решений

Статус: предложение по итогам аудита, не реализованный API. Реальные имена атрибутов и формат сдачи уточняются по датасету.

## Происхождение значения

Разделить `extractor` (метод получения кандидата) и `evidence.field` (поле карточки). Позиции задавать относительно неизменённого исходного поля: нумерация с нуля, Unicode code points, интервал `[start, end)`. При реализации UI учесть, что индексация строк JavaScript использует UTF-16; для emoji и других символов вне BMP потребуется преобразование координат.

Для title `Смартфон Samsung Galaxy S24 256GB Black`:

```json
{
  "schema_version": "proposal-0.1",
  "product_id": "sku_123",
  "category_id": "smartphone",
  "attribute": "storage_capacity",
  "raw_value": "256GB",
  "canonical_value": "256 ГБ",
  "extractor": "rule",
  "evidence": {
    "field": "title",
    "start": 28,
    "end": 33,
    "text": "256GB"
  },
  "confidence": null,
  "decision": "review",
  "reason_codes": ["uncalibrated"],
  "validation_flags": [],
  "versions": {
    "extractor": "rules_v0",
    "normalizer": "units_v0",
    "dictionary": "taxonomy_v0"
  }
}
```

Значение confidence здесь неизвестно: это иллюстрация, не результат модели. В финальном контракте задания требуется confidence; способ его вычисления и допустимость null для отказа необходимо определить до формирования submission. Внутреннее null не экспортировать без согласованного адаптера. Не подставлять 0.99 только потому, что сработало правило.

## Инварианты

1. Один итоговый результат на каждую обязательную пару `(product_id, attribute)`; неподходящие категории не увеличивают знаменатель coverage.
2. `original_field[start:end] == evidence.text`. Поле существует, границы допустимы. Для seller attributes использовать однозначный путь к значению, а не непредсказуемую сериализацию всего объекта.
3. В простом случае `raw_value == evidence.text`; более широкий контекст хранить отдельным полем. `canonical_value` получается из raw по версионированному правилу и не обязан дословно встречаться в тексте.
4. `extractor` принимает одно значение enum; `decision` — ровно одно из `auto_accept`, `review`, `abstain`.
5. `abstain`: итоговое значение null, причина обязательна. Диагностические кандидаты хранить отдельно, чтобы их не принять за заполненное поле.
6. При нескольких конфликтующих кандидатах хранить все их evidence; `review` не выбирать победителя произвольно.
7. Нормализация TB/GB, цвета, вариантов моделей и единиц следует справочнику задания; не считать похожие строки эквивалентными без политики. RAM и storage — разные атрибуты.
8. Подтверждение цитатой означает наличие текста, а не истинность характеристики в реальном мире. Оценка проверяет соответствие задаче и эталону.

## Единый gate

```text
extract candidates from available permitted methods
normalize candidates using category schema
check source offsets, types, units, attribute context and conflicts
if candidates conflict:
    review with all candidates
elif no supported valid candidate:
    abstain with reason
elif calibrated confidence meets selected attribute threshold:
    auto_accept
elif candidate is usable for human checking:
    review
else:
    abstain
```

Rules, encoder, LLM и cache hit проходят одинаковые финальные проверки. Валидность JSON, найденная цитата и высокая уверенность сами по себе не заменяют остальные проверки.

## Метрики

- `TP`: каноническое значение совпало с gold для пары SKU–атрибут; неверное значение при имеющемся gold даёт и FP, и FN. Отказ при имеющемся gold даёт FN. Для многозначных атрибутов заранее определить set matching.
- Неизвестная разметка исключается из supervised quality-метрик с явным отчётом её объёма; не превращается в отрицательный gold. Подтверждённое отсутствие значения обрабатывается отдельно.
- `auto_coverage = число пар auto_accept / число всех применимых обязательных пар`.
- `auto_precision = верные auto_accept / оцениваемые auto_accept`. При нулевом знаменателе — N/A и count=0, не 100%.
- Review, abstain и auto_accept считать по тому же набору пар; отдельно можно показывать долю SKU со всеми заполненными полями.
- Таблицы качества всех финальных кандидатов и автоматически принятых значений разделить; основной протокол сверить с официальной оценкой.
- Пороги выбирать на validation, фиксировать до test; показывать число примеров и интервалы неопределённости для auto_precision.
- LLM-call rate указывать отдельно по SKU и парам атрибутов; сравнивать полный пайплайн на одном test. Учесть повторы, cache и локальный inference в расчёте времени и расходов.
