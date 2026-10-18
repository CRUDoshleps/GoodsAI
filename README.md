# GoodsAI

Извлечение характеристик товара из названия и описания. Текущая версия —
воспроизводимый rules baseline для смартфонов (`761`) и чайников (`482`).
Она возвращает нормализованное значение, точный фрагмент исходного текста и
явное решение `review` или `abstain`.

Проект развивается как гибридная система. Правила закрывают частые и хорошо
формализуемые случаи. Модель или LLM будет получать только сложный остаток.
Любой кандидат проходит одну проверку схемы, диапазона, конфликта и evidence.
LLM пока **не подключена к основному runtime**; это задача следующего этапа.

## Что работает сейчас

- CLI для подготовки данных, пакетного прогноза и оценки;
- HTTP API `/health` и `/predict` на порту 8000;
- правила для бренда, модели, памяти, экрана, батареи, мощности, объёма и цвета;
- нормализация единиц и словарных значений;
- точные offsets evidence в исходном тексте;
- отказ при конфликте или отсутствии значения;
- атомарная запись predictions и manifest;
- синтетическое демо из шести сценариев;
- unit и интеграционные проверки.

## Быстрый запуск

Требуется Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[serve,test]'
python -m goodsai.demo --output-dir outputs/demo
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[serve,test]"
python -m goodsai.demo --output-dir outputs/demo
```

Демо создаёт в `outputs/demo/` вход, predictions, manifest и отчёт проверки.
Ожидаемый итог — `6/6`. Это проверка сквозного сценария, а не оценка качества
на реальных товарах.

## Пакетный прогноз

Минимальная строка входного JSONL:

```json
{"schema_version":"0.1","sku_id":"demo-1","category_id":"761","title":"Смартфон Acme X1 8/256 ГБ, черный","description":null,"seller_attributes":[],"source_flags":[]}
```

Запуск:

```bash
goodsai predict \
  --input src/goodsai/examples/synthetic/products.jsonl \
  --output outputs/predictions.jsonl
```

Для каждого запрошенного атрибута ответ содержит одну запись. Найденное
значение имеет `decision=review`, эвристический `confidence`, метод и evidence.
При отсутствии или конфликте возвращается `decision=abstain` с `reason_codes`.
Текущий confidence не является вероятностью и не разрешает `auto_accept`.

## HTTP API

```bash
goodsai-serve --host 0.0.0.0 --port 8000
```

Проверка health:

```bash
curl http://127.0.0.1:8000/health
```

`POST /predict` принимает один JSON-объект по схеме из примера выше. Контракт
API временный до публикации точной схемы организаторов.

## Подготовка данных

Исходные данные не хранятся в Git. Поместите выданные файлы в `data/raw/`,
затем выполните:

```bash
goodsai inventory \
  --raw-dir data/raw \
  --output data/processed/source_inventory.json

goodsai prepare \
  --catalog outputs/eda/catalog_skus.parquet \
  --descriptions data/raw/sku_desc.parquet \
  --inventory data/raw/.local_inventory.json \
  --output-dir data/processed/e1
```

Подготовка включает проверку источников, выбор разрешённых текстовых полей,
приведение типов, контроль SKU, фиксацию provenance и manifest с hashes.
Готовые target-поля каталога не передаются extractor как подсказки.

## Оценка

```bash
goodsai evaluate \
  --predictions outputs/predictions.jsonl \
  --gold data/gold/e1/reference.jsonl \
  --output outputs/metrics.json
```

Главные метрики: precision, recall и F1 по атрибутам, coverage, доля отказов,
ошибки по категориям и методы извлечения. Метрика без независимой ручной
разметки не считается финальным качеством.

Последний development-замер на 20 AI-assisted human-reviewed карточках:
`69 TP / 0 FP / 14 FN`, `P=100%`, `R=83,1%`, `F1=90,8%`. Эта выборка
использовалась при разработке правил, поэтому результат нельзя выдавать за
независимый test. Подробности и более ранние срезы: [оценка](docs/EVALUATION.md).

## Проверки

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

На опубликованном Gitea `main` команда ранее получила 82 проверки на
Windows/Python 3.12.6. После каждого нового изменения проверки выполняются
заново в своей среде; этот README не заменяет свежий test report.

## Репозитории и ветки

- **GitHub** — рабочая разработка, feature-ветки и review.
- **Gitea организаторов** — только проверенные релизы для оценки.
- `main` в Gitea не используется как общая черновая ветка.

Новая работа начинается с [TASKS.md](TASKS.md): сначала задача переводится в
`IN_PROGRESS` отдельным commit, затем меняется код. Подробный процесс —
[CONTRIBUTING.md](CONTRIBUTING.md), выпуск — [docs/RELEASES.md](docs/RELEASES.md).

## Карта документации

| Файл | Назначение |
| --- | --- |
| [TASKS.md](TASKS.md) | очередь, владельцы, статусы и подробные подзадачи |
| [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) | актуальное техническое задание и критерии приёмки |
| [RESEARCH.md](RESEARCH.md) | научные и open source основания решений |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | что реально сделано и что ещё отсутствует |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | текущая и целевая архитектура гибридного pipeline |
| [docs/DATASET.md](docs/DATASET.md) | подготовка, ограничения и защита от утечки |
| [docs/EVALUATION.md](docs/EVALUATION.md) | дизайн эксперимента, формулы и честные метрики |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | трассировка требований и шести артефактов |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | запуск, диагностика и восстановление |
| [docs/RELEASES.md](docs/RELEASES.md) | GitHub → VM → Gitea и чек-лист релиза |

## Границы текущей версии

- поддерживаются две категории, а не весь каталог;
- seller attributes пока запрещены, чтобы не подмешать target;
- LLM/encoder отсутствуют в основном пути;
- `auto_accept` выключен до независимой оценки и калибровки;
- фактическое качество на независимом test неизвестно;
- публичный API временный;
- реальные данные, gold, predictions, модели, логи и секреты не входят в Git.

Эти ограничения превращены в задачи с владельцами и критериями готовности в
[TASKS.md](TASKS.md).
