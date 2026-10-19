# Состояние проекта

Актуально на 19 октября 2026 года.

## EVAL-006: catalog-silver diagnostics — DONE

По поручению Владислава PR #95 принят в main `5711949`; Issue #91 закрыт.
Четыре GitHub checks головы `bd7cd51` SUCCESS; конфликтов и замечаний review
не было. Автопубликация Gitea: mirror run 39313644701 SUCCESS. Это приёмка
инструментов диагностики; независимая разметка и качество моделей не подтверждены.

Claim `f04abec`, ветка `eval/eval-006-silver-diagnostics`, Issue #91.
Producer итогового измерения `f33e3fc` после включения main `62898fb`
с LLM-003 коллеги. Наши изменения не меняют runtime актуального main.
Добавлены отдельные подготовка noisy reference, support matcher,
evaluator с family-bootstrap и traffic, offline logistic/Platt и парное
сравнение полного input либо фиксированного development subset.

3037 карточек / 1270 семейств, закрытый reserve 40 не предсказывался.
Agreement: 7522 TP / 425 FP / 4413 FN, P 94,65%, R 63,02%, F1 75,67%;
supported recall 75,75%, coverage 54,31%. Это **не human quality**.
Range buckets каталога проверяются как ограничения exact reference;
старые результаты mapping не перезаписаны. Offline Brier 0,06575 → 0,03870,
но Platt не лучше fitted logistic 0,03865; auto_accept запрещён.

266 основных tests и 3 reader tests прошли; demo 6/6, clean-run 11/11,
pip check OK. Strict adversarial по-прежнему 20/21, exit 1, известный #15.
Support human audit и независимый gold остаются pending/BLOCKED.
PR Глеба #90 проверен повторно на `3c1e1cb`, token names поддержаны;
живые registry/GLiNER/LLM predictions для frozen comparison не предоставлены,
варианты not_run. 3037 predictions до/после включения main совпали, кроме run_id.
PR #90 слит коллегой; EVAL-006 принят через PR #95 и опубликован в Gitea.
Внешних модельных вызовов, расходов и deploy в этой задаче не было.

[Инструкция](SILVER_EVALUATION.md), [публичные метрики](../reports/metrics.md),
[результаты и передача](research/silver_evaluation_results.md).

## LLM-003: opt-in LLM-fallback — REVIEW

Ветка `llm/llm-003-evidence-first-fallback`, владелец Глеб Алферов.
`goodsai.llm` добавляет к правилам один запрос на карточку для атрибутов
`not_found_by_rules`, если в видимом тексте есть сигнал для этого атрибута
(pre-router без вызова модели). Ответ принимается только при цитате из видимого текста,
значении, выведенном из цитаты общим нормализатором, и прохождении
`validate_candidate`; итог `method=llm`, `review`, эвристический score 0.6.
Бюджет вызовов, ограниченные повторы с `Retry-After`, circuit breaker, точный
кэш, отдельные reason codes для 429/5xx/timeout/ключа/бюджета, учёт токенов и
стоимости в manifest. Включается флагом `--llm` или `GOODSAI_LLM_ENABLED=1`;
без него вывод и manifest прежние.

Политика данных и бюджета принята владельцем 19.10.2026
(`llm-data-policy-2026-10-19`): только HTTPS-шлюз организаторов, видимый текст
без SKU и меток, закрытый test не отправляется, 100 вызовов на запуск и 300 в
сутки по общему журналу; всё проверяется кодом.

Проверено: 245 основных тестов (37 новых с поддельным провайдером), 3 reader
tests, fuzz, demo 6/6, `pip check` — Linux, Python 3.12. Живой synthetic trace
(`goodsai.cli llm-trace`) запускается на VM с ключом; качество маршрута не
измерено и не заявляется. Подробности: [LLM](LLM.md).

## CONF-001 — кандидат конфигурации runtime

[DONE — feature candidate] Совмещён с `main` 977c5ed: сохранены
relation verifier и BASE-003. 223 основных tests — OK на macOS/Python 3.14.8.
Тест preflight изолирует версию Python для проверок disk/dirty; worker ablation
получает разрешённые identity tags, не переключающие runtime policy.
Не выполнены независимая приёмка, VM deploy и merge.

Ветка `arch/conf-001-runtime-config`, claim `3cb7560`, исполнитель `timur0o31`.
Добавлен полный профиль `config_version=1`: bounds, heuristic scores, окна
правил и API limits. CLI/API используют общий strict loader, старые профили
без config_version явно мигрируются; ошибки конфигурации дают fail-fast.
Category ID связан с существующим rule-family через конфиг. Input/output
schema 0.1, единицы, production defaults, review/abstain сохранены;
конфиг не включает LLM/auto_accept. После включения `main` с LLM-003 opt-in
LLM-fallback использует те же `numeric_bounds`/`rule_limits`: значение вне
настроенных границ даёт `llm_value_not_in_quote`, а не падение карточки.

