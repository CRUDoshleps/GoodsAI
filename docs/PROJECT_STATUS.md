# Состояние проекта

Актуально на 19 октября 2026 года.

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
| опубликованный runtime baseline | Gitea `main`, без ночных docs-only изменений | `48b45dc` |
| последняя проверенная интеграционная база | GitHub / Gitea `main`, BASE-002 + DOCS-002 и mirror 19.10 | `1e922aa` |
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

- реальный LLM или обученный encoder в основном inference path;
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
