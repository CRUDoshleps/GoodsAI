# Оценка качества, стоимости и надёжности

## Отдельная диагностика по каталогу

EVAL-006 добавляет [catalog-silver evaluation](SILVER_EVALUATION.md) с отдельным
reference kind и [протоколом](research/silver_evaluation_protocol.md).
Это согласованность с шумными параметрами, не независимое качество.
Ручной evaluator сохраняет требования к human reference. Silver не снимает
блокеры gold/test и не разрешает auto_accept. Offline-калибровка сохраняет
runtime heuristic confidence и review/abstain.

## Единица оценки

Для разбора регрессий `model` доступен offline adapter
`python -m scripts.research.prepare_model_adjudication evaluate-models --help`.
Он принимает явно подтверждённый AI-assisted development reference и frozen
predictions с manifests, строит model-only view с исключением остальных полей
и вызывает существующий evaluator. Повторяемые hashes/paired deltas остаются
в private output, [ограниченные агрегаты](RESULTS.md) не выдаются за независимый
test. Error-selected карточки не позволяют оценить качество всего каталога.

Публикуемые frozen aggregates доступны в [отчёте](../reports/quality_20261021.md)
и [JSON](../reports/quality_20261021.json). Экспорт существующих private reports:
`python -m scripts.research.export_quality_report --help`. Проверяются ожидаемые
source hashes, AI-assisted reviewed provenance и совпадение frozen code/config
с текущим default checkout. Публикуются только numeric aggregates и фиксированные
dimension labels; входные тексты, raw values, seller identities и credentials
не переносятся. Старый датированный отчёт остаётся snapshot, не метрикой любой
будущей версии. Автоматический text-support matcher не заменяет human audit.

Например, для разрешённого приватного frozen пакета (пути адаптировать к его
manifest, ожидаемые SHA взять из заранее зафиксированного протокола):

```bash
python -m scripts.research.export_quality_report \
  --silver outputs/frozen-comparison/report.json --silver-sha256 "$SILVER_REPORT_SHA256" \
  --human outputs/reviewed-models/metrics.json --human-sha256 "$HUMAN_REPORT_SHA256" \
  --producer outputs/frozen-comparison/after/cold.manifest.json \
  --reference outputs/reviewed-models/reference.partial.jsonl \
  --output-dir outputs/public-quality-next
```

Это повторная публикация проверенных агрегатов, а не новый inference. Для
пересчёта самих метрик из predictions используются существующий
[silver runner](SILVER_EVALUATION.md) и model-only `evaluate-models` в
`scripts.research.prepare_model_adjudication`; они требуют приватных входов.
Без них воспроизвести эксперимент нельзя. Публичные файлы можно проверить
без карточек: `sha256sum reports/quality_20261021.json reports/quality_20261021.md`
(PowerShell: `Get-FileHash reports/quality_20261021.* -Algorithm SHA256`).
Ожидаемый JSON SHA указан в [RESULTS](RESULTS.md), hashes сдаваемых файлов и
source GitHub SHA — в `submission-manifest.json` опубликованного Gitea checkout.
Exporter и оба публичных snapshot используют LF, поэтому файловые hashes
совпадают с Git blobs и Gitea manifest независимо от Windows checkout.
Это не нормализует runtime fingerprints: code_sha256 описывает загруженные
байты Python и может отличаться между CRLF/LF checkout. При таком несовпадении
экспорт frozen source отклоняется; для повтора нужны те же loaded source bytes.

Основная единица — пара `(SKU, attribute)`. Для каждой пары gold определяет,
есть ли характеристика, какое значение допустимо и каким текстом оно
подтверждается. `ambiguous` не включается в обычные TP/FP/FN и показывается
отдельно.

## Классификация результата

| Prediction | Gold | Класс |
| --- | --- | --- |
| правильное значение | present | TP |
| неверное значение вместо правильного | present | FP + FN |
| значение при отсутствии характеристики | absent | FP |
| abstain/нет значения | present | FN |
| abstain | absent | TN, отдельно от P/R/F1 |

Exact evidence проверяется программно по исходному полю и offsets. Семантическую
связь с атрибутом основного товара оценивает reviewer; совпавший span сам по себе
её не доказывает. Evaluator сопоставляет canonical value+unit с reviewed reference;
отдельной полной семантической метрики evidence сейчас нет.

