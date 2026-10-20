# GoodsAI

Извлечение характеристик товара из названия и описания. Текущая версия —
воспроизводимый rules baseline для смартфонов (`761`) и чайников (`482`).
Она возвращает нормализованное значение, точный фрагмент исходного текста и
явное решение `review` или `abstain`.

Проект развивается как гибридная система. Правила закрывают частые и хорошо
формализуемые случаи. Модель или LLM будет получать только сложный остаток.
Любой кандидат проходит одну проверку схемы, диапазона, конфликта и evidence.
LLM подключается **только явно** флагом `--llm`: она получает пропуски правил
и проходит проверки evidence и принадлежности значения товару. По умолчанию
runtime — только правила; сравнительное качество LLM ещё не подтверждено.

## Что работает сейчас

- CLI для подготовки данных, пакетного прогноза и оценки;
- HTTP API `/health` и `/predict` на порту 8000;
- правила для бренда, модели, памяти, экрана, батареи, мощности, объёма и цвета;
- нормализация единиц и словарных значений;
- точные offsets evidence в исходном тексте;
- отказ при конфликте или отсутствии значения;
- атомарная запись predictions и manifest;
- синтетическое демо из шести сценариев;
- opt-in LLM-fallback для пропусков правил: цитата из карточки, общий verifier,
  бюджет вызовов, повторы, кэш, учёт токенов в manifest ([LLM](docs/LLM.md));
  ответ шлюза ограничен по размеру, запрос карточки — по времени (120 с), дневной
  бюджет считает каждую HTTP-попытку (LLM-008);
- unit и интеграционные проверки.

Исправления #15/#21: цвет внутри имени бренда/модели не принимается за цвет
товара; явно указанные model codes извлекаются и перед `мл/ml` и другими
поддержанными спецификациями. На 40 ранее reviewed development-карточках
исправлено 9 model FN без новых FP и потери TP; это AI-assisted development,
не независимая оценка каталога. [Проверка связей](docs/RELATION_VERIFIER.md),
[замер model и оставшиеся отказы](docs/research/base001_followup_results.md).

## Быстрый запуск

Полный проверенный маршрут от `git clone` до ответа HTTP API на своих карточках,
с ожидаемыми выводами для Linux и PowerShell: [QUICKSTART](docs/QUICKSTART.md).
Что значат `review`, `abstain`, reason codes и ошибки API и что делать оператору:
[RESPONSES](docs/RESPONSES.md). Ниже — короткая версия.

Требуется Python 3.12+. Команды выполняются из корня checkout с полной Git-историей
(без `--depth`): comparison tests используют базовый commit `5f77d81`.
Датасеты, ключи и LLM для этого сценария не нужны.

```bash
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m pip check
mkdir -p outputs
cat > outputs/my-card.jsonl <<'JSON'
{"schema_version":"0.1","sku_id":"my-phone","category_id":"761","title":"Смартфон Samsung Orbit X73 12/512GB белый","description":"Экран 6,4 дюйма. Аккумулятор 4600 мАч."}
JSON
.venv/bin/python -m goodsai.cli predict --input outputs/my-card.jsonl --output outputs/my-predictions.jsonl
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[serve,test]"
.\.venv\Scripts\python.exe -m pip check
New-Item -ItemType Directory -Path outputs -Force | Out-Null
$goodsaiInput = '{"schema_version":"0.1","sku_id":"my-phone","category_id":"761","title":"Смартфон Samsung Orbit X73 12/512GB белый","description":"Экран 6,4 дюйма. Аккумулятор 4600 мАч."}'
[IO.File]::WriteAllText((Join-Path $PWD 'outputs/my-card.jsonl'), $goodsaiInput + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
.\.venv\Scripts\python.exe -m goodsai.cli predict --input outputs/my-card.jsonl --output outputs/my-predictions.jsonl
```

Это собственный внешний JSONL, без чтения packaged demo-файлов. Ожидаются
`status=processed`, brand=`Samsung`, model=`Orbit X73`, RAM=`12 GB`,
storage=`512 GB`, screen=`6.4 inch`, battery=`4600 mAh`, color=`белый`.
Все найденные значения имеют `decision=review` и точный source span.
Результат — `outputs/my-predictions.jsonl`, provenance/hashes —
`outputs/my-predictions.manifest.json`. Замените title/description своими
данными, сохраняя text-only схему; готовые vendor/model/params поля запрещены.
PowerShell пример пишет UTF-8 **без BOM**, в том числе на Windows PowerShell 5.

