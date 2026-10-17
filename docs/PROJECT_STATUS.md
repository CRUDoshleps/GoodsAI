# GoodsAI — состояние проекта и вход для команды

Актуализировано: **17 октября 2026 года, Europe/Moscow**. Состояние: рабочий E1 baseline; заморожены 22 AI-assisted human-reviewed карточки в reviewed-v2, выполнена отдельная development/validation-оценка. Независимой gold/test-оценки ещё нет.
Рабочий каталог: `C:\Users\vladn\projects\GoodsAI`; ветка: `feature/vlad-setup`; базовый коммит настройки: `cf16e59` (`chore: initialize local development environment`).
**Baseline, EDA, тесты и актуальные отчёты опубликованы в Gitea main через [PR #2](https://git.hub.gigaschool.ru/tochka-sborki-2026-team-054/project/pulls/2), merge-коммит `b3b3d55d05a276aa1db3e333fee7cc24d1c6a139`.** В него вошли baseline `c3feee2`, handoff `5e6160e` и документационный релиз `5d41970`. Текущий HEAD, включая последующие изменения статуса, проверять через Git.
Ветка отслеживает `origin/feature/vlad-setup`; наличие remote-ветки не означает успешную отправку последнего коммита. Доступность текущей версии проверять после успешного push, сравнив локальный и удалённый SHA.
17 октября пользователь явно разрешил commit/push и интеграцию в main через PR. После push `5d41970` PR #2 обновлён и слит без принудительного merge; API подтвердил `merged=true`, fetch — `origin/main=b3b3d55`. Tree main совпал с проверенной feature-версией, baseline и документы присутствуют, Git-данные/секреты не добавлены. Рабочая feature-ветка затем fast-forward обновлена до merge-коммита; локальный main не переключался и история не переписывалась. Вкладка платформы «Последний push в Gitea» инструментально не проверена.

**Текущий этап — сервис на порту 8000 и уточнение контракта интеграции.** По сообщениям организаторов с 18 октября в 06:00–10:00 МСК проверяется последний commit main; публикация baseline выполнена. На ВМ пользователь fast-forward обновил main до `78b052e`, создал `.venv` через uv 0.13.1 с Python 3.12.15/pip 26.2.1, установил GoodsAI 0.1.0 и PyArrow 26.0.0. Все **18 baseline/data + 3 reader tests прошли**, включая синтетический CLI. [Протокол ВМ](runbooks/vm_reproduction.md) основан на переданном SSH-выводе: агент сам сессию не контролирует. Реальные данные на ВМ не прогонялись. Позднее администраторы уточнили: на выходные достаточно решения на **8000** и всей кодовой базы в **main** одного репозитория; ручки/транзакции будут в понедельник вечером. Добавлен временный FastAPI/Uvicorn-адаптер над неизменным ядром v0.1: `/`, `/health`, `/predict`, `/docs`. Это внутренние маршруты до официальной спецификации. Инструкции — [HTTP runbook](runbooks/http_service.md). Постоянный запуск на ВМ, менеджер процесса и внешняя доступность пока не подтверждены.

Пользователь сохранил локальный `.gitignore` ВМ в отдельную backup-папку, перенёс его правила в `.git/info/exclude` и переместил исходник в backup перед обновлением. `ai.env` исключён и общим `.gitignore`. Для uv-окружения использован `--seed`; установка и тесты подтверждены по SSH-выводу. Менеджер процессов, занятые порты и внешний доступ проверяющей системы ещё не обследованы.

## 1. Как быстро восстановить контекст

1. Прочитать этот документ и [AGENTS.md](../AGENTS.md), проверить `git status --short --branch`.
2. Найти свою область в карте модулей ниже; открыть только соответствующий исходник и тесты.
3. Для команд использовать [инструкцию baseline](baseline.md), для измерений — [результаты E1](baseline_results.md).
   Требования задания, обязательные поля и состав сдачи — [REQUIREMENTS_AND_DELIVERY.md](REQUIREMENTS_AND_DELIVERY.md).
4. Детальный [EDA](research/dataset_findings.md), [контракт/архитектура](research/architecture_and_contract.md), [оценивание](research/evaluation.md) нужны при работе с данными, интерфейсами или метриками.
5. [Исходный план](research/implementation_plan.md) и [подготовка окружения](development_setup.md) — снимки предыдущих этапов. Указания «создать baseline» и «ещё не запускался» там исторические; не создавать повторно уже существующие модули.

Текущая разметочная работа: [план AI-разметки](research/annotation_plan.md). По всем 24 карточкам получена обратная связь. Актуальный локальный `data/gold/e1/ai/full.annotations.v4.jsonl` содержит **120 карточек / 720 решений: 517 present, 183 absent, 19 ambiguous, 1 unjudgeable**; спорных 20 пар в 15 карточках. Текущие формы — `review24.v4.md`, `disputes.v4.md`, `full.review.v4.md`, номера R/A сохранены. В v4 уточнены пять именований по первичным источникам: полное Galaxy Line в трёх явно подписанных title, model TWK4P439 и KRWK02. Новые свойства с сайтов не подставлялись; это AI-adjudication, а не ручное подтверждение.

**Текущая ручная часть — `review.human-reviewed.v6.jsonl`: 22 полные проверки / 130 пар (10 development, 12 validation).** В раунде 5 пользователь подтвердил R17/R19/R21/R22/R23; происхождение — `review.round5.feedback.json`, контрольные суммы — `review.manifest.v6.json`. Полный AI-набор v4 и прежний human-v5 не перезаписаны. R03/R04 остаются частичными: десятичное 1 TB = 1000 GB явно одобрено, универсальный GB default для RAM не утверждён, трактовка написания Tb отдельно не согласована. Голые числа и ошибочные единицы рекомендуется отправлять на review; в R19 объём остаётся unjudgeable, внешние литры не подставлены. Новая runtime-логика здесь не внедрялась.

**Текущая оценка — [reviewed-v2](research/baseline_evaluation_v2.md)**: `data/gold/e1/reviewed/reviewed-v2/`, 10 development / 57 judged и 12 validation / 67 judged; исключены 5 ambiguous и 1 unjudgeable. Validation: TP=29, FP=1, FN=21; **P=96,7%, R=58,0%, F1=72,5%**. Development: TP=18, FP=1, FN=19; F1=64,3%. Изменился набор карточек, а не метод; сравнение с v1 не доказывает прирост/деградацию baseline. В development model объясняет 9 FN. Два оставшихся случая — локальный `outputs/evaluation/reviewed-v2/pending_review.md`. Данные/метрики/SKU остаются вне Git.

История: этап [плана/промпта](research/next_stage_prompt.md) выполнен в [первой оценке и error analysis](research/first_baseline_evaluation.md). Сохранённый reviewed-v1: 9 development / 52 judged и 8 validation / 48 judged; validation F1=74,6%. Прежние 17 наборов меток в v2 не изменены. Обе версии — малые неслучайные AI-assisted выборки, validation участвовал в обсуждении политики, не независимый holdout.

Проверены hashes, raw evidence и совпадение всех 10 324 predictions с исходным E1; точных/нормализованных межsplit-дублей и пересечений групп не найдено. Аудит близких дублей остаётся участнику C. Текущие метрики/ошибки — `outputs/evaluation/reviewed-v2/`; v1 сохранён отдельно. Правила не улучшались, модели не обучались, commit/push не выполнялись. Следующий приоритет по development — extractor `model` (9 FN), затем цвета/бренды и числовой разбор. Рекомендация агента GPT-6.1 Sol / High в плане не выбирает модель runtime.

При расхождении документации и кода сначала проверить код, конфигурацию и manifest, затем исправить документацию. Полный EDA по умолчанию не повторять.

## 2. Проект, требования и ближайшие даты

GoodsAI решает кейс №3 М.Видео на хакатоне «Точка сборки»: извлекает характеристики из текстовой карточки, нормализует их и возвращает структурированные значения с уверенностью.
Проблема бизнеса — пропущенные/неоднородные характеристики мешают фильтрации, поиску и сравнению товаров. Рост CTR/GMV текущими экспериментами не доказан.
Целевой вход кейса: название, описание, поля продавца; выход: обязательные атрибуты, канонические значения и confidence. Текущий E1 намеренно **text-only**: без полей продавца.

Источник требований: [PDF кейсодателя](product-stage/context/case/attribute-extraction-case.pdf), стр. 10 и 16–18, и [сохранённый текст платформы](product-stage/context/case/platform-requirements.md).
Разделы 3–6 повторно предоставлены пользователем 17 октября и сверены: для смартфона прямо названы бренд, модель, память, диагональ, батарея и цвет; E1 включает их и дополнительный RAM. Пример ноутбука содержит бренд, CPU, RAM, накопитель, диагональ и цвет; ноутбуки пока не поддерживаются. Полная схема/справочники категорий остаются открытым вопросом; набор чайника — наш пилотный выбор. Подробная [связь требований с реализацией и сдачей](REQUIREMENTS_AND_DELIVERY.md) отделяет подтверждённые условия от проектных намерений продуктового этапа.
Требуются: только текст, извлечение/нормализация без выдуманных фактов, rules baseline и последующая проба ML или LLM, per-attribute P/R/F1 на gold.
Шесть артефактов сдачи: воспроизводимый код/ноутбук, README, EDA, pipeline, файл предсказаний, финальная презентация. Полный технический scoring rubric и формат автопроверки пока не подтверждены.
Задание требует один репозиторий или архив с запуском по README, попытку ML **или** LLM после rules baseline и per-attribute/per-category оценку. Обязательный дообученный encoder, конкретный каскад или web-интерфейс не заданы. Текущие 10 324 predictions — локальный пилот, не весь каталог; итоговый файл нужен в согласованном комплекте сдачи, хотя сейчас predictions исключены из Git. Обещанные CSV/JSON, готовая разметка и точная схема не совпали с обнаруженными Parquet/pickle и weak references; дополнительную выдачу нужно уточнить.
Продуктовый этап пройден с максимальной оценкой **по сообщению команды**; в репозитории сохранены его материалы, а не протокол проверки этой оценки.

| Дата | Что необходимо | Статус/основание |
| --- | --- | --- |
| До 06:00 МСК 18 октября, далее ежедневно | Рабочее решение в main выданного Gitea; отдельно запуск на ВМ | Main опубликован; пакет установлен на ВМ, 21 test прошёл; HTTP-сервис и официальный API ещё впереди |
| 19 октября | Первый технический checkpoint: реальный запуск, предсказания, validation-оценка на ручных метках, ограничения | Локальный data-run и AI-assisted reviewed-метрики есть; на ВМ только установка/синтетические tests, независимый gold ещё не готов |
| 21 октября | Сравнить rules с одним ML/LLM-вариантом на фиксированном split, если согласованы доступ и бюджет | Внутренний этап плана, **не подтверждённый внешний дедлайн** |
| 23 октября | Комплект шести артефактов, согласованный охват/формат, воспроизводимость и интеграция в Gitea main через PR | Технический отбор по сообщению пользователя; время сдачи уточнить |

## 3. Что работает и что ещё не сделано

| Состояние | Возможности |
| --- | --- |
| Реализовано и проверено локально | Временный HTTP-адаптер и CLI; пакетная подготовка двух категорий; text-only граница; правила, Decimal-нормализация, raw evidence, отказы/конфликты, JSONL, manifests, синтетические тесты |
| Реализован механизм, но результат ещё не получен | Evaluator ручной разметки; группы/split-manifest; исходные 120 заданий сохранены. Отдельно подготовлена полная AI-разметка и выборка для review; независимая оценка качества отсутствует |
| Частично | Бренды/цвета ограничены ручными словарями; правила покрывают часть формулировок; группировка точных/нормализованных дублей есть, аудит близких дублей ещё нужен |
| Явно не реализовано | Извлечение `model`: всегда `abstain`; калибровка, интервалы метрик, отдельная span-conditioned метрика нормализации, ML/LLM-вызовы, обучение, автоматическая запись, UI/очередь review |
| Проверено на Linux ВМ | Установка GoodsAI 0.1.0/PyArrow 26.0.0 на Python 3.12.15 и 18+3 tests; реальный data-run и постоянно работающий сервис ещё не проверены |
| Не проверено | HTTP-сервис на ВМ; официальный формат предсказаний; полный required-список/справочники; полный охват каталога |
| Гипотезы | Правила → LLM для остатка; локальный encoder; расширение на другие категории. Презентационный каскад не является реализованной системой |

Стек: Python `>=3.12`, локально проверен 3.12.6; версия пакета 0.1.0. Runtime-зависимость — PyArrow 26.0.0 для подготовки.
`predict`/evaluator используют stdlib; DuckDB 1.5.6 нужен только исследовательским скриптам. Есть optional FastAPI/Uvicorn HTTP-адаптер (`.[serve]`); HTTP-тесты требуют `.[serve,test]`. Нет Spring, сервера БД, frontend, torch/transformers.

## 4. Карта кодовой базы

Реальные директории: `src/goodsai/`, `tests/`, `scripts/research/`, `docs/research/`, `docs/product-stage/`; локальные данные/результаты — `data/`, `outputs/`, `logs/`, окружение — `.venv/`.
Конфигурация находится в пакете: **`src/goodsai/baseline.json`**. Каталог `configs/` из старого плана не создан и для запуска не нужен.

| Файл | Ответственность, вход → выход | Основные связи |
| --- | --- | --- |
| [pyproject.toml](../pyproject.toml), [__init__.py](../src/goodsai/__init__.py) | Установка, версия, ресурс JSON, entrypoint `goodsai`; исходники → Python-пакет | setuptools, CLI |
| [baseline.json](../src/goodsai/baseline.json) | Версии rules/dictionary, seed, категории/атрибуты, aliases брендов/цветов → config dict | `load_config`, Rules, annotation |
| [contracts.py](../src/goodsai/contracts.py) | `Product.from_dict`: JSON → строго text-only Product; `validate_prediction`: результат + config [+ Product] → проверка/ValueError | data, CLI, verifier, evaluator |
| [data.py](../src/goodsai/data.py) | `prepare`: доверенная проекция + raw descriptions + inventory → pilot/provenance/manifests; JSONL I/O и атомарная замена отдельных файлов | PyArrow, Product, CLI |
| [text.py](../src/goodsai/text.py) | HTML-строка → видимый текст + карта исходных координат; исключает script/style/attrs/comments | Rules; HTMLParser |
| [rules.py](../src/goodsai/rules.py) | `Rules.candidates(Product)` → Candidate со значением, единицей, span, score и rule_id; бренд/цвет/память/числовые характеристики | text, normalize, config |
| [normalize.py](../src/goodsai/normalize.py) | Строка числа + unit + attribute → каноническая десятичная строка; bounds, L/ml, W/kW, GB | Rules, contracts, verifier, evaluator |
| [verify.py](../src/goodsai/verify.py) | `Extractor.predict(Product, run_id)` → полный объект предсказания; объединяет совпадающие значения, конфликтующие отвергает | Rules, contracts, normalize |
| [annotation.py](../src/goodsai/annotation.py) | Pilot + отдельная provenance [+ EDA sample] → связанные группы, split-manifest, пустые задания, отчёт отбора | Product, data; extractor не вызывается |
| [evaluate.py](../src/goodsai/evaluate.py) | Predictions + reviewed manual gold → TP/FP/FN, P/R/F1, coverage, срезы/score bins; без gold → N/A | contracts, normalize, data |
| [runtime.py](../src/goodsai/runtime.py) | Config + текущий код/среда → hashes/git identity; процесс → peak RSS | CLI; Windows API / Unix resource |
| [cli.py](../src/goodsai/cli.py) | `inventory`, `prepare`, `predict`, `annotate`, `evaluate`; аргументы/файлы → JSONL/JSON и exit code | Связывает перечисленные модули; inference идёт через Extractor |
| [test_baseline.py](../tests/test_baseline.py) | 16 синтетических тестов правил, evidence, контрактов, evaluator, детерминизма | Не использует реальные данные как fixtures |
| [test_data_and_annotation.py](../tests/test_data_and_annotation.py) | 2 теста подготовки и группировки, защита от target leakage/изменённого источника | Временные синтетические Parquet/JSONL |

Исследовательские файлы не являются вторым runtime baseline:

| Файл | Когда нужен и что создаёт |
| --- | --- |
| [inspect_pickle.py](../scripts/research/inspect_pickle.py) | Первый read-only проход opcodes доверенного pickle → `outputs/eda/pickle_opcodes.json`, refs/SHA |
| [profile_catalog.py](../scripts/research/profile_catalog.py) | Sparse `CatalogReader` + проверенный scan + `--trusted-pickle` → проекция каталога и агрегаты; частный CPython API, проверен на 3.12.6 |
| [profile_parquet.py](../scripts/research/profile_parquet.py) | Полный Parquet audit при обоснованной необходимости → статистики и scratch DuckDB |
| [profile_joins.py](../scripts/research/profile_joins.py) | Агрегаты/проекция/описания → join-профиль и локальная ограниченная выборка |
| [requirements.txt](../scripts/research/requirements.txt), [test_catalog_reader.py](../scripts/research/test_catalog_reader.py) | Зависимости EDA отдельно; 3 синтетических теста sparse reader |

## 5. Данные и артефакты

Оригиналы находятся в `data/raw/`, суммарно 2 568 187 871 байт (~2,39 ГиБ). В Git их нет.

| Источник | Подтверждённое содержание |
| --- | --- |
| `sku_desc.parquet` | 1 177 200 уникальных SKU, `sku_id/title/description`; 49,31% описаний с HTML |
| `skus.pkl` | 546 069 товаров YML-подобного каталога, vendor/model/name/categories/param; 3 599 используемых категорий |
| `query_clicks.parquet` | 30 991 350 строк, 332 753 SKU; запрос, позиция, цена, subject/seo ID; нет показов/timestamps/click_count |

Связь — SKU: каталог↔описания 241 355; каталог↔кликовые SKU 241 661; описания↔кликовые SKU 158 158; все три файла 102 945.
Клики не участвуют в E1 extractor. Семантика одной строки лога и возможность traffic-weighting требуют уточнения; CTR из этих полей не вычисляется.
В каталоге 148 871 карточка с повторяющимися именами параметров; `param` иногда dict вместо list. Готовые параметры — слабые метки, не подтверждённый gold.
Структурированная категория берётся из каталога, не угадывается по запросу. E1 поддерживает только ID `761` и `482`; имя категории не является ключом.
В пилоте 4 244 SKU с описанием и 6 080 без. У 343 сопоставленных пилотных SKU названия источников различаются: основной title = `skus.name`, второй сохраняется в provenance с флагом `title_mismatch`.
Полные схемы, распределения, проблемы и метод — в [EDA](research/dataset_findings.md); здесь исследование заново не выполнялось.

Локальные производные файлы (все исключены из Git):

```text
data/raw/.local_inventory.json              размеры/SHA исходных копий
outputs/eda/catalog_skus.parquet             доверенная проекция; params сохранены только для 5 категорий EDA
outputs/eda/pickle_opcodes.json              проверка opcodes/ref/SHA для reader
outputs/eda/catalog_profile.json             агрегаты каталога
outputs/eda/parquet_profile.json             схемы/row groups/агрегаты
outputs/eda/joins_profile.json               связи и диагностика
outputs/eda/inspection_sample.json           реальные тексты; не публиковать
outputs/eda/profile.duckdb                   scratch database
data/processed/e1/pilot.jsonl                только разрешённый вход
data/processed/e1/provenance.jsonl           второй title и служебные vendor/model/seller
data/processed/e1/prepare_manifest.json      hashes, размеры срезов, время/RSS подготовки
data/gold/e1/tasks.jsonl                     120 незаполненных заданий
data/gold/e1/split_manifest.jsonl            SKU → группа → split
data/gold/e1/annotation_manifest.json        метод/размеры/ограничения отбора
data/gold/e1/ai/full.annotations.jsonl       исходный ai-full-v2, сохранён для истории
data/gold/e1/ai/full.annotations.v3.jsonl    сохранённый ai-full-v3
data/gold/e1/ai/full.annotations.v4.jsonl    актуальный ai-full-v4, 120 карточек / 720 решений
data/gold/e1/ai/full.manifest.v4.json        hashes текущей версии и источников
data/gold/e1/ai/review24.v4.md              текущая форма проверки с прежними номерами
data/gold/e1/ai/disputes.v4.md              текущие 20 спорных меток
data/gold/e1/ai/review.human-reviewed.v6.jsonl  22 полные проверки / 130 пар
data/gold/e1/reviewed/reviewed-v2/              замороженный dev/validation reference
outputs/evaluation/reviewed-v2/                метрики, ошибки, manifests
data/gold/e1/ai/full.manifest.v3.json        hashes текущей версии и её исходников
data/gold/e1/ai/review24.v3.md              сохранённая форма проверки v3
data/gold/e1/ai/disputes.v3.md              сохранённые 25 спорных решений v3
data/gold/e1/ai/review.human-reviewed.v4.jsonl  11 полных проверок / 75 пар
data/gold/e1/ai/full.manifest.json           hashes, статистика и ограничения полного прохода
data/gold/e1/ai/review24.md                  24 карточки для проверки пользователем
data/gold/e1/ai/disputes.md                  все 33 спорных решения с текстами
data/gold/e1/ai/pilot.human-reviewed.jsonl   две ранее проверенные development-карточки
data/gold/e1/ai/review.human-reviewed.v2.jsonl  три полные development-карточки после R02–R06
data/gold/e1/ai/review.round2.feedback.json  журнал подтверждений и вопросов R02–R06
data/gold/e1/ai/review.human-reviewed.v3.jsonl  шесть полных карточек / 40 пар после R07–R12
data/gold/e1/ai/review.round3.feedback.json  журнал подтверждений и вопросов R07–R12
outputs/baseline/predictions.jsonl           10 324 результата
outputs/baseline/predictions.manifest.json   code/config/input/output hashes, среда, счётчики
outputs/baseline/predictions.repeat.jsonl    побайтная проверка повторного запуска
outputs/baseline/metrics.json                N/A до ручной разметки
```

Также локально есть repeat-manifest и журналы запуска; это вспомогательные файлы, не вход extractor.
В Git не отправлять весь `data/`, `outputs/`, `logs/`, `.venv/`, кеши, секреты и реальные примеры в fixtures. Старый `context/datasets` также исключён.
Происхождение имеющегося pickle подтверждено пользователем; доверие не распространяется автоматически на другой файл. Не выполнять старые инструкции `git lfs pull` из архива продуктового этапа.

## 6. Фактический pipeline и границы

`доверенная проекция + raw descriptions → prepare → text-only Product → видимый текст/offset map → Rules → Decimal-нормализация → verifier → JSONL + manifest`.

| Категория | Requested attributes | Не реализовано |
| --- | --- | --- |
| Смартфоны `761` | brand, model, storage_gb, ram_gb, screen_inches, battery_mah, color | model всегда abstain |
| Чайники `482` | brand, model, capacity_l, power_w, color | model всегда abstain |

Rules используют явные фрагменты текста: `6/128GB`, контекст RAM/ROM, экран/дюймы, аккумулятор/мАч, объём/л, мощность/Вт, aliases цветов/брендов.
Нормализация: Decimal, запятая/пробелы/NBSP; `1700 мл → 1.7 L`, `2,4 кВт → 2400 W`; числа остаются строками. TB и произвольные оттенки не поддержаны.
Карта видимого HTML-текста переносит координаты в исходные поля; raw evidence может включать теги/entities между частями значения. Числа из href/script/style не используются.
Одинаковые нормализованные кандидаты объединяются; несколько различных `(value, unit)` дают `conflicting_evidence`, выбор «первого ответа» запрещён.
Нет кандидата → `not_found_by_rules`, а не доказанное отсутствие характеристики. Нет model-правила → `rule_not_implemented`.
Все непустые ответы — `review`; нет автоматического принятия, реальной очереди проверки или записи в каталог.
Confidence 0.75/0.8/0.85 — **эвристический score, не калиброванная вероятность**. Точное совпадение evidence доказывает источник, но не смысловую истинность.
Усилить качество и безопасность можно только после оценки по независимым ручным меткам; текущий код не гарантирует отсутствие семантических ошибок.

## 7. Контракт v0.1: что реально читает и пишет код

UTF-8 JSONL: один JSON-объект на строку. `Product.from_dict` допускает только перечисленные поля:

| Поле входа | Обязательность и смысл |
| --- | --- |
| schema_version | Обязательное, строка `"0.1"` |
| sku_id | Обязательная непустая строка; дубли SKU останавливают predict |
| title | Обязательная непустая после trim строка |
| category_id | Строка либо null; при отсутствии читается как null и категория не поддерживается |
| description | Необязательная строка/null, по умолчанию null |
| seller_attributes | Необязательный список, в E1 разрешён только `[]` |
| source_flags | Необязательный список строк, по умолчанию `[]`; prepare ставит missing_description/title_mismatch |

Vendor/model/param/gold/clicks и любые другие поля в text-only записи не разрешены. Provenance-файл не подавать в predict.
Выход всегда включает schema_version, run_id, sku_id, category_id, status, attributes. Для processed список соответствует порядку схемы, включая каждый отказ.
Атрибут содержит attribute/value/unit/confidence/confidence_kind/decision/method/rule_id/evidence/reason_codes. Для чисел unit — GB/inch/mAh/L/W, для строк null.
При abstain value/unit/confidence/evidence и rule_id равны null, reason_codes непуст. При кандидате decision=review, method=rule, confidence_kind=heuristic.
Evidence: field=`title` или `description`, start/end — Unicode code points, zero-based/end-exclusive; `source[start:end] == text`.

Ниже **синтетический** вход и полный результат `Extractor.predict(..., "doc-example")`, проверенные по текущему коду:

```json
{"schema_version":"0.1","sku_id":"demo-001","category_id":"482","title":"Электрочайник Tefal Demo","description":"Объём 1,7 л.","seller_attributes":[],"source_flags":[]}
```

```json
{
  "schema_version":"0.1", "run_id":"doc-example", "sku_id":"demo-001", "category_id":"482", "status":"processed",
  "attributes":[
    {"attribute":"brand","value":"Tefal","unit":null,"confidence":0.85,"confidence_kind":"heuristic","decision":"review","method":"rule","rule_id":"brand.explicit-title.v1","evidence":{"field":"title","start":14,"end":19,"text":"Tefal"},"reason_codes":[]},
    {"attribute":"model","value":null,"unit":null,"confidence":null,"confidence_kind":"heuristic","decision":"abstain","method":"rule","rule_id":null,"evidence":null,"reason_codes":["rule_not_implemented"]},
    {"attribute":"capacity_l","value":"1.7","unit":"L","confidence":0.8,"confidence_kind":"heuristic","decision":"review","method":"rule","rule_id":"capacity_l.explicit.v1","evidence":{"field":"description","start":6,"end":11,"text":"1,7 л"},"reason_codes":[]},
    {"attribute":"power_w","value":null,"unit":null,"confidence":null,"confidence_kind":"heuristic","decision":"abstain","method":"rule","rule_id":null,"evidence":null,"reason_codes":["not_found_by_rules"]},
    {"attribute":"color","value":null,"unit":null,"confidence":null,"confidence_kind":"heuristic","decision":"abstain","method":"rule","rule_id":null,"evidence":null,"reason_codes":["not_found_by_rules"]}
  ]
}
```

Статусы SKU: processed (допускает все abstain), unsupported_category (attributes=[]), invalid_input (attributes=[], input_line и reason_codes).
При invalid_input категория null; если исходный ID не строка, выходной sku_id пуст. `error` допускается валидатором, но текущий CLI не превращает программные исключения в такие строки — запуск прекращается.
Повреждённый JSONL, дубли, пустой вход или ошибка реализации останавливают запуск. Атомарно заменяется отдельный файл, не весь набор артефактов одной транзакцией.
Evaluator принимает reviewed manual gold с annotator, тем же текстовым входом и всеми requested attributes. Present требует canonical value/unit и точного evidence; absent — null; ambiguous/unjudgeable исключаются со счётчиком.
Wrong value = FP+FN; метрики считаются по канонической паре value/unit. Catalog weak labels не принимаются как manual gold; незаполненные задания дают N/A. Подробнее — [оценивание](research/evaluation.md).

## 8. Установка, запуск и проверка

Команды из корня проекта в PowerShell; установка пакета и полный pilot проверены в предыдущей итерации, тесты/CLI/формат повторно проверены при подготовке этого снимка.
Не запускать prepare/annotate просто для чтения контекста: они обновляют локальные производные файлы; заполненную разметку сохранять отдельно от tasks.jsonl.

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m goodsai.cli prepare
.\.venv\Scripts\python.exe -m goodsai.cli predict --input data/processed/e1/pilot.jsonl --output outputs/baseline/predictions.jsonl
.\.venv\Scripts\python.exe -m goodsai.cli annotate
.\.venv\Scripts\python.exe -m goodsai.cli evaluate --predictions outputs/baseline/predictions.jsonl --gold data/gold/e1/tasks.jsonl --output outputs/baseline/metrics.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Команда с tasks.jsonl выше — историческая проверка pending=120. Для текущей оценки использовать отдельные `data/gold/e1/reviewed/reviewed-v2/{development,validation}.jsonl` и новый output-путь; команды — в [отчёте v2](research/baseline_evaluation_v2.md). Источник `review.human-reviewed.v6.jsonl` содержит 22 AI-assisted проверки, 10 development / 12 validation. Происхождение и excluded ambiguous/unjudgeable раскрываются отдельно; это не независимый gold. Контекстные гипотезы R10 не оцениваются как present. Полные AI-файлы v2/v3/v4 не принимаются evaluator как reviewed/manual.
Отсутствующие inventory/проекцию готовить по [инструкции на другом компьютере](baseline.md#как-воспроизвести-на-другом-компьютере), без повторения всего click EDA.
CLI `inventory` пишет новый fingerprint-файл в data/processed; это не доказательство официального происхождения. `--config` — глобальная опция **перед** подкомандой.
Для чтения manifests без изменения данных: `Get-Content outputs/baseline/metrics.json` и `Get-Content outputs/baseline/predictions.manifest.json`.
Для сравнения имеющихся результатов: `Get-FileHash outputs/baseline/predictions.jsonl,outputs/baseline/predictions.repeat.jsonl -Algorithm SHA256`.

Полная read-only проверка SKU, schema и raw evidence уже существующего выхода:

```powershell
@'
from pathlib import Path
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_jsonl
products = {r['sku_id']: Product.from_dict(r) for r in read_jsonl(Path('data/processed/e1/pilot.jsonl'))}
seen = set()
for row in read_jsonl(Path('outputs/baseline/predictions.jsonl')):
    assert row['sku_id'] not in seen
    seen.add(row['sku_id'])
    validate_prediction(row, load_config(), products[row['sku_id']])
assert seen == set(products)
print('Schema/evidence/SKU check passed:', len(seen))
'@ | .\.venv\Scripts\python.exe -
```

Этот check не измеряет precision. На Linux заменить Windows python-path на `.venv/bin/python`; установка PyArrow wheel и синтетические CLI tests на ВМ уже прошли.
На ВМ подтверждены checkout main `78b052e`, установка и tests; диск 64G/свободно 55G до установки. CPU/RAM известны только по прежнему сообщению (2 CPU/4 ГБ), отдельной проверки пока нет. Deployment HTTP-сервиса ещё не выполнен.

## 9. Подтверждённые результаты E1

Источники: фактические manifests, существующий JSONL и [подробный отчёт](baseline_results.md); новый тяжёлый эксперимент не запускался.

| Показатель | Результат |
| --- | --- |
| Обработано | 10 324 SKU = 7 988 смартфонов + 2 336 чайников; все processed, invalid_input=0 |
| Кандидаты | 31 627 непустых пар из 67 596 запрошенных; **все review** |
| Карточки с ≥1 кандидатом / все abstain | 9 864 / 460 |
| С описанием | Смартфоны: 3 056 SKU, 12 355/21 392 пар; чайники: 1 188 SKU, 2 654/5 940 пар |
| Title-only | Смартфоны: 4 932 SKU, 15 763/34 524 пар; чайники: 1 148 SKU, 855/5 740 пар |
| Тесты | 18 baseline + 3 reader, синтетические fixtures; проходят |
| Воспроизводимость | Существующие полный выход и повтор побайтно одинаковы; run_id `8a72d1342ed8e7a6f13d` |
| Локальный predict | 13,869 с; p50 0,526 мс / p95 4,955 мс на запись; peak working set 29,7 МиБ |
| Отдельный prepare | 13,856 с; peak working set ~485 МиБ |
| Качество | Текущий reviewed-v2: 12 validation-карточек / 67 judged, P=96,7%, R=58,0%, F1=72,5%; [отчёт](research/baseline_evaluation_v2.md). Reviewed-v1 и старый `outputs/baseline/metrics.json` с pending=120 сохранены как история |

**Покрытие НЕ равно точности.** Рабочий extractor и точные spans не заменяют независимую ручную проверку.
Это измерения Windows 11 / Python 3.12.6, не VM benchmark; время не является SLA. Полные hashes и определения таймеров — в отчёте/manifests.
Manifests сохраняют старый commit + dirty status и отдельные SHA кода/config: один `cf16e59` не идентифицирует незакоммиченный baseline.

## 10. Долг, приоритеты и задачи для параллельной работы

На время проверки разметки Владом подготовлено отдельное [распределение задач команды](TEAM_TASKS.md): A — Linux-воспроизводимость, B — изолированный прототип model, C — аудит split и вопросы по требованиям. Это рабочее предложение на трёх остальных участников; принятие задач исполнителями и выполнение не подтверждены. Разметка и изменения общей схемы остаются у Влада с Codex.

P0 — препятствует честной оценке/сдаче; P1 — следующий прирост качества; P2 — после измерений. Backlog ниже — **предложение, не назначение участников и не разрешение на VM/API**.
Общие blockers P0: нет независимого gold и полной официальной схемы/формата интеграции. Интеграция baseline в main и установка/синтетические tests на Linux ВМ выполнены; следующий P0 — постоянный сервис на 8000 по новому уточнению администраторов. Временный адаптер реализован; VM deployment ещё не подтверждён.
Замеры H05 на доступной проверенной части выполнены, полный независимый reference H03 ещё не готов. Долг P1: model отсутствует (9 development FN в v2), цвета/бренды и числовой разбор ограничены; confidence не калиброван, near-duplicates не проверены. P2: ML/LLM-опыт, интервалы метрик и отдельная span-conditioned normalization-оценка.

| ID | Приоритет / задача | Зависимости | Где работать | Критерий готовности | Независимость |
| --- | --- | --- | --- | --- | --- |
| H01 | Выполнено: интеграция baseline в main | PR #2 merged, `b3b3d55`; состав и remote проверены | Git, этот статус | Команда создаёт новые ветки от актуального main; VM-публикация отдельно | Координатор; не начинать новые ветки от старого initial main |
| H02 | P0: уточнить required fields, словари, формат и правила gateway | Ответы организаторов | docs/research, этот статус | Зафиксирован источник ответа; влияние на контракт согласовано | Можно параллельно, сообщения самостоятельно не отправлять |
| H03 | P0: ручной dev/validation gold | Имеющиеся tasks; H02 при уточнении схемы | Локальный data/gold, evaluation guide | 120 заданий заполнены, часть проверена вторым человеком, split сохранён | Два участника по категориям, без новых изменений кода |
| H04 | P0: аудит групп и резерв test | split-manifest, H03 | annotation.py, tests/test_data_and_annotation.py | Нет выявленных межsplit дублей/семейств; reviewed test заморожен отдельно | Независим от правил; общую схему не менять |
| H05 | P0: получить validation-метрики и error analysis | H03 | evaluate.py, tests/test_baseline.py, отчёт | Реальные TP/FP/FN и P/R/F1 по категориям/атрибутам, честные знаменатели | QA отдельно от авторов правил |
| H06 | P1: правила смартфонов и model | H05 + development-примеры | rules.py, baseline.json, tests/test_baseline.py | Консервативные spans, regression tests, измеренный Δ на validation | Реализовывать в своей ветке; координация с H07 на общих файлах |
| H07 | P1: чайники, бренды и нормализация | H05; schema agreement | rules.py, normalize.py, baseline.json, tests | Исправлены подтверждённые FP/FN, нет подмены power/standby/объёма | Параллельно H06 по category-блокам; слияния последовательно |
| H08 | P1: пороги/калибровка и интервалы | Достаточный H03/H05 | evaluate.py, verify.py, contracts.py | Score не выдан за probability; отдельная validation/test проверка, изменение decision согласовано | Зависит от gold; общий контракт — через согласование |
| H09 | P2: сравнение одного ML/LLM-метода | H02/H05, разрешение доступа/бюджета | Текущий интерфейс Extractor + будущий согласованный адаптер | Тот же split/verifier; quality, FP, latency/tokens/cost; без выдуманного выигрыша | Только после готового gold и разрешения |
| H10 | P0: Linux/VM-воспроизводимость и финальные артефакты | H01/H02, отдельное разрешение VM | pyproject, CLI, README, документы сдачи | На реальной среде воспроизведён запуск; есть шесть согласованных артефактов | До разрешения — только локальная подготовка, без deploy-скрипта |

Предлагаемое распределение для четырёх человек:

| Роль | Основной поток | Что согласовать с другими |
| --- | --- | --- |
| Участник 1: интеграция/данные | H01/H02, H04, подготовка H10 | Версии входа, общий контракт, порядок PR |
| Участник 2: смартфоны | Своя часть H03, затем H06 | Разметку не утверждать единолично; изменения rules/config с участником 3 |
| Участник 3: чайники/нормализация | Своя часть H03, затем H07 | Единицы и verifier должны оставаться общими |
| Участник 4: QA/оценка | Независимая перепроверка H03, H05/H08; план H09 | Не подбирать правила по test; проверять результаты авторов правил |

Все помогают с разметкой; финальный test проверяют независимо. Ближайший bottleneck — ручные метки и качество, не добавление инфраструктуры или тяжёлой модели.

## 11. Совместная работа и передача изменений

- Основной репозиторий сдачи — [Gitea команды](https://git.hub.gigaschool.ru/tochka-sborki-2026-team-054/project); архив GitHub — только происхождение продуктовых документов, не основная история.
- Локальная разработка — Windows; итоговая проверка — Linux VM организаторов. Не путать локальный успешный прогон с проверкой VM.
- Каждый работает в отдельной feature-ветке от согласованной актуальной базы; интеграция через PR. Не менять main, не делать force push, не переписывать чужую историю.
- Baseline/research и текущие отчёты вошли в main через PR #2. Новую рабочую ветку создавать после fetch от актуального main. Незакоммиченные изменения и локальные data/outputs не передаются через Git.
- Для текущей передачи документов разрешены commit и push в `feature/vlad-setup`; создание PR/merge остаётся отдельным действием. Команда может начать от согласованного commit этой ветки; после merge обновить общую базу.
- До интеграции обязательны относящиеся тесты; для общих rules/contracts/normalize/verifier — весь baseline suite. Контракт и семантику canonical values не менять без согласования.
- Не выполнять `git add -A` без проверки состава. Данные/секреты/разметку/predictions не коммитить; синтетические tests разрешены. Пароли вводятся только в локальном интерфейсе авторизации.
- Не перезаписывать незакоммиченные файлы других участников. Для параллельных веток на одном компьютере использовать отдельные checkout/worktree по согласованной базе.
- Новые сессии Codex начинают с этого статуса и [AGENTS.md](../AGENTS.md); далее читают только модуль своей задачи. Изменения без commit/push/PR остальным участникам могут быть недоступны.

## 12. Как актуализировать этот документ

Обновлять в том же PR после нового модуля, изменения контракта, новых измерений, выбора/замены модели, проверки VM или существенного архитектурного решения.
Проверить фактические пути/CLI, статус реализации, метрики с источником/средой и открытый backlog; не копировать весь EDA или журнал работ.
В шапке обновить дату, ветку, состояние и commit; при dirty-коде сослаться на manifest/SHA. Исторические результаты не выдавать за текущие без проверки версии.
Автоматических hooks нет. При публикации baseline и контракты не менялись. Commit/push и PR/merge текущего релиза явно разрешены пользователем. Установка и 21 test на ВМ подтверждены пользовательским SSH-выводом; постоянный HTTP-сервис и реальный data-run ещё не подтверждены.

## Проверка временного HTTP-адаптера (17 октября)

Основание — новое уточнение администраторов о сервисе на 8000 на выходные.
Код: `src/goodsai/api.py`; синтетические HTTP-тесты: `tests/test_api.py`;
временный контракт и запуск: [HTTP runbook](runbooks/http_service.md).
На локальном Windows/Python 3.12.6 прошли **25 baseline/data/HTTP + 3 reader
tests**, без пропусков; `pip check` не нашёл конфликтов. Отдельный процесс
Uvicorn действительно слушал localhost:8000: health=200, извлечение смартфона
и чайника=200 с проверкой значений, ошибочный JSON=400. После smoke этот
локальный процесс остановлен. Эти результаты не подтверждают запуск на ВМ.

Правила, словари, единицы и decision не менялись. Все кандидаты остаются review.
Зависимости сервера устанавливаются extras; CLI доступен отдельно. Добавление
Python-модуля меняет будущий code hash CLI identity; замороженные отчёты,
reference и predictions этим релизом не пересчитывались. Новый API пока
не является спецификацией организаторов. На ВМ предстоят установка extras,
HTTP-тесты, постоянный запуск и проверка доступности после выхода из SSH.
