# 21.10.2026: EVAL-009 — model code regression исправлена, human review pending

Issue #137, claim `0b84069`, ветка `eval/eval-009-model-adjudication`. Получены
приватные frozen артефакты PR #136 read-only SFTP, без изменения ВМ/сервиса/ветки
коллеги. Проверены все inventory hashes и source report SHA публичного агрегата.
Набор: 2974 карточки / 1250 families, прежний development_feedback, reserve закрыт.

Подготовлены M01–M26 по всем model new_fp/lost_tp. AI draft написан по тексту до
чтения catalog/prediction values; при этом selection уже использует predictions.
Предварительно 20 catalog mismatches объясняются включёнными в catalog model
цветом/материалом/памятью/состоянием/SIM; подтверждение Владислава ещё нужно.
В 6 lost matches verifier ошибочно отвергал цельные коды из-за unit-like suffix
или brand-like prefix. Исправление `31c4590`, runtime candidate `185e053`:
границы measurement tokens; узкое разрешение дефисного кода с brand-like prefix
только при существующем полном model span. Shared verifier 1.2; contract,
confidence, decisions и прочие attribute rules не менялись.

На тех же frozen input/reference/config: 6 new catalog TP, 0 new FP / lost TP;
другие атрибуты без изменений. Есть седьмой новый model при catalog conflict:
не скрыт, добавлен post-prediction supplement M27. Общий catalog F1
0,759222 → 0,759604, model F1 0,617551 → 0,622030. Это noisy agreement,
не independent human quality. Cold/warm predictions совпали в каждом runtime.

Проверки: 486 unittest + 3 reader PASS, pip check; targeted model 18,
development_review 9, adjudication 5, verifier 22 PASS. Синтетический positive
регрессии воспроизводился до фикса в четырёх subtests. Текущая форма:
`outputs/eval010/model-adjudication-20261021/draft-all27-v2/review.md`.
Human reviewed=0, human P/R/F1=N/A. Используется existing exact-label validator
и feedback workflow с сохранением AI-origin и prediction-selection provenance.
Полный внутренний протокол: `docs/research/eval009_model_adjudication.md`.

Влад выбрал AI-assisted review без дополнительных участников. Независимая
приёмка #6/#38 этим не выполнена; не заявляется и не подменяется development.
#137 ждёт явных ответов M01–M27, #149 остаётся незавершённой. Код/подготовка
поставляются PR #154 отдельно от human acceptance. Matrix 17/17, внешние 103/103
и verify PASS; положительный новый код отдельно проверен через CLI/API.
PR #136 не сливался,
новых model calls/расходов и deployment не выполнялось.

# 21.10.2026: EVAL-010 — доступный инкремент merged, полное завершение BLOCKED

Issue #149, claim `d2f5321`, ветка `eval/eval-010-quality-audit` от main
`7542d00`, runtime candidate `2246425`. Учтён merged PR #150; его evaluator/
human workflow/quality tool не дублируются. Оценённый организаторами SHA
остаётся unknown: скриншот 4,87/5 не связывается произвольно с текущим code.

Найден и воспроизведён дефект: LLM мог заполнить power_w=300 из «Мощность
подогрева 300 Вт», хотя rules отбрасывает вспомогательный режим. Общий numeric
gate теперь переиспользует те же `excluded_quantity_context` для мощности,
дополнительного экрана и объёма. Не добавлены новые units/thresholds/decisions;
обычный LLM fallback «Потребляет 2200 Вт» сохраняется. `candidate-verifier-1.1`,
reason `verifier_unsupported_value` уже существовал; model rules не менялись.

В существующую matrix добавлен внешний auxiliary-power case; SCN-015 связывает
verifier/config. Offline JSON содержит исполненные test_ids; пропажа обязательного
контроля даёт failure независимо от остальных зелёных тестов. Новый runner не
создавался. Таблица QV/QE в VERIFIER связывает поведение/причины со сценариями,
тестами и hash-bound артефактами; README/RESULTS/SCENARIO_MATRIX обновлены.
Полный внутренний аудит — `docs/research/eval010_quality_audit.md` (не для Gitea).

Фактические проверки: 20 verifier, 64 LLM, 13 matrix harness tests PASS;
полная Windows-регрессия **479 tests PASS** (149,712 s), reader 3/3, pip check.
Отдельный committed matrix seed 20261021: 17/17 executable групп, 103/103 внешних
CLI/socket checks без packaged examples и verify PASS. Пробелы остаются:
4 not_implemented, 7 not_verified, 1 unknown; complete_case_evidence=false.
До/после source snapshot новый synthetic defect test воспроизводит ошибку
на базе и проходит на candidate; существующие 12 rules probes — 12/12,
false_values=0, missed_true_facts=0, lost_true_facts=0 в обеих версиях.

Приватные synthetic outputs: `outputs/eval010/scenarios-2246425/`,
`outputs/eval010/auxiliary-before-after-2246425/`, `outputs/eval010/rules-before-after-2246425/`.
Исторические reviewed/silver цифры не менялись. Real/independent P/R/F1 = N/A.
Полная приёмка #149 **BLOCKED #6/#38/PR #136/#137**. Коллега продолжает #136,
его код/пакеты не менялись. Нет reserve/test просмотра или inference, model API,
расходов, полного EDA, новых категорий, калибровки или обновления VM.
По последующему поручению Владислава PR #152 принят в main, merge
`ce4a00d248501c7e323e077f66825761ac0394df`. Все 6 CI checks на final head
`38438e0` SUCCESS; дерево merge совпало с протестированным. Весь #149 остаётся
OPEN/BLOCKED; это завершение доступного инкремента, не независимой оценки.
Автоматическая публикация этого merge в Gitea завершилась SUCCESS.

