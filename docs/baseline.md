# GoodsAI E1: рабочий baseline

17 октября 2026 года. Реализован локальный пакетный Python CLI для категорий
`761` (смартфоны) и `482` (электрические чайники). Исследовательские документы
и скрипты предыдущего этапа сохранены. Фактические результаты текущего запуска
приведены в [baseline_results.md](baseline_results.md).

## Как устроено решение

1. `prepare` проверяет SHA-256 оригиналов и использует уже полученную локальную
   проекцию каталога. Читает только необходимые колонки пакетами, соединяет
   товары с описаниями по SKU. Вход содержит name каталога, description,
   category и source flags. Исходный второй title, продавец, vendor и model
   остаются в **отдельной** provenance-таблице для аудита и группировки.
2. Extractor принимает строго text-only контракт. Готовые target params,
   vendor/model, клики и непустые seller attributes отвергаются. Нет lookup
   готового значения по SKU. Ручные словари содержат общеупотребительные
   названия брендов и цветов, не автоматически выгруженные значения test.
3. Правила находят явные величины и контекст. Например, `8/256GB` даёт RAM и ROM,
   а «карта памяти до 512 ГБ» не становится встроенной памятью. Мощность ожидания
   не подменяет мощность нагревателя. Модель товара пока всегда получает явный отказ.
4. Нормализация использует Decimal: `1700 мл` → `1.7 L`, `2 400 Вт` → `2400 W`.
   Варианты GB/ГБ, десятичная запятая, NBSP поддерживаются. Конверсия TB пока
   не реализована. Неизвестный оттенок не сводится автоматически к базовому цвету.
5. Видимый HTML-текст имеет карту исходных координат. Атрибуты HTML, script/style
   и комментарии не используются. Теги и entities могут оказаться внутри raw
   evidence, если разделяют значение: это всё ещё точный span исходного поля.
6. Verifier проверяет schema, число/единицу/диапазон и совпадение raw span.
   Разные кандидаты одного атрибута дают `conflicting_evidence` и abstain.
   Все непустые результаты имеют `decision=review`, `confidence_kind=heuristic`.
   Score 0.75/0.8/0.85 — инженерное ранжирование, не калиброванная вероятность.
7. `predict` выдаёт один объект на входную строку, по всем requested attributes.
   Отказы содержат null и причину. Неизвестная категория получает отдельный статус;
   невалидная запись — `invalid_input`. Дубликат SKU, сломанный JSONL или ошибка
   реализации останавливают запуск, временный файл не заменяет прежний результат.

Перечень модулей:

| Файл | Назначение |
| --- | --- |
| `src/goodsai/baseline.json` | Версионированная схема двух категорий, бренды, цвета, seed |
| `contracts.py` | Строгий вход и инварианты результата |
| `data.py` | Inventory, пакетная подготовка и JSONL |
| `text.py` | Видимый HTML-текст и исходные offsets |
| `rules.py`, `normalize.py`, `verify.py` | Кандидаты, единицы, отказы и слияние |
| `annotation.py` | Группы товаров, splits и пустые задания разметки |
| `evaluate.py` | Метрики по ручной разметке |
| `runtime.py`, `cli.py` | Запуск, идентичность кода/конфигурации, время и память |

Никакой серверной инфраструктуры нет. `predict` и evaluator используют стандартную
библиотеку Python; для подготовки нужен PyArrow. DuckDB остаётся зависимостью
только старого EDA, в runtime baseline он не используется.

## Установка и запуск на текущем компьютере

Все команды выполняются из корня GoodsAI, Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m goodsai.cli prepare
.\.venv\Scripts\python.exe -m goodsai.cli predict --input data/processed/e1/pilot.jsonl --output outputs/baseline/predictions.jsonl
.\.venv\Scripts\python.exe -m goodsai.cli annotate
.\.venv\Scripts\python.exe -m goodsai.cli evaluate --predictions outputs/baseline/predictions.jsonl --gold data/gold/e1/tasks.jsonl --output outputs/baseline/metrics.json
```

`prepare` по умолчанию ожидает `outputs/eda/catalog_skus.parquet`, оригинальное
`data/raw/sku_desc.parquet` и `data/raw/.local_inventory.json`. Эти файлы уже
есть локально после EDA. Проекция считается доверенным локальным артефактом
предыдущего исследования; manifest фиксирует её SHA, но не является независимым
криптографическим доказательством соответствия pickle. Runtime baseline сам
pickle не десериализует и не принимает произвольные pickle как вход.

Прогон после установки не обращается к сети. Повторные команды обновляют
соответствующие производные файлы; перед работой над **заполненной** ручной
разметкой скопировать tasks в отдельный файл, чтобы `annotate` её не перезаписал.
Активация окружения и изменение ExecutionPolicy не нужны.

Пример собственного config: `python -m goodsai.cli --config path/to/config.json predict ...`.
Конфигурация должна сохранять поддерживаемые v0.1 атрибуты/контракт; этот флаг
не делает произвольные новые категории автоматически поддержанными правилами.

## Как воспроизвести на другом компьютере

Нужен Python 3.12+ и копия официальных данных, переданная отдельно от Git.
Создать venv (`py -3.12 -m venv .venv` на Windows или `python3.12 -m venv .venv`
на Linux), затем установить пакет. Runtime-зависимость зафиксирована:
`pyarrow==26.0.0`; версия baseline — `0.1.0`.

Если нет локального inventory/проекции, после подтверждения официального источника
данных выполнить:

```powershell
.\.venv\Scripts\python.exe -m goodsai.cli inventory
.\.venv\Scripts\python.exe scripts/research/inspect_pickle.py data/raw/skus.pkl outputs/eda/pickle_opcodes.json
.\.venv\Scripts\python.exe scripts/research/profile_catalog.py --trusted-pickle
.\.venv\Scripts\python.exe -m goodsai.cli prepare --inventory data/processed/source_inventory.json
```

Эти исследовательские шаги нужны однократно для подготовки из raw; заново выполнять
весь Parquet/click EDA не требуется. Fingerprints подтверждают неизменность копии,
а не её официальное происхождение. Нельзя применять `--trusted-pickle` к
неизвестному файлу. Специальный reader опирается на частный CPython API и проверен
на 3.12.6; на другой версии сначала выполнить его tests.

На Linux заменить `.\.venv\Scripts\python.exe` на `.venv/bin/python`.
Код учитывает различия Windows/Linux при измерении RSS, но на VM он пока
не запускался. Версию Python, wheel PyArrow и ресурсы VM проверить отдельно.

## Артефакты, остающиеся вне Git

```text
data/processed/e1/
  pilot.jsonl                  только разрешённый вход extractor
  provenance.jsonl             отдельные служебные метаданные; не подавать predict
  prepare_manifest.json        SHA входов/проекции, размеры выборок, время/RSS
