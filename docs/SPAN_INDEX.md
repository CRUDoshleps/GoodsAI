# Индекс исходных фрагментов

BASE-002 / [#64](https://github.com/CRUDoshleps/GoodsAI/issues/64).
Внутренний `SpanIndex` готовит фрагменты для будущего выбора span ID моделью.
Он работает отдельно от predictor: категории, normalizer, verifier, confidence
и публичный input/output не меняются. Индекс не определяет значение атрибута.

```python
from goodsai.contracts import Product
from goodsai.span_index import SpanConfig, build_span_index

product = Product("synthetic", "761", "Неизвестный Zorion QX-900")
config = SpanConfig(max_spans=2048, max_window_tokens=8)
index = build_span_index(product, config)
fragment = next(entry for entry in index.entries if entry.surface == "Zorion QX-900")
assert index.resolve(fragment.span_id, product, config) == fragment
```

## Контракт и identity

Frozen dataclasses содержат:

- `SpanIndex`: algorithm version, source/config SHA-256, index ID, status,
  reason codes и tuple entries;
- `SpanEntry`: span ID, `title`/`description`, start/end, raw surface;
- `SpanConfig`: четыре числовых лимита.

Offsets — индексы Python Unicode code points, end исключительный. Это не
байтовые координаты и не JavaScript UTF-16. Для каждой entry выполняется
`source[start:end] == surface`. HTML/entities используют текущую visible→raw
карту; raw surface может включать исходную inline-разметку. Нельзя выбирать
половину entity, скрытый текст или span через block/hidden boundary.

Source hash включает оба неизменённых поля с различением null/пустой строки;
SKU/category/служебные flags в него не входят. Hash вычисляется порциями без
создания второй полной строки. Config hash включает все лимиты, index ID —
version/source/config. Span ID включает index ID, field и координаты. Повторы
одинаковой цитаты имеют разные ID. Изменённый источник/конфиг и неизвестный ID
дают ValueError при resolve; приблизительного lookup нет. При изменении
алгоритма требуется новая version. Индекс — доверенный внутренний объект,
не парсер недоверенного model payload и не доказательство смысловой связи.

## Генерация и ограничения

Алгоритм `span-index-1` обходит title, затем description. В каждом поле сначала
числовые spans, затем token windows, максимум W токенов. Есть варианты
неизвестных названий и кодов; brand dictionary не используется. Отрицание
сохраняется в исходном тексте и может входить в span. Это материал для общего
verifier, не разрешение принять отрицённый факт.

| Лимит | Default | Допустимый максимум |
| --- | ---: | ---: |
| raw characters title+description | 65536 | 262144 |
| entries | 2048 | 20000 |
| token window | 8 | 16 |
| raw/visible characters в span | 192 | 1024 |

Лимиты — положительные int, bool/float/неизвестные ключи не принимаются.
Большой source возвращает unavailable до HTML-map construction. Обход токенов
линеен при фиксированном W и max span length; все O(n²) интервалы не строятся.
Количество возвращаемых entries ограничено. HTML-map/список токенов ограничены
длиной входа. Любой сырой источник необходимо прочесть для source hash.

Статусы: available, truncated, unavailable. Reasons: source_length_limit,
span_count_limit, window_token_limit, span_length_limit, no_visible_spans.
Window/length limits явно отмечают исключённые более длинные интервалы.
При max_spans ранние title-кандидаты могут вытеснить description; truncated
запрещено интерпретировать как отсутствие факта. При пропуске selector обязан
отказаться или применить согласованный fallback, не подменять ближайшей цитатой.

## Проверка покрытия и ресурсов

Публичная синтетика: три карточки, шесть заранее заданных spans, включая
неизвестное имя, повтор цитаты, Unicode/HTML и отрицание:

```bash
python -m scripts.research.check_span_index --input tests/fixtures/span_index/products.jsonl --reference tests/fixtures/span_index/reference.json --output outputs/span-index-synthetic.json
```

Та же команда принимает **разрешённый reviewed development** text-only input
и отдельную span-разметку. `--config` — JSON с полями SpanConfig. Reference:

```json
{"reference_kind":"reviewed_development","records":[{"sku_id":"synthetic","spans":[{"field":"title","start":0,"end":7}]}]}
```

Фрагменты должны быть проверены на точные координаты человеком до реального
замера. Имя reference_kind — декларация caller, не доказательство независимости.
Blind/test reference этой командой не принимается. Gold/target не передаётся
генератору: сопоставление координат выполняется после построения индекса.

Отчёт содержит code/mapping/measurement/config/input/reference hashes, Git SHA
и dirty flag, число entries, status/reason counts, build time с tracemalloc и
peak traced Python bytes. Последний показатель не равен RSS и не включает
всю память процесса. В публичных aggregates нет SKU, raw text, entries или
evidence. Recall = matched exact field/start/end / все reference spans;
truncated/unavailable случаи не выкидываются из знаменателя. Без reference
recall=null. Целевой output должен быть новым.

Synthetic fixture даёт 6/6 exact spans. Это проверка механики; precision,
end-to-end F1, candidate recall реального каталога и качество будущей LLM
не измерены. Keep для следующего selector: invariants/ограничения выполнены;
решение о runtime integration зависит от отдельного end-to-end эксперимента.

## Проверки

```bash
python -m unittest discover -s tests -p 'test_span_index*.py' -v
```

14 tests проверяют identity, все limits, отсутствие ближайшего lookup,
повторы, кириллицу/emoji/combining marks, inline HTML/entities, скрытые блоки,
отрицание, null description, неизвестное название, source длиной 60000
символов, отсутствие изменений prediction и безопасный measurement report.
Данные/словарь/модель/gold для этих проверок не нужны.