## Формулы

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2PR / (P + R)
Coverage  = predicted_required_pairs / all_required_pairs
```

Micro-метрика суммирует пары. Macro сначала считает показатель по полю или
категории и усредняет. Текущий evaluator выдаёт micro, per-attribute/category,
category×attribute и macro_attribute_f1; отдельный macro-category не реализован.
В evaluator candidate coverage считается по **judged** парам. Покрытие по всем
запрошенным парам из prediction manifest показывается отдельно; ambiguous/
unjudgeable и кандидаты на них не исчезают из диагностического отчёта.

Для решений:

```text
AutoAcceptPrecision = correct_auto_accept / all_auto_accept  # N/A сейчас: auto_accept нет
ReviewRate          = review_pairs / required_pairs
AbstainRate         = abstain_pairs / required_pairs
EvidenceExactRate   = exact_evidence / predicted_pairs
```

Для ресурсов:

```text
CostPer1000 = 1000 * inference_cost / cards
LLMShare    = cards_with_llm_call / cards
Throughput  = cards / elapsed_seconds
```

ReviewRate, EvidenceExactRate и CostPer1000 выше — определения для отчётности,
не обещание отдельных готовых полей evaluator. В rules-only режиме нет model
API-вызовов; стоимость compute в рублях этим не измеряется. Opt-in model/LLM
routes существуют: для конкретного запуска calls/tokens/latency/стоимость
берутся из его manifest/usage. Отсутствующее измерение — N/A, а не ноль.

## Обязательные срезы

- категория и атрибут;
- title-only и title+description;
- частые и редкие значения;
- длина текста;
- продавец, если идентификатор допустим только для аналитического slice;
- exact rule, model/LLM и fallback route;
- known и новая категория;
- conflict, ambiguous и корректный abstain.

## Исторические результаты

Все значения ниже получены до независимого test и не являются финальной
оценкой качества каталога.

| Набор | Cards / judged | TP / FP / FN | P / R / F1 | Ограничение |
| --- | ---: | ---: | ---: | --- |
| reviewed-v2, исторический baseline | 12 / 67 | 29 / 1 / 21 | 96,7 / 58,0 / 72,5% | теперь development_feedback, не holdout |
| M2 до policy fixes | 20 / 115 | 58 / 3 / 25 | 95,1 / 69,9 / 80,6% | development, использовался для решений |
| M2 после policy fixes | 20 / 115 | 69 / 0 / 14 | 100 / 83,1 / 90,8% | тот же development, не независимый test |

M2 содержит 120 полей: 83 present, 32 absent, 5 ambiguous. В P/R/F1 входят
115 judged решений. Улучшение после просмотра ошибок показывает, что fixes
работают на этом development, но не оценивает перенос на новые карточки.
Полная последовательность M1/M2, per-attribute/category таблицы, SHA reference,
snapshots и команды — в [RESULTS.md](RESULTS.md). Сам факт
`evaluation_status=manual_reference` не означает независимость: происхождение
AI-assisted и использование для разработки фиксируются отдельно.

## Организаторский прогон 18 октября

По сохранённым скриншотам оценённые технические критерии дали 17,17/20.
Блок качества результата оставался без оценки; продуктовый этап был 10/10,
но платформа не объяснила его включение в общий балл. Основные замечания:

- нет реального ML/LLM route в основном pipeline;
- thresholds и ветви решений недостаточно конфигурируемы;
- готовый predictions-файл и отчёт метрик слабо связаны с README/runtime;
- нужны более явные end-to-end сценарии и release evidence;
- эксплуатационные риски: pickle-import, логи и временные файлы.

После этого улучшены атомарная запись и model rules, реализованы opt-in LLM
route, общий verifier и сборщик шести артефактов. Это не завершает независимый
human gold или финальную приёмку полного комплекта на целевой версии:
их статус и ограничения указаны в [RESULTS](RESULTS.md).

## Подготовка воспроизводимого human quality-пакета

EVAL-003 использует существующие [human workflow](HUMAN_GOLD.md),
`goodsai.evaluate.evaluate` и парные transitions из `compare_model_stage`.
Новый orchestration tool не предсказывает, не размечает, не открывает reserve
и не аутентифицирует людей. Пока нет gold, подготовка безопасна:

```bash
.venv/bin/python scripts/research/quality_evidence.py prepare --output-dir outputs/evaluation/quality-plan-next
.venv/bin/python scripts/research/quality_evidence.py verify --bundle outputs/evaluation/quality-plan-next
```

В PowerShell executable — `.\.venv\Scripts\python.exe`. Нужен Python 3.12+
и для assemble/verify с метриками полный development Git clone, содержащий
frozen GitHub commit. Gitea-only clone с другой историей недостаточен.
Каждый output-dir новый и находится в `outputs/`.
Результат prepare: `status=blocked`, `independent_reference=false`, P/R/F1=null,
baseline/hybrid=`not_run`, плюс заполняемый spec. Verify подтверждает целостность,
но сохраняет `final_acceptance=blocked`. Exit 0 здесь означает успешную подготовку
или проверку целостности, **не успешную независимую оценку**.

### Когда люди закончат разметку

В отдельной копии `evaluation.spec.template.json` указать записи
`{"path": "…", "sha256": "…"}` для:

- `input` — ровно text-only проекция выбранных reference-карточек;
- `reference_package` — `manifest.json` готового EVAL-001 `finalize` пакета;
- `review_packages.A/B` — `manifest.json` исходных раздельных human-пакетов;
- `runs` — ровно baseline и hybrid, в этом порядке. Для готового запуска
  `status=completed` и записи `predictions`, `manifest`, `config`. Manifest —
  сохранённый CLI `.manifest.json`, конфиг — точный эффективный профиль;
  для непроведённого hybrid — `status=not_run` и короткий `reason` код.

Пути разрешаются **относительно spec**, абсолютные также допустимы. SHA должны
идентифицировать утверждённые неизменённые файлы; нельзя обновлять их ради
обхода ошибки. Baseline обязателен для сборки с gold. Для rehearsal на
вымышленных данных `purpose=synthetic_workflow_check`; такой отчёт остаётся
synthetic и не становится человеческой оценкой.

```json
{
  "name": "baseline",
  "status": "completed",
  "predictions": {"path": "baseline/predictions.jsonl", "sha256": "<64 lowercase hex>"},
  "manifest": {"path": "baseline/predictions.manifest.json", "sha256": "<64 lowercase hex>"},
  "config": {"path": "profile.json", "sha256": "<64 lowercase hex>"}
}
```

Это пример одной записи runs, не исполняемый spec. Gold/predictions сначала
создаются отдельным разрешённым frozen experiment; orchestration их не запускает.

```bash
.venv/bin/python scripts/research/quality_evidence.py assemble --spec outputs/evaluation/quality-inputs/spec.json --output-dir outputs/evaluation/quality-bundle-next
.venv/bin/python scripts/research/quality_evidence.py verify --bundle outputs/evaluation/quality-bundle-next --expected-sha256 <trusted-manifest-sha256>
```

Результаты сохраняются без перезаписи и публикуются локально только после
успеха всей сборки:

```text
manifest.json                   SHA-256 всех captured артефактов
public/report.json              per-attribute/category/category×attribute, FP/FN,
                                coverage, exclusions, agreement и paired changes
