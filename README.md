# GoodsAI

Проект команды tochka-sborki-2026-team-054: извлечение атрибутов товаров из
названия и описания. Rules baseline E1 поддерживает смартфоны (`761`) и чайники
(`482`), возвращает JSONL с каноническими значениями и точными текстовыми
свидетельствами. Все найденные значения — кандидаты `review`.

[Демо](#демо-одной-командой) · [Своя карточка](#проверить-свою-карточку) ·
[HTTP](#http-сервис-на-порту-8000) · [Тесты](#тесты) ·
[Полный JSON](#полный-пример-входа-и-результата) · [Артефакты сдачи](docs/DELIVERY_INDEX.md)

## Демо одной командой

Нужны Git checkout этой версии проекта и Python **3.12+** (проверен 3.12).
Открой терминал **в корне GoodsAI**, где находится `pyproject.toml`, и выбери
инструкцию для своей ОС. Выполняй команды по порядку; при ошибке сначала
устрани её. Для первой установки на Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/demo
```

На Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m goodsai.demo --output-dir outputs/demo
```

Если `.venv` уже настроена, повторно создавать её не нужно. После обновления
исходников достаточно установки `-m pip install -e .` и команды демо из блока
своей ОС. Активация окружения не требуется: в командах указан его Python.
`py -3.12`/`python3.12` предполагают установленный Python 3.12; если используешь
другой подходящий Python, укажи его при создании окружения.

Если Python установлен через uv, вместо создания venv используйте
`~/.local/bin/uv venv --python 3.12 --seed .venv`: `--seed` добавляет pip.
Установка требует сети; само демо работает локально, без raw, gold и LLM.
После установки его можно запускать из другой папки через абсолютный путь
к Python окружения; относительный output-dir считается от текущей папки.

Команда вызывает существующий batch `predict`, проверяет все шесть сценариев
и печатает JSON-сводку. Ожидается `checks_passed=6`, `checks_total=6`,
`rows=6`, `llm_calls=0`. Это smoke-проверка синтетических примеров, не P/R/F1.

```text
outputs/demo/
  input.jsonl                  синтетический вход
  predictions.jsonl            реальный результат predict: одна строка на вход
  predictions.manifest.json    run_id, SHA входа/выхода/кода/config, среда, счётчики
  summary.json                 проверки сценариев, статусы, причины, SHA артефактов
```

Рядом могут быть служебные файлы `.*.goodsai.lock`. Это не предсказания и не
признак ошибки: блокировка хранится ОС, а пустой lock-файл остаётся после работы.
Не удаляй его, пока процесс читает или записывает результат.

Каталог должен быть **новым**. Повторный запуск в существующий каталог,
даже пустой, завершается с кодом 2 без перезаписи. Для следующего запуска
укажите, например, `--output-dir outputs/demo-next`. При сбое новый каталог
сохраняется для диагностики; summary появляется только после успеха всех проверок.
Запись в data/raw и в каталог поставляемых примеров запрещена.

Чтобы посмотреть результат на Windows:

```powershell
Get-Content outputs/demo/summary.json -Raw -Encoding UTF8 | ConvertFrom-Json | Select-Object checks_passed, checks_total, rows
Get-Content outputs/demo/predictions.jsonl -Encoding UTF8
```

На Linux:

```bash
cat outputs/demo/summary.json
cat outputs/demo/predictions.jsonl
```

В сводке должны быть `checks_passed=6`, `checks_total=6`, `rows=6`.
JSONL означает: каждая строка — отдельный JSON-объект. Файлы также можно
открыть в редакторе; если выбрано другое имя output-dir, замени его в путях.

| Синтетический сценарий | Ожидаемый результат |
| --- | --- |
| demo-phone | processed; Samsung, 256 GB, 8 GB RAM, 6.5 inch, 5000 mAh, черный |
| demo-kettle | processed; Tefal, 1700 мл → 1.7 L, 2,2 кВт → 2200 W, белый |
| demo-conflict | processed; storage_gb=null, abstain, conflicting_evidence |
| demo-missing | processed; все запрошенные значения null/abstain |
| demo-unknown | unsupported_category; attributes=[] |
| demo-invalid | invalid_input; attributes=[]; строка 6 с title=42 нарушает контракт |

Итого: **4 processed, 1 unsupported_category, 1 invalid_input**, 11 кандидатов
review и 13 отказов abstain среди 24 запрошенных пар. `processed` означает,
что карточка обработана, и не обещает наличия найденных значений. Невалидная
карточка в демо намеренная; если исходы отличаются, команда завершится ошибкой.

Единый источник вымышленных примеров — [products.jsonl](src/goodsai/examples/synthetic/products.jsonl);
отдельные [ожидания](src/goodsai/examples/synthetic/expectations.json) используются
только для проверки результата, не передаются extractor. Ресурсы входят в wheel;
копировать реальные карточки в примеры не нужно.

## Проверить свою карточку

Создай `my-card.jsonl` в корне проекта: UTF-8 **без BOM**, один JSON-объект
на строку. Пример содержимого одной строки:

```json
{"schema_version":"0.1","sku_id":"my-phone","category_id":"761","title":"Смартфон Samsung Demo 8/256GB черный","description":"Аккумулятор 5000 мАч.","seller_attributes":[]}
```

`sku_id` — твой строковый идентификатор, `category_id` — строка `761` для
смартфона или `482` для чайника. title — обязательная непустая строка;
description может отсутствовать или быть null. Непустые seller_attributes
и готовые target-поля в текущем E1 не поддерживаются.

Windows:

```powershell
.\.venv\Scripts\python.exe -m goodsai.cli predict --input my-card.jsonl --output outputs/my-card/predictions.jsonl
```

Linux:

```bash
.venv/bin/python -m goodsai.cli predict --input my-card.jsonl --output outputs/my-card/predictions.jsonl
```

Рядом появится `predictions.manifest.json`. Для нового запуска выбирай новый
output: обычный CLI predict, в отличие от demo, может перезаписать производный
файл. Запись одного output защищена блокировкой: конкурирующий процесс получает
`Output is busy` и должен повторить попытку после завершения первого. Predictions
и manifest публикуются с журналом восстановления; evaluator проверяет SHA пары.
Если запуск прервали, [порядок восстановления](docs/runbooks/output_recovery.md)
позволяет прочитать последний согласованный результат. Неизвестная категория
даёт unsupported_category, невалидная карточка —
invalid_input; проверяй status каждой строки, даже если команда завершилась
без ошибки. Это пакетный вызов; HTTP-сервер для него не нужен.

## Измеренное качество и комплект сдачи

На реальном **AI-assisted human-reviewed** validation reviewed-v2:

| Карточки | Judged-пары | TP / FP / FN | Precision | Recall | micro-F1 |
| ---: | ---: | --- | ---: | ---: | ---: |
| 12 | 67 | 29 / 1 / 21 | 96,7% | 58,0% | 72,5% |

Reference целиком содержит 22 полные проверки; development — ещё 10 карточек,
57 judged-пар, он не включён в строку выше. Выборка малая и неслучайная;
validation участвовал в обсуждении политики и не является независимым holdout.
Эти исторические метрики не пересчитываются демо и не относятся ко всему каталогу.
Candidate coverage не равно precision; auto-accepted coverage текущего E1 — 0.

Per-attribute/per-category P/R/F1, support, coverage и SHA:
[reviewed-v2](docs/research/baseline_evaluation_v2.md).
Все шесть требуемых артефактов, команды, версии и открытые пункты:
[индекс сдачи](docs/DELIVERY_INDEX.md).
Реальные данные, reference и predictions хранятся вне Git; согласованный канал
передачи итогового файла пока открыт. Финальная техническая презентация и
сравнение с ML/LLM ещё не готовы. Демо эти пункты не заменяет.

## HTTP-сервис на порту 8000

17 октября администраторы уточнили: на выходные достаточно решения на **8000**
и всей кодовой базы в **main** одного выданного репозитория. Официальные ручки
и транзакции обещаны в понедельник вечером. Маршруты ниже — временные,
это не утверждённый контракт организаторов.

Для ручного запуска HTTP на Windows (PowerShell, из корня проекта):

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[serve,test]'
.\.venv\Scripts\python.exe -m goodsai.api --host 127.0.0.1 --port 8000
```

На Linux/ВМ после создания `.venv`:

```bash
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m goodsai.api --host 0.0.0.0 --port 8000
```

Последняя команда работает в foreground. Для постоянного запуска после выхода
из SSH нужен менеджер процессов: [инструкция сервиса](docs/runbooks/http_service.md).
Windows-команда слушает только этот компьютер. На ВМ организаторов требуется
`0.0.0.0:8000`. Если служба GoodsAI уже работает на 8000, второй процесс
на этом порту не запускай: используй существующий сервис. Остановить ручной
запуск можно Ctrl+C в его терминале; CLI demo завершается сам.

Пока сервер работает, открой `http://127.0.0.1:8000/docs` **в браузере того же
компьютера**: POST /predict → Try it out → заполни JSON → Execute.
Для проверки с компьютера через платформу открывай адрес демо команды с `/docs`
в конце. `127.0.0.1` на твоём компьютере не является адресом удалённой ВМ.
Корневой `/` показывает служебный JSON, отдельной web-формы товара пока нет.

Из второго терминала Windows:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/predict' -Method Post -ContentType 'application/json' -Body '{"schema_version":"0.1","sku_id":"demo","category_id":"761","title":"Samsung Example 8/256GB"}'
```

Из второго терминала ВМ:

```bash
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  --data '{"schema_version":"0.1","sku_id":"demo","category_id":"761","title":"Samsung Example 8/256GB"}'
```

`/health` возвращает `status=ok`, `/predict` — один JSON того же v0.1, что CLI
(у HTTP `run_id=http-rules-v0`). Корень `/` описывает сервис; интерактивная
документация — `/docs`. Неизвестная категория даёт `unsupported_category`.
Все извлечённые кандидаты по-прежнему `review`, confidence не калиброван.
Этот адаптер не улучшает качество извлечения и не вызывает внешние модели.

## Тесты

Для всех тестов основного пакета, включая HTTP, сначала установи extras
`.[serve,test]` из HTTP-раздела. Без них HTTP-тесты будут пропущены — это не
подтверждает их прохождение. Новая установка pip-зависимостей требует сети.

Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Для текущей версии ожидаются 42 основных и 3 reader tests, включая отдельные
процессы для конкуренции и принудительного завершения записи. Локально проверены
Windows/Python 3.12.6, запуск демо из wheel в чистом окружении и вне репозитория.
Эта новая demo-версия на Linux/ВМ ещё не проверялась и не устанавливалась.

## Для разработчиков

Первый прогон организаторов: [баллы и разбор 18 октября](docs/reviews/2026-10-18_first_run.md).
Текущий порядок доработок: [план после ревью](docs/research/post_review_plan.md).

Начните с [актуального состояния проекта](docs/PROJECT_STATUS.md): карта модулей,
контракты, результаты и задачи для команды. Новым сессиям Codex также нужно
прочитать [AGENTS.md](AGENTS.md), затем только файлы своей задачи.

Подробные исследования: [docs/research/](docs/research/).
Подтверждённые требования, обязательные атрибуты и комплект сдачи:
[docs/REQUIREMENTS_AND_DELIVERY.md](docs/REQUIREMENTS_AND_DELIVERY.md).
Проверенные команды установки, запуска и тестирования: [инструкция baseline](docs/baseline.md).
Первая оценка неизменного baseline на небольшой проверенной части разметки:
[метрики, error analysis и ограничения](docs/research/first_baseline_evaluation.md).
После новых подтверждений reference расширен до 22 карточек:
[текущая оценка reviewed-v2](docs/research/baseline_evaluation_v2.md).
Публикация для ежедневной проверки и обязательный запуск на ВМ:
[план main + ВМ](docs/runbooks/main_and_vm_release_plan.md) (main опубликован; systemd/HTTP smoke на ВМ подтверждены пользователем).

## GoodsAI: первая рабочая версия

Локальный text-only baseline извлекает характеристики смартфонов и электрических
чайников с помощью правил и словарей. Результат — JSONL с исходными текстовыми
доказательствами, нормализованными значениями и эвристическим score.

Установка, запуск, результаты на реальных данных и ограничения:
[docs/baseline.md](docs/baseline.md).

Исследование датасетов: [docs/research/dataset_findings.md](docs/research/dataset_findings.md).
Данные, разметка и предсказания хранятся локально в исключённых из Git `data/` и `outputs/`.

## Полный пример входа и результата

Первая синтетическая карточка:

```json
{
  "schema_version": "0.1",
  "sku_id": "demo-phone",
  "category_id": "761",
  "title": "Смартфон Samsung Demo 8/256GB черный",
  "description": "Диагональ экрана 6,5 дюйма; аккумулятор 5000 мАч.",
  "seller_attributes": [],
  "source_flags": []
}
```

Один объект из predictions.jsonl ниже отформатирован для чтения (в самом файле
он занимает одну строку). run_id показан из локального demo-run и изменится
при изменении байтов входа, кода или config; готовый ответ не подставляется.

```json
{
  "schema_version": "0.1",
  "run_id": "7ea0515dfbe78d18542e",
  "sku_id": "demo-phone",
  "category_id": "761",
  "status": "processed",
  "attributes": [
    {
      "attribute": "brand",
      "value": "Samsung",
      "unit": null,
      "confidence": 0.85,
      "confidence_kind": "heuristic",
      "decision": "review",
      "method": "rule",
      "rule_id": "brand.explicit-title.v1",
      "evidence": {
        "field": "title",
        "start": 9,
        "end": 16,
        "text": "Samsung"
      },
      "reason_codes": []
    },
    {
      "attribute": "model",
      "value": null,
      "unit": null,
      "confidence": null,
      "confidence_kind": "heuristic",
      "decision": "abstain",
      "method": "rule",
      "rule_id": null,
      "evidence": null,
      "reason_codes": [
        "rule_not_implemented"
      ]
    },
    {
      "attribute": "storage_gb",
      "value": "256",
      "unit": "GB",
      "confidence": 0.8,
      "confidence_kind": "heuristic",
      "decision": "review",
      "method": "rule",
      "rule_id": "memory.title-pair.v1",
      "evidence": {
        "field": "title",
        "start": 22,
        "end": 29,
        "text": "8/256GB"
      },
      "reason_codes": []
    },
    {
      "attribute": "ram_gb",
      "value": "8",
      "unit": "GB",
      "confidence": 0.8,
      "confidence_kind": "heuristic",
      "decision": "review",
      "method": "rule",
      "rule_id": "memory.title-pair.v1",
      "evidence": {
        "field": "title",
        "start": 22,
        "end": 29,
        "text": "8/256GB"
      },
      "reason_codes": []
    },
    {
      "attribute": "screen_inches",
      "value": "6.5",
      "unit": "inch",
      "confidence": 0.8,
      "confidence_kind": "heuristic",
      "decision": "review",
      "method": "rule",
      "rule_id": "screen_inches.explicit.v1",
      "evidence": {
        "field": "description",
        "start": 17,
        "end": 26,
        "text": "6,5 дюйма"
      },
      "reason_codes": []
    },
    {
      "attribute": "battery_mah",
      "value": "5000",
      "unit": "mAh",
      "confidence": 0.8,
      "confidence_kind": "heuristic",
      "decision": "review",
      "method": "rule",
      "rule_id": "battery_mah.explicit.v1",
      "evidence": {
        "field": "description",
        "start": 40,
        "end": 48,
        "text": "5000 мАч"
      },
      "reason_codes": []
    },
    {
      "attribute": "color",
      "value": "черный",
      "unit": null,
      "confidence": 0.75,
      "confidence_kind": "heuristic",
      "decision": "review",
      "method": "rule",
      "rule_id": "color.explicit.v1",
      "evidence": {
        "field": "title",
        "start": 30,
        "end": 36,
        "text": "черный"
      },
      "reason_codes": []
    }
  ]
}
```

`value` — каноническая строка, `unit` — единица или null; `evidence` указывает
поле и точный raw-фрагмент с zero-based, end-exclusive offsets. `confidence`
с `confidence_kind=heuristic` — инженерный score, **не вероятность**.
Найденные значения остаются `review`; автоматического принятия нет.
`model=null` с `rule_not_implemented` — известная граница текущего baseline.
При abstain value/unit/confidence/evidence равны null, причина — в reason_codes.
Точный span доказывает источник текста, но не истинность характеристики.
