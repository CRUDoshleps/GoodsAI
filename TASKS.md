# Рабочие задачи команды

Этот файл — единая доска задач для людей и агентов. Перед изменением кода
исполнитель сначала переводит одну задачу в `IN_PROGRESS`, указывает себя,
ветку и дату, делает отдельный commit и публикует ветку в рабочем GitHub.
GitHub Issues хранит обсуждение, labels и связь с PR; правила синхронизации
двух досок описаны в `docs/TASK_MANAGEMENT.md`.

## Статусы

`BACKLOG` → `READY` → `IN_PROGRESS` → `REVIEW` → `DONE`.

`BLOCKED` означает, что указан конкретный блокер. `CANCELLED` используется
только вместе с причиной. Одновременно у задачи один исполнитель и не больше
одной рабочей ветки.

## Типы задач

| Код | Область |
| --- | --- |
| `GOV` | процесс команды, роли и правила работы |
| `ARCH` | архитектура и контракты |
| `SYNC`, `ENV` | синхронизация репозиториев и окружение |
| `DATA` | данные, подготовка и качество выборки |
| `BASE` | правила и словари baseline |
| `ML` | локальные модели и обучение |
| `LLM` | интеграция LLM и контроль расходов |
| `EVAL` | разметка, метрики и эксперименты |
| `API` | CLI, API и пакетная обработка |
| `QA`, `VER` | тестирование, verifier и отказоустойчивость |
| `OPS` | окружение, VM и наблюдаемость |
| `DOCS` | документация |
| `REL`, `ART` | сборка, артефакты и выпуск в Gitea |
| `PRODUCT`, `SPEC` | пользовательский сценарий, контракт и бизнес-метрики |
| `CONF`, `ROUTE` | конфигурация и маршрутизация pipeline |
| `ACTIVE` | active learning и цикл обратной связи |
| `SEC` | секреты и безопасная работа с данными |

Префикс ID сохраняет конкретную подсистему, а label `type:*` объединяет задачи
по рабочей области. Например, `CONF-001` имеет `type:architecture`, а
`ENV-001` — `type:ops`.