Если `.venv` уже существует, сначала проверьте её Python; не создавайте её заново
поверх рабочего окружения. Системный `python3` на VM может быть 3.10; используйте
имеющуюся `.venv/bin/python` версии >=3.12. Вариант с установленным `uv` описан
в [RUNBOOK](docs/RUNBOOK.md). Активация окружения не требуется.

Дополнительный smoke из шести заранее подготовленных случаев:

```bash
.venv/bin/python -m goodsai.demo --output-dir outputs/demo-first-run
```

В PowerShell executable — `.\.venv\Scripts\python.exe`.
Демо создаёт в `outputs/demo-first-run/` `input.jsonl`, `predictions.jsonl`,
`predictions.manifest.json`, `summary.json`, `metrics.json`, `report.md` и
`artifacts.json` с hashes шести файлов. В stdout и summary ожидаются
`checks_passed=6`, `checks_total=6`, `rows=6`, `llm_calls=0`.
Повторять с **новым** `--output-dir`: существующий каталог не перезаписывается.
Это проверка сквозного сценария, а не P/R/F1 на реальном каталоге.
`report.md` показывает значения, evidence locations, причины abstain и доли
review/abstain; `metrics.json` сохраняет quality=N/A без manual reference,
нулевые API calls/cost и неизвестную стоимость compute. Synthetic checks и
candidate coverage не являются точностью извлечения.

Проверка существующего комплекта не запускает predictor и не меняет файлы:

```bash
.venv/bin/python -m goodsai.demo --verify-dir outputs/demo-first-run
```

Изменённый/отсутствующий файл, посторонний path в manifest и разные run ID
отклоняются. Это локальный demo-комплект, не финальный release bundle.

## Пакетный прогноз

Для проверки внешнего ввода без встроенных demo-файлов:

```bash
.venv/bin/python scripts/release/external_acceptance.py --seed 20261020 --output-dir outputs/external-first
```

Команда генерирует свой `input.jsonl` и ожидаемые ответы, запускает CLI и настоящий
HTTP на временном loopback-порту из копии пакета **без `examples/`**. Отчёты:
`outputs/external-first/report.json` и `report.md`. Ожидается `passed`, **83/83**,
exit `0` после исправлений #15/#21. Exit `1` означает найденные ошибки;
exit `2` — сбой самого прогона. Known issues тоже считаются ошибками,
проверки не исключаются. Это synthetic acceptance,
не оценка точности каталога. [Сценарии, ограничения и запуск в PowerShell](docs/EXTERNAL_ACCEPTANCE.md).

Для проверки из чистого checkout одной командой, включая изолированное
окружение, hash-locked зависимости, batch, API contract и artifact verification:

```bash
python3.12 scripts/release/clean_run.py --output-dir outputs/clean-first
```

Внешний JSONL передаётся через `--input`. Повтор команды проверяет сохранённые
артефакты; ограничения OS/Python, отчёты и recovery — в [CLEAN_RUN](docs/CLEAN_RUN.md).

Минимальная строка входного JSONL:

```json
{"schema_version":"0.1","sku_id":"demo-1","category_id":"761","title":"Смартфон Samsung Demo X82 8/256GB черный","description":null,"seller_attributes":[],"source_flags":[]}
```

Запуск на своём файле (например, созданном в «Быстром запуске»):

