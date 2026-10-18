# M2 — расширение reference и резерв независимой оценки

**Актуальное состояние:** все 20 карточек подтверждены в round6, reference
заморожен и A/B/C измерены; [итоговый отчёт](m2_evaluation_results.md).
Это development, не независимый test. Далее сохранён протокол первоначальной
подготовки и история промежуточных N/A/partial-статусов.

После человеческой обратной связи согласована [политика v2](m2_annotation_policy_v2.md).
Форма промежуточного round5 — `data/gold/e1/m2/v2/review-round5/development.review.md`;
на том этапе в `feedback/round5.*` были 119 полей / 19 полных карточек.
Последнее model-поле D18 затем подтверждено ambiguous в round6;
[внешний контекст отдельно](m2_round5_external_context.md).
Числа исходного черновика ниже сохранены как история; новая версия содержит
policy-v2: 82 present / 32 absent / 6 ambiguous. Рабочие решения round4:
84 present / 32 absent / 4 ambiguous; в round5 83 / 32 / 5 соответственно.
После round6 P/R/F1 рассчитаны в итоговом отчёте, промежуточные N/A — история.

18 октября 2026 года. База — `origin/main=c813f31` (PR #10), ветка
`feature/vlad-model-evaluation`. Runtime M1, контракт v0.1, confidence и
review/abstain не менялись. M2 подготовлен **до человеческой проверки**,
а не завершён как оценка качества.

## Результат подготовки

| Артефакт | Состояние |
| --- | --- |
| Новый development | 20: по 10 смартфонов и чайников, в каждой категории 5 с описанием / 5 без |
| AI-assisted черновик | 120 решений: 79 present, 32 absent, 9 ambiguous; все pending |
| Резерв test | 40: по 20 каждой категории, по 10 с описанием / без; только metadata и пустые задания |
| Новые TP/FP/FN, P/R/F1 | **N/A**, нет подтверждённого reference |
| Predictions / модельные вызовы | Не запускались в M2; расходы 0 |
| Публикация / ВМ | Не выполнялись |

Все реальные тексты, SKU, метки и manifests — в игнорируемом
`data/gold/e1/m2/`. В Git входят инструменты, синтетические тесты и агрегированный
протокол. Старые gold, predictions и отчёты не изменены.
Начать с локального `data/gold/e1/m2/v2/START_HERE.md`, затем
`review-v2/development.review.md`; вопросы — `review-v2/development.disputes.md`.
**D01–D20 относятся только к v2**. Тексты test сейчас не экспортированы.

## Отбор до предсказаний

Seed: `goodsai-m2-selection-20261018-v1`. `prepare_m2.py freeze` создаёт новую
папку и policy с временем UTC и identity M1, не читая карточки. `select`
проверяет policy/runtime, затем использует только разрешённые тексты и отдельно
split/group metadata. Predictions, target params, vendor/model-подсказок нет.
SKU нужен для ranking/аудита экспозиции, не для определения атрибутов.

Development: category × наличие description, по 5 в ячейке. Заранее заданы
слоты: неоднозначное имя, проблема единиц, HTML, мало числовых признаков,
случайный. Это эвристики отбора, не диагноз baseline. Если сигнала нет,
берётся первый доступный по SHA256(seed:purpose:SKU). Фактически признаки
имени есть у 11 карточек, единиц у 5, HTML у 9, sparse у 11; они пересекаются.
«кг» может быть правильным весом, sparse не доказывает отсутствие атрибута.
Test: случайный hash ranking, 10 на ячейку, строго `test_reserved`.
В итоговых 60 заданиях — по одной карточке из вычисленного семейства.

Источник — 10 324 существующих text-only Product из `data/processed/e1/pilot.jsonl`,
SHA256 `68875ae2ef66c3527915be0e2cca29639c4a1c792e359973ae8623a404b70fe3`.
Полный EDA и pickle не повторялись. SHA split, источников экспозиции, policy,
каждого результата, инструмента и runtime — в `selection.summary.json`.

### Уточнение группировки до оценки

Первый отбор v1 сохранён (20 development / 40 metadata-only test). После
просмотра **только development**, до любых predictions, обнаружены варианты
одного имени с разными кодами в скобках. Скелет названия усилен удалением
скобок с содержимым; это правило quarantine, не извлечения model.

Policy v2 заморожена заново с прежним seed. Все 20 открытых development из v1
включены в экспозицию и не считаются новыми в v2. v1 сохранён, но его резерв
**не использовать**. Выбран единственный итоговый резерв v2; не выбирать между
ними по качеству. Это раскрытая доработка отбора, а не полностью слепой
первичный дизайн. Предсказания не использованы ни для v1, ни для v2.
Дальше отбор заморожен; неудобные карточки после оценки не заменять.

## Пересечения и независимость

Учтены прежние 120 заданий / full AI v4, 400 E1-карточек EDA и 20 из v1:
**532 уникальных известных экспозиции**. Реконструированный EDA совпал с
фактическим inspection_sample.json: 400 E1 SKU, дополнительных не найдено.
Неучтённые просмотры вне этих источников доказать невозможно.

Компоненты строятся по прежней group_id, точному нормализованному видимому
title/description, скелету title (без памяти/единиц/цвета/скобок), близким
title/description. Точные исходные дубли покрыты нормализованным равенством.
Для title — Jaccard символьных триграмм ≥0,90; для description — Jaccard
5-словных шинглов ≥0,90. HTML обрабатывает visible_view, регистр/пунктуация/ё
нормализуются только для аудита. Prefix-filter проверен против brute force.

Получено **2 196 семейств**. Исключены целиком 317 семейств с экспозицией и
632 семейства, затрагивающих несколько исходных split; множества пересекаются.
Осталось 2 010 допустимых строк; квоты заполнены. У выбранных 60 карточек
нет пересечений SKU/group_id/family_id. Исходный split не переписывался.
`family.manifest.jsonl` и `audit.edges.jsonl` хранят причины объединений;
счётчики edges показывают успешные объединения, не все похожие пары.

Лексический аудит не доказывает отсутствия всех семантических родственников.
Удаление скобок может излишне объединять варианты, уменьшая доступный пул.
При позднем обнаружении родственников dev/test quarantine применяется целиком
до оценки с новой версией manifest. Плохой результат test не основание замены.

## Черновик и человек

AI-разметка составлена по development-текстам и [политике](annotation_plan.md),
без predictions/внешних источников. Размечены все применимые поля независимо
от возможностей runtime. Границы model, новые оттенки и формы памяти вынесены
на обсуждение. У non-present value/unit/evidence=null, есть объяснение.
У present — точный raw span Unicode [start:end] и каноническое значение.

`development.decisions.json` хранит решения автора. `review_m2.py build`
только находит заданную автором цитату, проверяет видимость/координаты,
единицы, числовую канонизацию и сохранение символов model, затем строит JSONL
и Markdown. Правильность смысла проверяет человек, а не этот скрипт.

Ответы: `D01: всё верно`; `D03: model=8C, остальные верно`;
`D06: color — не уверен`. Можно проверять по 5 карточек.
Подтверждение ambiguous — согласие с неоднозначностью, не достоверное значение.
Внешние исправления без текстового свидетельства сохранять отдельно.

После ответов создать новые feedback/reviewed-файлы с происхождением и SHA.
Не переименовывать весь AI-файл в manual. Неотвеченные поля остаются pending,
частичная карточка не становится полной reviewed. Только после проверки всех
полей допустимы annotation_status=reviewed, label_source=manual, имя reviewer,
с сохранением ai_assisted=true и ссылки на feedback. Это не независимый gold.

## Протокол оценки после подтверждений

1. Заморозить новый reviewed development отдельным файлом; сохранить support,
   исключённые ambiguous/unjudgeable и pending. Новую политику сначала
   согласовать и версионировать; runtime M2 не менять.
2. Проверить frozen M1: c813f31, rules `rules-0.2.1-model-boundaries`, code SHA
   `3fa9972c690370806c0ad42ad1e90d8174cce920f4c7c33a5dc8d0f2728fee85`, config SHA
   `974ffffb9f56d30386ea41b456c5d78b1ff72ebbb40cd33ca3779af2c88e3b98`.
   git_dirty=true в manifest объясняется M2-инструментами; runtime неизменен.
   Смена runtime требует отдельно названного опыта.
3. Запустить существующий compare_model_stage.py: A — baseline 5f77d81;
   B — текущие проверки с отключённым model generation только в ablation;
   C — текущий M1. A не является «M1 до фикса». Вход одинаковый text-only.
4. P/R/F1 и TP/FP/FN — по attribute/category/category×attribute, micro/macro,
   judged/present/absent support и исключения. Ошибка значения = FP+FN.
   Coverage отдельно от качества. Разобрать все model FN/FP, новые TP, потери
   TP и изменения остальных атрибутов. M2 не обещает улучшения предсказаний.
5. Runner сохраняет парные Δ, predictions/manifest/SHA, три повтора latency,
   p50/p95 и throughput. Дополнить агрегат title-only/description и заранее
   записанными feature-срезами из manifest по тем же frozen predictions.
   Если этих срезов нет в runner, рассчитать отдельным отчётом без изменения
   evaluator/подбора правил. На малом support p95 описательный. API calls,
   tokens/cost=0; продавцы/трафик N/A без подходящих метаданных.
6. Старый validation называть development_feedback: на нём исправлялись
   правила. Новый development также не holdout. При новых FP/неясной роли
   имени зафиксировать провал и отдельную задачу; test для исправления не открывать.

Команда только после подтверждений и появления указанного reviewed-файла:

```powershell
.\.venv\Scripts\python.exe scripts/research/compare_model_stage.py `
  --gold data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl `
  --split development --baseline-ref 5f77d81 --repeats 3 `
  --output-dir outputs/experiments/model-stage/m2-reviewed-development-v1
```

На этапе подготовки этот файл намеренно отсутствовал. После round6 он создан
отдельно, новые predictions/метрики сохранены в новом run-dir; см. итоговый отчёт.

### Будущий независимый test

test_reserve.blank.jsonl содержит только T01–T40, SKU/category/group/family/split
и пустые атрибуты. Это **не Product input**: title, description, target,
predictions, AI-ответов и rationale в нём нет.
До фиксации сравниваемых C/D и политики оценки тексты не материализовать для
анализа. Затем отдельный человек-reviewer, не подбиравший правила по этим
карточкам, получает только исходные разрешённые тексты и пустой шаблон.
Записать reviewer, инструкцию, дату, ослепление и SHA. AI-предзаполнения нет.
Если reviewer сам разрабатывал правила, раскрыть ограничение независимости.
После фиксации человеческого reference выполнить один финальный прогон
frozen-методов. Ошибки test не использовать для подбора правил; дальнейшая
разработка требует нового резерва. Сейчас это лишь кандидат на независимую
оценку, без подтверждения человеком и семантическим аудитом.
M3/API/budget и VM — отдельные разрешения.

## Воспроизведение и проверки

Новые каталоги не должны существовать. Для точного v2 нужны локальные
источники экспозиции, включая сохранённый v1.

```powershell
.\.venv\Scripts\python.exe scripts/research/prepare_m2.py freeze --bundle data/gold/e1/m2/reproduction
.\.venv\Scripts\python.exe scripts/research/prepare_m2.py select `
  --bundle data/gold/e1/m2/reproduction --input data/processed/e1/pilot.jsonl `
  --split-manifest data/gold/e1/split_manifest.jsonl `
  --seen data/gold/e1/tasks.jsonl --seen data/gold/e1/ai/full.annotations.v4.jsonl `
  --seen data/gold/e1/m2/v1/development.tasks.jsonl `
  --eda-sample outputs/eda/inspection_sample.json
.\.venv\Scripts\python.exe scripts/research/review_m2.py audit --bundle data/gold/e1/m2/v2
.\.venv\Scripts\python.exe scripts/research/review_m2.py build `
  --bundle data/gold/e1/m2/v2 --decisions data/gold/e1/m2/v2/development.decisions.json `
  --output data/gold/e1/m2/v2/review-copy
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_m2_preparation.py -v
```

7 новых синтетических тестов прошли на Windows/Python 3.12.6: repeatable
selection, quarantine, близость против brute force, split/policy/SHA guards,
неперезапись, shortfalls без принудительного добора, blind blanks,
Unicode/HTML evidence, отсутствие manual-продвижения и N/A evaluator для AI.
Audit реального v2 прошёл. Linux/ВМ здесь не проверялись.
Полная baseline/data/API/demo/model/storage suite — **66 tests, OK**.
После правки отображения таблиц целевые 7 тестов повторены; AI-решения
не менялись. Первоначальная форма review сохранена, актуальная — review-v2.
