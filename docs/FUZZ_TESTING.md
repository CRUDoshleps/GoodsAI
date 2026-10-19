# Генеративные проверки и минимальные регрессии

QA-003 / [#47](https://github.com/CRUDoshleps/GoodsAI/issues/47).
Набор использует только синтетические данные, без corpus из реальных карточек.
Установка test dependency и quick-прогон:

```bash
python -m pip install -e '.[serve,test,fuzz]'
python -m unittest discover -s tests/fuzz -v
```

Hypothesis зафиксирован на 6.170.1 в extra `fuzz`; runtime от него не зависит.
Property suite находится отдельно: обычный `discover -s tests` запускает
сохранённые regression examples, но для генерации нужна команда выше.
Отсутствие Hypothesis в property job является ошибкой импорта, а не skip.

В начале stdout печатаются profile, seed и `max_examples`. По умолчанию
`GOODSAI_FUZZ_PROFILE=quick`, `GOODSAI_FUZZ_SEED=20261019`. Quick: до 300
примеров на каждое из 11 свойств (до 3300 принятых примеров); nightly: до 2000
(до 22000). Hypothesis может исчерпать конечную стратегию раньше и выполняет
дополнительные вызовы при shrinking. Число примеров не является числом
проверенных комбинаций всех возможных входов.

Linux/macOS:

```bash
GOODSAI_FUZZ_PROFILE=nightly GOODSAI_FUZZ_SEED=20261020 python -m unittest discover -s tests/fuzz -v
```

PowerShell:

```powershell
$env:GOODSAI_FUZZ_PROFILE = 'nightly'
$env:GOODSAI_FUZZ_SEED = '20261020'
python -m unittest discover -s tests/fuzz -v
```

Сохранить Python version, Hypothesis version, profile, seed и revision теста.
Replay требует тех же версий: смена стратегии или Hypothesis меняет corpus.
При сбое Hypothesis уменьшает пример и печатает `@reproduce_failure` blob;
его можно временно вставить перед конкретным тестом на той же версии.
Минимальный случай переносится в `tests/test_fuzz_regressions.py` с описанием
причины. Локальная example database отключена: реальные карточки не добавляются.
В property assertions выводятся только сгенерированные синтетические строки.

## Проверяемые свойства

| Область | Инвариант и границы |
| --- | --- |
| Product schema | Произвольный малый JSON либо отклоняется через ValueError, либо проходит text-only round-trip; target-like поля всегда запрещены |
| JSONL | Unicode dicts round-trip без изменения bytes текста; пустые/повреждённые/необъектные строки отклоняются |
| HTML/Unicode | Полная длина position map; монотонные исходные координаты; decoded символ принадлежит raw span; combining marks, emoji, entities, hidden blocks и malformed tags |
| Extractor | На малом допустимом text input результат детерминирован, schema-valid; каждое значение имеет exact raw evidence; отсутствие значения означает явный abstain |
| Model span | Commercial name равен разрешённой нормализации видимого raw span |
| Numbers | Конвертация ml→L, пробел/NBSP/narrow NBSP, допустимые диапазоны и canonical idempotence; nonfinite/overflow дают ValueError |
| Output schema | Повреждённые типы status/category/attributes отклоняются через ValueError |
| Hidden facts | script/style/template/noscript не поставляют мощность/объём и другие кандидаты |
| Evidence tamper | null, не-объект, неверное поле, bool/negative/oversized offsets не проходят validator |
| Длинный текст | Отдельный фиксированный случай: 2000 повторов emoji + combining mark + entity, скрытая конфликтующая мощность; raw offsets остаются корректны |

Размеры property input ограничены стратегиями: строки до 160/512 символов,
JSON до 12 leaves, HTML до 24 chunks по ≤12 случайных символов плюс фиксированные
synthetic tags. Это лимиты тестового генератора, не новые runtime limits.
Unicode strategies используют scalar values; lone surrogates, глубокие JSON
и неограниченные размеры не объявляются проверенными. Per-example deadline —
500 ms quick / 1000 ms nightly. Job timeout — 10 минут, включая установку.

Workflow `Synthetic property tests` запускает quick на PR, nightly ежедневно
в 02:17 UTC (05:17 Москва) и позволяет ручной выбор profile/seed. Seed в CI
берётся из run number, если не передан вручную, и печатается до тестов. До merge
новый schedule не запускается: GitHub выполняет scheduled workflow из default
branch. Это CI-проверки кода; отдельная пользовательская automation не создаётся.

## Найденные ошибки

1. `evidence=None` приводил к AttributeError при `.get`, а не к contract reject.
   Исправлено проверкой формы evidence; также проверяются top-level record,
   status/category и элементы attributes до обращения к ним. Валидный контракт,
   допустимые значения, confidence и decisions не меняются.
2. `numeric('power_w', '1e999999', 'kW')` приводил к `decimal.Overflow` на
   умножении. Decimal conversion exceptions теперь превращаются в ValueError,
   согласованный с остальными ошибками normalizer. Это защита самого normalizer;
   правила извлечения научную нотацию не генерируют.

Оба случая сохранены в основном regression suite без зависимости от Hypothesis.
Это доказательство свойств и исправленных ошибок, не измерение P/R/F1,
семантической правильности всех spans или устойчивости к произвольной нагрузке.
Новые semantic invariants добавит VER-002 после согласования его контракта.
Правила конфигурации Hypothesis:
[settings, seed и limits](https://hypothesis.readthedocs.io/en/latest/settings.html),
[число примеров и shrinking](https://hypothesis.readthedocs.io/en/latest/explanation/test-case-count.html).

## Фактический локальный прогон

macOS arm64 / CPython 3.12.13 / Hypothesis 6.170.1: 125 основных tests,
3 reader tests, pip check и diff check прошли. Quick seed 20261019 и nightly
seed 20261020: все 11 свойств прошли; nightly занял около 21 секунды.
Новые метрики качества на реальных данных не вычислялись.
