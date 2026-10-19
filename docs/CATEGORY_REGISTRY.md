# CONF-003: train-only реестр категорий

[DONE — feature candidate] Реализован opt-in `config_version=2` с
`category_registry.registry_version=1`. Он стоит поверх CONF-001 и внутреннего
stage contract ARCH-001. Публичная форма JSON E1 остаётся `0.1`; набор полей
и единицы каждой экспериментальной категории явно определены конфигом.
Это расширение требует архитектурного review перед интеграцией. По умолчанию
по-прежнему работают две исходные категории и конфиг v1.

## Запуск вымышленного примера

Из корня checkout с установленными зависимостями проекта:

```bash
.venv/bin/python scripts/research/demo_category_registry.py --output-dir outputs/category-demo
```

Папка должна быть новой. Пример создаёт 120 вымышленных train-карточек,
учит 30 вымышленных категорий, затем предсказывает 30 text-only карточек.
В папке находятся train/split/traffic, `registry/config.json`,
`registry/learning_report.json`, predictions и manifest. Число извлечённых
кандидатов вычисляется по manifest. Это не real top-30 coverage и не метрика
качества; P/R/F1 не заявляются. Повторный запуск требует другого output-dir.

Повторить inference уже построенным конфигом:

```bash
.venv/bin/python -m goodsai.cli --config outputs/category-demo/registry/config.json predict --input outputs/category-demo/text-only.jsonl --output outputs/category-demo/repeat.jsonl
.venv/bin/python -m goodsai.api --config outputs/category-demo/registry/config.json --host 127.0.0.1 --port 8001
```

API и batch используют один loader/Extractor/verifier. Порт 8001 позволяет
проверить candidate отдельно от уже запущенного сервиса.

## Что передать от data/evaluation

[PLAN] Реальное обучение требует отдельной разрешённой train-выгрузки.
Исходный pickle и полный каталог инструмент не открывает. Существующий
`test_reserved` и любые тексты validation/test не подаются в learner.
Производитель выгрузки отвечает за family/seller-safe split: learner проверяет
только disjoint SKU и hashes, а не доказывает независимость семейств.
Hash связывает файлы, но не аутентифицирует их источник.

1. `train.jsonl`: строго train, по одной карточке на SKU:

```json
{"sku_id":"invented-train-1","category_id":"invented-category","title":"Прибор 8/256GB","description":"Материал: металл;","params":[{"name":"Оперативная память","value":"8","unit":"GB"},{"name":"Накопитель","value":"256","unit":"GB"},{"name":"Материал","value":"металл","unit":null}]}
```

`params` используются только на этапе обучения, не передаются в Product или
predict. Число и единица предварительно разделяются data-проекцией; единицы и
названия параметров должны быть согласованы. Синонимы названий не объединяются
автоматически. Неоднозначные/дублирующиеся параметры требуют решения data,
а не случайного выбора значения.

2. `split.json`: только IDs и SHA-256 файла train, без heldout-текстов:

```json
{"schema_version":"goodsai-train-split-1","train_sha256":"<64 hex characters>","train_sku_ids":["invented-train-1"],"validation_sku_ids":[],"test_sku_ids":[]}
```

Проекция обязана точно совпасть с train_sku_ids. Повторы, пересечение split,
лишние и отсутствующие SKU приводят к отказу. Даже если неверный файл назван
train, при принадлежности SKU validation/test он не интерпретируется как
обучающий пример. Подготовку нового разбиения learner не выполняет.

3. `traffic.json`: агрегаты разрешённого train-трафика, без query/click rows:

```json
{"schema_version":"goodsai-category-traffic-1","scope":"train","train_sha256":"<same SHA-256>","category_traffic":{"invented-category":100}}
```

Приоритет задаётся убыванием трафика, при равенстве — category ID. Все категории
train должны иметь агрегат, отсутствующий трафик не подменяется частотой SKU.
Отбор по train предотвращает настройку схем по heldout. Если команда согласует
другую основу рейтинга top-30, формат и provenance меняются отдельно.

## Реальный кандидат конфига

```bash
.venv/bin/python -m goodsai.learn_categories --train data/processed/approved/train.jsonl --split data/processed/approved/split.json --traffic data/processed/approved/traffic.json --output-dir outputs/category-registry --top-k 30
.venv/bin/python -m goodsai.cli --config outputs/category-registry/config.json predict --input data/processed/approved/development-text-only.jsonl --output outputs/category-registry/development-predictions.jsonl
```

