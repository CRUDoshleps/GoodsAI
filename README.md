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

Требуется Python 3.12+. Команды выполняются из корня checkout с полной Git-историей
(без `--depth`): comparison tests используют базовый commit `5f77d81`.
Датасеты, ключи и LLM для этого сценария не нужны.

```bash
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m pip check
.venv/bin/python -m goodsai.demo --output-dir outputs/demo-first-run
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[serve,test]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/demo-first-run
```

Если `.venv` уже существует, сначала проверьте её Python; не создавайте её заново
поверх рабочего окружения. Системный `python3` на VM может быть 3.10; используйте
имеющуюся `.venv/bin/python` версии >=3.12. Вариант с установленным `uv` описан
в [RUNBOOK](docs/RUNBOOK.md). Активация окружения не требуется.

Демо создаёт в `outputs/demo-first-run/` `input.jsonl`, `predictions.jsonl`,
`predictions.manifest.json` и `summary.json`. В stdout и summary ожидаются
`checks_passed=6`, `checks_total=6`, `rows=6`, `llm_calls=0`.
Повторять с **новым** `--output-dir`: существующий каталог не перезаписывается.
Это проверка сквозного сценария, а не P/R/F1 на реальном каталоге.

## Пакетный прогноз

Минимальная строка входного JSONL:

```json
{"schema_version":"0.1","sku_id":"demo-1","category_id":"761","title":"Смартфон Samsung Demo X82 8/256GB черный","description":null,"seller_attributes":[],"source_flags":[]}
```

Запуск:

```bash
.venv/bin/python -m goodsai.cli predict \
  --input src/goodsai/examples/synthetic/products.jsonl \
  --output outputs/predictions.jsonl
```

Для каждого запрошенного атрибута ответ содержит одну запись. Найденное
значение имеет `decision=review`, эвристический `confidence`, метод и evidence.
При отсутствии или конфликте возвращается `decision=abstain` с `reason_codes`.
Текущий confidence не является вероятностью и не разрешает `auto_accept`.

Например, запись `model` для строки выше выглядит так (это один элемент
`attributes`, а не полный ответ):

```json
{"attribute":"model","value":"Demo X82","unit":null,"confidence":0.8,"confidence_kind":"heuristic","decision":"review","method":"rule","rule_id":"model.phone-title.v2","evidence":{"field":"title","start":17,"end":25,"text":"Demo X82"},"reason_codes":[]}
```

`not_found_by_rules` означает отсутствие подходящего кандидата;
`conflicting_evidence` — несовместимые значения. В обоих случаях значение `null`
и решение `abstain`. Evidence содержит координаты в исходном тексте, но не
гарантирует смысловую правильность извлечения. Примеры всех шести ответов доступны
после демо в `predictions.jsonl`.

Для PowerShell заменяйте `.venv/bin/python` на `.\.venv\Scripts\python.exe`,
многострочную Bash-команду вводите одной строкой.

## HTTP API

```bash
.venv/bin/python -m goodsai.api --host 0.0.0.0 --port 8000
```

Проверка health:

```bash
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  --data '{"schema_version":"0.1","sku_id":"demo-1","category_id":"761","title":"Смартфон Samsung Demo X82 8/256GB черный"}'
```

`POST /predict` принимает один JSON-объект по схеме из примера выше. Контракт
API временный до публикации точной схемы организаторов. Swagger UI — `/docs`.
В PowerShell используйте `curl.exe` или `Invoke-RestMethod`; повторный запуск
сервиса не нужен, если порт уже обслуживает systemd unit.

## Подготовка данных

