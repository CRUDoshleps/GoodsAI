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
manifest запуска. Пример проверен локально на Windows с теми же JSONL-записями;
полный Linux/VM-прогон пока не подтверждён.

Сейчас HTTP-сервиса и официального API-адаптера нет, непустые seller attributes
не поддержаны, runtime ML/LLM-эксперимент ещё не выполнен. Код опубликован в
main через PR #2; следующий этап — воспроизводимый запуск на ВМ, затем сервис
и улучшение качества.

## Для разработчиков

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
[план main + ВМ](docs/runbooks/main_and_vm_release_plan.md) (main опубликован; deployment ещё не выполнен).

## GoodsAI: первая рабочая версия

Локальный text-only baseline извлекает характеристики смартфонов и электрических
чайников с помощью правил и словарей. Результат — JSONL с исходными текстовыми
доказательствами, нормализованными значениями и эвристическим score.

Установка, запуск, результаты на реальных данных и ограничения:
[docs/baseline.md](docs/baseline.md).

Исследование датасетов: [docs/research/dataset_findings.md](docs/research/dataset_findings.md).
Данные, разметка и предсказания хранятся локально в исключённых из Git `data/` и `outputs/`.
