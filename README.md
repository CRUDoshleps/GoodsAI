# project

tochka-sborki-2026-team-054 hackathon project

GoodsAI извлекает атрибуты товаров из названия и описания. Текущий baseline —
Python CLI на правилах для смартфонов (`761`) и чайников (`482`). Возвращает
JSONL с каноническими значениями, точными текстовыми свидетельствами и
эвристической уверенностью. Все найденные значения — кандидаты для review.

## Быстрый запуск без датасетов

Нужны Git checkout проекта и Python **3.12+**. На Linux в чистой рабочей копии:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Если Python установлен через uv, окружение можно создать командой
`~/.local/bin/uv venv --python 3.12 --seed .venv` вместо первой строки (`--seed`
устанавливает pip для следующей команды). На Windows
используйте `py -3.12 -m venv .venv` и `.venv\Scripts\python.exe`.
Установка зависимостей требует сети; само извлечение выполняется локально.

Синтетический пример для Linux; исходные данные и разметка не нужны:

```bash
goodsai_demo="$(mktemp -d)"
cat > "$goodsai_demo/input.jsonl" <<'JSONL'
{"schema_version":"0.1","sku_id":"demo-phone","category_id":"761","title":"Смартфон Samsung Example 8/256GB черный","description":"Диагональ экрана 6,5 дюйма; аккумулятор 5000 мАч.","seller_attributes":[],"source_flags":[]}
{"schema_version":"0.1","sku_id":"demo-kettle","category_id":"482","title":"Электрочайник Tefal Example белый","description":"Объем 1.7 л. Мощность 2200 Вт.","seller_attributes":[],"source_flags":[]}
JSONL
.venv/bin/python -m goodsai.cli predict --input "$goodsai_demo/input.jsonl" --output "$goodsai_demo/predictions.jsonl"
cat "$goodsai_demo/predictions.jsonl"
```

Ожидаются две строки `processed`: у смартфона, например, storage `256 GB`,
RAM `8 GB`, screen `6.5 inch`; у чайника capacity `1.7 L`, power `2200 W`.
Поле `model` в текущем baseline всегда null с причиной `rule_not_implemented`.
Результат содержит value/unit/evidence/confidence/decision, рядом сохраняется
manifest запуска. Пример проверен локально на Windows с теми же JSONL-записями.
На ВМ организаторов установлен GoodsAI и прошли 18 baseline/data + 3 reader
tests, включая синтетический CLI; отдельный пример выше и реальные данные
на ВМ ещё не прогонялись. [Протокол воспроизведения](docs/runbooks/vm_reproduction.md).

Непустые seller attributes не поддержаны, runtime ML/LLM-эксперимент ещё не
выполнен. Установка и тесты CLI на ВМ подтверждены. Ниже — временный HTTP-адаптер;
его запуск на ВМ через systemd, health и synthetic predict подтверждены выводом пользователя.

## HTTP-сервис на порту 8000

17 октября администраторы уточнили: на выходные достаточно решения на **8000**
и всей кодовой базы в **main** одного выданного репозитория. Официальные ручки
и транзакции обещаны в понедельник вечером. Маршруты ниже — временные,
это не утверждённый контракт организаторов.

В корне проекта на Linux:

```bash
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m goodsai.api --host 0.0.0.0 --port 8000
```

Последняя команда работает в foreground. Для постоянного запуска после выхода
из SSH нужен менеджер процессов: [инструкция сервиса](docs/runbooks/http_service.md).
На Windows замените путь к Python на `.venv\Scripts\python.exe`.
Для локальной проверки можно оставить default host `127.0.0.1`.

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
