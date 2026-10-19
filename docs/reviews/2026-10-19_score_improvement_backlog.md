# План улучшения оценки после технического чекпоинта

Дата: 19 октября 2026 года. Документ создан в задаче `GOV-003` и описывает
backlog. Ни одно из перечисленных улучшений этим документом не считается
реализованным.

## Что известно точно

Интерфейс платформы показывает:

- продуктовый чекпоинт: `10/10`;
- оценённая техническая часть: `17,81/20`;
- общий индикатор: `17,81/35`;
- блок «Качество результата»: пока без оценки;
- три критерия финальной защиты: пока без оценки.

Правило суммирования этапов на платформе не описано, поэтому этот план не
складывает баллы самостоятельно и не обещает конкретный прирост. Для каждой
задачи указан критерий, доказательство и ограничение. Повторный балл зависит от
того, что именно запустят организаторы.

## Где находится резерв

| Критерий | Сейчас | Максимум | Наблюдаемый резерв | Что отсутствует в доказательствах |
| --- | ---: | ---: | ---: | --- |
| Покрытие обязательных сценариев | 2,74 | 3,00 | 0,26 | исполняемая матрица сценариев и seller attributes |
| Соблюдение ограничений | 1,83 | 2,00 | 0,17 | общий verifier и формальная политика внешних вызовов |
| Сквозной сценарий | 2,84 | 3,00 | 0,16 | явные fallback-переходы и устойчивый batch |
| Воспроизводимость запуска | 1,46 | 2,00 | 0,54 | одна команда от clean clone до проверенного bundle |
| Качество результата | не оценено | 5,00 | неизвестно | независимый gold, frozen predictions, метрики и калибровка |
| Архитектура и развитие | 1,95 | 2,50 | 0,55 | стабильные interfaces и versioned registry вместо hardcode |
| Ошибки и сбои | 2,25 | 2,50 | 0,25 | fuzz, failure injection и доказанный recovery |
| Работа оператора | 2,84 | 3,00 | 0,16 | пакетная review-очередь и audit trail |
| Подача результата | 1,90 | 2,00 | 0,10 | автоматическая сводка с источником каждой цифры |
| Финальная защита | не оценено | 15,00 | неизвестно | пилот, экономика, evidence ledger и репетиция Q&A |

Самый большой технический риск — пустой блок качества. Его нельзя закрыть
добавлением ещё одной модели или цифрой на development-наборе. Нужна цепочка:

```text
официальный контракт
  → независимый gold и аудит split
  → frozen pipeline/config
  → frozen predictions
  → общий verifier
  → per-attribute metrics и calibration
  → human-readable report
  → release manifest с точным SHA
```

## Принципы приоритизации

1. Сначала доказательства и ограничения, затем более сложная модель.
2. Blind test не используют для подбора правил, prompt или thresholds.
3. Каждая цифра связывается с input hash, gold hash, config hash и Git SHA.
4. Новая функция не попадает в основной путь без отрицательных примеров и
   безопасного fallback.
5. Внешний LLM получает только разрешённые поля. Ответ без точного evidence
   отклоняется тем же verifier, что и ответ локальной модели.
6. `READY` можно брать независимо. `BLOCKED` нельзя переводить в работу, пока
   не выполнены указанные зависимости.

## 20 заведённых задач

### P0: доказать кейс и качество