Проверка candidate на macOS / Python 3.14.8: 123 основных теста (15 новых),
3 reader tests, demo 6/6. На 15 синтетических карточках сохранены прежние
values/units/confidence/evidence/decisions; run identity закономерно меняется.
Это не независимое измерение качества и не обновление VM. Реальные данные,
gold/test reserve, внешние модели и зависимости не менялись. Детали и команды:
[CONFIGURATION.md](CONFIGURATION.md). До merge результат относится к этой
feature-ветке, не к опубликованному release.

## Интеграция всех открытых PR — 19.10.2026

По поручению владельца приняты #71, #79, #85, #86, #87 и #88.
Конфликты разрешены с сохранением актуальных задач и владельцев.
Общий main `dc3fbad` доставлен в Gitea: mirror run 39304194251 SUCCESS.
Producer проверок `7f20fe4` имеет идентичные src/tests/scripts/requirements
и pyproject.toml: 208 основных + 3 reader tests, pip check, чистый запуск
11/11, demo 6/6, проверка 6 payload hashes, реальный HTTP 22/22.
Строгий adversarial suite: 20/21, exit 1; RED SOLUTION/color остаётся #15.
Батарея мА*ч теперь проходит HTTP semantic probe. Это synthetic проверки,
не независимое качество каталога. Модели и VM deployment не запускались.

BASE-003, ART-002, QA-001 (доставка набора проверок), GOV-005 (план) DONE.
EVAL-001 остаётся BLOCKED до независимой разметки; VER-001 остаётся READY
для оставшегося ложного цвета. ENV-003 и QA-005 BLOCKED: независимый участник,
официальный API и UI/save/reload/export ещё необходимы. Ни один merge не
означает окончательную приёмку продукта. Разделы ниже сохраняют исторические
проверки и статусы на момент исходных прогонов.



## ENV-003 / QA-005: техническая проверка в ветке

Producer `3ad28e4` на VM: существующий clean-run 11/11, 160 + 3 tests,
22/22 реальных loopback HTTP checks; внешний synthetic batch и его повтор
совпали побайтно. Добавлен самостоятельный listening probe поверх действующего
API, без изменения default pipeline. Режим rules, model calls 0, quality N/A.
Финальная приёмка не предоставлена: исполнитель участвовал в разработке,
API provisional, regression cases #74/#15 всё ещё не проходят. UI, сохранение
решений и export отсутствуют; QA-005 rehearsal NOT RUN. Полные границы и
передача независимому участнику: [протокол](reviews/2026-10-19_final_acceptance.md).

## QA-001: synthetic adversarial suite — REVIEW

Добавлены 21 versioned expected-output case и команда goodsai.adversarial через
реальный batch predictor. Отчёт проверяет status, value/unit, decision/reason и
точные evidence; повреждённая prediction/manifest пара не оценивается. Actual:
20/21 passed, оставшийся RED SOLUTION/color дефект #15 явно FAILED, exit 1.
Known issue не скрывается. 162 основных + 3 reader tests проходят; unit PASS
не подменяет strict suite PASS. Dependency exceptions и silent abstain fault
injection проверены. Concurrent/crash/recovery тесты переиспользованы из storage;
provider timeout/budget N/A для отключённого route. Основано на #79/#86;
качество каталога, human reference и test reserve не оценивались.

## ART-002: читаемый demo-комплект — REVIEW

Одна команда goodsai.demo создаёт input, predictions/manifest, summary, metrics,
report.md и artifacts.json с hashes шести файлов. Verify проверяет hashes,
размеры, whitelist paths и общий run ID без повторного inference. На synthetic
demo: 6/6 checks, review 13/24, abstain 11/24, API calls/cost 0; P/R/F1 N/A,
compute cost N/A. Это не качество каталога и не финальный release bundle.
162 основных + 3 reader tests, pip check и фактический CLI create/verify прошли.
Прежний каталог не перезаписывается; corrupt predictions не дают success summary.
Команды и границы — в README, раздел «Быстрый запуск».

## Интеграция PR автора e345ee — 19.10.2026

[DONE] По поручению пользователя проверены и слиты PR #55, #63, #76, #72,
#73 и #80. Конфликты TASKS/PROJECT_STATUS/config extras/source allowlist
разрешены без потери владельцев, закрытых задач и независимых веток работы.
В TASKS 64 уникальных ID; сохранены все 20 GOV-003 и 10 GOV-004 задач.
GOV-003/GOV-004/ENV-001/ENV-002/QA-003 завершены; ML-001 остаётся REVIEW для
независимой приёмки, хотя отдельный opt-in prototype уже доступен в main.