Эти команды — [PLAN] для разрешённых файлов data; таких файлов в Git нет.
`top_k_complete=false` честно сообщает, что нужные 30 категорий не получены.
Категории без eligible-полей не заменяются более низкими в рейтинге молча.
Входы хешируются до/после двух проходов; при ошибке результат не публикуется.
Новый private output-directory публикуется rename, config/report имеют mode
0600, каталог 0700 на POSIX. Это локальный single-writer инструмент; против
враждебного изменения каталогов или сетевой FS гарантий нет. Конфиги со
словарями содержат данные train и остаются в outputs вне Git. Только безопасные
агрегаты после согласования можно публиковать отдельно.

## Схема и словари

- Заполненность: число train-SKU с параметром / все train-SKU категории.
  Порог по умолчанию 0.5; ниже 0.5 конфиг не принимается.
- Имена `catalog_<sha256(name.casefold())[:16]>` не пересекаются с исходными
  brand/model/etc. Оригинальное название хранится в spec.name. Для сравнения
  со старым gold необходим явный согласованный mapper; learner не переименует
  старые labels автоматически.
- Категориальные значения берутся только из train. Регистр/пробелы
  нормализуются; неизвестное значение → abstain, синонимы не выдумываются.
- Числа: неотрицательный decimal, точная единица, запятая → точка. Новое
  значение может обобщаться через изученный шаблон; произвольные преобразования
  единиц не выполняются. Canonical unit задан в каждом spec.
- Смешанные единицы и словари больше 1024 уникальных значений исключаются с
  reason count. Не более 128 eligible атрибутов категории.

## Правила и изучение порядка чисел

`Ключ: значение` и `Ключ = значение` извлекаются в начале текстового блока
или после `;`, с полной границей значения. Источник — title/description.
Неизвестная часть значения, например «металл с покрытием» вместо «металл»,
не обрезается до известного словарного префикса.

Для пар `a/b<unit>` и размеров `a×b×c<unit>` / `axbxc<unit>` / `aхbхc<unit>`
порядок атрибутов определяется совпадением чисел с train params. Код не
назначает первую позицию RAM или ширине по имени поля. Нужны минимум 3 разных
SKU и >=95% согласия среди наблюдений формы в категории. Повтор одной строки
в title не увеличивает support. Равные числа с несколькими возможными ролями
не становятся обучающим голосом. Это ограниченная библиотека форм; произвольные
regex или Python из конфига не исполняются. Новые формы требуют отдельного кода.

Кандидаты проходят общий structural/relation/conflict/output verifier. Exact
raw evidence включает ключ или всю числовую группу, например `8/256GB`.
Проверяется, что нормализованное значение получается из этого evidence
разрешённой грамматикой. HTML/entities сохраняют исходные offsets; скрытые
или пересекающие block-boundary фрагменты отвергаются. Широкое семантическое
связывание с главным товаром не доказано: conservative syntax guards остаются
ограничением. Все результаты — review/abstain, score heuristic, LLM off,
auto_accept off. 95% template agreement не равно precision или calibration.

## Передача на оценку и приёмку

[PLAN] Data/evaluation передаёт разрешённые train/split/traffic и их provenance;
архитектор согласует category/attribute IDs, единицы и scope. После обучения
фиксируются config SHA, code SHA, training hashes, schema mapper и manifest.
Только затем на разрешённом frozen validation проверяются новые категории,
худшие атрибуты, FP/FN, время/RAM и вклад этого шага. До этого реальный top-30,
качество, production enable и полная CONF-003 не считаются завершёнными.
Калибровка, LLM, аналоги каталога и seller attributes остаются отдельными задачами.

[Доказательства] `tests/test_category_registry.py`: 30 вымышленных категорий,
конфиг без изменения orchestration, API/batch parity, точные HTML offsets,
конфликт/неизвестное значение/negation, split/hash guards, fail-before-publish,
проверка недоверенного source. Это инженерные проверки, не independent gold.

## Следующий шаг: явное сопоставление разметки и validation report