data/gold/e1/
  split_manifest.jsonl         SKU → группа → split
  tasks.jsonl                  120 незаполненных заданий
  annotation_manifest.json     метод отбора и ограничения
outputs/baseline/
  predictions.jsonl
  predictions.manifest.json    хеши входа/выхода/кода/config, среда, покрытие, время/RSS
  predictions.repeat.jsonl     проверка детерминизма
  metrics.json                 сейчас N/A без ручной разметки
```

Запуск фиксирует git commit и dirty status плюс SHA кода/config: текущие изменения
ещё не коммитились. Один commit hash сам по себе не идентифицирует эту рабочую
копию. Предсказания детерминированы при одинаковом коде/config/входе; время и RSS
в manifest ожидаемо отличаются.

## Разметка и оценка

Созданы 5 383 связанные группы по нормализованному title, description и
vendor/model (метаданные используются **только для split**). Development содержит
5 541 SKU, validation — 3 167, test_reserved — 1 616. Группы с исследованными
EDA-карточками целиком перенесены в development. Без файла EDA-sample команда
восстанавливает его исходный детерминированный отбор; на текущих данных проверено
точное совпадение всех 400 ID двух категорий.

Наибольшая группа — 530 товаров: группировка консервативна и может объединять
карточки из-за общего шаблонного описания. Проверка близких дублей/семейств вручную
остаётся обязательной до объявленного независимого test. `test_reserved` пока
только резерв, не размеченный и не оценённый тестовый набор.

Задания: по 30 development и 30 validation каждой категории; в каждой части
поровну title-only и title+description, не более одной карточки на связанную
группу. Это стратифицированный пилот, а не репрезентативная выборка всего каталога.

Человек копирует задания в, например, `data/gold/e1/validation.reviewed.jsonl`,
оставляет только нужный split и заполняет:

- `annotation_status: "reviewed"`, `label_source: "manual"`, непустое `annotator`;
- для каждого атрибута `status`: `present`, `absent`, `ambiguous`, `unjudgeable`;
- при present — канонические строковое `value`, `unit` и evidence с полем,
  zero-based/end-exclusive offsets и точным raw text; при absent всё это null;
- значения должны подтверждаться только title/description, не знаниями о модели
  и не готовыми полями каталога. Сначала размечать вслепую без predictions.

Пример последующего запуска:

```powershell
.\.venv\Scripts\python.exe -m goodsai.cli evaluate --predictions outputs/baseline/predictions.jsonl --gold data/gold/e1/validation.reviewed.jsonl --output outputs/baseline/validation.metrics.json
```

Evaluator считает P/R/F1 и TP/FP/FN по атрибутам и категориям, micro/macro,
coverage, ложные значения и precision по диапазонам эвристического score.
Неверное значение даёт FP+FN. Неоднозначные пары исключаются с явным счётчиком;
пропущенное предсказание не исчезает из знаменателя. Слабые каталожные метки
не принимаются как manual gold. Незавершённые задания дают N/A. Совпадение
evidence проверяет происхождение, но не доказывает семантическую истинность.

Не реализованы калибровка, интервалы неопределённости и отдельная метрика
нормализации при условии правильного span; canonical exact-match уже входит
в P/R/F1. Для финальной защиты дополнить оценку после получения gold.

## Тесты и дальнейшая работа

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Fixture-данные синтетические. Проверяются скрытые targets, split-группы,
отсутствующие описания, HTML и offsets, units, диапазоны, RAM/ROM, отказы,
неоднозначные оттенки, детерминизм, повреждённый источник и формулы evaluator.

Приоритет команды: заполнить 120 заданий и перепроверить часть вторым человеком;
измерить validation-качество; разбирать реальные ошибки, затем добавить модель
товара, расширить проверенные словари и контекстные правила. К 23 октября провести
отдельно разрешённое сравнение с ML/LLM на том же split и с тем же verifier.
Обязательный список полей, канонические справочники, формат сдачи и допустимость
передачи карточек шлюзу остаются вопросами к организаторам.

Baseline закрывает первый ограниченный технический эксперимент; охват всего
каталога, официальный evaluator и производительность VM ещё не подтверждены.