public/report.md                краткая сводка и явный статус каждого метода
public/integrity.json            hashes и SHA самого manifest
private/input.jsonl              закрытые тексты
private/human/                  captured reference и review A/B
private/baseline/, hybrid/      predictions + manifests + configs (если выполнены)
private/changed_pairs.json       локальные пары ошибок, не для публикации
private/evaluation.spec.json     исходные ссылки и hashes
```

Сборка повторяет `reconcile` и `finalize` по сохранённым human answers/signoff,
сравнивает reference побайтно, проверяет guideline/freeze, существующий
split-audit и eligible reserve membership без повторного sampling. Для сборки
должны быть доступны исходные metadata/audit/source пути EVAL-001; их нельзя
молча переписать. Поля approved/human-only и разные ID — заявления людей,
а не доказательство их личности или независимости.

Перед evaluator проверяются точные SKU/text наборы, evidence, manifest counts,
run IDs, input/output/config/code hashes, clean producer и frozen Git tree.
Строка с ошибкой обработки остаётся в unprocessed counts и даёт FN для present
gold. В paired view это отсутствующее значение с исходным row status, а не
успешный abstain; исходные predictions не переписываются. Пропущенная строка
или изменённый SKU-набор останавливают сборку, а не сокращают знаменатель.
Проверяются effective policy snapshot/hash; baseline не может содержать
LLM/model результаты. Обе версии сейчас должны происходить из **одного
замороженного commit и семантически одного config** EVAL-001: это сравнение
режимов одного frozen runtime, не поддержка произвольных исторических producers.
Model weights/prompts и отсутствие test-based выбора отдельно требуют
проверки процесса; инструмент не выдаёт им автоматическую приёмку.

Verify повторяет evaluator/paired transitions на captured файлах без исходных
human-путей, требует ту же версию evaluator/runtime и доступный frozen commit.
Code hashes относятся к байтам, включая EOL: при переносе Windows/Linux нужны
исходные bytes/environment, молча пересчитывать identities для обхода ошибки нельзя.
Изменённый metrics JSON не принимается даже после обновления внутренних hashes,
если результат не совпадает с повторным расчётом. Доверенный внешний hash manifest
проверяется через `--expected-sha256`; внутренние hashes сами по себе не являются
подписью или защитой от согласованной подмены всего пакета.

После assemble статус `assembled_awaiting_process_review` (либо
`synthetic_workflow_checked`), **финальная приёмка всё ещё blocked**. Для #38
нужны реальный independent gold #6 и проверка процесса/заморозки всех методов.
Автоматического закрытия Issue, выпуска или включения auto_accept нет.
Метрики exact canonical value/unit не доказывают полную семантику evidence;
grouped CI, seller/rare slices и cost/latency этот инструмент не вычисляет.
Они остаются отдельными измерениями, отсутствие данных явно раскрывается.

Файлы `private/`, gold, forms и predictions не публикуются. `public/` — только
агрегаты/hashes, но префикс не является разрешением загрузить их в Git: сначала
проверить малые группы и согласовать состав сдачи через существующий release gate.
Сборщик [шести артефактов](ARTIFACT_BUNDLE.md) сохраняется отдельно; quality-пакет
не выдаётся за полный комплект или независимую приёмку VM.

## Протокол эксперимента

Для независимой разметки используется [human-review protocol](HUMAN_GOLD.md).
Инструменты/пустые формы не являются gold; одиночная разметка и AI-assisted
ответы не заменяют два независимых человеческих ответа с adjudication.

Перед новым независимым sampling проверить [аудит split EVAL-002](SPLIT_AUDIT.md).
Исходный E1 split и validation нельзя объявлять независимым holdout. Аудитор
выпускает отдельный filtered partition + карантин без замены старых данных;
blind reserve проверяется только алгоритмически по metadata/fingerprints.

1. Зафиксировать commit, конфиг, prompts и входные hashes.
2. Зафиксировать split и версию annotation guideline.
3. Выполнить A/B на одинаковых парах и одном verifier.
4. Сохранить raw predictions, manifest, metrics и error table.
5. Посчитать доверительный интервал bootstrap по SKU/groups.
6. Проверить деградации каждого обязательного атрибута.
7. Отдельно показать цену, latency, LLMShare и ошибки API.
8. До просмотра test выбрать финальный вариант и пороги.
9. Открыть test один раз и опубликовать результат без донастройки.

## Release gate для нового метода

До EVAL-001 gate задаётся относительным сравнением:

- нет новых нарушений schema/evidence;
- precision критических полей не падает на validation;
- прирост recall подтверждён списком исправленных FN;
- regressions имеют объяснение и отдельные тесты;
- стоимость и latency измерены;
- отказ LLM не ломает rules route;
- результат воспроизводится из clean environment.

После независимого gold команда фиксирует числовые пороги. Запрещено выбирать
порог по test или объявлять heuristic confidence калиброванной вероятностью.

## Ошибки, которые показываем отдельно

- brand в фразе «совместимо с Samsung»;
- характеристика чехла или комплекта вместо телефона;
- два объёма без понятной роли RAM/storage;
- два несовместимых цвета;
- модель другого товара в описании;
- значение за границами категории;
- формат/единица, которых нет в справочнике;
- значение LLM без точного evidence;
- новая категория;
- пустой или повреждённый вход.

## Reference новых категорий (CONF-003 candidate)

[DONE — feature candidate] В конфиге v2 enum-словарь ограничивает извлечение,
но не допустимый набор human reference. Новое правильное значение из validation
не должно вызывать ошибку evaluator или исчезать из знаменателя recall: если
система его не нашла, это FN. Отдельная normalize_reference сохраняет такое
значение, не расширяя обученный inference-словарь. Numeric canonical form и
единицы по-прежнему проверяются. Default config и прежние категории не меняются.

Явный hash-bound mapper и запуск `goodsai.registry_evaluation` описаны в
[CATEGORY_REGISTRY](CATEGORY_REGISTRY.md). Несопоставленные target labels
становятся unjudgeable; отчёт показывает excluded и judged/requested counts.
P/R/F1 на сопоставленной части не выдаются за полноту всей новой схемы.
Разрешён только весь заранее declared validation split, без train/test SKU.
Pending/silver не переименовываются в reviewed manual. Сам факт успешного
mapping/evaluate не доказывает независимость разметки и не разрешает auto_accept.