Общий код прошёл 160 основных и 3 reader tests, pip check и isolated clean-run
11 этапов; QA-003 nightly seed 20261020 прошёл 11/11 свойств. CI последнего
feature head `47fabbd`: Ubuntu/Windows clean run, invariants и properties
SUCCESS. Все шесть merge доставлены в Gitea fast-forward workflow;
последний runtime/code merge — `468e35e`. Исторические delivery bytes сохранены.

При интеграции добавлены проверка посторонних ML artifact files, UTF-8
экспериментального CLI, игнор .venv-ml и включение public guides в source archive.
Штатные CLI/API продолжают использовать rules; ML зависимости/веса не нужны
для обычного пути. При этой интеграции не запускались реальные модели, новые
quality experiments, приватный gold/test и VM deployment. Данные VM/ML в
отдельных отчётах относятся к исходным историческим producer SHA.

## ML-001: opt-in гибрид — REVIEW

Реализован отдельный экспериментальный `HybridExtractor`: rules + локальный
GLiNER только для пропущенного однословного бренда. Основной CLI/API не менялся.
На ранее просмотренном development AI-reference: 80 карточек, 425 judged полей,
TP/FP/FN 208/8/88 → 225/8/71, F1 81.25% → 85.07%. Метод доработан после анализа
ошибок, поэтому это screening, не независимое подтверждение accuracy. Широкий
brand/model fallback отвергнут из-за дополнительных FP относительно reference.
146 + 3 tests и pip check прошли на VM; два runtime-повтора совпали, отдельный
offline smoke прошёл при заблокированной сети. Default enable/auto_accept
остаются закрыты EVAL-001/004. Команды, ресурсы и ограничения:
[EXPERIMENTAL_GLINER](EXPERIMENTAL_GLINER.md).

## QA-003: генеративные проверки — DONE

Добавлены 11 Hypothesis properties для text-only input, JSONL, Unicode/HTML
position maps, schema, numeric conversion, hidden facts и no-evidence-no-value.
Quick/nightly profiles имеют ограничение размера/времени и явный seed;
shrunk examples переносятся в основной regression suite. Исправлены contract
type guards (включая evidence=null) и Decimal overflow при конвертации единиц.
Валидный schema 0.1 и решения baseline не изменены. Это synthetic robustness,
не независимая оценка качества. Запуск и ограничения:
[FUZZ_TESTING.md](FUZZ_TESTING.md). Фактические результаты фиксируются в PR.

## ENV-002: чистый запуск — DONE

`scripts/release/clean_run.py` создаёт отдельное окружение CPython 3.12,
устанавливает 23 hash-locked distributions, проверяет `pip check`, demo,
внешний JSONL batch, exact evidence/manifest, API contract и synthetic bundle.
Успешный повтор проверяет hashes и installed versions; failed attempts
сохраняются, следующий запуск создаёт новую попытку. JSON/Markdown report
содержит этапы и exit codes без текстов карточек. P/R/F1 без gold — N/A.
Описание, аудит pins и поддерживаемые OS: [CLEAN_RUN.md](CLEAN_RUN.md).
Hosted Linux/Windows CI добавлен; VM организаторов и listening socket этой
реализацией не подтверждены; clean-run принят как локальная/hosted CI проверка.

Последнее фактическое VM-подтверждение: [ENV-001, Linux-прогон и ошибки](reviews/2026-10-19_vm_quality_audit.md).
На `1d53dad`: 119 основных + 3 reader tests, demo 6/6; 2171 SKU обработан,
три повтора совпали с frozen `1754970` побайтно. Runtime/config hashes одинаковы.
Согласие с диагностической AI-reference: P96,3/R70,3/F181,3 на 425 judged-парах
из 480; 55 исключены. Это development, с исправлением сериализации reference
после первого сравнения, не независимая human quality. Подтверждены synthetic
пропуск `мА*ч` и ложный цвет из имени бренда; задачи #74 и #15 (P0).
Все найденные значения всё ещё review, LLM в GoodsAI runtime не вызывается.

## DOCS-002: текст и доказательства — DONE

[DONE] Принято в PR #77 (`1e922aa`), зеркало Gitea проверено. Подготовлены [CONTENT_STYLE](CONTENT_STYLE.md), checklist PR
и [проверка презентации](PRESENTATION_REVIEW.md). Они разделяют DONE/PLAN/
HYPOTHESIS, требуют источники claims и запрещают декоративные AI-визуалы.
Текстовый аудит README, delivery report и Markdown-слайдов:
[content audit](reviews/2026-10-19_docs-002_content_audit.md). Это редакционные
правила, не автоматическая проверка истинности и не новая оценка качества.
Исторические frozen artifacts и PDF не перезаписывались.