# 21.10.2026: EVAL-003 — подготовка quality-пакета merged, финальная приёмка BLOCKED

Issue #38, подготовительный инкремент для #149 по поручению Владислава;
claim `87887ce`, ветка `eval/eval-003-quality-evidence`. Реализован
`scripts/research/quality_evidence.py`: prepare создаёт metadata/spec и
blocked report с P/R/F1=null без чтения реальных данных. Assemble принимает
уже готовые sealed human A/B/reference и сохранённые predictions, повторяет
существующие reconcile/finalize, audit verification и evaluator. Собственных
форм, разметки, извлечения или формул P/R/F1 не добавлено.

Проверяются exact SKU/text/evidence, raw/config/effective policy/code hashes,
clean producer и один frozen method commit/config; reference должен побайтно
совпасть с replay human answers/signoff. Нет hybrid — явный not_run. Ошибочные
строки не исчезают: unprocessed, FN и lost TP сохраняются. Есть per-attribute/
category/category×attribute, exclusions/agreement и private paired changes.
Verify проверяет inventory/hashes и повторяет evaluator/paired transitions
на captured input, с контролем версии evaluator/runtime. Доверенный внешний
manifest SHA допускается отдельно; checksum не доказывает подлинность людей.

15 новых synthetic tests PASS: blocked/no data, hash/signoff/reference tamper,
freeze/audit/producer mismatch, text/SKU/failed rows, missing methods, repeat и
ложные метрики даже после обновления внутренних hashes. CI добавлен в
Linux/Windows acceptance workflow. CLI prepare → verify и assemble пустого
template → verify реально проверены в новых локальных outputs: blocked,
independent_reference=false, metrics_recomputed=false. Pip check и diff check PASS.
Полная финальная Windows-регрессия: **475 tests PASS** (145,099 s), отдельный
research reader suite 3/3 PASS. Это проверки кода на synthetic fixtures,
не реальные независимые метрики качества и не новый VM-прогон.
README/submission README, HUMAN_GOLD и EVALUATION описывают команды, provenance,
границы и fail-closed поведение; исправлены исторические общие заявления о
якобы отсутствующей LLM-интеграции.

**Весь #38 не завершён:** независимый human gold #6 отсутствует, реальных
independent P/R/F1 нет. Даже сборка с gold требует внешней проверки процесса
и заморозки model/policy artifacts, автоматическая final acceptance не выдаётся.
Нет открытия/разметки реального reserve, новых predictions по test, model API,
расходов, calibration/auto_accept, изменений runtime v0.1, gold или VM.
PR #150 принят в main по поручению Владислава, merge
`467418ed3871597320c5170c77e0bc9e6c5b7148`. Все 6 CI checks на final head
`181de65` SUCCESS; дерево merge совпало с протестированным. После commit
9 submission tests PASS, allowlist export 189 файлов без private data/outputs
и внутренних статусов. Весь #38 остаётся OPEN/BLOCKED, #149 — частично blocked.
Обновление VM не выполнялось.

# 20.10.2026: OPS-004 — DONE, закрытие SQLite-ресурсов QueueAudit

Issue #142, claim `69b2c2c`, ветка `fix/ops-004-sqlite-lifecycle`. Операции
init/begin/finish/report используют общий локальный transaction context:
курсор закрывается перед commit/rollback, соединение закрывается и при
ошибках SQL, получения курсора или commit. Begin/finish, уникальность,
неизменяемость завершённых сессий и формат БД/отчётов сохранены.

PR #145 принят в main, merge `8cad64312cd3a198a316d3fac9bd0ce54ab49f00`;
Issue #142 закрыта с status:done. Все 6 CI checks на final head `8c8772c`
SUCCESS, включая audit suite и внешние сценарии на Windows/Linux.
Дерево merge совпало с протестированным деревом. Экспорт 185 файлов проверен;
внутренние документы статуса и реальные данные в состав сдачи не входят.

11 audit tests PASS, включая 6 новых: сильные ссылки на handles исключают
маскировку утечки сборщиком мусора; проверены немедленные move/delete файла,
duplicate begin, повторный/неизвестный finish, rollback при RuntimeError/
KeyboardInterrupt/SystemExit, отложенный FK commit failure и SQL/cursor errors.
Полная Windows-регрессия с PYTHONUTF8=1: **451 tests PASS**, прежнего WinError 32
больше нет. Skip/xfail, gc.collect, sleeps и retries удаления не добавлялись.
Cross-platform audit suite добавлен в CI Linux/Windows.

README и команды не менялись: поправка не требует нового способа запуска.
Обновлены эксплуатационное REVIEW_PRIORITY и текущая оговорка SCENARIO_MATRIX;
SCN-109 остаётся непокрытой общей очередью #19/#50, но SQLite-дефект больше
не указан как её текущий блокер. Новых API/JSON полей, конфигурации, метрик
качества, изменений gold/датасетов, model calls или действий на VM нет.

# 21.10.2026: DATA-001 — DONE, воспроизводимая text-only подготовка

Issue #5, claim `5d705ed`, ветка `data/data-001-reproducible-prepare`.
PR #147 принят в main, merge `ee1c4f8f22603f45b0feb8e91635514f22d9caaf`;
Issue #5 закрыта с status:done. Final head `3023090`, CI 6/6 SUCCESS,
дерево merge совпало с проверенным деревом. Экспорт 187 файлов и ссылки
проверены, внутренние документы и реальные данные исключены. Сравнение
merge-tree с PR #136 не добавило новых конфликтующих файлов: только прежний
PROJECT_STATUS конфликт, существовавший до DATA-001.
Inventory разделяет text-only (skus + descriptions) и analytics (+clicks),
проверяет существующий reference по флагу и запрещает перезапись. CLI default
inventory/prepare пути согласованы. Prepare-v2 проверяет схему/ID/join/hash,
фиксирует accounting и публикует только полный новый каталог. Данные Unicode/
HTML сохраняются, targets не попадают в Product. Результат v0.1 не меняется.