| ID | Issue | Статус | Что должно появиться | Какой критерий поддерживает |
| --- | --- | --- | --- | --- |
| SPEC-002 | [#35](https://github.com/CRUDoshleps/GoodsAI/issues/35) | BLOCKED | исполняемая матрица обязательных сценариев | покрытие кейса |
| DATA-002 | [#36](https://github.com/CRUDoshleps/GoodsAI/issues/36) | BLOCKED | безопасный путь seller attributes | покрытие и ограничения |
| VER-002 | [#37](https://github.com/CRUDoshleps/GoodsAI/issues/37) | BLOCKED | общий evidence/relation verifier | защита от выдумывания |
| EVAL-003 | [#38](https://github.com/CRUDoshleps/GoodsAI/issues/38) | BLOCKED | blind gold + frozen evidence package | весь блок качества |
| EVAL-004 | [#39](https://github.com/CRUDoshleps/GoodsAI/issues/39) | BLOCKED | calibration и risk-coverage | auto-accept precision |
| EVAL-005 | [#40](https://github.com/CRUDoshleps/GoodsAI/issues/40) | BLOCKED | Pareto rules/LLM/encoder/hybrid | качество и стоимость |
| ENV-002 | [#41](https://github.com/CRUDoshleps/GoodsAI/issues/41) | READY | одна команда clean clone → report | воспроизводимость |
| REL-004 | [#42](https://github.com/CRUDoshleps/GoodsAI/issues/42) | BLOCKED | release gate точного SHA и bundle | воспроизводимость |

### P1: сделать решение расширяемым и устойчивым

| ID | Issue | Статус | Что должно появиться | Какой критерий поддерживает |
| --- | --- | --- | --- | --- |
| ARCH-001 | [#43](https://github.com/CRUDoshleps/GoodsAI/issues/43) | READY | interfaces этапов и composition root | архитектура |
| CONF-003 | [#44](https://github.com/CRUDoshleps/GoodsAI/issues/44) | BLOCKED | registry категорий, единиц и constraints | развитие |
| ROUTE-002 | [#45](https://github.com/CRUDoshleps/GoodsAI/issues/45) | BLOCKED | fallback state machine и reason codes | сквозной путь |
| API-002 | [#46](https://github.com/CRUDoshleps/GoodsAI/issues/46) | BLOCKED | checkpoint/resume/idempotency | работоспособность |
| QA-003 | [#47](https://github.com/CRUDoshleps/GoodsAI/issues/47) | READY | property-based и fuzz suite | ошибки и сбои |
| QA-004 | [#48](https://github.com/CRUDoshleps/GoodsAI/issues/48) | BLOCKED | concurrency/failure-injection report | ошибки и сбои |
| OPS-002 | [#49](https://github.com/CRUDoshleps/GoodsAI/issues/49) | BLOCKED | безопасные quality/latency/cost counters | внедрение и стоимость |

### P1/P2: оператор, отчёт и финальная защита

| ID | Issue | Статус | Что должно появиться | Какой критерий поддерживает |
| --- | --- | --- | --- | --- |
| PRODUCT-002 | [#50](https://github.com/CRUDoshleps/GoodsAI/issues/50) | BLOCKED | пакетная review-очередь | пользовательский сценарий |
| ART-004 | [#51](https://github.com/CRUDoshleps/GoodsAI/issues/51) | BLOCKED | читаемый отчёт из machine outputs | подача результата |
| DOCS-002 | [#52](https://github.com/CRUDoshleps/GoodsAI/issues/52) | READY | правила против нейрослопа и пустых claims | доверие и питч |
| PRODUCT-003 | [#53](https://github.com/CRUDoshleps/GoodsAI/issues/53) | BACKLOG | seller/category quality dashboard | продуктовая ценность |
| PRODUCT-004 | [#54](https://github.com/CRUDoshleps/GoodsAI/issues/54) | BLOCKED | проверяемый пилот, экономика и Q&A | финальная защита |

В каждом Issue находятся шаги, приёмка, зависимости, связь с критерием и
явный раздел «не входит в задачу». Это уменьшает риск, что участник возьмёт
слишком широкий scope или объявит задачу готовой по одному скриншоту.

## Критический путь

### Поток A: качество

```text
SPEC-001 ─┬─→ SPEC-002
          ├─→ DATA-001 → EVAL-002 ─┐
          └─→ EVAL-001 ────────────┴→ EVAL-003 → EVAL-004
LLM-003 + ML-001 + ROUTE-001 ────────────────────────└→ EVAL-005
VER-001 → VER-002 ───────────────────────────────────┘
```

До завершения `EVAL-003` можно разрабатывать компоненты на development и
synthetic data, но нельзя заявлять финальное качество. `EVAL-004` использует
validation для выбора thresholds и только затем один раз оценивает test.

### Поток B: воспроизводимость и выпуск

```text
DOCS-001 → ENV-002 ────────────────┐
ART-003 ───────────────────────────┼→ REL-004
QA-002 + GitHub→Gitea mirror ─────┘
```

Проверка организаторов идёт по Gitea, поэтому зелёный локальный запуск без
совпавшего release SHA не является доказательством.

### Поток C: промышленная архитектура

```text
SPEC-001 + CONF-001 → ARCH-001 → CONF-003
LLM-003 + VER-002 + ROUTE-001 → ROUTE-002
API-001 + OPS-001 → API-002 → QA-004
ROUTE-002 + API-002 → OPS-002
```

### Поток D: пользователь и защита

```text
PRODUCT-001 + API-002 + VER-002 → PRODUCT-002
EVAL-005 + OPS-002 + ART-003 → ART-004
PRODUCT-002 + OPS-002 → PRODUCT-003
EVAL-005 + ART-004 + OPS-002 → PRODUCT-004
```

## Что можно брать параллельно сейчас

После отдельного claim commit независимы друг от друга:

- `ENV-002`: clean-run runner;
- `ARCH-001`: interfaces и composition root;
- `QA-003`: property-based/fuzz invariants;
- `DOCS-002`: правила доказательного текста и дизайна.

При этом существующие P0 `SPEC-001`, `DATA-001`, `EVAL-001`, `EVAL-002`,
`CONF-001`, `LLM-003`, `OPS-001`, `ART-003` и `QA-002` остаются частью более
раннего backlog. Новые задачи не заменяют их и не должны обходить их
критерии приёмки.

## Формулы, которые нужно заморозить до измерения

### Качество извлечения

Для атрибута `a`:

```text
Precision_a = TP_a / (TP_a + FP_a)
Recall_a    = TP_a / (TP_a + FN_a)
F1_a        = 2 × Precision_a × Recall_a / (Precision_a + Recall_a)
```

Отчёт должен показывать per-attribute значения, macro average и micro totals.
Одна общая accuracy не используется как главный показатель.

### Безопасность автоматического принятия

```text
AutoAcceptPrecision = correct_auto_accept / all_auto_accept
CriticalErrorRate   = wrong_auto_accept / all_eligible
Coverage             = non_abstain_decisions / all_eligible
ReviewRate           = review_decisions / all_decisions
AbstainRate          = abstain_decisions / all_decisions
```

`AutoAcceptPrecision` считается только после калибровки. До неё candidate
остаётся `review`, а heuristic score не называется вероятностью.

### Стоимость

```text
CostPer1000SKU = 1000 × total_measured_run_cost / processed_sku
LLMCallRate    = llm_calls / processed_sku
```

В отчёте обязательны версия тарифов, валюта, дата, число входных и выходных
токенов. Если цена неизвестна, значение равно `null`, а не нулю.

### Операторский сценарий

```text
MedianReviewTime
P90ReviewTime
CorrectionRate
OperatorAgreement
QueueResolutionRate
```

Эти метрики измеряются на фиксированном наборе задач и не смешиваются с
качеством extractor-а.

## Минимальный набор доказательств для следующего прогона

1. Точный GitHub SHA и совпадающий Gitea SHA.
2. Версия Python, lock зависимостей и environment fingerprint.
3. Input hash, число строк и schema version.
4. Config/rules/dictionaries/model/prompt versions.
5. Predictions hash и одна строка на каждый вход.
6. Manifest со status counts, latency, usage и cost.
7. Metrics JSON с provenance reference.
8. Human-readable report без ручного копирования цифр.
9. Команды запуска и exit codes.
10. Явный список того, что не проверялось.

## Правила для документации и презентации

`DOCS-002` должна оформить это как отдельный стандарт. Основа для него:

- [GOV.UK: Publishing accessible documents](https://www.gov.uk/guidance/publishing-accessible-documents)
  рекомендует простые слова, короткие предложения, смысловые заголовки и
  таблицы только для данных;
- [GOV.UK content principles](https://www.gov.uk/government/publications/govuk-content-principles-conventions-and-research-background/govuk-content-principles-conventions-and-research-background)
  рекомендует конкретику, активные глаголы и вывод в начале;
- [GitHub Docs content design principles](https://docs.github.com/en/contributing/writing-for-github-docs/content-design-principles)
  ставит ясность, корректность и консистентность выше объёма и рекомендует
  создавать ровно столько документации, сколько нужно пользователю;
- [Material Design foundations](https://m3.material.io/foundations/) связывает
  content design, accessibility, layout и design tokens с понятностью UI.

Для проекта из этого следуют проверяемые правила:

- писать «сделано», «план» или «гипотеза», не смешивая статусы;
- ставить ссылку на commit/test/metric/source рядом с фактическим claim;
- не использовать «инновационный», «революционный», «умный», «бесшовный» без
  измеримого определения;
- не рисовать декоративные мозги, роботов, сияющие сети и абстрактные облака;
- показывать настоящий input, output, evidence, reason code, trace и метрику;
- одна схема отвечает на один вопрос и использует реальные имена компонентов;
- диаграмма не считается доказательством реализации;
- слайд с числом указывает split, размер, дату и provenance;
- не придумывать ROI, цитаты пользователей, партнёров и результаты пилота.

## Решение о порядке работ

Если цель — увеличить подтверждённый технический результат за короткое время,
рекомендуемый порядок такой:

1. закончить `ART-003`, взять `ENV-002` и получить один чистый bundle;
2. параллельно завершить `SPEC-001`, `EVAL-001` и `EVAL-002`;
3. реализовать `VER-002` и только затем подключать model/LLM path;
4. получить `EVAL-003`, откалибровать решения в `EVAL-004`;
5. сравнить режимы в `EVAL-005` и оставить только полезные компоненты;
6. собрать `ART-004`, проверить `REL-004` и подготовить `PRODUCT-004`;
7. после доказанного batch делать операторскую очередь и dashboard.

Это не заменяет claim-процесс. Каждый следующий исполнитель берёт один Issue,
публикует отдельный `chore(tasks): claim <ID>` и только после этого меняет код.