## Активная очередь

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-001 | [#2](https://github.com/CRUDoshleps/GoodsAI/issues/2) | P0 | REVIEW | архитектор/интегратор | Codex | `docs/gov-001-team-workflow` | единая документация и процесс совместной работы |
| GOV-002 | [#1](https://github.com/CRUDoshleps/GoodsAI/issues/1) | P0 | DONE | архитектор/интегратор | Codex | `gov/gov-002-task-system` | GitHub labels, issue forms и проверяемый захват задач |
| SYNC-001 | — | P0 | DONE | интегратор | Codex | `main` | актуальный Gitea `main` перенесён в основной GitHub `main` |
| SEC-001 | [#3](https://github.com/CRUDoshleps/GoodsAI/issues/3) | P0 | READY | владелец доступов | — | — | заменить опубликованные VM, Gitea, Jupyter и LLM-секреты |
| ENV-001 | [#4](https://github.com/CRUDoshleps/GoodsAI/issues/4) | P0 | READY | QA/MLOps | — | — | воспроизвести последний SHA на VM и сохранить протокол |
| DATA-001 | [#5](https://github.com/CRUDoshleps/GoodsAI/issues/5) | P0 | READY | data engineer | — | — | воспроизводимая предобработка и свежий data manifest |
| EVAL-001 | [#6](https://github.com/CRUDoshleps/GoodsAI/issues/6) | P0 | READY | аналитик/разметчик | — | — | независимый human gold без просмотра ответов системы |
| EVAL-002 | [#7](https://github.com/CRUDoshleps/GoodsAI/issues/7) | P0 | DONE | data/QA | urasha / Codex (сессия Влада) | `eval/eval-002-split-leakage` | PR #69 merged `c49540f`; filtered partition + quarantine; M2 reserve 40/40 checks OK |
| ART-001 | [#8](https://github.com/CRUDoshleps/GoodsAI/issues/8) | P0 | REVIEW | интегратор/аналитик | Codex (сессия Влада) | `release/art-001-prepared-delivery` | checkpoint: 2198 predictions, reviewed metrics, EDA, PDF, bundle verified |
| CONF-001 | [#9](https://github.com/CRUDoshleps/GoodsAI/issues/9) | P0 | READY | архитектор | — | — | вынести пороги, модели и схемы категорий в конфигурацию |
| SPEC-001 | [#10](https://github.com/CRUDoshleps/GoodsAI/issues/10) | P0 | READY | product/аналитик | — | — | подтвердить формат выхода, обязательные поля и confidence |
| REL-001 | [#11](https://github.com/CRUDoshleps/GoodsAI/issues/11) | P0 | READY | release engineer | — | — | воспроизводимый выпуск проверенного GitHub SHA в Gitea |
| REL-002 | — | P0 | DONE | release engineer | Codex | `ops/rel-002-main-mirror` | GitHub `main` автоматически fast-forward публикуется в Gitea `main` |
| DOCS-001 | [#28](https://github.com/CRUDoshleps/GoodsAI/issues/28) | P1 | DONE | technical writer | Codex (сессия Влада) | `docs/docs-001-reproducible-instructions` | PR #31 merge `55378f1`, зеркало Gitea успешно |
| ART-003 | [#32](https://github.com/CRUDoshleps/GoodsAI/issues/32) | P0 | REVIEW | release/QA | Codex (сессия Влада) | `release/art-003-artifact-bundle` | offline smoke/assemble/verify, 100 + 3 tests OK |
| BASE-001 | [#21](https://github.com/CRUDoshleps/GoodsAI/issues/21) | P1 | READY | NLP/baseline | — | — | консервативный прототип извлечения модели товара |
| LLM-001 | [#12](https://github.com/CRUDoshleps/GoodsAI/issues/12) | P1 | BACKLOG | LLM engineer | — | — | OpenAI-compatible adapter со structured output и бюджетом |
| LLM-002 | [#13](https://github.com/CRUDoshleps/GoodsAI/issues/13) | P1 | BLOCKED | LLM engineer/аналитик | — | — | сравнение доступных моделей; ждёт EVAL-001 и лимит бюджета |
| ROUTE-001 | [#14](https://github.com/CRUDoshleps/GoodsAI/issues/14) | P1 | BLOCKED | архитектор/ML | — | — | измеряемый rules → model/LLM → verifier router; ждёт EVAL-001 |
| VER-001 | [#15](https://github.com/CRUDoshleps/GoodsAI/issues/15) | P1 | REVIEW | NLP/QA | urasha / Codex (сессия Влада) | `qa/ver-001-relation-verifier` | claim 9400302; relation guard; synthetic false accepts 8→0, 0 lost TP на двух development references |
| ML-001 | [#16](https://github.com/CRUDoshleps/GoodsAI/issues/16) | P1 | BLOCKED | ML engineer | — | — | компактный encoder только после baseline и gold; ждёт EVAL-001 |
| API-001 | [#17](https://github.com/CRUDoshleps/GoodsAI/issues/17) | P1 | READY | backend | — | — | финальный batch/API-контракт и диагностика ошибок |
| QA-001 | [#18](https://github.com/CRUDoshleps/GoodsAI/issues/18) | P1 | IN_PROGRESS | QA | Codex (tunaIT) | `qa/qa-001-hard-cases` | 19.10: expected-output synthetic adversarial suite; depends on #79/#86 for relation/unit fixes |
| PRODUCT-001 | [#19](https://github.com/CRUDoshleps/GoodsAI/issues/19) | P2 | BACKLOG | product/UX | — | — | экран review с evidence и решениями оператора |
| ACTIVE-001 | [#20](https://github.com/CRUDoshleps/GoodsAI/issues/20) | P2 | BLOCKED | ML/product | — | — | active learning из правок; ждёт рабочего review-сценария |
| DOCS-002 | [#52](https://github.com/CRUDoshleps/GoodsAI/issues/52) | P1 | DONE | technical writer | Codex (e345ee) | `main` | PR #77 merged 1e922aa; author review по поручению пользователя; 135 + 3 tests, smoke/verify; mirror OK |
| BASE-002 | [#64](https://github.com/CRUDoshleps/GoodsAI/issues/64) | P1 | DONE | NLP/baseline | Codex (e345ee) | `main` | PR #75 merged 61b9260; review fixes 0693d21; 135 + 3 tests; mirror OK; selector not integrated |

| BASE-003 | [#74](https://github.com/CRUDoshleps/GoodsAI/issues/74) | P0 | REVIEW | NLP/baseline | Codex (tunaIT) | `baseline/base-003-battery-units` | Units fix; 158+3 tests; synthetic TP5→12 / FP0; requires PR #79; docs/BATTERY_UNITS.md |

## Как взять задачу

1. Обновить рабочую базу: `git fetch work`.
2. Создать ветку от согласованной интеграционной ветки.
3. Изменить в этой таблице статус на `IN_PROGRESS`, указать исполнителя,
   ветку и дату начала в примечании задачи.
4. Сделать отдельный commit: `chore(tasks): claim <ID>`.
5. Опубликовать ветку в GitHub и только затем менять код или документы.

## DOCS-001 — воспроизводимые инструкции и результаты

- Передано сессии Влада 19.10.2026 по явному решению Влада в чате.
- Предыдущий claim: `1952c70`, ветка `rel/rel-003-review-remediation`.
  Остальные задачи той ветки этой передачей не затрагиваются.
- Владелец: Codex (сессия Влада); ветка `docs/docs-001-reproducible-instructions`.
- Scope: этап A из плана второго прогона — README/RUNBOOK, prerequisites
  подготовки, правила метрик и компактный индекс исторических результатов.
- Приёмка: публичный сценарий проходит в чистом clone с полной историей;
  приватные команды имеют согласованные входы и hashes; тексты данных не
  публикуются; runtime и независимый test не меняются.
- Сборщик шести артефактов, LLM и deployment в scope не входят.
- Результат: README/RUNBOOK и путь inventory исправлены; добавлен
  `docs/RESULTS.md` с историей M1/M2 и hashes; бывший validation явно feedback.
  В полном clone с новым окружением: 82 + 3 tests, demo 6/6, pip check OK.
  BASE-001 уже имеет реализацию M1; статус общей задачи должен сверить интегратор.

## ART-003 — сборщик комплекта артефактов

- Начато 19.10.2026, база `work/main=55378f1`, после DOCS-001.
- Scope: этап B плана второго прогона, отдельный `scripts/release/build_release.py`,
  синтетические проверки и инструкция. Контракт/runtime/demo не меняются.
- Проверки: комплектность шести артефактов, SHA и provenance, согласованность
  input/predictions/manifest/metrics, запрет перезаписи и публикации реальных
  данных в публичном smoke; при отсутствующем gold — качество N/A.
- ART-002 в `rel/rel-003-review-remediation` и его runtime/demo не затрагиваются.
  Финальный реальный batch и утверждённый канал сдачи остаются ART-001.
- DOCS-001 завершён по разрешению Влада: PR #31 слит `55378f1`, GitHub Actions
  mirror success, SHA GitHub/Gitea совпали. VM не обновлялась.
- Реализованы CLI smoke/assemble/verify, frozen spec и публикационные границы.
  18 новых synthetic tests; общий прогон 100 + 3 tests, smoke 6/6, pip check OK.
  Документация — `docs/ARTIFACT_BUNDLE.md`; нет реальных новых predictions,
  финальных технических слайдов или независимой оценки. Это готовность инструмента,
  а не автоматическое закрытие ART-001 и шести артефактов сдачи.

## ART-001 — подготовка реальных артефактов текущего этапа

- Начато 19.10.2026 по прямому запросу Влада завершить подготовку.
- Ветка создана от `work/main=55378f1`, затем fast-forward включена зависимость
  ART-003 `9cf8d2e` (PR #33 остаётся на review, main не меняется).
- Scope: прогноз по разрешённым development-группам, reviewed M2-метрики,
  EDA-агрегаты из имеющихся отчётов, Markdown-черновик технических слайдов,
  frozen spec и полная offline-сборка с verify.
- Исключить все защищённые test_reserved/family и остальные не-development
  группы; не открывать test tasks и не выдавать ограниченный batch за весь каталог.
- Реальные input/gold/predictions и полный комплект остаются локально;
  в PR — инструменты, безопасные агрегаты и слайды. Нет LLM, pickle/полного EDA,
  правок правил/контракта, расходов или VM deployment.
- Сборка фиксируется на чистом code candidate; публикационные документы могут
  быть последующим commit с явной ссылкой на producer SHA.
- Результат: code candidate `047e1ee`, 2198 allowed-development predictions,
  M2 69/0/14, EDA caches summary, 8-страничный PDF и editable Markdown.
  Сборка complete, verify и ZIP roundtrip OK; отдельный clean-worktree replay
  даёт побайтно те же predictions и идентичные метрики без исходных caches.
  108 + 3 tests, pip check OK. Локальный полный ZIP и публичные агрегаты описаны
  в `docs/delivery/2026-10-19/README.md`. Закрытый test не предсказывался.
- REVIEW относится к подготовке текущего development checkpoint. Задачу не
  закрывать как официальную полную сдачу: whole-catalogue inference, конечный
  канал передачи и итоговая независимая оценка здесь не выполнялись.

## Как передать результат

Перед `REVIEW` исполнитель добавляет в PR:

- что изменено и зачем;
- точный commit и изменённые файлы;
- реально выполненные проверки и их результат;
- метрики с названием split и происхождением разметки;
- ограничения, блокеры и способ отката;
- ссылку на артефакт, если задача его создаёт.

`DONE` ставит интегратор после merge. Разработка идёт в GitHub. В Gitea
попадает только проверенный релиз по процессу из `docs/RELEASES.md`.

## GOV-001

- Начато: 2026-10-19.
- Основа: Gitea `main` на commit `48b45dc`.
- Цель: сократить документы, зафиксировать роли, архитектуру, научные ссылки,
  подробный backlog и разделить рабочую разработку с релизами организаторам.
- Результат: документальный commit `dab5a48`; 49 Markdown-файлов сведены к
  16 актуальным, подробные исторические версии остаются в Git history.
- Проверено: `git diff --check`, локальные Markdown-ссылки и поиск известных
  секретов; missing links `0`. Runtime и его tests в задаче не менялись.
- Reviewer должен проверить смысл задач, роли и решение о сохранении старых
  GitHub `main`/`dev`. После review интегратор ставит `GOV-001` в `DONE`.

## Подробные задачи

### GOV-002 — система задач GitHub

- Начато: 2026-10-19.
- Владелец: Codex.
- Ветка: `gov/gov-002-task-system`.

**Шаги**

1. Создать labels для типа, приоритета, статуса, риска и потребности в review.
2. Добавить формы для обычной задачи, эксперимента, ошибки, решения и релиза.
3. Добавить PR template с task ID, claim commit, проверками и рисками.
4. Связать GitHub Issues с версионируемым индексом `TASKS.md`.
5. Описать переходы статусов, блокировку, review, merge и закрытие задачи.
6. Завести текущие незавершённые задачи в GitHub Issues.

**Готово, когда:** участник может выбрать `READY`-задачу, назначить себя,
опубликовать отдельный claim commit и пройти до review без устной координации;
тип, приоритет и статус каждой активной задачи видны в GitHub.

**Передано в review:** claim commit `d4e20e0`; GitHub Issue #1; создано 29
labels, пять Issue forms и PR template; активные задачи заведены в Issues
#2–#21 и связаны с таблицей. Из `TEAM_TASKS.md` отдельно восстановлена
пропущенная задача `BASE-001`.

**Выполнено 19 октября:** PR #22 объединён merge commit
`81fe5be0e9fd2256f8434cb43f84e42adfe951bb`; workflow run `39178695967`
успешно доставил тот же commit в Gitea. Формы доступны из GitHub `New issue`.

### SYNC-001 — рабочая база GitHub

**Шаги**

1. Проверить Gitea `main`, дерево и последний SHA.
2. Добавить remotes `work` и `release` без credentials в URL.
3. Опубликовать актуальную историю в новой GitHub-ветке.
4. Не переписывать старые GitHub `main`/`dev`.
5. Сделать перенесённую историю новым GitHub `main`, сохранив старый main.

**Готово, когда:** GitHub содержит актуальный код Gitea, source SHA записан,
команда знает базовую ветку, а старые ветки не потеряны.

### SEC-001 — ротация доступов

**Шаги**

1. Капитан перевыпускает показанные в чате VM/Gitea/Jupyter/LLM credentials.
2. Проверяет, что старые значения больше не работают.
3. Осматривает Git history, notebook outputs, shell history и логи.
4. Настраивает передачу через менеджер секретов или страницу команды.
5. Публикует только факт ротации, без значений.

**Готово, когда:** открытые значения отозваны, секретов нет в Git и логах.

### ENV-001 — воспроизводимость VM

**Шаги**

1. Взять утверждённый GitHub SHA.
2. Создать чистое Python 3.12 окружение на VM.
3. Установить пакет и выполнить `pip check`.
4. Запустить обе test suites и demo.
5. Проверить batch, API health и один синтетический predict.
6. Сохранить безопасный отчёт: SHA, OS, Python, команды, exit codes, время.

**Готово, когда:** тот же SHA воспроизводится одной инструкцией, service active,
демо 6/6, все проверки зелёные и известен rollback.

### DATA-001 — подготовка датасета

**Шаги**

1. Обновить inventory исходных файлов с размером и SHA-256.
2. Проверить schemas, типы, null, Unicode/HTML и аномальные длины.
3. Построить безопасную проекцию title/description/category/SKU.
4. Проверить join, пропуски, несовпадающие titles и повторяющиеся params.
5. Построить exact/normalized/near-duplicate группы.
6. Проверить split и исключить target leakage/exposed families.
7. Создать processed JSONL, provenance и manifest.
8. Обновить EDA-агрегаты без реальных текстов в Git.

**Готово, когда:** одна команда повторяет выход по тем же hashes; все потери
строк объяснены; дубли не пересекают splits; targets не входят в inference.

### EVAL-001 — независимый gold/test

**Шаги**

1. Заморозить annotation guideline и категории.
2. Выбрать карточки из неэкспонированных product families.
3. Дать двум людям текст без predictions и готовых params.
4. Сохранить независимые ответы и disagreements.
5. Провести adjudication третьим человеком или заранее назначенным экспертом.
6. Зафиксировать present/absent/ambiguous и evidence.
7. Версионировать manifest, hashes и reviewer provenance.
8. Не открывать test разработчикам до freeze методов.

**Готово, когда:** есть достаточный blind human reference, agreement report и
строгая граница validation/test. Размер утверждает аналитик до разметки.

### EVAL-002 — аудит split и leakage

Claim `697148c`, producer `62388ad`, 19.10.2026. [Отчёт](docs/reviews/2026-10-19_eval-002_split_audit.md),
[метод](docs/SPLIT_AUDIT.md). DONE после согласования Владом и merge PR #69
`c49540f` 19.10.2026: 632 mixed components, новый filtered partition
3411 eligible / 6913 quarantined, текущий reserve 40/40 без выявленных проблем.
119 + 3 tests, два clean run byte-identical, verify — OK. Данные и списки
пересечений локально, старые split/gold не менялись. Независимый human review,
решение о подключении нового partition и проверка Linux/VM не выполнены.

**Шаги**

1. Проверить уникальность SKU и group ID.
2. Найти exact и normalized text duplicates.
3. Выдать near-duplicate candidates без публикации реальных текстов.
4. Проверить product families между splits.
5. Пометить AI/model-exposed карточки.
6. Сформировать агрегаты и список нарушений локально.

**Готово, когда:** подтверждённых пересечений нет либо создана новая версия
split; test contents не использовались для настройки.

### ART-001 — комплект результата

**Шаги**

1. Уточнить официальный вход и формат output.
2. Выполнить полный batch на release candidate.
3. Проверить одну строку результата на каждую входную карточку.
4. Создать manifest с hashes, Git SHA, config и status counts.
5. Запустить evaluator на разрешённом reference.
6. Связать predictions, metrics и release report checksums.
7. Передать большой файл по утверждённому каналу.

**Готово, когда:** сторонний reviewer может связать каждую цифру с конкретным
файлом и commit, а артефакт доступен организаторам.

### CONF-001 — конфигурация

**Шаги**

1. Инвентаризировать hardcoded bounds, scores, limits и model names.
2. Спроектировать versioned category/method/runtime configs.
3. Добавить строгую валидацию и fail-fast.
4. Сохранить безопасные defaults: LLM off, auto_accept off.
5. Обеспечить одинаковую загрузку CLI/API/tests.
6. Добавить config hash в manifest.

**Готово, когда:** новая категория/модель не требует правки orchestration-кода,
невалидный config останавливает запуск, а defaults безопасны.

### SPEC-001 — официальный контракт

**Шаги**

1. Передать организаторам вопросы из `docs/REQUIREMENTS.md`.
2. Сохранить ответы со ссылкой и датой.
3. Отделить требования от решений команды.
4. Обновить input/output schema и migration notes.
5. Согласовать confidence, abstain и seller attributes.

**Готово, когда:** неизвестные пункты либо подтверждены источником, либо явно
помечены внутренней политикой; API и batch используют одну версию.

### REL-001 — GitHub → Gitea

**Шаги**

1. Назначить source SHA и release engineer/reviewer.
2. Собрать test/demo/artifact reports.
3. Проверить неизменность Gitea `main`.
4. Push release-ветки и PR без force.
5. Merge, tag, update VM и smoke test.
6. Сохранить manifest и rollback SHA.

**Готово, когда:** Gitea `main` и VM работают на одном проверенном SHA,
происхождение из GitHub доказуемо, rollback проверяем.

### REL-002 — автоматическое зеркало main

**Шаги**

1. Сохранить прежний GitHub `main` в резервной ветке.
2. Сделать актуальный код Gitea и новую документацию GitHub `main`.
3. Добавить workflow, который запускается только после push в GitHub `main`.
4. Проверять, что Gitea `main` является предком публикуемого commit.
5. Запретить force push из workflow.
6. Хранить Gitea credentials только в GitHub Secrets.
7. Выполнить ручной запуск и проверить совпадение SHA двух `main`.

**Готово, когда:** обычный commit в GitHub `main` автоматически доходит до
Gitea fast-forward; divergence останавливает job, а старый GitHub `main`
доступен в резервной ветке.

**Выполнено 19 октября:** прежний GitHub `main` сохранён в
`legacy/github-main-before-gitea-sync-2026-10-19`; новый `main` создан из
актуального Gitea commit и документации. Workflow run `39177817712` завершился
успешно и fast-forward обновил Gitea. Secrets сохранены только в GitHub Actions.

### BASE-001 — прототип извлечения модели товара

**Шаги**

1. Извлекать только явно указанное коммерческое имя или код модели.
2. Не включать бренд, память, цвет и состояние товара.
3. Использовать description только при подтверждённой связи с главным товаром.
4. Сохранять точный raw evidence span, включая HTML/entities.
5. Отказываться при нескольких кодах, чужой сущности и неоднозначной границе.
6. Добавить synthetic cases для явной модели, отсутствия, повторного бренда,
   памяти/цвета рядом, нескольких кодов и HTML-разрывов.
7. Оставить прототип изолированным до review и независимого замера.

**Готово, когда:** прототип запускается отдельно, имеет негативные проверки,
точные offsets и список решений для интеграции; development и готовое поле
`model` не выдаются за независимую оценку качества.

### LLM-001 — gateway adapter

**Шаги**

1. Создать provider interface без импорта в rules.
2. Читать URL/key только из окружения.
3. Отправлять только неразобранные поля и минимальный текст.
4. Требовать JSON schema, evidence, offsets и возможность abstain.
5. Ввести timeout, ограниченный retry, concurrency и budget guard.
6. Проверять ответ общим verifier.
7. Логировать безопасные агрегаты tokens/cost/latency/reason.
8. Добавить fake provider tests без реальных вызовов.

**Готово, когда:** provider можно выключить; недоступность не ломает rules;
невалидный или неподтверждённый ответ отвергается; секреты не логируются.

### LLM-002 — сравнение моделей

**Шаги**

1. После EVAL-001 выбрать fast и strong модели доступного шлюза.
2. Заморозить prompts, schema и budget.
3. Прогнать rules, LLM-only и cascade на одном validation.
4. Посчитать P/R/F1, evidence, calls, tokens, рубли, p50/p95.
5. Разобрать ошибки и построить Pareto-таблицу.
6. Выбрать model IDs конфигом или отказаться от route.

**Готово, когда:** выбор основан на зафиксированном отчёте, а не на размере
модели или единичных примерах.

### ROUTE-001 — гибридный router

**Шаги**

1. Маршрутизировать по атрибутам, а не целым карточкам без причины.
2. Сохранять успешные rules-кандидаты.
3. Отправлять остаток в разрешённый model route.
4. Объединять ответы только через verifier.
5. Записывать route reasons и расходы.
6. Реализовать budget/provider fallback в abstain.
7. Калибровать thresholds на validation.

**Готово, когда:** cascade улучшает выбранную Pareto-точку, воспроизводим и
безопасно работает при отключённой LLM.

### VER-001 — relation verifier

19.10.2026: реализация на REVIEW, claim `9400302`, сессия Влада.
[Результат и ограничения](docs/RELATION_VERIFIER.md). Общий candidate guard,
без изменения v0.1 и extractor rules; на 20 synthetic probes ложные извлечения
8→0, сохранены 10/10 положительных фактов. Два reviewed development по 20 карточек:
M2 69 TP/0 FP/14 FN, D21–D40 59 TP/0 FP/23 FN, до=после, 0 lost TP/new FP.
Это AI-assisted development, не independent test. Main/VM не обновлялись.

**Шаги**

1. Собрать отрицательные шаблоны: совместимость, аксессуар, комплект, negation.
2. Проверять связь evidence с главным товаром.
3. Обрабатывать несколько сущностей и значения разной роли.
4. Добавить conflict policy title/description.
5. Применить один интерфейс к rules/encoder/LLM.
6. Измерить false accepts до/после.

**Готово, когда:** коварный набор QA-001 проходит, а recall loss раскрыт.

### ML-001 — компактный encoder

**Шаги**

1. Начинать только после независимого gold и split audit.
2. Выбрать token classification или span extraction baseline.
3. Зафиксировать seed, tokenizer, checkpoint и training manifest.
4. Не использовать test и готовые catalog targets как признаки.
5. Сравнить с rules/LLM по качеству, latency, RAM и стоимости поддержки.
6. Экспортировать веса и воспроизводимый inference либо отклонить гипотезу.

**Готово, когда:** модель даёт измеримую пользу на validation и помещается в
ограничения VM; иначе решение «не использовать» считается валидным итогом.

### API-001 — официальный интерфейс

**Шаги**

1. Получить официальный contract.
2. Согласовать batch и single-card semantics.
3. Ввести request/run ID, limits, timeouts и stable error codes.
4. Проверить content type, size, JSON depth и unknown fields.
5. Добавить readiness отдельно от liveness при model route.
6. Документировать примеры и обратную совместимость.

**Готово, когда:** контракт проходит organizer scenarios, ошибки предсказуемы,
а transport не меняет prediction core.

### QA-001 — коварный и аварийный набор

**Шаги**

1. Добавить синтетические конфликты, negation, совместимость и редкие единицы.
2. Проверить пустой/огромный/невалидный JSON и неизвестную категорию.
3. Проверить provider timeout, malformed schema и budget exhaustion.
4. Проверить параллельную запись, interruption и recovery.
5. Проверить CLI/API parity и отсутствие текста/секретов в логах.

**Готово, когда:** каждый риск имеет ожидаемый status/reason и regression test.

### PRODUCT-001 — review-сценарий

**Шаги**

1. Показать карточку, значение, evidence, method и reason.
2. Реализовать принять/исправить/отклонить.
3. Записывать reviewer и время без перезаписи исходного prediction.
4. Измерить время обработки и agreement.
5. Экспортировать проверенные правки в очередь разметки.

**Готово, когда:** оператор решает 10–20 карточек без поиска evidence вручную,
а действия воспроизводимо превращаются в versioned feedback.
