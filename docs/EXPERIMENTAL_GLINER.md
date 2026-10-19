# ML-001: экспериментальный гибрид для бренда

Статус: опциональный development prototype. Основные CLI/API по-прежнему
используют правила. Включение по умолчанию и auto_accept не разрешены этим
экспериментом; для них нужна независимая приёмка EVAL-001/004.

## Что реализовано

`HybridExtractor` сначала запускает неизменённый `Extractor`. Только для
`brand` с причиной `not_found_by_rules` вызывается локальный GLiNER. Он получает
видимые первые 512 символов title, метки `brand` / `product model`, порог 0.5.
Из результата используется только однословный бренд до позиции 65; общие
названия товаров, аксессуары, совместимость и отрицание в предшествующем
контексте отбрасываются. Разные бренды дают abstain. Значения модели товара
не дополняются: в первом опыте её названия часто извлекались неполностью.

Mapping проверяет точные raw offsets, HTML/entities и видимый текст. Результат
проходит существующие проверки кандидата и prediction. Источник `method=model`,
score остаётся эвристикой; все новые значения имеют `decision=review`.
Найденные правилами значения и конфликты не перезаписываются. При отсутствии
модели/зависимости сохраняется rules output с `model_unavailable` на пропущенном
бренде; повторные попытки загрузки в этом экземпляре отключаются. Это не
доказательство семантической корректности каждого предложения.

## Воспроизведение на CPU

Отдельное окружение Python 3.12; основной пакет не устанавливает ML-зависимости.

```bash
python3.12 -m venv .venv-ml
.venv-ml/bin/python -m pip install 'torch==2.9.1+cpu' --index-url https://download.pytorch.org/whl/cpu
.venv-ml/bin/python -m pip install -e '.[ml]'
.venv-ml/bin/python -m pip check
.venv-ml/bin/python scripts/research/prepare_gliner.py --output /absolute/private/models/gliner-brand-v1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-ml/bin/python -m goodsai.experimental_gliner \
  --artifact /absolute/private/models/gliner-brand-v1 \
  --input /absolute/private/development-input.jsonl \
  --output /absolute/private/hybrid-predictions.jsonl
```

Подготовка явно скачивает ~1.16 GB safetensors и tokenizer assets. Каталог
назначения должен отсутствовать. Нужны свободное место и запас RAM; измеренный
peak RSS ниже не является верхней границей для любых входов/окружений.
Подготовленный каталог привязан к абсолютному пути encoder; после переноса
нужна повторная подготовка. Inference не скачивает веса и не исполняет remote
code/pickle. Загрузка lazy: первый пропущенный бренд включает imports, проверки
hashes и создание модели. Остальные запросы используют тот же экземпляр.
CLI не заменяет основной release runner и не собирает его шесть артефактов.

