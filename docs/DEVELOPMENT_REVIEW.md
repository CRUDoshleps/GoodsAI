# EVAL-001: AI-assisted development review D21–D40

19.10.2026 Влад согласовал продолжение прежнего процесса: ИИ делает черновик,
Влад проверяет/исправляет. Текущий этап [Issue #6](https://github.com/CRUDoshleps/GoodsAI/issues/6)
уточнён соответственно. Это полезный development-reference, не новая независимая
оценка. [Blind-review инструменты](HUMAN_GOLD.md) сохранены для отдельного этапа.
40 резервных карточек не раскрываются и не предсказываются.

## Что открыть

Локальная финальная форма:
`outputs/evaluation/development-review-20261019-v2-ai/development.review.md`.
Короткий список спорного — соседний `disputes.md`. Реальные тексты/разметка/списки
SKU не публикуются в Git. Во всех 20 карточках / 120 полях human review пока pending.

**Обновление после ответа Влада:** все D21–D40 просмотрены. Влад явно подтвердил
неуказанные карточки и неуказанные атрибуты, а затем уточнил, что комментарий
про `G` относится к D27; память D25 подтверждена без изменений. Новая версия:
`outputs/evaluation/development-review-20261019-human-v2/development.human-reviewed.jsonl`.
20 карточек/120 подтверждённых полей, AI-assisted origin сохранён,
independent_reference=false. Draft выше — историческая версия до проверки.

Изменены только два memory-label D27: RAM 12 GB / storage 512 GB, с raw evidence
`12+512G` и provenance **manual_contextual_correction**. Это ручная трактовка
пользователем именно этой карточки; общий алиас G→GB и runtime-правило не добавлены.
В будущей оценке эти две пары нужно показывать отдельным provenance-срезом.
D24 подтверждена как ошибка категории; семь unjudgeable в схеме смартфона
сохранены. D29/storage, D31/model, D36/model+color остаются ambiguous.
Итого 82 present / 27 absent / 4 ambiguous / 7 unjudgeable, 109 judged / 11 excluded.
Изменение support связано с разметкой, не с улучшением extractor.

P/R/F1 не считались: текущий ответ — human-review/provenance, не новый прогон
метода. Старые draft/reference/results и reserve не заменены. Вопросы routing,
одиночной памяти и подсказок LLM — предложения для отдельной реализации.

Постоянные номера **D21–D40**, старые D01–D20 не меняются. Ответ можно присылать
партиями по 5 карточек:

```text
D21: всё верно.
D22: color = ..., остальные поля подтверждаю.
D23: по model не уверен; остальные поля подтверждаю.
```

Если хотите подтверждать неупомянутые поля, явно напишите для этой партии:
«Все неуказанные поля подтверждаю». Без такого подтверждения pending сохраняется.
Проверять нужно present, absent и ambiguous/unjudgeable. Свидетельства и заметки
в форме — предложения ИИ, не готовые истинные ответы. Внешние сведения не
подменяют то, что можно извлечь из разрешённого текста.

## Отбор и provenance

- Frozen policy `development-review-20261019-v1`, seed
  `goodsai-development-review-20261019-v1`, сохранены **до** просмотра карточек.
- Используется verified EVAL-002 eligible partition. Только development;
  блокируется целое семейство при любом known/family exposure или protected split.
- Пул — 800 development SKU без известного exposure. Отобраны 20 разных семей:
  по 10 смартфонов/чайников, по 5 с description/без description на категорию.
- Слоты в каждой ячейке: HTML, unit issue, неоднозначное имя, sparse, deterministic
  random fallback. Отбор целевой, не репрезентативная выборка каталога. Не отбираем
  по успешным predictions: predictor не запускается и не импортируется.
- Draft написан автором по тексту, а не автоматически заполнен runtime-правилами.
  Все 120 решений проходят проверку статуса/единиц/канонического числа и exact
  raw evidence с offsets. Model допускает только минимальную нормализацию.
- `annotation_status=draft`, `label_source=ai_assisted`, `human_review_status=pending`,
  `independent_reference=false`; P/R/F1=N/A. Подтверждения человека добавляются
  отдельной версией только после его ответов; существующие draft/gold не заменяются.

В draft: **80 present, 27 absent, 6 ambiguous, 7 unjudgeable**. Это распределение
предложенных labels, не измерение качества extractor. Новая спорная политика
по этим карточкам не применяется к runtime автоматически.

## Воспроизведение

Требуются локальные E1/EVAL-002 данные и установленный проект. Windows:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.development_review select --audit-bundle outputs/evaluation/eval-002-20261019-final --output-dir outputs/evaluation/development-review-replay
.\.venv\Scripts\python.exe -m scripts.research.development_review build --bundle outputs/evaluation/development-review-replay --decisions outputs/evaluation/development-review-20261019-decisions.json --output-dir outputs/evaluation/development-review-replay-ai
```

Linux: заменить executable на `.venv/bin/python`; Linux здесь не проверен.
Decisions — авторский private JSON с отдельным решением/цитатой/заметкой для
каждого поля, не поставляемый в Git датасет. Код не придумывает их при запуске.
Каждый output-dir новый, защищённые входы и артефакты сверяются по SHA.

Версионирование явного feedback (private JSON содержит автора, hash draft,
явное глобальное подтверждение, комментарии, уточнение номера и точечные overrides):

```powershell
.\.venv\Scripts\python.exe -m scripts.research.development_review feedback --draft-bundle outputs/evaluation/development-review-20261019-v2-ai --feedback outputs/evaluation/development-review-20261019-feedback-round1.json --output-dir outputs/evaluation/development-review-human-replay
```

Без явного confirm_all_existing_labels=true функция не повышает draft до reviewed.
Hash исходного draft обязателен. Contextual corrections проходят те же canonical/
exact evidence проверки; все исходные ответы и их происхождение сохраняются.
Эта команда не запускает predictions/evaluator и не подтверждает независимость.

Финальный bundle — `development-review-20261019-v2/`, draft — `...-v2-ai/`.
Предварительные v1 сохранены; набор карточек тот же, v2 включает окончательные
проверки и exposure manifest. Повтор текущей frozen selection — воспроизведение
этой партии, не новая партия/независимая выборка.

## Не потерять историю просмотров

`...-v2-ai/exposure.manifest.jsonl` фиксирует 20 новых AI-exposed SKU и семьи.
Для **следующей новой партии** передавать его через `select --seen <path>` вместе
со всеми следующими ledgers. Это исключает всю семью, а не только конкретный SKU.
При новом EVAL-002 audit включать этот источник в полный exposure ledger
(`--exposure-source` заменяет дополнительные defaults; старые источники не терять).
SHA ledgers фиксируются в selection policy. Нельзя менять seed и забывать новые
просмотры, а затем объявлять отбор независимым. Sample reserve 40 не трогать.

Runtime, категории, confidence/decision, правила, зависимости и VM не меняются.
Обращений к model gateway/внешним API для карточек и новых расходов нет.

## Выполненные проверки

Producer инструментов: `ffa35ca`. Windows / Python 3.12.6: **134 основных теста**
(6 новых development-review tests), 3 reader tests, pip check, CLI/link/
secret-pattern checks и git diff --check — OK. Проверены family-level exposure
gate до Product/signals, stratification, стабильные номера, отсутствие принудительных
замен, неверные цитаты, tampering и исключение новых просмотров следующего раунда.

Финальный select и replay дали побайтно одинаковые 4 selection-файла. Четыре
draft-артефакта (JSONL, review, disputes, exposure) также byte-identical; private
draft manifests различаются путём к replay bundle и не объявляются идентичными.
Все 80 present evidence совпадают с raw source; 20 families уникальны.
Повторный EVAL-002 verify подтвердил сохранение источников; reserve freeze всё
ещё approved=false. Gold, agreement людей и новые метрики extractor не созданы.

| Локальный артефакт | SHA-256 |
| --- | --- |
| `selection.policy.json` | `c24c03cf66e21e3b31f0844aa59a79983a7be43c483ac8576dcb7f91c22bb917` |
| `selection.summary.json` | `2a1738265174d8347108cc9293233403c2ee185e6ffb478bdf200280bc28b1a4` |
| `draft.manifest.json` | `224f5110524ac782686915cccfaeb43e9227cca28bc29766a4a22a638a19b438` |
| `development.ai-draft.jsonl` | `5d1c039f897e0b8d5d61bdb70752ac4a4bcf76a6c025534fa0ef210672d873c8` |
| `exposure.manifest.jsonl` | `ab017344d46437c26f7f81bc002fcdbc51559d91919c716ff24fce0ff83bfb3c` |
