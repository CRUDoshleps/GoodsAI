# Рабочие задачи команды

## Следующий технический прогон — приоритетные доработки

Общая метка GitHub: `review:next-checkpoint`. Формирование очереди —
[GOV-007 #121](https://github.com/CRUDoshleps/GoodsAI/issues/121).
Метка не снимает блокировки и не меняет владельца: перед работой проверить
`status:ready`, зависимости и опубликовать отдельный claim.

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-007 | [#121](https://github.com/CRUDoshleps/GoodsAI/issues/121) | P1 | REVIEW | аналитик/координатор | urasha / Codex (сессия Влада) | `gov/gov-007-next-checkpoint-backlog` | claim 5de5aab; четыре новые задачи и общая метка опубликованы; существующие задачи включены без смены владельцев/статусов; индекс подготовлен к интеграции |
| DOCS-004 | [#122](https://github.com/CRUDoshleps/GoodsAI/issues/122) | P0 | READY | technical writer/QA | — | — | согласовать публичные REQUIREMENTS/RESULTS/reports и оба README с runtime; история и provenance сохраняются |
| EVAL-007 | [#123](https://github.com/CRUDoshleps/GoodsAI/issues/123) | P1 | REVIEW | evaluation/data | Codex (e345ee) | `eval/eval-007-frozen-baseline` | 20.10: comparison runner + hash-bound handoff; 445 synthetic/regression tests; frozen EVAL-006 bundle/audit не найдены локально/на VM, свежий real baseline не заявляется |
| CONF-004 | [#124](https://github.com/CRUDoshleps/GoodsAI/issues/124) | P1 | BLOCKED | архитектор/data/NLP | Codex (e345ee) | `eval/eval-007-frozen-baseline` | 20.10: offline plan/детерминированный train-only selection готовы; real inference ждёт #10/#5/#44 и owner mapping/family approval |
| EVAL-008 | [#125](https://github.com/CRUDoshleps/GoodsAI/issues/125) | P1 | BLOCKED | evaluation/ML/LLM | Codex (e345ee) | `eval/eval-007-frozen-baseline` | 20.10: offline plan + paired candidate error/resource diagnostics готовы; GLiNER files есть на VM; ждёт frozen #123 и разрешения exact packet/global budget; model calls 0 |

Порядок: #122 и #123 можно брать после claim; далее подтверждённый контракт
#10/#17 и матрица #35, разрешённая train-проекция #5 и пилот #124 через
существующий #44. Сравнение #125 ограничено development и не заменяет
независимые gates #6/#38/#40. Одиночный review-экран остаётся #19;
интеграционная приёмка — #29/#26, целевая VM — #82, release gate — #42.

Также метка кампании добавлена к существующим #5/#10/#16/#17/#19/#25/#26/#29/
#35/#36/#40/#42/#44/#82. Их приоритеты, статусы и владельцы сохранены.
Перед новой работой уточнить фактическую приёмку #44/#25: часть реализации
уже в main. Синхронизация GitHub/Gitea проверяется через source SHA и hashes
submission-manifest, а не равенство SHA двух репозиториев.

## Ревью прогона 2 — подготовка backlog

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-006 | [#97](https://github.com/CRUDoshleps/GoodsAI/issues/97) | P1 | DONE | аналитик/координатор | urasha / Codex (сессия Влада) | `main` | PR #102 merged 857115d; campaign backlog и метка опубликованы |
| QA-006 | [#98](https://github.com/CRUDoshleps/GoodsAI/issues/98) | P0 | DONE | QA/backend | urasha / Codex (сессия Влада) | `main` | PR #103 merged aee1bba; CI 6/6 SUCCESS; strict 83/83; mirror 39384309897 SUCCESS |
| LLM-007 | [#99](https://github.com/CRUDoshleps/GoodsAI/issues/99) | P0 | DONE | LLM/backend | urasha / Codex (сессия Влада) | `main` | PR #107 merged f8f4a59 по поручению Влада; CI 6/6 SUCCESS, 334+3 tests OK, внешний rules acceptance 83/83; issue закрыта |
| LLM-008 | [#100](https://github.com/CRUDoshleps/GoodsAI/issues/100) | P1 | DONE | LLM/MLOps | Глеб Алферов | `llm/llm-008-bounded-calls` | PR #112 merged 7aec082; Issue #100 closed; 1 МиБ, 120 с, 300 физических попыток в сутки |
| DOCS-003 | [#101](https://github.com/CRUDoshleps/GoodsAI/issues/101) | P1 | REVIEW | technical writer/QA | Глеб Алферов | `docs/docs-003-own-jsonl-quickstart` | проверенный запуск с собственным JSONL и объяснения ответов; QUICKSTART + RESPONSES, Linux-прогон в чистом клоне 7aec082 |

Связь с баллами и существующими задачами:
[план прогона 2](docs/reviews/2026-10-20_run_2_action_plan.md).
Метка `review:run-2` не снимает BLOCKED/BACKLOG у прежних задач.

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
| GOV-005 | [#81](https://github.com/CRUDoshleps/GoodsAI/issues/81) | P0 | DONE | product/QA/интегратор | Codex (tunaIT) | `main` | PR #85 merged; mirror dc3fbad OK; интеграция 208+3 tests, clean-run 11/11; качество N/A |
| GOV-004 | [#57](https://github.com/CRUDoshleps/GoodsAI/issues/57) | P1 | DONE | product/архитектор | Codex (tunaIT) | `main` | PR #63 merged f214985; mirror OK; 10 задач; BASE-002 остался DONE; дубли удалены |
| GOV-003 | [#34](https://github.com/CRUDoshleps/GoodsAI/issues/34) | P0 | DONE | product/аналитик/архитектор | Codex | `main` | PR #55 merged 0e5ac39; mirror OK; 20 задач; актуальные владельцы и статусы сохранены |
| SYNC-001 | — | P0 | DONE | интегратор | Codex | `main` | актуальный Gitea `main` перенесён в основной GitHub `main` |
| SEC-001 | [#3](https://github.com/CRUDoshleps/GoodsAI/issues/3) | P0 | READY | владелец доступов | — | — | заменить опубликованные VM, Gitea, Jupyter и LLM-секреты |
| ENV-001 | [#4](https://github.com/CRUDoshleps/GoodsAI/issues/4) | P0 | DONE | QA/MLOps | Codex (tunaIT) | `main` | PR #76 merged a10534a; mirror OK; VM audit принят; исходный 1d53dad, human quality N/A; новый deploy не выполнялся |
| BASE-003 | [#74](https://github.com/CRUDoshleps/GoodsAI/issues/74) | P0 | DONE | NLP/baseline | Codex (tunaIT) | `main` | PR #86 merged; mirror dc3fbad OK; интеграция 208+3 tests, clean-run 11/11; качество N/A |
| DATA-001 | [#5](https://github.com/CRUDoshleps/GoodsAI/issues/5) | P0 | READY | data engineer | — | — | воспроизводимая предобработка и свежий data manifest |
| EVAL-006 | [#91](https://github.com/CRUDoshleps/GoodsAI/issues/91) | P0 | DONE | evaluation/data | urasha / Codex (сессия Влада) | `main` | PR #95 merged 5711949; mirror 39313644701 SUCCESS; 3037 cards, catalog agreement F1 75.67%; 266+3 tests, clean-run 11/11; independent gold gates unchanged |
| EVAL-001 | [#6](https://github.com/CRUDoshleps/GoodsAI/issues/6) | P0 | BLOCKED | аналитик/разметчик | urasha / Codex (сессия Влада) | `main` | PR #71 принят; independent human gold/test не выполнен, нужны независимые разметчики |
| EVAL-002 | [#7](https://github.com/CRUDoshleps/GoodsAI/issues/7) | P0 | DONE | data/QA | urasha / Codex (сессия Влада) | `eval/eval-002-split-leakage` | PR #69 merged `c49540f`; filtered partition + quarantine; M2 reserve 40/40 checks OK |
| ART-001 | [#8](https://github.com/CRUDoshleps/GoodsAI/issues/8) | P0 | REVIEW | интегратор/аналитик | Codex (сессия Влада) | `release/art-001-prepared-delivery` | checkpoint: 2198 predictions, reviewed metrics, EDA, PDF, bundle verified |
| CONF-001 | [#9](https://github.com/CRUDoshleps/GoodsAI/issues/9) | P0 | IN_PROGRESS | архитектор | timur0o31 | `arch/conf-001-runtime-config` | 19.10.2026: конфигурация bounds/scores/limits, строгая валидация; defaults без изменения поведения |
| SPEC-001 | [#10](https://github.com/CRUDoshleps/GoodsAI/issues/10) | P0 | READY | product/аналитик | — | — | подтвердить формат выхода, обязательные поля и confidence |
| REL-005 | [#115](https://github.com/CRUDoshleps/GoodsAI/issues/115) | P0 | DONE | release engineer | Codex (e345ee) | `main` | PR #116 merged 741df14; publish 39421217155 SUCCESS, Gitea f15f99b; 154 файла, 369+3 tests, clean-run 11/11, внешний CLI/HTTP 83/83; VM не менялась |
| REL-001 | [#11](https://github.com/CRUDoshleps/GoodsAI/issues/11) | P0 | READY | release engineer | — | — | воспроизводимый выпуск проверенного GitHub SHA в Gitea |
| REL-002 | — | P0 | DONE | release engineer | Codex | `ops/rel-002-main-mirror` | GitHub `main` автоматически fast-forward публикуется в Gitea `main` |
| CONF-002 | [#24](https://github.com/CRUDoshleps/GoodsAI/issues/24) | P0 | DONE | архитектор | urasha / Codex (сессия Влада) | `main` | PR #109 merged b99512f по поручению Влада; CI 6/6 SUCCESS, 346+3 tests, acceptance 83/83, clean-run 11/11; issue закрыта |
| LLM-003 | [#25](https://github.com/CRUDoshleps/GoodsAI/issues/25) | P0 | REVIEW | LLM/backend | Глеб Алферов | `llm/llm-003-evidence-first-fallback` | evidence-first fallback через шлюз хакатона; opt-in `--llm`, pre-router, политика данных и бюджета 19.10 закреплена кодом; живой trace — `llm-trace` на VM |
| OPS-001 | [#26](https://github.com/CRUDoshleps/GoodsAI/issues/26) | P0 | READY | MLOps/security | — | — | безопасные логи и границы temp/pickle |
| ART-002 | [#27](https://github.com/CRUDoshleps/GoodsAI/issues/27) | P0 | DONE | release/docs | Codex (tunaIT) | `main` | PR #87 merged; mirror dc3fbad OK; интеграция 208+3 tests, clean-run 11/11; качество N/A |
| QA-002 | [#29](https://github.com/CRUDoshleps/GoodsAI/issues/29) | P0 | READY | QA | — | — | регрессия полного review-remediation сценария |
| REL-003 | [#30](https://github.com/CRUDoshleps/GoodsAI/issues/30) | P0 | BLOCKED | интегратор | — | — | выпуск исправлений review; ждёт подзадачи |
| ART-003 | [#32](https://github.com/CRUDoshleps/GoodsAI/issues/32) | P0 | DONE | release/QA | Codex (сессия Влада) | `release/art-003-artifact-bundle` | offline smoke/assemble/verify, 100 + 3 tests OK |
| DOCS-001 | [#28](https://github.com/CRUDoshleps/GoodsAI/issues/28) | P1 | DONE | technical writer | Codex (сессия Влада) | `docs/docs-001-reproducible-instructions` | PR #31 merge `55378f1`, зеркало Gitea успешно |
| BASE-001 | [#21](https://github.com/CRUDoshleps/GoodsAI/issues/21) | P1 | DONE | NLP/baseline | urasha / Codex (сессия Влада) | `main` | PR #105 merged 71cae4b; CI 4/4 SUCCESS; 9 model FN→TP on development, без новых FP/lost TP |
| LLM-001 | [#12](https://github.com/CRUDoshleps/GoodsAI/issues/12) | P1 | DONE | LLM engineer | — | — | покрыто LLM-003 PR #90 и LLM-008 PR #112; Issue #12 closed |
| LLM-002 | [#13](https://github.com/CRUDoshleps/GoodsAI/issues/13) | P1 | BLOCKED | LLM engineer/аналитик | — | — | сравнение доступных моделей; ждёт EVAL-001 и лимит бюджета |
| ROUTE-001 | [#14](https://github.com/CRUDoshleps/GoodsAI/issues/14) | P1 | BLOCKED | архитектор/ML | — | — | измеряемый rules → model/LLM → verifier router; ждёт EVAL-001 |
| VER-001 | [#15](https://github.com/CRUDoshleps/GoodsAI/issues/15) | P0 | DONE | NLP/QA | urasha / Codex (сессия Влада) | `main` | PR #104 merged d9e279a; CI 4/4 SUCCESS; имена/материал не цвет, LLM relation guard; QA-001 21/21 |
| ML-001 | [#16](https://github.com/CRUDoshleps/GoodsAI/issues/16) | P1 | REVIEW | ML engineer | Codex (tunaIT) | `main` | PR #80 merged 468e35e; opt-in prototype принят; default/human quality gate остаётся открыт |
| API-001 | [#17](https://github.com/CRUDoshleps/GoodsAI/issues/17) | P1 | READY | backend | — | — | финальный batch/API-контракт и диагностика ошибок |
| QA-001 | [#18](https://github.com/CRUDoshleps/GoodsAI/issues/18) | P1 | DONE | QA | Codex (tunaIT) | `main` | PR #88 merged; mirror dc3fbad OK; интеграция 208+3 tests, clean-run 11/11; качество N/A |
| PRODUCT-001 | [#19](https://github.com/CRUDoshleps/GoodsAI/issues/19) | P1 | BACKLOG | product/UX | — | — | экран review с evidence и решениями оператора |
| ACTIVE-001 | [#20](https://github.com/CRUDoshleps/GoodsAI/issues/20) | P2 | BLOCKED | ML/product | — | — | active learning из правок; ждёт рабочего review-сценария |
| QA-003 | [#47](https://github.com/CRUDoshleps/GoodsAI/issues/47) | P1 | DONE | QA | Codex (e345ee) | `main` | PR #73 merged ba392d6; mirror OK; 11 свойств quick/nightly; schema/Decimal regressions; CI OK |
| ENV-002 | [#41](https://github.com/CRUDoshleps/GoodsAI/issues/41) | P0 | DONE | MLOps/QA | Codex (e345ee) | `main` | PR #72 merged 50101a7; mirror OK; locked clean-run, Linux/Windows CI и repeat OK; 11 этапов |
| DOCS-002 | [#52](https://github.com/CRUDoshleps/GoodsAI/issues/52) | P1 | DONE | technical writer | Codex (e345ee) | `main` | PR #77 merged 1e922aa; author review по поручению пользователя; 135 + 3 tests, smoke/verify; mirror OK |
| BASE-002 | [#64](https://github.com/CRUDoshleps/GoodsAI/issues/64) | P1 | DONE | NLP/baseline | Codex (e345ee) | `main` | PR #75 merged 61b9260; review fixes 0693d21; 135 + 3 tests; mirror OK; selector not integrated |

## 20 улучшений по оценке 19 октября

Эти задачи созданы в рамках `GOV-003`. Их актуальные статусы и владельцы приведены ниже. `READY`
означает, что задачу можно отдельно взять по обычному claim-процессу;
`BLOCKED` и `BACKLOG` требуют указанных зависимостей. Подробная связь с
критериями и критический путь находятся в
[`docs/reviews/2026-10-19_score_improvement_backlog.md`](docs/reviews/2026-10-19_score_improvement_backlog.md).

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SPEC-002 | [#35](https://github.com/CRUDoshleps/GoodsAI/issues/35) | P0 | BLOCKED | product/QA | — | — | исполняемая матрица всех обязательных сценариев; зависимости: SPEC-001 |
| DATA-002 | [#36](https://github.com/CRUDoshleps/GoodsAI/issues/36) | P0 | BLOCKED | data engineer/security | — | — | seller attributes без target leakage и с provenance; зависимости: SPEC-001, DATA-001 |
| VER-002 | [#37](https://github.com/CRUDoshleps/GoodsAI/issues/37) | P0 | DONE | QA/backend | urasha / Codex (сессия Влада) | `qa/ver-002-common-verifier` | PR #118 принят 20.10.2026, merge 0a1d134; claim 8a55d81; общий gate rules/LLM/cache/experimental GLiNER; CI 6/6; проверен вместе с ARCH-001: 402+3 tests, external 83/83, clean-run 11/11; reviewed development без регрессии; #10 остаётся открытой |
| EVAL-003 | [#38](https://github.com/CRUDoshleps/GoodsAI/issues/38) | P0 | BLOCKED | аналитик/разметчик | — | — | независимый blind-пакет доказательств качества; зависимости: EVAL-001, EVAL-002 |
| EVAL-004 | [#39](https://github.com/CRUDoshleps/GoodsAI/issues/39) | P0 | BLOCKED | ML/аналитик | — | — | калибровка и безопасные auto-accept thresholds; зависимости: EVAL-003, CONF-001/002 |
| EVAL-005 | [#40](https://github.com/CRUDoshleps/GoodsAI/issues/40) | P0 | BLOCKED | аналитик/ML/LLM | — | — | Pareto-сравнение качества, coverage, latency и цены; зависимости: EVAL-003, model stages |
| REL-004 | [#42](https://github.com/CRUDoshleps/GoodsAI/issues/42) | P0 | BLOCKED | release engineer/QA | — | — | gate точного SHA и проверенных артефактов; зависимости: ART-003, ENV-002, QA-002 |
| ARCH-001 | [#43](https://github.com/CRUDoshleps/GoodsAI/issues/43) | P1 | DONE | архитектор | urasha / Codex (сессия Влада) | `arch/arch-001-pipeline-composition` | PR #119 принят после #118, merge 88a216b; claim ff89c14; сохранены интерфейсы Тимура e59c175; shared composition CLI/API/trace; 402+3 tests, CI 6/6, external 83/83, clean-run 11/11; 40 reviewed development без изменений; Gitea 02b0151, workflow 39427937162 SUCCESS; SPEC-001 #10 остаётся открытой |
| CONF-003 | [#44](https://github.com/CRUDoshleps/GoodsAI/issues/44) | P1 | IN_PROGRESS | архитектор/NLP | timur0o31 | `arch/conf-003-train-registry` | 19.10.2026: по поручению Тимура — opt-in train-only registry candidate; stacked CONF-001 + ARCH-001; полная приёмка остаётся зависимой от SPEC-001/CONF-002 и разрешённого train split |
| ROUTE-002 | [#45](https://github.com/CRUDoshleps/GoodsAI/issues/45) | P1 | BLOCKED | архитектор/QA | — | — | детерминированная fallback state machine; зависимости: ROUTE-001, LLM-003, VER-002 |
| API-002 | [#46](https://github.com/CRUDoshleps/GoodsAI/issues/46) | P1 | BLOCKED | backend | — | — | идемпотентный batch с checkpoint и resume; зависимости: API-001, OPS-001 |
| QA-004 | [#48](https://github.com/CRUDoshleps/GoodsAI/issues/48) | P1 | BLOCKED | QA/MLOps | — | — | concurrency и failure-injection отчёт; зависимости: API-002, ROUTE-002, OPS-001 |
| OPS-002 | [#49](https://github.com/CRUDoshleps/GoodsAI/issues/49) | P1 | BLOCKED | MLOps/аналитик | — | — | безопасные quality/latency/cost метрики; зависимости: CONF-002, ROUTE-002, API-002 |
| PRODUCT-002 | [#50](https://github.com/CRUDoshleps/GoodsAI/issues/50) | P1 | BLOCKED | product/UX/backend | — | — | пакетная очередь проверки оператором; зависимости: PRODUCT-001, API-002, VER-002 |
| ART-004 | [#51](https://github.com/CRUDoshleps/GoodsAI/issues/51) | P1 | BLOCKED | аналитик/release | — | — | человеко-читаемый отчёт с источником каждой цифры; зависимости: ART-003, EVAL-005, OPS-002 |
| PRODUCT-003 | [#53](https://github.com/CRUDoshleps/GoodsAI/issues/53) | P2 | BACKLOG | product/аналитик | — | — | качество продавцов и источников без смешения ошибок; зависимости: PRODUCT-002, ACTIVE-001, OPS-002 |
| PRODUCT-004 | [#54](https://github.com/CRUDoshleps/GoodsAI/issues/54) | P1 | BLOCKED | product/аналитик | — | — | проверяемый пилот, экономика и evidence для защиты; зависимости: EVAL-005, OPS-002, ART-004 |

## Дополнительные задачи runtime и интерфейса

Заведены в GOV-004 для команды tunaIT. Описание и критерии:
[план задач](docs/reviews/2026-10-19_runtime_improvement_tasks.md).
Ниже приведены актуальные состояния функций; BLOCKED указывает на перечисленные
в Issues зависимости. Начинать реализацию можно только после их закрытия,
согласования контракта и отдельного опубликованного claim.

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ML-002 | [#58](https://github.com/CRUDoshleps/GoodsAI/issues/58) | P1 | BLOCKED | ML/аналитик | — | — | Предлагать категорию по тексту с безопасным отказом; зависимости в Issue |
| LLM-004 | [#59](https://github.com/CRUDoshleps/GoodsAI/issues/59) | P1 | REVIEW | LLM/backend | Codex (e345ee) | `main` | 20.10.2026: PR #128 merged; exact cache v2, TTL/fingerprint и thread/process single-flight; 6 tests; representative keep gate #59 остаётся |
| PRODUCT-005 | [#60](https://github.com/CRUDoshleps/GoodsAI/issues/60) | P1 | REVIEW | product/backend | Codex (e345ee) | `main` | 20.10.2026: PR #133 merged; dictionary UI/RBAC/impact/immutable publish/CAS/rollback; 20 synthetic proposals, browser smoke; UX/registry integration остаются |
| OPS-003 | [#61](https://github.com/CRUDoshleps/GoodsAI/issues/61) | P1 | REVIEW | MLOps/аналитик | Codex (e345ee) | `main` | 20.10.2026: PR #131 merged; frozen aggregate drift, Wilson/JS, redaction/hysteresis; 6 tests; OPS-002 и calibration остаются |
| PRODUCT-006 | [#62](https://github.com/CRUDoshleps/GoodsAI/issues/62) | P2 | REVIEW | product/аналитик | Codex (e345ee) | `main` | 20.10.2026: PR #132 merged; severity/age/rare/audit ranking + local session audit; 5 tests; PRODUCT-002/UX benchmark остаются |

В существующих задачах [ML-001 #16](https://github.com/CRUDoshleps/GoodsAI/issues/16),
[LLM-003 #25](https://github.com/CRUDoshleps/GoodsAI/issues/25),
[EVAL-005 #40](https://github.com/CRUDoshleps/GoodsAI/issues/40) и
[PRODUCT-002 #50](https://github.com/CRUDoshleps/GoodsAI/issues/50) уточнена приёмка.
Их владельцы, статусы и claims не менялись; второй encoder/router/review UI
отдельными задачами не заводился.

## Задачи выбора фрагментов, контекста и повторной обработки

BASE-002 уже принят; LLM-005 и LLM-006 выполняются после
готовности зависимостей. Аудит повторов выполняется в LLM-004 #59 без нового
Issue. ARCH-002 и PRODUCT-007 не задерживают существующие P0.

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LLM-005 | [#65](https://github.com/CRUDoshleps/GoodsAI/issues/65) | P1 | REVIEW | LLM/NLP | Codex (e345ee) | `main` | 20.10.2026: PR #130 merged; client enum IDs, source-only Candidate/shared gate; 5 tests; E1 recall/F1/token gate остаётся |
| LLM-006 | [#66](https://github.com/CRUDoshleps/GoodsAI/issues/66) | P1 | REVIEW | LLM/NLP | Codex (e345ee) | `main` | 20.10.2026: PR #129 merged; raw blocks/full fallback и отказ по budget; 4 tests; E3 независимый keep gate остаётся |
| ARCH-002 | [#67](https://github.com/CRUDoshleps/GoodsAI/issues/67) | P2 | BLOCKED | архитектор/backend | — | — | Полный private snapshot кандидатов и новый decision diff; ждёт #24, #37, #43, #44 |
| PRODUCT-007 | [#68](https://github.com/CRUDoshleps/GoodsAI/issues/68) | P2 | BLOCKED | product/backend | — | — | Нейтральный запрос уточнения после проверенного source gap; ждёт #10, #37, #50 |

У каждой задачи есть шаги, эксперимент, keep/drop и границы. READY относится
к изолированному индексу и synthetic-проверкам; это не разрешение на внешние
model calls или использование test. Начало реализации требует отдельного claim
после публикации согласованного индекса. Автоматическая отправка вопросов
продавцам не входит в PRODUCT-007.

Уточнены fingerprint и предварительный аудит в [#59](https://github.com/CRUDoshleps/GoodsAI/issues/59),
а также независимая calibration и риск среди принятых значений в
[#39](https://github.com/CRUDoshleps/GoodsAI/issues/39). Владельцы и статусы сохранены.

## Финальная приёмка — GOV-005

Порядок исполнения и критерии: [FINAL_ACCEPTANCE_PLAN](docs/FINAL_ACCEPTANCE_PLAN.md).
Implementation существующих задач и их claims не перезапускаются. Приоритет
PRODUCT-001 #19 повышен до P1 для рабочего одиночного UI. ENV-002 #41 уже
merged; независимый прогон конкретного candidate SHA выделен отдельно.

| ID | Issue | P | Статус | Роль | Исполнитель | Ветка | Результат / блокер |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ENV-003 | [#82](https://github.com/CRUDoshleps/GoodsAI/issues/82) | P0 | BLOCKED | независимый QA/MLOps | Codex (tunaIT), технический прогон | `gov/gov-005-final-acceptance` | SHA 3ad28e4: VM 11/11, 160+3 tests, HTTP 22/22, repeat equal; НЕ финальная приёмка: нет независимого исполнителя/официального API, дефекты #74/#15 |
| QA-005 | [#83](https://github.com/CRUDoshleps/GoodsAI/issues/83) | P1 | BLOCKED | независимый QA/product | Codex (tunaIT), readiness audit | `gov/gov-005-final-acceptance` | Producer 3ad28e4: root JSON, routes / /health /predict; UI/save/reload/export отсутствуют; rehearsal NOT RUN; ждёт #19/#17/#37 и независимого участника |

Этап A EVAL-005 #40: правила против узкого GLiNER из PR #80 на независимых
данных #6/#38; не ждёт отсутствующую LLM или полный router. Широкая матрица
остаётся этапом B. 85.07% development agreement не является independent gate.

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

### GOV-003 — backlog улучшения оценки

- Начато: 2026-10-19.
- Claim commit: `864730a`.
- Основание: детализация баллов технического чекпоинта и пустой блок качества.
- Scope: создать ровно 20 задач улучшения и не начинать их реализацию.
- Результат: Issues #35–#54 с типом, приоритетом, статусом, шагами,
  зависимостями, приёмкой и связью с критерием оценки; задачи без исполнителей.
- Расширенное заключение дополнительно распределено по #24, #25, #26, #35,
  #41, #42, #44, #46, #48, #50 и #51: dependencies, `BaseException`,
  network FS locks, pickle, защита API, production config и operator workflow.
- Анализ: `docs/reviews/2026-10-19_score_improvement_backlog.md` содержит
  критический путь, формулы метрик, release evidence и порядок работ.
- Проверка: 20/20 Issue ID совпадают с таблицей; у каждого ровно один label
  `type:*`, `priority:*`, `status:*`; локальные Markdown-ссылки существуют.
- Runtime, данные, модели и test split не изменялись.

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

Результат 19.10.2026: [Linux-протокол и диагностика](docs/reviews/2026-10-19_vm_quality_audit.md).
Claim `3001fee`, ветка `env/env-001-vm-quality-audit`, владелец Codex (tunaIT).
На clean `1d53dad`: 119 + 3 tests, pip check, demo 6/6; frozen runtime HTTP
64/64; 2171 SKU, три повтора идентичны frozen `1754970`. Действующий сервис
не перезапускался; оригинальный checkout `48b45dc` сохранён для rollback.
Штатный inventory требует лишний clicks: clean real-data путь имеет blocker
#5, применён отдельно описанный inventory двух настоящих источников.
AI-reference P96,3/R70,3/F181,3 — не human accuracy: 425/480 judged,
canonicalization исправлена после первого сравнения, test не использовался.
Создана BASE-003 #74 READY/P0; VER-001 #15 повышена до P0; уточнены
#5/#6/#10/#17/#21/#25/#38. Runtime fixes и независимый gold не выполнены.
REVIEW означает готовность протокола аудита, не снятие release blockers.

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

**Уточнение Влада 19.10.2026:** текущий этап — ещё 20 новых development-карточек,
AI-assisted draft с последующей проверкой Владом, как в M2. Reserve 40 не раскрывать.
Сохранить independent-reference=false, без новых P/R/F1 до human-подтверждения.
Предыдущее требование двух людей относится к будущей независимой оценке, а не к
этому development-инкременту. Issue #6 не закрывать только подготовкой draft.
Development tooling `ffa35ca`: 20 карточек/120 полей, 0 human-reviewed; форма
`outputs/evaluation/development-review-20261019-v2-ai/development.review.md`.
134 основных + 3 reader tests — OK; replay selection/draft deterministic,
EVAL-002 sources unchanged, reserve закрыт. REVIEW текущего инкремента — проверка
draft Владом и code review; независимая оценка остаётся незавершённой.

Feedback Влада получен для всех D21–D40, с явным подтверждением неуказанных полей.
Уточнение номера: G относится к D27, D25 memory подтверждена. Reviewed версия
human-v2: 20 карточек/120 labels; 82 present/27 absent/4 ambiguous/7 unjudgeable;
2 manual-contextual corrections D27, independent-reference=false. D24 неверная
категория, phone schema unjudgeable; runtime/category policy не менялась.
Новый прогон P/R/F1 не выполнялся. Не закрывать независимый этап этой записью.

Claim `fab562f`, инструменты `257fe1f`, 19.10.2026. [Протокол](docs/HUMAN_GOLD.md),
[инструкция](docs/HUMAN_GOLD_GUIDELINES.md). 128 основных + 3 reader tests — OK;
offline HTML проверен только на synthetic. Реальный metadata-only пакет:
40 карточек/240 пустых полей, два запуска byte-identical, test-тексты не раскрыты.
BLOCKED для полной приёмки: Влад пока единственный разметчик, второго и
adjudicator нет, итоговый метод не заморожен, human answers/agreement/gold отсутствуют.
Следующее решение: сохранить reserve до freeze или оценить только текущий rules;
AI-assisted продолжение на development не закрывает требование двух людей.
Инструменты могут пройти code review отдельно, Issue #6 не закрывать по их merge.

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

- Начато: 19.10.2026. Исполнитель: `timur0o31`.
- Ветка: `arch/conf-001-runtime-config`; Issue: #9.
- Claim публикуется отдельным commit до начала реализации.
- Claim опубликован: `3cb7560`. Реализация: versioned runtime config, strict
  loader, общие bounds/scores/windows для rules/verifier и CLI/API.
- Проверки macOS/Python 3.14.8: 123 + 3 tests, demo 6/6; 15 synthetic
  before/after предсказаний совпали по значениям, evidence и решениям.
- LLM/auto_accept выключены. Реальные данные, независимый test, VM и
  зависимости не менялись; документация: `docs/CONFIGURATION.md`.

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

19.10.2026: по поручению пользователя выполнен development screening и добавлен
отдельный opt-in `HybridExtractor`; первый этап независимой приёмки ниже не
пропущен для штатного включения. Широкий brand/model fallback отклонён; после
development feedback сохранён только однословный brand. Основной CLI/API и
auto_accept не меняются. Протокол и ограничения: [EXPERIMENTAL_GLINER](docs/EXPERIMENTAL_GLINER.md).

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

## GOV-004 — дополнение backlog

- Claim `35c6b5b` опубликован до правок документов; ветка `gov/gov-004-runtime-improvement-tasks`.
- Продолжение планирования: claim `84f596e` опубликован до дополнения документов.
- Добавлены десять отдельных задач #58–#62 и #64–#68 с experiment/keep-drop, зависимостями и приёмкой.
- Уточнены #16, #25, #39, #40, #50, #59 без смены их владельцев/статусов.
- BASE-002 готова к изолированному исполнению, остальные новые функции ждут перечисленных зависимостей.
- Runtime, модели, test reserve, реальные данные и VM не менялись.
- Дубликаты задач #35–#54 не создавались; PR #55 и чужие claims не изменены.

## CONF-003: train-only feature candidate — 19.10.2026

Исполнитель timur0o31; claim fef035b, ветка arch/conf-003-train-registry,
база CONF-001 e0b746f + ARCH-001 e59c175 + upstream 977c5ed.
[DONE — feature candidate] Конфиг v2 с registry v1, fill >=50%, train-only
словари, key:value, пары и размеры с выученными ролями; общие verifier и
CLI/API; 238 основных + 3 reader tests OK на macOS/Python 3.14.8. Default две категории и auto_accept/LLM off сохранены.
[PLAN] Полная приёмка CONF-003 остаётся заблокированной разрешённым train/
split/traffic, schema mapper, согласованием категорий и review. Реальные
топ-30 и качество не подтверждены. GitHub PR/labels требуют публикации через
доступный пользователю GitHub-интерфейс. До этого статус IN_PROGRESS,
а не REVIEW/DONE. Подробности: docs/CATEGORY_REGISTRY.md.
ARCH-001 также остаётся feature candidate с открытыми условиями принятия.

### CONF-003: продолжение оценки; зависимость PR #92

По поручению Тимура продолжается та же ветка arch/conf-003-train-registry.
Добавлены явный hash-bound schema mapper и private validation report, при этом
обязательные unlabelled поля остаются unjudgeable. Исправлен evaluator FN для
правильного неизвестного train-словарю значения. Source-independent inference
не получает reference/params. Это feature candidate, не реальные метрики;
полная приёмка и independent quality gates не закрыты. Команды и ограничения:
docs/CATEGORY_REGISTRY.md. По GitHub metadata PR #92 содержит CONF-001, а не CONF-003. Отдельные
ARCH-001/CONF-003 PR через подключение не созданы (GitHub 403 FORBIDDEN).
Review/merge и перевод задач в DONE не выполнялись. Проверки: 247 основных + 3 reader
tests OK, macOS/Python 3.14.8; 9 evaluation tests OK на Python 3.12.14.