```bash
.venv/bin/python -m goodsai.cli predict \
  --input outputs/my-card.jsonl \
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
гарантирует смысловую правильность извлечения. Примеры всех исходов
(`processed`, конфликт, пропуски, `unsupported_category`, `invalid_input`) с
действиями оператора — в [RESPONSES](docs/RESPONSES.md).

Для PowerShell заменяйте `.venv/bin/python` на `.\.venv\Scripts\python.exe`,
многострочную Bash-команду вводите одной строкой.

## Экспериментальный ML для пропущенного бренда

Есть отдельный opt-in гибрид: правила → GLiNER для пропущенного однословного
бренда → точное evidence → review. Основные CLI/API его не включают.
На просмотренном development AI-reference он добавил 17 совпадений без новых
несовпадений; независимое качество не установлено. Команды, веса, метрики,
RAM и ограничения: [EXPERIMENTAL_GLINER](docs/EXPERIMENTAL_GLINER.md).

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

## Конфигурация

Настройки запуска описаны в [CONFIGURATION](docs/CONFIGURATION.md): versioned
профиль задаёт границы чисел, scores правил, контекстные окна, HTTP limits
и не-секретные LLM-параметры. Полный безопасный пример —
[configs/production.example.json](configs/production.example.json).
CLI принимает `--config path.json` перед подкомандой; HTTP-сервис поддерживает
тот же профиль через `python -m goodsai.api --config path.json`. Невалидный
профиль останавливает запуск; LLM включается только явным opt-in, auto-accept
запрещён. Приоритет настроек общий: профиль → разрешённые env → явные CLI-флаги.
Manifest содержит effective config/policy и их SHA-256 без ключа/URL шлюза;
у API эти hashes доступны в `/health`. Числовой review threshold до калибровки
не поддерживается (`null`), score остаётся эвристическим.

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

Оценка baseline по каталогу, offline-калибровка и передача результатов коллег:
[инструкция EVAL-006](docs/SILVER_EVALUATION.md). Это диагностика по шумному
reference, независимое качество пока не подтверждено.

Результат на 3037 development/feedback карточках: agreement P 94,65%,
R 63,02%, F1 75,67%, supported recall 75,75%. Полные знаменатели и ограничения:
[метрики](reports/metrics.md), [run stats](reports/run_stats.json),
[выводы](docs/research/silver_evaluation_results.md). С результатами ручной
разметки ниже эти числа напрямую не сравниваются.

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

## Сложные synthetic случаи

```bash
.venv/bin/python -m goodsai.adversarial --output-dir outputs/qa-hard-cases
```

Команда прогоняет 21 заранее описанный synthetic случай через настоящий batch:
конфликты, memory roles/card, преобразование единиц, редкий alias/неизвестный
бренд, отсутствие значения, чужая сущность, negation/range, HTML/entities/emoji,
повтор цитаты, hidden text, неверный вход и неизвестная категория. У каждого
случая в `examples/synthetic/adversarial.json` есть expected value/unit,
evidence field/raw offsets/text, decision/reason либо domain status.

Новый каталог содержит input, predictions/manifest и report.json с fingerprints.
Exit 0 — все ожидания совпали, 1 — наблюдаемые регрессии (включая known issue),
2 — ошибка самого прогона. Исключения backend не превращаются в abstain/успех;
их payload не попадает в отчёт. Существующий каталог не перезаписывается.

После исправления #15 через PR #104: **21/21** совпадений. Цвет из имени
RED SOLUTION отклоняется. Метка known_issue не подавляет failure и ненулевой exit.
Это regression suite, не human gold или качество каталога. Unit tests проверяют
harness и отсутствие новых нетрекированных failures; их PASS не заменяет
отдельный strict прогон. Изменение fixture требует review.

Programming/dependency failure и corrupted predictions проверены fault injection
в test_adversarial.py; API failures — в test_api.py; реальные child-process
concurrency/crash/recovery — в test_storage.py. В default rules runtime LLM не
вызывается; лимиты opt-in маршрута (размер ответа, дедлайн, физические попытки,
бюджет) проверены локальным HTTP-сервером в test_llm_bounds.py (LLM-008).

## Проверки

Контекстные отказы verifier, воспроизводимое сравнение и ограничения:
[VER-001](docs/RELATION_VERIFIER.md) (включено в main через PR #104).

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

В Windows PowerShell используйте `.\.venv\Scripts\python.exe` и перед общим
suite задайте `$env:PYTHONUTF8='1'`: существующие config/registry tests создают
временные Unicode-файлы. После LLM-008 — 359 основных + 3 reader tests;
результат предшествующего принятого snapshot — 322 + 3 и strict acceptance 83/83
([SHA, CI и границы проверки](docs/reviews/2026-10-20_linked_acceptance.md)).

Проверка повреждённых LLM-ответов отдельно:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_llm*.py' -v
```