Этот путь нужен только для локальных выданных данных и не является условием
запуска демо. Требуются `skus.pkl`, `sku_desc.parquet`, `query_clicks.parquet`
в `data/raw/` и **готовая доверенная проекция** `outputs/eda/catalog_skus.parquet`.
Существующие источники/EDA не пересоздавайте: сначала проверьте provenance и hashes.
Подготовка отсутствующей проекции описана в [DATASET](docs/DATASET.md#подготовка-проекции).

```bash
.venv/bin/python -m goodsai.cli inventory \
  --raw-dir data/raw \
  --output data/processed/source_inventory.json

.venv/bin/python -m goodsai.cli prepare \
  --catalog outputs/eda/catalog_skus.parquet \
  --descriptions data/raw/sku_desc.parquet \
  --inventory data/processed/source_inventory.json \
  --output-dir data/processed/e1-next
```

Подготовка включает проверку источников, выбор разрешённых текстовых полей,
приведение типов, контроль SKU, фиксацию provenance и manifest с hashes.
Готовые target-поля каталога не передаются extractor как подсказки.
Здесь создаются `pilot.jsonl`, `provenance.jsonl`, `prepare_manifest.json`.
Указывайте новый каталог вместо перезаписи существующего E1; `prepare` сам
не резервирует весь каталог от повторной записи. Старый inventory подтверждает
неизменность локальной копии, новый фиксирует текущее состояние и не заменяет
проверку происхождения файлов.

## Оценка

Без gold можно получить только отчёт `N/A`:

```bash
.venv/bin/python -m goodsai.cli evaluate --predictions outputs/demo-first-run/predictions.jsonl --output outputs/demo-first-run/quality-unavailable.json
```

Для реальных метрик нужны локальные reviewed-метки и predictions **тех же**
карточек. Нельзя сравнивать synthetic predictions с реальным reference.
Воспроизводимая команда для утверждённого M2 development, SHA reference и
ограничения приведены в [индексе результатов](docs/RESULTS.md#воспроизведение-m2).

Главные метрики: precision, recall и F1 по атрибутам, coverage, доля отказов,
ошибки по категориям и методы извлечения. Метрика без независимой ручной
разметки не считается финальным качеством.

Последний development-замер на 20 AI-assisted human-reviewed карточках:
`69 TP / 0 FP / 14 FN`, `P=100%`, `R=83,1%`, `F1=90,8%`. Эта выборка
использовалась при разработке правил, поэтому результат нельзя выдавать за
независимый test. Подробности: [результаты и provenance](docs/RESULTS.md),
[правила оценки](docs/EVALUATION.md).

## Проверки

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

На опубликованном Gitea `main` команда ранее получила 82 проверки на
Windows/Python 3.12.6. После каждого нового изменения проверки выполняются
заново в своей среде; этот README не заменяет свежий test report.

## Сборка комплекта артефактов

Проверка упаковки без датасетов (PowerShell, новый output-dir):

```powershell
.\.venv\Scripts\python.exe scripts/release/build_release.py smoke --output-dir outputs/release/smoke-next
.\.venv\Scripts\python.exe scripts/release/build_release.py verify --bundle outputs/release/smoke-next
```

На Linux использовать `.venv/bin/python`. Ожидается `synthetic_smoke`, затем
`verified`: это не финальная сдача. Сборка шести реальных артефактов по frozen
spec, статусы incomplete/N/A и правила публикации — в
[ARTIFACT_BUNDLE.md](docs/ARTIFACT_BUNDLE.md).

Подготовка реальных development-артефактов из уже существующих локальных
E1/EDA caches, на чистом Git checkout:

```powershell
.\.venv\Scripts\python.exe -m scripts.release.prepare_delivery --report-date 2026-10-19 --output-dir outputs/delivery/checkpoint-next
```

Команда сохраняет predictions, reviewed M2-метрики, EDA-сводку, Markdown-слайды,
frozen spec и полный проверенный bundle. Закрытые и смешанные test/validation
семейства исключаются; это development checkpoint, не весь каталог и не
независимая итоговая оценка. Папка должна быть новой. Prerequisites описаны в
[инструкции сборки](docs/ARTIFACT_BUNDLE.md#подготовка-реального-development-checkpoint).

Готовый [checkpoint 19.10.2026](docs/delivery/2026-10-19/README.md): EDA,
метрики, PDF/Markdown-слайды, manifest и инструкция к локальному полному архиву.
Реальный batch содержит 2198 development SKU; закрытые группы исключены.

## Репозитории и ветки

- **GitHub `main`** — основная интеграционная ветка после review.
- **GitHub feature-ветки** — вся незавершённая работа.
- **Gitea `main`** — автоматическое fast-forward зеркало GitHub `main`.

Каждый push или merge в GitHub `main` запускает Actions workflow. Если Gitea
содержит отдельный commit, зеркало безопасно останавливается и ничего не
перезаписывает. Поэтому в GitHub `main` должны попадать только проверенные PR.

Новая работа начинается с [TASKS.md](TASKS.md): сначала задача переводится в
`IN_PROGRESS` отдельным commit, затем меняется код. Подробный процесс —
[docs/TASK_MANAGEMENT.md](docs/TASK_MANAGEMENT.md), совместная разработка —
[CONTRIBUTING.md](CONTRIBUTING.md), выпуск — [docs/RELEASES.md](docs/RELEASES.md).

## Карта документации

Статусы результатов, источники цифр и оформление материалов проверяются по
[CONTENT_STYLE](docs/CONTENT_STYLE.md); для слайдов есть отдельный
[checklist защиты](docs/PRESENTATION_REVIEW.md).

| Файл | Назначение |
| --- | --- |
| [TASKS.md](TASKS.md) | очередь, владельцы, статусы и подробные подзадачи |
| [docs/TASK_MANAGEMENT.md](docs/TASK_MANAGEMENT.md) | labels, Issue forms, claim commit, review и закрытие |
| [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) | актуальное техническое задание и критерии приёмки |
| [RESEARCH.md](RESEARCH.md) | научные и open source основания решений |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | что реально сделано и что ещё отсутствует |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | текущая и целевая архитектура гибридного pipeline |
| [docs/SPAN_INDEX.md](docs/SPAN_INDEX.md) | внутренние исходные spans, limits и отдельный замер покрытия |
| [docs/DATASET.md](docs/DATASET.md) | подготовка, ограничения и защита от утечки |
| [docs/EVALUATION.md](docs/EVALUATION.md) | дизайн эксперимента, формулы и честные метрики |
| [docs/RESULTS.md](docs/RESULTS.md) | происхождение, snapshots и воспроизведение M1/M2 |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | трассировка требований и шести артефактов |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | запуск, диагностика и восстановление |
| [docs/RELEASES.md](docs/RELEASES.md) | GitHub → Gitea → VM и чек-лист релиза |
| [docs/ARTIFACT_BUNDLE.md](docs/ARTIFACT_BUNDLE.md) | offline-сборщик шести артефактов, hashes и проверка переноса |

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
