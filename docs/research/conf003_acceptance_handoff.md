# CONF-003: приёмка механизма и передача в реальный пилот

Дата: 21.10.2026. Владелец продолжения #44 — timur0o31, ветка
`codex/conf-003-acceptance`, база `5f8b05d`, claim `a652ec1`.
Это внутренний документ; он не добавляется в PUBLIC_FILES publisher.

## Проверенный scope

PR #92/#93/#94 уже интегрированы; #9, #24, #43 закрыты в GitHub.
Существующий learner/evaluator и composition root используются без переписывания.
Новый инкремент добавляет только registry format version и content hash в
runtime metadata/batch manifest и HTTP health; prediction E1 v0.1 не меняется.

| Условие #44 | Доказательство / остаток |
| --- | --- |
| Явный opt-in профиль и fail-fast | config v2 через CLI `--config` / `create_app(config_path)`; `test_category_registry`, `test_config` |
| Новая категория без правки orchestration | существующие 30 invented категорий; новый CLI/API acceptance test для трёх |
| Train-only и отсутствие target hints на inference | membership/hash guards learner; Product отвергает params; новый API negative case |
| Версия схемы и содержимого в каждом batch run | `category_registry.registry_version/registry_sha256` и effective profile в manifest; строки связаны run_id |
| HTTP provenance | те же registry/effective hashes в health; responses требуют сохранения health вместе с результатом |
| Совместимость | E1 JSON прежний; default две категории; learned profile сохраняет legacy attributes |
| Отрицательные случаи | existing conflict/unknown/negation/HTML, input/schema/split tamper, unseen reference → FN |
| Aliases/default inheritance/plugins | универсальное расширение не реализовано; нужен отдельный согласованный scope |
| Версия категории в каждой prediction | прямого поля нет; архитектор решает, достаточен ли run-level hash без изменения E1 |
| Реальное качество | NOT RUN; synthetic pass не является real coverage или human quality |

## Реальный пилот: конкретный недостающий handoff

По live GitHub у #124 назначен e345ee. В этой работе владелец #124 не меняется.
DATA-001 #5 и SPEC-001 #10 закрыты, но завершение text-only E1 подготовки само
по себе не подтверждает наличие approved расширенной train-проекции.
В локальном `/Users/timuralmetov/GoodsAI` есть исходные pickle/parquet, но нет
готовых approved train/split/traffic; raw не открывались. Новый split из полного
каталога для обхода этого отсутствия не создаётся.

От data/владельца #124 нужны существующие приватные файлы и подтверждение их
назначения (пути и hashes, без передачи текстов в GitHub):

1. `train.jsonl` по CATEGORY_REGISTRY: SKU/category/title/description/params;
   numeric value и unit разделены, имена уникальны в карточке. Только train.
2. `split.json` формата goodsai-train-split-1: hash train и disjoint IDs;
   плюс исходный family/source audit и его hash. Learner сам family leakage
   не доказывает. Test содержит только IDs; его тексты не открываются.
3. `traffic.json` формата goodsai-category-traffic-1: train-only category
   aggregates, связанные с тем же train hash. Click rows не нужны.
4. Разрешённый frozen validation text-only JSONL по утверждённому scope,
   без params/vendor/model/seller targets и lookup-обогащения.
5. При оценке P/R/F1 — пригодный reviewed reference с provenance и явный
   one-to-one mapper, связанный с effective config hash. Catalog-silver нельзя
   объявлять manual reference; без подходящего reference human P/R/F1 = N/A.

До inference владелец фиксирует в приватном pilot record source hashes,
family audit, критерии отбора, category IDs и названия, required attributes,
units и принятую политику. Предлагаемый отбор: первые три новые категории вне
761/482 по train traffic с минимум четырьмя train SKU и eligible-полями,
без подбора по predictions; tie-break — category ID. Ноутбуки включаются при
наличии данных и согласованной схемы; отклонение от traffic order фиксируется
до inference. Это предложение для согласования, не уже утверждённый отбор.
Список отклонённых категорий/причин сохраняется, отсутствие трёх подходящих
категорий считается ограничением данных. Типы полей и единицы проверяются
архитектором до model run. Текущий min_template_support=3 и fill>=0.5 сохраняются.

После приёмки #44 и подтверждения handoff: отдельный claim #124 его владельца,
existing learn_categories → frozen config/hash и schema review → existing
CLI/API checks → existing registry_evaluation только с подходящим reference.
Никаких новых runner/evaluator, внешних model calls или просмотра reserve.

Ресурсы берутся из существующего manifest: elapsed_seconds,
cards_per_second_including_io, extractor_p50_ms/p95_ms, peak_process_rss_bytes.
RSS — пик всего процесса, а не изолированная RAM одного компонента.
Отчёт разделяет schema availability, candidate coverage, synthetic checks,
catalog agreement и human quality; поддержка схемы не равна качеству извлечения.

## Review и откат

Профиль остаётся opt-in, LLM/auto_accept не включаются этим инкрементом.
Новые schema/units/aliases/решения требуют архитектора. При critical FP или
невоспроизводимости real профиль не включать по умолчанию, сохранить hashes
и открыть узкий дефект. Откат metadata-инкремента — revert его commit;
откат реального профиля — packaged v1 без перезаписи прежних outputs.
#44 передаётся в REVIEW после опубликованного PR; DONE остаётся интегратору.
#124 сохраняет BLOCKED до согласования scope/данных/приёмки #44.

## Фактические проверки продолжения

Source `8861b91`, macOS 15.7.5 arm64, CPython 3.14.8:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`: 502 tests PASS, 44.617 s; venv переиспользован из исходного checkout, импорт — из текущего src.
- Research reader suite: 3 tests PASS; pip check: no broken requirements.
- Existing fuzz quick, seed 20261021: 11 tests PASS, 4.034 s. Hypothesis 6.170.1 установлен в ignored `outputs/conf003-acceptance/fuzz-deps`, добавлен к PYTHONPATH только этого прогона.
- Existing E1 demo: 6/6 + verify; existing category demo: 120 invented train cards → 30 invented categories / 180 candidates. Качество реальных категорий N/A.
- Новые metadata/entrypoint regressions: до реализации два ERROR на отсутствующем registry metadata; после — 3/3 PASS.

Первый общий прогон на dirty worktree в sandbox: 502 tests, 3 failures/13 errors
(socket bind запрещён, frozen producer не был clean). Исправления в проверках
не делались; после commit и разрешения loopback полный suite PASS. Первый fuzz
preflight без extra завершился ModuleNotFoundError; повтор с declared dependency
PASS. Логи первоначальных и итоговых запусков сохранены вне Git.

Это локальная инженерная проверка. CI/merge/Gitea, Linux/Windows нового
инкремента, реальный pilot quality и deployment этим отчётом не подтверждены.