Это 63 теста с fake provider и локальным HTTP stub: CLI batch, HTTP API и
cache replay сохраняют rules при неверном ответе; медленный, огромный, chunked
и оборванный ответ шлюза, 429/5xx и исчерпанный бюджет не ломают карточку. Ключ шлюза не нужен,
платных вызовов нет. Семантика смешанного ответа и причин отказов — в
[LLM](docs/LLM.md#повреждённый-ответ-и-кэш-llm-007).

Единая конфигурация, precedence и production-пример проверяются отдельно:

```bash
.venv/bin/python -m unittest discover -s tests -p test_runtime_policy.py -v
```

12 tests используют синтетику и fake provider; production-пример дополнительно
запускается настоящими CLI и HTTP-процессом на loopback. Платных вызовов нет.

Генеративные проверки Unicode/HTML, schema, единиц и evidence запускаются
отдельно после установки `.[fuzz]`:

```bash
.venv/bin/python -m unittest discover -s tests/fuzz -v
```

Profiles quick/nightly, seed, replay и найденные regression cases — в
[FUZZ_TESTING](docs/FUZZ_TESTING.md).

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
- **Gitea `main`** — состав сдачи: код, тесты, инструкции и публичные артефакты.

Каждый push или merge в GitHub `main` запускает Actions workflow публикации.
Внутренние исследования, планы, TASKS, AGENTS и reviews остаются в GitHub.
Состав задаётся явным списком; README сдачи отдельный. GitHub и Gitea SHA
различаются, связь и hashes файлов записаны в `submission-manifest.json` Gitea.
Публикация идёт обычным следующим commit без force push. Посторонние изменения
Gitea останавливают job; прежняя история сохраняется.

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
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | проверенный запуск с нуля на своём JSONL: CLI, проверка manifest, HTTP, opt-in LLM |
| [docs/RESPONSES.md](docs/RESPONSES.md) | статусы, решения, reason codes, ошибки API и действия оператора |
| [TASKS.md](TASKS.md) | очередь, владельцы, статусы и подробные подзадачи |
| [docs/TASK_MANAGEMENT.md](docs/TASK_MANAGEMENT.md) | labels, Issue forms, claim commit, review и закрытие |
| [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) | актуальное техническое задание и критерии приёмки |
| [RESEARCH.md](RESEARCH.md) | научные и open source основания решений |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | что реально сделано и что ещё отсутствует |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | текущая и целевая архитектура гибридного pipeline |
| [docs/SPAN_INDEX.md](docs/SPAN_INDEX.md) | внутренние исходные spans, limits и отдельный замер покрытия |
| [docs/DATASET.md](docs/DATASET.md) | подготовка, ограничения и защита от утечки |
| [docs/EVALUATION.md](docs/EVALUATION.md) | дизайн эксперимента, формулы и честные метрики |
| [docs/LLM.md](docs/LLM.md) | opt-in LLM-fallback: запуск, проверки, причины отказов, бюджет и кэш |
| [docs/HUMAN_GOLD.md](docs/HUMAN_GOLD.md) | blind human review, формы и проверки; gold требует двух людей и adjudication |
| [docs/DEVELOPMENT_REVIEW.md](docs/DEVELOPMENT_REVIEW.md) | текущая AI-assisted партия D21–D40 для проверки Владом |
| [docs/RESULTS.md](docs/RESULTS.md) | происхождение, snapshots и воспроизведение M1/M2 |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | трассировка требований и шести артефактов |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | запуск, диагностика и восстановление |
| [docs/RELEASES.md](docs/RELEASES.md) | GitHub → Gitea → VM и чек-лист релиза |
| [docs/ARTIFACT_BUNDLE.md](docs/ARTIFACT_BUNDLE.md) | offline-сборщик шести артефактов, hashes и проверка переноса |

## Границы текущей версии

- поддерживаются две категории, а не весь каталог;
- seller attributes пока запрещены, чтобы не подмешать target;
- LLM-маршрут opt-in; его качество на реальном каталоге не измерено, encoder в основном пути нет;
- `auto_accept` выключен до независимой оценки и калибровки;
- фактическое качество на независимом test неизвестно;
- публичный API временный;
- реальные данные, gold, predictions, модели, логи и секреты не входят в Git.

Эти ограничения превращены в задачи с владельцами и критериями готовности в
[TASKS.md](TASKS.md).

### Кандидат расширения категорий

[PLAN для интеграции; DONE как opt-in feature candidate] Обучение схем и
словарей только на разрешённом train, key:value, пары и размеры с изучением
порядка полей: [CATEGORY_REGISTRY](docs/CATEGORY_REGISTRY.md). Есть отдельное
демо на 30 вымышленных категориях. Реальное покрытие top-30 и качество не
измерены; штатный baseline без нового конфига сохраняет две категории.