## BASE-002: исходные spans — DONE

[DONE] Принято в PR #75 (`61b9260`), зеркало Gitea проверено.
Добавлен внутренний bounded SpanIndex с deterministic source/config identity,
точными raw offsets и явными truncated/unavailable reasons. Неизвестные имена,
числа, повторы и HTML/entities проверяются synthetic tests. Отдельный CLI
измеряет exact candidate-set recall, время и traced Python memory на явно
разрешённой span-разметке; raw text/SKU в report не выводятся. Synthetic fixture
покрывает 6/6 reference spans. Runtime predictor и публичный schema не менялись;
интеграция selector/LLM и реальное качество ещё не подтверждены.
Контракт, ограничения и команды: [SPAN_INDEX.md](SPAN_INDEX.md).

## Review и интеграция BASE-002 / DOCS-002

По прямому поручению пользователя автор выполнил review и интеграцию.
Критерии и решения ACCEPT записаны в [PR #75](https://github.com/CRUDoshleps/GoodsAI/pull/75)
и [PR #77](https://github.com/CRUDoshleps/GoodsAI/pull/77). Это авторский review,
не независимая разметка или подтверждение качества каталога.

После review исправлены пересечения HTML comments/declarations в raw spans,
проверка неизменности measurement input/reference и двусмысленность PLAN/REVIEW
в style guide. Алгоритм SpanIndex — `span-index-2`. На совместном candidate
`967108a` прошли 135 основных и 3 reader tests, pip check, demo 6/6, synthetic
span fixture 6/6, bundle smoke/verify и local Markdown targets. Frozen delivery
bytes не изменены. CI invariants прошёл для исправленного BASE-002 и совместного
candidate; mirror workflow успешен для обоих merge SHA.

Issues #64 и #52 закрыты после merge. VM, независимый gold/test, model calls,
новая визуальная PDF-проверка и репетиция не выполнялись.

## Версии

| Назначение | Репозиторий/ветка | Commit |
| --- | --- | --- |
| действующий сервис VM в момент ENV-001 | checkout `~/project`, сервис не перезапускался | `48b45dc` |
| последняя проверенная на Linux интеграционная база | изолированный clean checkout GitHub `main`, ENV-001 | `1d53dad` |
| последняя проверенная интеграционная база | GitHub / Gitea `main`, шесть PR и mirror 19.10 | `468e35e` |
| реорганизация командной работы | GitHub `docs/gov-001-team-workflow` | `dab5a48` + status handoff |
| типизированная система задач | GitHub `main` | PR #22, merge `81fe5be` |
| runtime schema | `0.1` | — |
| rules | `rules-0.3.0-m2-policy` | — |
| dictionaries | `manual-reviewed-brand-and-color-names-v2` | — |

GitHub и Gitea имели независимые истории. Прежний GitHub `main` сохранён в
`legacy/github-main-before-gitea-sync-2026-10-19`, после чего актуальный код
Gitea стал новым GitHub `main`. Каждый push в GitHub `main` автоматически
fast-forward публикуется в Gitea; divergence останавливает workflow.

## Реализовано

- Python 3.12 package, CLI и временный FastAPI service;
- text-only вход с запретом неизвестных и target-подобных полей;
- смартфоны `761` и чайники `482`;
- rules extraction бренда, явной модели, памяти, экрана, батареи, цвета,
  мощности и объёма в соответствии со схемой категории;
- normalizer для единиц, чисел, модели и aliases;
- точные raw evidence spans и schema validation;
- конфликт → abstain, кандидат → review;
- атомарная запись predictions/manifest и блокировка writers;
- run identity: hashes кода/конфига/входа/выхода, Git SHA и ресурсы;
- синтетическое демо на шести сценариях;
- evaluator с per-attribute метриками и coverage;
- systemd unit и runbook для VM.
- GitHub labels по типу/приоритету/статусу, формы задач и проверяемый claim;
- активный backlog перенесён в Issues #1–#21 и связан с `TASKS.md`.

## Не реализовано

- LLM в inference path по умолчанию (есть opt-in маршрут LLM-003, не измерен) и обученный encoder;
- cost-aware router между правилами и моделями;
- калиброванный confidence и `auto_accept`;
- независимый human gold/test;
- полная поддержка ноутбуков и новых категорий;
- обработка непустых seller attributes;
- финальный официальный API contract;
- официальный полный predictions-файл, доставленный организаторам;
- финальная презентация защиты (технический checkpoint PDF/Markdown подготовлен).

## Данные и оценка

Рабочий пилот содержит 10 324 SKU двух категорий. Реальные данные, reference и
predictions хранятся локально и исключены из Git.

Последний development-набор M2: 20 карточек, 120 полей, из них 83 present,
32 absent и 5 ambiguous; 115 judged-пар. После policy fixes rules получили
`69 TP / 0 FP / 14 FN`, `P=100%`, `R=83,1%`, `F1=90,8%`.

Это AI-assisted human-reviewed development, просмотренный во время настройки.
Он доказывает исправление известных примеров, но не качество на независимом
test и не перенос на весь каталог.

Более ранний reviewed-v2 validation: 12 карточек / 67 judged-пар,
baseline `29 TP / 1 FP / 21 FN`, `P=96,7%`, `R=58,0%`, `F1=72,5%`.
После просмотра его ошибок срез стал **development_feedback**, не независимым
validation. Последовательность измерений, frozen hashes и команды восстановлены
в [RESULTS.md](RESULTS.md); правила подсчёта — [EVALUATION.md](EVALUATION.md).

Итоговый резерв test M2 v2: 40 карточек (по 20 каждой категории), только
metadata и blank tasks. В DOCS-001 проверены агрегаты selection summary и
наличие файлов; тексты заданий не открывались, predictions не запускались.
BASE-001 в TASKS всё ещё READY, хотя model rules реализованы и измерены;
это расхождение передано интегратору, чужой статус автоматически не изменён.

## Проверки

### VER-001: relation guard подготовлен на review, 19 октября

Ветка `qa/ver-001-relation-verifier`, claim `9400302` от `37066be`.
Общая проверка перед merge кандидатов отклоняет явные отрицания, совместимость,
сравнения, комплект и характеристики аксессуара/другого объекта. Raw evidence
проверяется до semantic filtering; v0.1, confidence и review/abstain сохранены.
Реализация ещё не в main. [Отчёт](RELATION_VERIFIER.md), synthetic probes 8→0
ложных извлечений при сохранении 10/10 положительных. Reviewed development:
M2 69 TP/0 FP/14 FN и D21–D40 59 TP/0 FP/23 FN, до=после, 0 lost TP/new FP.
Это не независимые метрики и не доказательство прироста качества каталога.
Предсказания/разметка остаются private, test/LLM/VM не использовались.
151 основной + 3 reader tests, demo 6/6 и pip check — OK на Windows/Python 3.12.6.

Последний сохранённый отчёт команды для опубликованного функционала:

- 82 tests на Windows/Python 3.12.6;
- demo 6/6;
- CLI/API parity на синтетических входах;
- предыдущая версия сервиса запускалась на VM и отвечала на health/predict.

Это исторический результат из ветки Gitea. Для текущей GitHub-ветки проверка
документации выполняется отдельно; перед любым релизом нужен новый полный прогон
на том же SHA, который пойдёт в Gitea.

### DOCS-001: проверка инструкций, 19 октября

После явной передачи задачи Владом опубликован claim `949dbcd`, ветка
`docs/docs-001-reproducible-instructions`. Исправлены README/RUNBOOK,
inventory path, выбор Python и разделение demo/real evaluation; восстановлен
компактный индекс M1/M2 без публикации данных. Runtime/контракт не менялись.

В отдельном полном локальном clone `949dbcd` с копией проверяемых документов
создана новая `.venv` (Windows / Python 3.12.6), установка `.[serve,test]`
прошла. Пакет импортирован из `src` этого clone, каталога data/raw там нет.
`pip check` — OK; demo 6/6; evaluate без gold — unavailable/null P/R/F1;
82 основных и 3 reader tests — OK. Пример model JSON совпадает с extractor;
локальные Markdown-ссылки и 6 исторических путей проверены.
Локальные логи: `outputs/docs-001-verification/` (вне Git).

Это проверка candidate-документации на неизменном runtime, не clean release
и не новое измерение M1/M2. Полный EDA, pickle loading, независимый test,
LLM и VM не запускались. Linux-команды проверены по CLI/исходникам, но
на Linux в рамках DOCS-001 не выполнялись. Сборщик шести артефактов — следующий
инкремент; его наличие здесь не заявляется.

### DOCS-001 опубликован; ART-003 подготовлен на review

По разрешению Влада PR #31 слит в GitHub `main` (`55378f1`); mirror workflow
успешен, Gitea `main` указывает на тот же SHA. DOCS-001 завершён.
VM в этом шаге не обновлялась.

Этап B реализован в feature `release/art-003-artifact-bundle`, claim `d49f300`,
задача [ART-003 #32](https://github.com/CRUDoshleps/GoodsAI/issues/32).
[Offline-сборщик](ARTIFACT_BUNDLE.md) принимает frozen spec, связывает шесть
артефактов с кодом/конфигом/input/predictions/metrics, сообщает incomplete
при mismatch/missing и проверяет hashes после переноса. Public smoke получает
только встроенную синтетику; private-входы/gold/документы остаются локально.
Без gold P/R/F1 N/A. Конфиг ограничен versioned rules config; новый LLM runtime
потребует отдельного расширения, auto_accept не вводился.

Windows / Python 3.12.6: **100 основных тестов** (18 новых release tests),
3 reader tests, pip check — OK; smoke 6/6 и `verify` — OK. Локальные логи:
`outputs/art-003-full-tests-final.log`; candidate bundle:
`outputs/release/art-003-smoke-candidate/` (dirty candidate, не clean release).
Полный synthetic fixture со всеми шестью компонентами проверен тестами;
реальная техническая презентация и официальный dataset-wide release не созданы.

Runtime, schema v0.1, правила и зависимости не менялись. Реальные данные,
прежние gold/predictions/отчёты и резерв test не читались для новых предсказаний;
полный EDA, pickle, LLM, расходы и deployment не выполнялись. Приватная сборка
на реальном release candidate и Linux остаётся следующей проверкой ART-001/ENV-001.
Нужные безопасные агрегаты/слайды можно отдельно подготовить к публикации в Gitea
по разрешению Влада; автоматической публикации raw/gold/data нет.

### ART-001: реальные development-артефакты подготовлены

[Комплект checkpoint 19.10](delivery/2026-10-19/README.md) подготовлен на чистом
code candidate `047e1ee4abc5e04b0c3d49da3bfab81760f4376f` в
`release/art-001-prepared-delivery` (зависит от PR #33).

- Реальный batch: 2198 development SKU (1527 смартфонов, 671 чайник), все processed.
  Исключены 8126 прочих/защищённых/смешанных E1 SKU, включая все test_reserved;
  полный каталог не предсказывался, закрытые задания не открывались.
- M2 reviewed development: 69 TP / 0 FP / 14 FN, P100/R83,1/F190,8%,
  тот же reference SHA и те же ограничения AI-assisted, не независимый test.
- Candidate coverage на batch: 7953/14044 запрошенных пар (56,6%), не P/R/F1.
- EDA-агрегаты восстановлены из caches без полного EDA/pickle. Исправлена
  ошибка DATASET: каталог 546069 SKU; 148871 — SKU с дублирующимися названиями параметров.
- Подготовлены технические Markdown-слайды и PDF (8 страниц, весь рендер просмотрен).
  Это checkpoint, не финальная защита; PPTX не создавался.
- Полный PDF-комплект: assemble complete → verify → ZIP → извлечение → verify.
  В отдельном чистом worktree candidate без исходных caches из ZIP повторены
  predict/evaluate: JSONL побайтно идентичен, метрики идентичны, git_dirty=false.

108 основных + 3 reader tests и pip check — OK, Windows/Python 3.12.6.
Оригинальные input/caches/reference/старые outputs проверены hashes до/после,
не изменены. Runtime/схема/правила/зависимости не менялись. Не было LLM,
калибровки, расходов API, независимой оценки или изменения VM.

Локальный приватный архив: `outputs/delivery/art-001-20261019-v1/delivery-bundle-pdf.zip`,
SHA `31690a5fdefe2f3ee7e9059f2855bdc526b87f19f264498e20709bb08b3dc9de`.
В PR включаются только инструменты, агрегаты, checksums и слайды; raw/input/gold/
predictions/архив в Git не добавлены. Публикационные документы — последующий
commit, producer SHA остаётся указанным выше. Официальная полная сдача/доставка
архива организаторам и итоговый blind gold остаются отдельными действиями.

## Результат организаторского review

### EVAL-001: подготовка human-review, итоговый gold не готов

**Human feedback D21–D40 получен:** Влад явно подтвердил все неуказанные карточки/
поля. Номер комментария про G уточнён как D27, память D25 подтверждена.
Версионированный reviewed development сохраняет AI-assisted origin и
independent_reference=false: 20 карточек/120 labels, 82 present / 27 absent /
4 ambiguous / 7 unjudgeable, 109 judged / 11 excluded. Две ручные contextual
коррекции единиц памяти D27 с сохранением raw evidence; глобальная политика
единиц не менялась. Ошибка категории D24 подтверждена, в smartphone-схеме
unjudgeable сохранён; часы не добавлены в schema. Конфликты D29/D31/D36 остаются
ambiguous. Файл: `outputs/evaluation/development-review-20261019-human-v2/development.human-reviewed.jsonl`.
P/R/F1 пока N/A, реальный prediction/evaluation не запускался; reserve закрыт.
Влад согласовал направление обработки конфликтов: предложение исправленной
категории с подтверждением человека, без автоматической замены исходной категории;
рекомендации по единицам и неоднозначным model/color также приняты.
Это ещё не runtime-функция. Реализация категории — ML-002 (#58), пока BLOCKED
зависимостями и согласованием контракта; детали в DEVELOPMENT_REVIEW.md.
Producer feedback `4349c39`: 137 основных + 3 reader tests и pip check — OK,
4 human-reference файла byte-identical на повторе. Reviewed reference SHA:
`9f8a2ef601bd76704551340cedfe0aef7c8d42677446044cb4dfe37b8ee443ae`.

**Продолжение по решению Влада:** Issue #6 уточнён: сейчас выполняется
[AI-assisted development D21–D40](DEVELOPMENT_REVIEW.md) с последующей проверкой
Владом. Пул 800 unexposed development SKU, отобраны 20 разных семей / 120 полей,
по 10 карточек категории и по 5 с/без description. Draft: 80 present / 27 absent /
6 ambiguous / 7 unjudgeable; human-reviewed=0, все pending, P/R/F1=N/A,
independent_reference=false. Source/test не раскрываются вне development-партии.
Новый exposure ledger сохраняется рядом с draft и исключает эти семьи из будущих
новых отборов через --seen. Старые задания/разметка/предсказания сохранены.
Форма: `outputs/evaluation/development-review-20261019-v2-ai/development.review.md`.
Producer `ffa35ca`: 134 основных + 3 reader tests, pip check — OK; 4 selection
и 4 draft-файла byte-identical на повторе. Exact evidence и уникальность семей
проверены; EVAL-002 verify подтверждает неизменность источников, freeze test
остаётся approved=false. Текущий инкремент передан на REVIEW, не DONE.

В `eval/eval-001-blind-human-gold` подготовлены [протокол](HUMAN_GOLD.md),
[guideline](HUMAN_GOLD_GUIDELINES.md), offline HTML и команды
prepare/materialize/check/reconcile/finalize. Claim `fab562f`, code `257fe1f`.
128 основных + 3 reader tests, pip check, CLI/link/secret-pattern checks — OK;
synthetic browser smoke подтвердил Unicode offsets/navigation/JSON download+import.

Локальный `outputs/evaluation/eval-001-20261019-metadata/`: 40 карточек/240 полей,
только metadata/blank labels, 6 файлов двух запусков byte-identical. Package ID
`c2a18dfba7f9d23c2c913443f906ea3eba98adb9229aa9f437ae3e18f7c5cba0`.
Неутверждённый freeze блокирует раскрытие; реальный HTML/тексты test не создавались,
answers/gold/predictions отсутствуют, P/R/F1 и agreement N/A. Проверяемый candidate
в template — `1d53dad` (rules-0.3.0-m2-policy), это предложение, не утверждённый freeze.

Влад сообщил, что размечать будет один и раньше видел AI-assisted development.
Это не автоматически exposure нового reserve, но не выполняет требование двух
независимых людей. Будущий независимый подэтап ожидает разметчиков/adjudicator,
решения о freeze и сбора ответов. Сам Issue #6 продолжен для AI-assisted development;
такой набор не объявляется независимым test. Runtime/исходные данные/VM не менялись.

### EVAL-002: split/leakage audit — 19.10.2026

Подготовлен [аудит E1 split](reviews/2026-10-19_eval-002_split_audit.md),
[метод и CLI](SPLIT_AUDIT.md), ветка `eval/eval-002-split-leakage`, Issue #7.
После согласования Владом PR #69 слит в GitHub main (`c49540f`), Issue #7 закрыт.
Это принятие инструмента/результатов аудита, не независимый human gold и не
автоматическая замена manifests в downstream-процессах. VM не обновлялась.
Producer `62388ad`, clean Windows/Python 3.12.6. Исходные 10324 SKU содержат
632 mixed семейных компонента; прежний original split целиком не является
независимым. Отдельный `eval-002-quarantine-v1` сохраняет 3411 SKU
(2198 development / 882 validation-feedback / 331 test_reserved), 6913 строк
целиком исключены в консервативный карантин. В eligible нет обнаруженных
межsplit-компонентов/exposed test-семейств. Validation остаётся development feedback.

Действующий M2 v2 reserve: 40 SKU / 40 семейств, 0 выявленных проблем;
тексты не выводились/не экспортировались, predictions не запускались, проверена
пустота labels. Независимого human gold это не создаёт. Все 9 файлов двух чистых
run побайтно совпали, verify и hashes входов — OK. 119 основных + 3 reader tests,
pip check — OK. Старые split/gold/results не перезаписаны, runtime/VM не изменены.
Локальные identities/fingerprints/нарушения в `outputs/evaluation/`, вне Git.
Новый partition подключается явно после review, автоматической миграции нет.

Обновление 19.10.2026: [аудит второго прогона и план](reviews/2026-10-19_second_run_plan.md).
Сумма оценённых технических критериев выросла с 17,17 до **17,81/20** (+0,64).
Снизились воспроизводимость (−0,10), архитектура (−0,33) и обработка ошибок
(−0,11); блок качества результата по-прежнему не оценён.
Локально получен Gitea `0736753`: ночные изменения после `48b45dc` затронули
документацию и GitHub workflow, но не runtime/тесты/зависимости. На этом SHA
прошли 82 основных теста, 3 reader tests и demo 6/6 (Windows, Python 3.12.6).
Точный SHA организаторского прогона и новое состояние VM не проверены.
Ближайший предложенный порядок: исправить инструкции и восстановить ссылки
на доказательства → собрать проверяемую поставку шести артефактов → усилить
release gate. Blind human review готовить параллельно, test не использовать
для настройки. Это предложение приоритетов, без изменения чужих claims в TASKS.

По скриншотам первого технического прогона оценённые критерии дали 17,17/20.
Неоценённый блок качества результата оставался пустым. Product checkpoint —
10/10, но способ его включения в общий балл не описан.

### Backlog по новой детализации оценки

Платформа отдельно показывает продуктовый чекпоинт `10/10`, оценённые
технические критерии `17,81/20`, пустой блок качества `—/5` и пока
неоценённую финальную защиту `—/15`. Общий индикатор на странице равен
`17,81/35`; правило объединения этапов не опубликовано, поэтому значения здесь
не складываются самостоятельно.

В `GOV-003` заведены ровно 20 новых задач
[#35–#54](https://github.com/CRUDoshleps/GoodsAI/issues?q=is%3Aissue+is%3Aopen+created%3A2026-10-19),
которые переводят текстовый feedback в проверяемые результаты. Наибольший
приоритет имеют независимый пакет качества, калибровка auto-accept, чистый
воспроизводимый запуск и release gate точного SHA. Архитектурные, операторские
и презентационные задачи идут после их зависимостей. На момент создания плана реализация не была начата; актуальные статусы
смотрите в TASKS.md. Критический путь находится в
[плане улучшения оценки](reviews/2026-10-19_score_improvement_backlog.md).

Организаторы подтвердили сильные стороны: работающий end-to-end baseline,
модульность, тесты, JSONL output и документация. Основной долг:

1. модельный/LLM слой в runtime;
2. конфигурируемые решения и thresholds;
3. готовые predictions и metrics, связанные с одним запуском;
4. более простой воспроизводимый сценарий для пользователя;
5. эксплуатационные проверки и явные fallback.

Атомарная запись, явная model grammar и часть policy problems уже исправлены.
Остальные пункты находятся в [TASKS.md](../TASKS.md).

## Приоритеты

### P0 — доказать результат

1. Независимый blind human gold/test.
2. Аудит split, дублей и leakage.
3. Официальный predictions-файл + manifest + metrics.
4. Вынести конфигурацию и подтвердить contract.
5. Воспроизвести последний SHA на VM.
6. Настроить безопасный GitHub → Gitea release.

### P1 — добавить гибрид

1. Подключить OpenAI-compatible LLM gateway за adapter.
2. Сравнить rules, LLM-only и rules→LLM на frozen validation.
3. Добавить общий relation verifier и budget guard.
4. Проверить компактный encoder только при наличии достаточной разметки.

### P2 — продуктовый контур

1. Review UI с evidence и причинами.
2. Active learning из проверенных исправлений.
3. Seller/category quality dashboard и downstream A/B.

## Риски

| Риск | Текущее снижение | Следующее действие |
| --- | --- | --- |
| галлюцинации | no evidence → reject | общий verifier для LLM |
| завышенная метрика | provenance и честная пометка development | независимый test |
| утечка target | строгий text-only contract | split/leakage audit |
| стоимость LLM | вызовов сейчас нет | budget и cost metrics |
| конфликт участников | task claim и один owner | PR review и интегратор |
| расхождение репозиториев | отдельные work/release remotes | release manifest с source SHA |
| секреты в истории | `.gitignore`, env-only | немедленная ротация показанных секретов |

## Следующее решение команды

Не выбирать большую модель до готовности EVAL-001. Сначала получить честный
gold и release artifact, затем измерить самый простой гибрид rules → fast LLM.
Encoder добавлять, если эксперимент покажет пользу по качеству, цене или latency.