[DONE — feature candidate, продолжение CONF-003; зависимость — CONF-001 / PR #92] Команда
`goodsai.registry_evaluation` принимает готовый frozen config, text-only
validation input, reviewed manual reference, тот же split manifest и явный
schema mapper. Она переиспользует обычные predict/evaluate, не обучает rules,
не меняет словарь и не вызывает LLM. Это инструмент development feedback;
происхождение разметки и независимость человека он доказать не может.

Mapper связывает имена полей исходной разметки с target IDs конфига:

```json
{"mapping_version":"1","config_sha256":"<effective config hash>","categories":{"<category ID>":{"<reference field>":"<target attribute ID>"}}}
```

Hash effective config вычисляется так (путь заменить своим frozen config):

```bash
.venv/bin/python -c 'from goodsai.config import load_config; from goodsai.registry_evaluation import config_hash; print(config_hash(load_config("outputs/category-registry/config.json")))'
```

Сопоставление задаёт человек до измерения; fuzzy match по именам, изменение
категорий, отбор удачных ответов или подмена единиц не выполняются. Оно должно
быть one-to-one, target должен входить в schema, единица reviewed label должна
точно совпасть с target. Ссылка на отсутствующий source label — ошибка, а не
молчаливое исключение. Поля, для которых нет сопоставленного label, получают
`unjudgeable`, а не `absent`; их число и judged/requested пары видны в отчёте.
Из метрики только на небольшой размеченной части нельзя делать вывод о полном
качестве новых категорий.

Исходный reference содержит те же source title/description и SKU, что input;
`split="validation"`, `annotation_status="reviewed"`, `label_source="manual"`,
непустые annotator и group_id/family_id, labels со статусами
present/absent/ambiguous/unjudgeable. Present требует точное evidence из
разрешённого source. Отсутствующие/дублирующиеся карты, pending/silver labels,
расхождение текстов и единиц приводят к отказу до публикации. Каталожные silver
метки не становятся manual labels через mapper; их диагностика — отдельное
направление EVAL-006. Вход/разметка должны покрыть весь declared validation;
самостоятельного открытия test или нового split нет.

```bash
.venv/bin/python -m goodsai.registry_evaluation --config outputs/category-registry/config.json --input data/processed/approved/validation-text-only.jsonl --reference data/gold/approved/validation-reviewed.jsonl --split data/processed/approved/split.json --mapping data/processed/approved/schema-map.json --output-dir outputs/category-validation
```

Эта команда для реальных данных остаётся [PLAN], пока data/evaluation не
передаст перечисленные разрешённые файлы. Learner должен быть заморожен до
раскрытия validation labels. Split hash обязан совпасть с config provenance;
train и test SKU запрещены. После validation любые изменения метода являются
настройкой на validation, а не независимой проверкой. Закрытый test не открывается.

В новой private папке публикуются input, mapped_reference, predictions/manifest,
`report.json`, `report.md` и `artifacts.json` с hashes. Полные source/labels
хранятся только в private файлах; отчёты содержат агрегаты по category/attribute,
TP/FP/FN/P/R/F1, mapped/excluded counts, code/config/input/reference/split/mapper
hashes, run ID и измеренные ресурсы predictor. Нет scored labels — N/A и CLI
exit 2; несуществующие precision/F1 не заменяются нулём. Таблица отсортирована
по наименьшему F1 среди judged slices, N/A в конце. Не делается автоматического
вывода о том, какие правила следует изменить. Входные bytes и code hash
проверяются до/после; при изменении final output не публикуется. Это локальная
single-writer публикация, не distributed transaction/network-FS протокол.

Исправлен reference-vocabulary defect: enum-значение manual reference,
неизвестное train-словарю, остаётся в gold и может дать FN. Оно не добавляется
в inference dictionary и не превращается в исключённую пару. Нормализация
reference не требует присутствия значения в train, но по-прежнему требует
каноническую форму и согласованную единицу. Для output/candidate проверки
ограничения inference-словаря сохранены.

[Доказательства] `tests/test_registry_evaluation.py`: воспроизведение прежнего
падения и FN для неизвестного значения, корректный TP, пять unmapped полей →
unjudgeable, hash/mapping guards, train/test exclusion, ошибочные source/units/
evidence, изменение входов до публикации и фиксированная безопасная CLI ошибка.
Все примеры вымышленные; реальная human quality не измерялась.