Weights: [GLiNER multilingual v2.1](https://huggingface.co/urchade/gliner_multi-v2.1),
Apache-2.0, revision `443d26d654e0324125a96bebd8e796c14ff2efe6`;
encoder/tokenizer: [mDeBERTa-v3-base](https://huggingface.co/microsoft/mdeberta-v3-base),
MIT, revision `a0484667b22365f84929a935b5e50a51f71f159d`.
SHA256 weights: `2100142f31627531497850659dcb3821c99d5e71c08a8e01a98e4b11ef32a199`.
Сохраняется manifest файлов; loader проверяет hashes и локальный encoder.

Проверенное окружение: torch 2.9.1+cpu, gliner 0.2.29, transformers 4.57.6,
protobuf 6.33.5, tokenizers 0.22.2, huggingface-hub 0.36.2. При первом preflight
не хватало protobuf; зависимость добавлена до успешной загрузки модели.

## Development-измерение 19.10.2026

Inference проверен на VM с четырьмя vCPU и около 8 GB RAM, CPU float32,
два torch-потока. База первого сравнения — claim `c463e02`; код опционального
runtime — `c3706d2`. Базовые правила в них одинаковы.

80 ранее просмотренных development-карточек: 40 смартфонов и 40 чайников.
Эталон получен AI-assisted диагностикой предыдущего аудита, затем приведён
к действующей сериализации значений/единиц. Он **не human gold и не независимый
test**. Из 480 полей оцениваются 425: 296 present и 129 absent; 49 unjudgeable
и 6 ambiguous исключены явно. Вход, reference и evaluator одинаковы во всех
строках таблицы; test reserve не открывался.

| Режим | TP / FP / FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| Правила | 208 / 8 / 88 | 96.30% | 70.27% | 81.25% |
| GLiNER для пропущенных brand/model, без role guards | 228 / 18 / 68 | 92.68% | 77.03% | 84.13% |
| GLiNER для brand/model с заранее заданными title guards | 231 / 14 / 65 | 94.29% | 78.04% | 85.40% |
| Только однословный бренд, после анализа development-ошибок | 225 / 8 / 71 | 96.57% | 76.01% | 85.07% |

Первые три режима, labels/threshold, checkpoint, input/reference hashes и
keep/drop были зафиксированы до первого inference. Наличие нового FP относительно
этого эталона запрещало сохранять широкий вариант. Последняя строка выбрана
**после просмотра ошибок**: это development feedback и потенциально оптимистичная
оценка. Порог не перебирался, веса не обучались. Нельзя называть 85.07% финальным
качеством или сравнивать эту цифру с чужим F1 на другой выборке.

Широкий guarded вариант добавил 23 совпадения и 6 несовпадений с reference:
пять неполных названий модели товара и один бренд с частью названия линейки.
Поэтому он не включён в runtime. Узкий вариант добавил 17 совпадений бренда
без новых несовпадений на judged development-парах. Brand recall: 57/79 → 74/79
(72.15% → 93.67%); FP бренда остался 1. Все остальные поля совпадают с правилами.
FP здесь — несовпадение с AI-reference, не обязательно подтверждённая человеком
ошибка системы. В наборе нет judged absent-брендов: этот режим не оценён на
реальных карточках без бренда. Проверки отрицательных ролей пока synthetic.

Опциональный runtime воспроизвёл последнюю строку на двух запусках с одинаковыми
prediction objects. 21 из 80 карточек вызвала ML, 17 получили новое предложение.
Exact evidence/schema проверены у всех результатов; API inference calls — 0.
Отдельный synthetic smoke загрузил модель и выполнил inference при запрещённом
`socket.connect`: сетевых попыток не было. Это проверка офлайн-работы, не качества.

| Ресурс | Измерение |
| --- | ---: |
| Все 80 карточек, холодный первый запуск | 14.64 s |
| Все 80 карточек, второй запуск с загруженной моделью | 2.36 s |
| Первый model call с imports/hash checks/load | 12.35 s |
| Warm model call p50 / p95, второй запуск | 105 / 111 ms |
| All-card p50 / p95, второй запуск | 2.69 / 109.52 ms |
| Peak process RSS | 2750 MiB |

Низкий all-card p95 не отражает cold start; загрузка показана отдельно. Рубли
за локальный compute не измерялись. Библиотеки выдают предупреждения fast-tokenizer
о byte fallback/regex и отсутствии заданного tokenizer max length. Ограничение
title в 512 символов и точное сопоставление evidence действуют, но применимость
tokenizer к более широким входам требует отдельной проверки; настройки tokenizer
по итогам этого опыта не менялись.

## Доказательства и ограничения

- Input SHA256: `6372c63fafb6e2119a225eff8c994f1790a6b0b339191c6c0299aa6fa675efa2`.
- Reference SHA256: `ad393485465028c85c0700a7466e541f4fd43804b4c82fbb699058bcdcff3e89`.
- Приватные input/reference/predictions и диагностические логи в Git не попадают.
  Их hashes и метрики выдаются отдельно в обезличенной сводке эксперимента.
- 146 основных и 3 reader tests прошли на VM; 11 новых тестов проверяют fallback,
  отсутствие скрытых вызовов, unknown/known brand, конфликты, отрицательные роли,
  offsets/HTML, malformed entities и отказ модели. Они не доказывают real-world
  precision/recall. `pip check` прошёл.
- Решение keep: сохранить узкий прототип как opt-in development experiment.
  Широкий brand/model вариант — drop. Default enable, обещания accuracy и
  auto_accept — заблокированы независимой приёмкой.
- Перед штатным включением нужны human-reviewed positive/absent/hard-negative
  примеры, family-safe split, проверка после интеграции VER-001/002 и повторный
  сравнительный замер с зафиксированными методами на независимых данных.