Одна команда `scripts/research/prepare_dataset.py` повторяет prepare и связывает
его с проверенным frozen EVAL-002 audit, без нового grouping/split/predictions.
`--verify` сверяет источники, выходы и hash-связь с exact/normalized/near/family/
exposure quarantine. Нет аудита или изменился JSONL — handoff останавливается.
Обычный prepare по-прежнему доступен, но имеет split_status=not_checked.

На локальных реальных источниках: 10324 строки (7988/2336), 4244 descriptions,
6080 title-only, 343 mismatch. JSONL/provenance при повторе идентичны; input SHA
`68875ae2...b70fe3` совпал с frozen audit. Eligible 3411/quarantine 6913,
reserve не материализован для просмотра или inference, разбиения не менялись.
9 новых tests с подслучаями PASS: profiles/legacy inventory, schema/null/joins,
source tamper, Unicode/HTML, target exclusion, staging failure, repeat/CLI и
связь с реальным split-auditor. Целевой data suite 11/11 PASS, полная финальная
Windows-регрессия 460/460 PASS, research reader 3/3, pip check PASS.
Тесты подготовки прошли Windows/Linux CI. Реальные 10324 строки с тем же
input SHA также воспроизведены из чистого git archive committed head `3023090`.

README и DATASET описывают профили, новый каталог, одну команду и ограничения.
Приватные данные/результаты не публикуются, LLM calls и VM deployment не
выполнялись. Это воспроизводимость подготовки, не независимая оценка качества.
Разрешённая train-проекция новых категорий и seller input всё ещё требуют
собственных решений/проверок #124/#36. PR #136 коллеги не изменялся.

# 20.10.2026: SPEC-002 — DONE, исполняемая матрица с видимыми пробелами

Claim `1a68c67`, ветка `qa/spec-002-scenario-matrix`. Реализованы независимый
inventory требований REQ-* и bindings SCN-* (`spec-002-v1`), source status,
заранее заданные ожидания, coverage report и artifact/source hash-manifest.
PR #143 принят в main, merge `432963fddd49a7d5fc64e6f61a80927f943eb1b9`;
Issue #35 закрыта с status:done. На final head `b1ea6cf` все 6 CI checks SUCCESS,
включая matrix в Linux/Windows; дерево merge совпало с протестированным деревом.
Чистые committed прогоны seed 20261020/20261021 оба PASS, input hashes разные;
export 185 файлов с links/hashes проверен, внутренние metadata исключены.
Одна команда `scripts/release/scenario_matrix.py` запускает внешний CLI/socket
HTTP в копии runtime без examples, offline verifier/LLM/API и отдельный demo.
Новые fixtures: только вымышленные названия/значения; реальных model calls нет.

Текущий scope: 17 executable групп; 4 not_implemented, 7 not_verified,
1 unknown — всего 29. Внешняя часть: 46 cases × CLI/HTTP + 9 стадий = 101/101.
Нулевой suite, пропавший/дублированный case, ослабленное ожидание или удалённая
обязательная привязка не считаются PASS. Packaged demo и финальная сдача
различаются явно; complete_case_evidence=false, качество каталога N/A.

12 новых harness tests PASS, 3 research reader tests PASS, pip check PASS.
Полная Windows-регрессия с PYTHONUTF8=1: 445 tests, 444 PASS и 1 прежний error
очистки QueueAudit audit.sqlite. Ошибка отдельно воспроизведена на неизменённом
main d4ff5f6 (5 review-priority tests, 1 error) и вынесена в OPS-004 #142;
5 dictionary tests на той же базе PASS. Первый локальный запуск без UTF-8
также выявил ошибки неявной кодировки в старых tests; с UTF-8 они исчезли.
Scope SPEC-002 не меняет src/runtime/config, версии JSON, старые metrics/gold,
VM и модельные API. Операционный дефект не маскируется skip/xfail.

Добавлены Linux/Windows CI, инструкция SCENARIO_MATRIX, команды в оба README
и явный Gitea allowlist документа. Интеграция выполнена после зелёного CI;
независимое качество, seller inputs, новые категории и операторская очередь
не закрываются прохождением synthetic gate.

# 20.10.2026: SPEC-001 — DONE, рабочая политика команды зафиксирована

По поручению Владислава и скриншотам разделов 2–6 подготовлен `spec-team-v1`
в TECHNICAL_SPEC, раздел 0; claim `1190fa6`, ветка `docs/spec-001-team-contract`.
PR #140 принят в main, merge `0ac3b185e8d279293ee2c388d0e0ed6a63ebdc38`;
Issue #10 закрыта с status:done. Final head `c28d774`: CI 6/6 SUCCESS;
дерево merge совпало с протестированным деревом. Локально: 16 baseline,
9 API и 9 submission tests PASS; committed export 180 файлов, links/hashes
и исключение внутренних документов проверены.
Дополнительного ответа организаторов нет: конечные endpoints/транзакции,
детальный категорийный перечень, состав разрешённого LLM payload и канал
передачи полного комплекта не объявляются официально подтверждёнными.

Зафиксированы JSON v0.1, эвристические review/abstain, единицы, точный raw
evidence, прежние правила brand/model/memory/color и отказ при неопределённости.
Seller attributes разрешены самим кейсом; их отсутствие в E1 признано долгом
DATA-002. Catalog vendor/model/params не допускаются без доказанного seller
provenance; новую форму seller evidence предстоит согласовать отдельно.
Реальный LLM пакет требует отдельного scope/hash/model/budget решения; reserve
закрыт. Шесть артефактов обязательны, локальный закрытый bundle не считается
уже переданным организаторам. Порог до калибровки не выдумывается.

SPEC-002 #35 переведена в READY без назначения владельца: можно строить
матрицу подтверждённых/командных сценариев с явным статусом источника;
DATA-001, DATA-002, приёмка CONF-003, новый реальный пилот и независимая оценка
не закрываются этим решением. Изменены только документы; runtime, JSON schema,
конфигурация, старые predictions/reference/метрики, VM и model API не менялись.

# 20.10.2026: DOCS-004 — DONE, публичные claims согласованы

Issue #122, ветка `docs/docs-004-runtime-evidence`, claim `a0f5a5f`, код базы
`1c64463`. REQUIREMENTS, RESULTS, ARCHITECTURE, LLM и VERIFIER сверены с кодом.
По поручению Влада [PR #138](https://github.com/CRUDoshleps/GoodsAI/pull/138)
принят в main, merge `7c49c6e4eaf62d613bc092205fc68d376985a04b`; Issue закрыта
с `status:done`. На final head `f17a1d9` все 6 CI checks SUCCESS, конфликтов нет;
merge-tree точно совпал с протестированным деревом файлов.
В оба README добавлены краткие доказательства с версиями/reference; README
сдачи содержит проверенный фрагмент JSON и действия по review/abstain/errors.
Исторические числовые таблицы silver и `reports/run_stats.json` не менялись;
RED SOLUTION помечен исторической ошибкой, последующее исправление указано
отдельно. Неподтверждённые model/catalog расхождения #137 не скрываются.

Пример своего JSONL выполнен фактическим CLI: все семь значений/decisions и
точный raw evidence совпали с документацией. На committed `7b79925` внешний
CLI/HTTP: 83/83; demo 6/6 + verify; pip check; 9 submission tests OK. Сформирован
состав сдачи из 180 файлов: относительные ссылки, hashes и исключение внутреннего
индекса проверены. Locked clean-run на том же commit: 11/11 passed.
Финальный export `f17a1d9`: те же 180 файлов, rewritten links и hashes валидны;
публичный runtime/config и числовые исторические таблицы не изменены.
Нет новых P/R/F1, реальных model calls, расходов, изменений VM или test access.
Чужой PR #136 не менялся. На момент завершения DOCS-004 собственный #127
оставался открытым из-за конфликта с записью шести функций коллеги.
По последующему поручению Влада в #127 выполнено согласование с main:
сохранены запись коллеги, результат DOCS-004 и завершение GOV-007.

# 20.10.2026: реализации шести задач приняты, экспериментальная приёмка открыта

По прямому поручению владельца реализованы #59/#66/#65/#61/#62/#60 отдельными
claims и PR #128–#133. Все шесть PR слиты после зелёных 6/6 CI checks.
Перед интеграционным follow-up: 431 основной test + 3 reader tests, synthetic
browser lifecycle dictionary draft→impact→review→publish выполнен. Добавлены
отдельные проверки single-flight между двумя процессами и точного producer
config у drift snapshot. PR #134 принят после 6/6 зелёных CI: 433 основных +
3 reader tests. Отдельный очищенный checkout: 433 tests, изолированный clean-run
11/11 и внешний CLI/HTTP 83/83. В README сдачи добавлены команды и ссылки
на эксплуатационные руководства; прежний фильтр внутренних документов сохранён.

- LLM-004: versioned exact cache, namespace/revision/TTL, integrity, bounded
  single-flight, свежий downstream verifier и аудит повторов без model calls.
- LLM-006: исходные blocks/raw offsets, неизвестная проза сохраняется;
  negation/relations/multiple mentions → full fallback, budget overflow → abstain.
- LLM-005: только attribute/span_id|null; source-only normalizer и общий gate;
  enum проверяется клиентом, server constrained generation не заявляется.
- OPS-003: локальные allowlisted агрегаты, совместимый frozen baseline,
  uncertainty/min support/persistence/hysteresis и ручное действие для alert.
- PRODUCT-006: severity/age ranking, oldest/rare/audit quotas, equal demand по
  умолчанию, approved aggregate weights и локальный audit сессий оператора.
- PRODUCT-005: UI над существующими config brands/colors, proposal/impact/review,
  server-side RBAC, immutable version/hash/author/reviewer/publisher/date,
  CAS publication и rollback; старые runs не переключаются автоматически.

Issues остаются REVIEW: representative cache/E1/E3 keep/drop, независимая
validation, OPS-002/PRODUCT-002/CONF-003 integration и human UX benchmark не
выполнены и не подменены synthetic tests. Default model routes выключены;
семантические alias, demand permissions и независимое качество не согласуются
автоматически. Реальные данные/gold/test, платные API и VM не использовались.
Новые эксплуатационные документы включены в явный Gitea allowlist; внутренние
исследования/планы/reviews и task board по-прежнему не публикуются.

# 20.10.2026: GOV-007 — DONE, очередь следующего технического прогона

По поручению Влада создана метка `review:next-checkpoint` и координатор
[GOV-007 #121](https://github.com/CRUDoshleps/GoodsAI/issues/121), claim `5de5aab`.
Индекс принят через [PR #126](https://github.com/CRUDoshleps/GoodsAI/pull/126),
merge `3e78ebf`, CI 6/6 SUCCESS; Issue закрыта с `status:done`.
Четыре новые узкие задачи: DOCS-004 #122 (публичные документы/README, P0 READY),
EVAL-007 #123 (fresh frozen-silver baseline, P1 READY), CONF-004 #124 (реальный
пилот категорий, P1 BLOCKED), EVAL-008 #125 (development model comparison,
P1 BLOCKED). Подробные условия и зависимости находятся в Issues и TASKS.

Связанные существующие задачи помечены той же меткой. Их owners/status/priority
не менялись; занятые задачи и блокировки не снимаются меткой кампании. Никаких
новых требований, метрик или повышенных баллов не заявляется. Runtime, данные,
политика confidence/decision, VM и бюджет шлюза в этой задаче не менялись.
Публичный состав Gitea не включает этот индекс и внутренний статус проекта.

# 20.10.2026: VER-002 + ARCH-001 — DONE, опубликованы в main и Gitea

По прямому поручению Влада последовательно приняты
[PR #118](https://github.com/CRUDoshleps/GoodsAI/pull/118) (Issue #37,
merge `0a1d13450b03ba617f8302c86e867b3a2bc65e6d`) и
[PR #119](https://github.com/CRUDoshleps/GoodsAI/pull/119) (Issue #43,
merge `88a216b3406cc7fd0f79eb8054ee8ad908fd3940`). Оба issues закрыты с
`status:done`, TASKS синхронизирован интегратором после фактического merge.
Запросов reviewer нет по указанию пользователя; независимое review не заявляется.

Перед merge у каждого PR 6/6 CI SUCCESS. После #118 база #119 изменена на main;
`git merge-tree --write-tree work/main HEAD` завершился без конфликтов, его
дерево `a4cf118a1122a41676b8f36056bac6447d05c114` точно совпало с HEAD
протестированного `2e43fa4`. Последняя мелкая правка добавляет отказы на
нестроковые router selections и сохраняет optional HTTP test extras;
targeted 16/16 прошли локально, весь набор прошёл в финальном CI.

Совместный результат: 402 основных + 3 reader tests; внешняя приёмка 83/83;
locked clean-run 11/11; synthetic demo 6/6 + verify. На прежних 40 reviewed
development результат не изменился: 143 TP / 0 FP / 22 FN, 224 judged /
16 excluded, A→C deltas отсутствуют. Это регрессионная проверка, не новый
independent quality result. Команды воспроизведения и границы этапов:
[ARCHITECTURE](ARCHITECTURE.md), [VERIFIER](VERIFIER.md).

Публикации Gitea обоих merge выполнены штатным allowlist workflow:
[39427814019](https://github.com/CRUDoshleps/GoodsAI/actions/runs/39427814019) и
[39427937162](https://github.com/CRUDoshleps/GoodsAI/actions/runs/39427937162)
SUCCESS. `origin/main` указывает на Gitea `02b0151`; его submission-manifest
ссылается на GitHub `88a216b`. Публичные runtime/контракты/архитектура включены;
TASKS и PROJECT_STATUS остаются только в GitHub. SHA двух репозиториев различны
по проектной политике. ВМ не обновлялась, model calls и расходы не выполнялись,
test reserve не открывался. SPEC-001 #10 остаётся открытой.

# 20.10.2026: ARCH-001 — проверка перед интеграцией (историческая запись)

По поручению Влада завершена недостающая часть Issue #43. Claim `ff89c14`,
ветка `arch/arch-001-pipeline-composition` от актуального main; поверх неё
локально включён PR #118 без merge в main. Исходные интерфейсы Тимура `e59c175`
сохранены. `composition.build_runtime` собирает CLI/API/trace из явного профиля
и runtime policy: typed source, normalizer, verifier factory, router, provider,
predictor и sink. Python overrides не требуют изменения orchestration;
LLM/GLiNER больше не зависят от `.rules.rules` внедрённого predictor.

Source возвращает канонические Candidate по stage v1; normalizer проверяет
числовое evidence. Gate, data policy, budgets и запрет перезаписи остаются в
основном пути. Rules-only не создаёт provider; fake provider доступен через
Python injection для offline tests. Файловый sink сохраняет прежнюю
транзакцию/recovery. HTTP не пишет файлы. Legacy imports и batch llm instance
сохранены; неизвестный policy или несовместимый профиль отклоняется до работы.
JSON v0.1, config v1/v2, confidence, units, review/abstain и команды запуска
не менялись. Официальное подтверждение SPEC-001 #10 не объявляется полученным.

Добавлены 16 synthetic tests для границ этапов, CLI/API parity с fake source и
provider/router, offline failure, rollback sink, legacy aliases, data policy,
неизменности снимков профиля и отсутствия eager import cycles/ML imports.
Полный прогон: **402 tests + 3 reader OK**, pip check OK. На committed `3d3dc49`:
внешняя приёмка **83/83**, locked clean-run **11/11**, demo **6/6** + verify.
Два comparison против frozen `2b0176d` на прежних 40 reviewed development:
TP/FP/FN **143/0/22** до = после, 224 judged / 16 excluded, нет A→C pair deltas,
новых FP или lost TP. Это AI-assisted human-reviewed development, не independent
test. Synthetic verifier suite также passed без lost true facts. Private
артефакты: `outputs/arch001-*3d3dc49*`, `outputs/evaluation/arch001-*-3d3dc49/`.
Открыт [PR #119](https://github.com/CRUDoshleps/GoodsAI/pull/119), stacked на #118;
финальный CI и последовательный merge ещё не объявлены выполненными.
Новых реальных model calls, расходов, просмотра test или изменений VM нет.
Прироста качества/баллов от архитектурного рефакторинга не заявляем.
Контракты и ограничения: [ARCHITECTURE](ARCHITECTURE.md).

# 20.10.2026: VER-002 — REVIEW, PR #118

Issue #37, ветка `qa/ver-002-common-verifier`, база `73faf07`, claim `8a55d81`
(кодировка исправлена `eddf6a1`), реализация `a2c0b32`. В рабочую ветку включён
актуальный `work/main` с REL-005; в `main` эта задача не сливалась.

`CandidateVerifier` проверяет структуру, raw/visible evidence, каноническую
нормализацию/единицы/диапазон, роль памяти, обнаруживаемые границы модели и
relation guard. Один gate используется rules, LLM (включая cache replay) и
experimental GLiNER. Relation 1.2 отклоняет явно служебные инструкции и
помеченные примеры JSON/ответа, сохраняя настоящие факты после них.
Контракт v0.1, конфигурация, heuristic score и review/abstain не менялись.
Общий stage contract v1 сохранён; официальное подтверждение SPEC-001 #10
не объявляется выполненным. Документация gate включена в allowlist сдачи.

Целевая synthetic regression: 5/12 → 12/12, неверные значения 4 → 0,
пропуски настоящих фактов 3 → 0, потеря прежде правильных фактов 0.
На 40 прежних AI-assisted human-reviewed development: TP/FP/FN 143/0/22
до = после, 224 judged / 16 excluded, 0 новых FP / lost TP / изменённых
значений. Это не independent gold и не доказательство улучшения каталожной F1.
Добавлены 17 targeted тестов, CLI/API parity, manifest reasons, fake provider
и cache replay, injected model entities без загрузки весов.
На интегрированном commit `9ce6432`: **386 основных + 3 reader tests OK**,
external acceptance **83/83**, synthetic demo **6/6** и verify OK, pip check OK,
locked clean-run **11/11**. Все 6 CI checks SUCCESS: invariants, properties,
external acceptance и clean-run на Linux/Windows. Freeze code hashes обоих
development comparisons совпали с текущим пакетом; A→C pair deltas пусты.

Реальных model calls, расходов, просмотра test reserve и изменений VM нет.
[PR #118](https://github.com/CRUDoshleps/GoodsAI/pull/118) открыт; запросы
reviewer не отправлялись по указанию Влада. Merge в main не выполнялся.
Схемы, ограничения, команды и private provenance: [VERIFIER](VERIFIER.md).

# 20.10.2026: REL-005 — опубликован состав сдачи Gitea

PR #116 слит в GitHub main (`741df14677a6d0639e55b40af1d5a95de328743f`).
Workflow [39421217155](https://github.com/CRUDoshleps/GoodsAI/actions/runs/39421217155)
успешно опубликовал 154 файла в Gitea commit
`f15f99b8f9602300195689766f3933f519640a18`, родитель `73faf07`.

Код, тесты, инструкции и материалы сдачи публикуются по allowlist с отдельным
README. TASKS/AGENTS/RESEARCH/PROJECT_STATUS, планы, docs/research и docs/reviews
остаются в GitHub. GitHub/Gitea SHA различаются; соответствие и hashes файлов
записаны в submission-manifest.json. История прежнего зеркала сохраняется;
новые development commits не становятся родителями Gitea commits.

CI PR: 6/6 SUCCESS, 369 основных + 3 reader tests, properties, clean-run и
внешняя приёмка Linux/Windows. Отдельный очищенный checkout: 368 основных tests
до добавления девятого boundary test; затем 9 boundary tests отдельно.
Изолированная установка/CLI/API/artifact smoke+verify: 11/11 passed; внешний
CLI/HTTP: 83/83. Относительные Markdown-ссылки проверены, code.zip из Gitea
состава также не содержит внутренних документов. Runtime не менялся; реальные
данные, платные API и VM не запускались. REL-005 #115 принят интегратором.
Исторические равенства GitHub/Gitea SHA ниже относятся к прежнему зеркалу.

# Состояние проекта

## 20.10.2026: CONF-002 — DONE, PR #109 принят в main

По прямому поручению Владислава PR #109 принят в main, merge `b99512f`.
На head `8dc66c2` все 6 CI checks SUCCESS, конфликтов нет; Issue #24 закрыта
с `status:done`. Ожидающие запросы reviewer сняты по указанию Владислава;
независимое review не заявляется. Публикация в Gitea — штатным mirror workflow.

Issue #24, база `1bedd07`, claim `3bddab1`, реализация `82cb134`, ветка
`arch/conf-002-runtime-policy`. Существующий профиль расширен общими настройками
LLM; resolver CLI/API применяет profile → env → explicit CLI flags и проверяет
все параметры до output/listen. Полные effective profile/policy и их hashes
пишутся в manifest без endpoint/key; API health возвращает те же hashes.
Production-пример проверен настоящими CLI и listening HTTP-процессом, включён
в source bundle. Старые v1/v2 без новых полей мигрируются детерминированно.

Решения не менялись: heuristic confidence, review/abstain, `auto_accept=false`,
`review_threshold=null`. Числовой порог без калибровки отклоняется; default LLM
выключен. Бюджеты пока логические, физические retries/deadline/bytes — #100.

На committed candidate: 346 основных + 3 reader tests OK, pip check OK,
внешний acceptance 83/83, locked clean-run 11/11. 12 новых policy tests:
precedence, типы/unknown keys, fail-fast, secrets exclusion, CLI/API hash/settings
parity, zero/false overrides, сохранность прежней пары и ограничение trace.
Frozen-method guards не ослаблялись: тесты, сравнивающие профиль с HEAD,
выполнены после фиксации нового профиля. Реальные данные/gold/test reserve,
внешние model APIs и VM в рамках задачи не использовались и не изменялись.
[Контракт и команды](CONFIGURATION.md#conf-002-единый-resolver-и-production-пример).

## 20.10.2026: LLM-007 — DONE, PR #107 принят в main

По прямому поручению Владислава PR #107 слит в `main`, merge `f8f4a59`.
На head `bb0d0bc` все 6 CI checks SUCCESS, конфликтов и requests for changes нет.
Ревью `wrakelft` было запрошено, отдельного ответа reviewer к моменту принятия нет;
решение о merge принято Владиславом. Issue #99 закрыта с `status:done`.

Issue #99, ветка `llm/llm-007-response-validation`, база `9086504`, claim `dce2c58`.
Устранён воспроизведённый `TypeError` при нестроковом `attribute` в LLM-ответе.
Типы proposals проверяются до membership/grounding одинаково для provider и cache;
gateway envelope/usage проверяются до accounting. Повреждённые элементы получают
фиксированные причины, допустимые соседи проходят verifier, rules сохраняются.
Контракт v0.1, heuristic score, review/abstain и политика conflicts прежние.

Локально: 334 основных + 3 reader tests OK (прежние 38 LLM + 12 новых regression),
pip check OK, внешний rules acceptance 83/83.
Новые tests исполняют настоящий CLI batch и HTTP-сервис через loopback stub;
проверены отсутствие 500, валидность predictions/manifest, продолжение партии,
CLI/API parity и cache replay без вызова провайдера. Внешних model calls нет.
Границы: byte/deadline/physical-attempt limits остаются #100; каталоговое качество
и изменение баллов не измерены. Публикация в Gitea выполняется штатным mirror
workflow после merge. ВМ не обновлялась.
[Поведение и воспроизведение](LLM.md#повреждённый-ответ-и-кэш-llm-007).

## 20.10.2026: связанные VER/BASE/QA приняты в main — DONE

По поручению Владислава последовательно приняты PR #104 (`d9e279a`),
#105 (`71cae4b`) и #103 (`aee1bba`); Issues #15/#21/#98 закрыты.
Итоговый runtime проверен: 322 основных + 3 reader tests, QA-001 21/21,
внешний CLI/HTTP без examples 83/83, locked clean-run 11/11.
У последнего head #103 `1f284af` все 6 checks SUCCESS на Ubuntu/Windows.
Gitea main опубликован автоматически: mirror run 39384309897 SUCCESS.
README начинает с проверенного своего JSONL, статусы и прежние ограничения
приведены в соответствие коду. VM не обновлялась, внешние model calls не выполнялись.
[Приёмка, SHA и область доказательств](reviews/2026-10-20_linked_acceptance.md).
Следующие разделы — история отдельных этапов и исходных дефектов.

## 20.10.2026: интеграционный кандидат #103/#104/#105

В QA-006 включены обе отдельные fix-ветки с сохранением всех статусов/документов.
Producer `12ae4c6`: strict внешний CLI/HTTP без examples **83/83, exit 0**
вместо 75/83; QA-001 v2 содержит все прежние случаи и точную причину отказа
для имени бренда. README начинает со своего JSONL, demo — дополнительный smoke.
Ниже сохранены результаты отдельных этапов, в том числе исходные ошибки.
Слияние в main выполняется только после общей регрессии и проверки CI.
Общий suite: 322 основных + 3 reader tests OK, pip check OK; PowerShell
пример README выполнен: все 7 значений совпали, input UTF-8 без BOM.

## 20.10.2026: QA-006 внешний ввод — REVIEW

Issue #98, claim `a7ca1db`, ветка `qa/qa-006-external-input`, база `857115d`.
Runner генерирует 16 новых synthetic inputs и добавляет все 21 QA-001 probe.
Настоящие CLI/HTTP работают из временной копии пакета без `examples/`.
Общие assertions проверяют value/unit/decision/reasons и exact evidence;
manifest и сохранение прежней пары после повреждённого JSONL проверяются отдельно.
Существующие runtime-правила и v0.1 не меняются.

При seed 20261020: 66/74 case checks и 9/9 stages, итого **75/83**, exit 1.
FAILED: RED SOLUTION/color (#15) и 3 model пропуска перед `мл` (#21), по обоим
transport. Expected не ослаблены, known issues не исключены из строгого CI.
311 основных тестов (Windows с PYTHONUTF8=1), 3 reader tests, pip check OK;
прежний listening HTTP probe 22/22; locked clean-run 11/11. Producer `4d177e1`
проверен чистым, same-seed input/expected/predictions побайтно совпали.
Это приёмка инструмента, не зелёная
функциональная приёмка или независимое качество каталога. Команды и границы:
[EXTERNAL_ACCEPTANCE](EXTERNAL_ACCEPTANCE.md). Main/VM и модели не обновлялись.

## 20.10.2026: VER-001 follow-up — REVIEW

Claim `c8e9374`, ветка `qa/ver-001-color-attachment`, база `857115d`.
Relation 1.1 защищает цвет внутри явного имени/модели и uppercase manufacturer
head перед кодом, отличает material-role; LLM проходит тот же relation guard.
QA-001 21/21 вместо 20/21. Для одного regression причина уточнена с generic
not_found на `relation_name_token`; требование color=null/abstain сохранено.
7 новых тестов; общий suite 313 tests OK, 40 AI-assisted reviewed development
без изменений значений (M2 72/0/11, D21–D40 62/0/20 TP/FP/FN до=после).
Это не независимая оценка. Нормализация, score и v0.1 не меняются.

## 20.10.2026: BASE-001 model follow-up — REVIEW

Claim `b348248`, база `857115d`, ветка `baseline/base-001-model-boundaries`.
Исправлены явные границы мл/ml, SIM feature, material/color modifier;
поддержаны digit-first index, split alphanumeric index и однозначные полные
коммерческие имена. Unknown multiword maker, unitless memory и служебные коды
с неясной ролью по-прежнему дают abstain. Единицы, normalization и v0.1 прежние.
310 tests OK, 4 новых model test methods. Демо 6/6. На прежних 40 AI-assisted
reviewed development: model TP/FP/FN 24/0/12 → 33/0/3; 0 lost TP/new FP,
0 изменений других атрибутов. Независимая оценка не выполнялась.
[Результаты и ограничения](research/base001_followup_results.md).

## 20.10.2026: backlog по ревью «прогон 2» — REVIEW

GOV-006 #97, claim `c15ec9b`, ветка `gov/gov-006-review-run-2`.
Созданы QA-006 #98, LLM-007 #99, LLM-008 #100, DOCS-003 #101
с меткой `review:run-2`; метка добавлена к #15/#19/#24/#35/#37/#40 без
смены владельцев/статусов. [Анализ и порядок](reviews/2026-10-20_run_2_action_plan.md).
Сумма восьми оценённых критериев 18,77 → 18,65/20; покрытие 2,80 → 2,34.
Код изучен на `890faad`; SHA ревью организаторов неизвестен.
38 LLM tests проходят, отдельно воспроизведён TypeError на `attribute=[]`
от fake provider. Это постановка задач, не исправление дефекта.
Runtime, VM, модели и приватные данные в GOV-006 не менялись.

Актуально на 19 октября 2026 года.

## DOCS-003: запуск с нуля и объяснение ответов — REVIEW

Ветка `docs/docs-003-own-jsonl-quickstart`, владелец Глеб Алферов, задача #101.
[QUICKSTART](QUICKSTART.md): клон → установка → свой JSONL из пяти карточек →
predict → проверка manifest по SHA-256 → HTTP `/predict` → opt-in LLM без ключа.
Linux-вариант выполнен в новом клоне `7aec082` (CPython 3.12.3), выводы в
документе — из этого прогона; PowerShell-вариант здесь не запускался, его шаги
покрывает CI `external-acceptance` на Windows. [RESPONSES](RESPONSES.md):
статусы, решения, reason codes rules/relation/LLM, ошибки HTTP и exit codes с
действием оператора. README больше не использует packaged examples в основном
batch-примере; устаревшие утверждения о LLM-маршруте и числе тестов обновлены.

## LLM-008: ограничения вызова LLM — REVIEW

Ветка `llm/llm-008-bounded-calls`, владелец Глеб Алферов, задача #100.
Ответ шлюза читается ограниченно (1 МиБ, вложенность JSON 32, до 32
предложений); один дедлайн 120 с на запрос карточки покрывает очередь, попытки,
паузы и socket timeout; дневной журнал 300 теперь считает физические
HTTP-попытки вместе с повторами. Значения в `runtime.llm` (CONF-002), с env и
CLI. Проверено: 359 основных тестов, из них 13 новых с локальным HTTP-сервером и
фейковыми часами; внешний шлюз не вызывался.

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

## CONF-003: передача на validation, зависимость от PR #92

[DONE — feature candidate] Добавлен явный schema mapper и private validation
runner поверх существующих predict/evaluate. Проверяются config/split hashes,
полный frozen validation scope, text identity и точные manual evidence.
Train/test и pending/silver reference отвергаются. Unmapped target labels →
unjudgeable с видимым judged/requested denominator. Отчёт сортирует judged
category/attribute slices по F1 и связывает файлы с run/code/config hashes.

Исправлен воспроизведённый тестом дефект: правильное значение manual reference,
которого нет в train-словаре, теперь даёт FN вместо ошибки/исключения.
Inference-словарь не расширяется. Проверено: 247 основных + 3 reader tests
OK (macOS/Python 3.14.8); 9 новых evaluation tests OK на CPython 3.12.14.
Реальные данные, gold/test, LLM, VM и зависимости не менялись. Код и команды: [CATEGORY_REGISTRY](CATEGORY_REGISTRY.md).
[PLAN] Реальные train/validation, schema mapping от команды, независимые
метрики и приёмка по-прежнему отсутствуют. GitHub metadata подтверждает: PR #92 содержит только CONF-001, base main,
head arch/conf-001-runtime-config. ARCH-001 и CONF-003 — отдельные ветки
поверх этой зависимости; в diff PR #92 они не входят. Новые PR через
подключение не созданы: GitHub отклонил создание с 403 FORBIDDEN.
Merge и назначение reviewer этим изменением не выполняются.

## Категории: новые feature candidates Тимура

[DONE — feature candidate] CONF-001 совмещена с main 977c5ed (e0b746f),
BASE-003 уже принята upstream. ARCH-001 добавляет внутренние stage interfaces
(e59c175); source не может обойти общий verifier. CONF-003 — opt-in реестр
из отдельного train с fill >=50%, словарями и изучением порядка чисел для
пар и размеров. Default runtime сохраняет прежние две категории.

[Доказательства] 30 вымышленных категорий / 120 train-карточек в synthetic
демо, точные spans, конфликт/negation, split guards и CLI/API parity покрыты
проверками. Итог: 238 основных + 3 reader tests OK (macOS/Python 3.14.8);
на CPython 3.12.14 — 9 registry tests OK, один API test пропущен из-за
отсутствия optional service dependencies. Windows/Linux VM не проверялись. Это не реальные top-30 и не оценка качества. Документ/команды:
[CATEGORY_REGISTRY](CATEGORY_REGISTRY.md).

[PLAN] Нужны разрешённые train/split/traffic, schema mapper, архитектурный
review и измерение на frozen validation. CONF-002/SPEC-001 и полная приёмка
ARCH-001/CONF-003 не объявлены завершёнными. Никакие private материалы,
реальные данные, gold/test или PDF в Git не добавлялись.

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
