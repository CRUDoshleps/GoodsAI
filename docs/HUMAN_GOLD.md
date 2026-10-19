# EVAL-001: слепая человеческая разметка

Задача [#6](https://github.com/CRUDoshleps/GoodsAI/issues/6), инструкция человеку:
[HUMAN_GOLD_GUIDELINES.md](HUMAN_GOLD_GUIDELINES.md).
Инструмент: `scripts/research/human_gold.py`; offline HTML —
`scripts/research/human_gold_form.html`. Runtime/контракт v0.1 не меняются.

**Текущий согласованный этап:** [AI-assisted development D21–D40](DEVELOPMENT_REVIEW.md)
с проверкой Владом. Описанная ниже независимая разметка остаётся отдельным
незавершённым этапом, не блокирует подготовку development draft и не нужна для
того, чтобы пользоваться разметкой для разработки. Reserve пока закрыт.

## Статус и приёмка

Подготовка инструментов не закрывает EVAL-001. Для приёмки нужны два разных
человека, раздельные ответы, agreement и третий человек для adjudication/signoff.
Сейчас Влад сообщил, что размечать будет один; он участвовал в разработке и видел
прежние AI-assisted development-примеры. Новый reserve автоматически exposed
этим не становится, но раскрывать его разработчику до freeze методов нельзя.

Пока нет согласованного freeze, пакет содержит **только metadata/пустые поля**,
40 карточек (20 смартфонов/20 чайников), 240 полей. Тексты не скопированы в формы.
Размер — малый pilot на фиксированном резерве M2 v2, не репрезентативная оценка
всего каталога или новых категорий. Sample и версия guideline фиксируются до
начала разметки; менять инструкцию по увиденным test-ответам нельзя молча.

Одна разметка может быть проверена и сохранена как single-human review.
`reconcile` в этом режиме выдаёт agreement/P/R/F1 = N/A и **не создаёт gold**.
Для дальнейших доработок после просмотра разработчиком это development feedback.
Ни AI, ни второй псевдоним того же человека не заменяют независимого разметчика.

## 1. Подготовка без раскрытия test

Нужны Python >=3.12, установленный проект и локальный verified EVAL-002 bundle.
Из корня проекта, каждый output-dir должен быть новым:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.human_gold prepare --audit-bundle outputs/evaluation/eval-002-20261019-final --method-ref work/main --output-dir outputs/evaluation/human-gold-next
```

На Linux заменить executable на `.venv/bin/python`. Данные не входят в clone.
CLI разрешает запись только под `outputs/`; существующие данные не заменяет.

Результат: `tasks.metadata.jsonl`, `schema.json`, `guidelines.md`, `plan.json`,
`freeze.template.json`, `manifest.json`. В metadata есть приватная связь task ID
с SKU/family ID; человеку она не выдаётся. Подготовка проверяет hashes EVAL-002,
допустимость всех 40 reserve tasks и отсутствие family exposure. Входные тексты
не парсятся, predictions/gold/target не читаются. Method commit/tree и semantic
config SHA, guideline SHA и source SHA связываются в manifest.

## 2. Freeze и раздельные пакеты

**Сейчас этот шаг для реального резерва не выполнялся.** Сначала координатор и
владелец метода определяют момент единственной итоговой оценки. Если планируется
M3/подбор порогов, резерв сохраняется закрытым до их фиксации. Другой вариант —
оценить только зафиксированный текущий rules; последующие улучшения не получат
на этом просмотренном разработчиком наборе независимой оценки.

Скопировать `freeze.template.json` в отдельный `freeze.approved.json` вне
sealed-пакета. После действительного согласования заполнить approved/approved_by,
methods_and_thresholds_frozen/no_test_based_tuning, проверить точные method/tree/
config/guideline hashes. Назначить реальные разные reviewer IDs A/B/C; значение
по умолчанию A=vlad отражает заявленный план, B/C остаются пустыми. Не ставить
true вместо отсутствующего решения и не менять метод/hash задним числом.

```powershell
.\.venv\Scripts\python.exe -m scripts.research.human_gold materialize --bundle outputs/evaluation/human-gold-next --freeze outputs/evaluation/freeze.approved.json --slot A --output-dir outputs/evaluation/human-review-A-next
.\.venv\Scripts\python.exe -m scripts.research.human_gold materialize --bundle outputs/evaluation/human-gold-next --freeze outputs/evaluation/freeze.approved.json --slot B --output-dir outputs/evaluation/human-review-B-next
```

Материализация — алгоритмический export text-only входа ровно выбранных SKU;
ничего не печатает из карточек и не запускает extractor. Не просматривать её
результат разработчиком до freeze. A получает **только** свои `review.html` и
`guidelines.md`, B — свои. Служебные tasks.private/origin/freeze/manifest и mapping
координатор хранит закрыто. Формы не содержат предсказаний, справочных target
values или чужих ответов. A/B видят одинаковые тексты, постоянные T01–T40.

HTML работает локально без сервера/сети. Выберите статус, значение и точную
цитату, при необходимости позицию; сохраните `answers-A.json`/`answers-B.json`.
Поле позиции использует Python Unicode offsets, включая emoji. Исходный HTML
показывается через textContent и не исполняется; embedded JSON экранирован.
После перерыва загрузите скачанный JSON в тот же файл формы. Автосохранения нет.
Разметчики не смотрят ответы друг друга, ИИ/интернет/predictions не используют.

## 3. Проверка и согласие

Ответы сохранить вне sealed-папок, иначе нарушается inventory:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.human_gold check --package-a outputs/evaluation/human-review-A-next --answers-a outputs/evaluation/answers-A.json
.\.venv\Scripts\python.exe -m scripts.research.human_gold reconcile --package-a outputs/evaluation/human-review-A-next --answers-a outputs/evaluation/answers-A.json --package-b outputs/evaluation/human-review-B-next --answers-b outputs/evaluation/answers-B.json --output-dir outputs/evaluation/human-comparison-next
```

`check` допускает unreviewed и сообщает pending; reconciliation/finalize — нет.
Проверяются точный набор task IDs/полей, declared human source, канонические
единицы/числа текущего E1, exact raw evidence/видимость, минимальная model
нормализация. Семантику связи «товар ↔ атрибут» подтверждает человек, не checksum.
Значения вне E1 bounds не подгонять: пакет требует отдельного решения о schema.

Для одного человека команда reconcile используется без package-b/answers-b.
Она сохраняет только single-review summary, independent_reference=false,
agreement и P/R/F1=null. Наличие заполненного JSON не превращает его в gold.

При двух ответах: status exact agreement, canonical exact agreement, отдельное
совпадение evidence, status Cohen kappa (N/A при вырожденных marginals), срезы
по категории/атрибуту. Это **agreement людей, не precision/F1 extractor**.
Разные evidence при одинаковом canonical решении отражаются отдельно и не
считаются автоматически конфликтом значения. Есть локальный полный список
canonical disagreements и пустой adjudication template, без выбора «победителя».

## 4. Adjudication и финализация

Третий человек получает тексты, оба зафиксированных ответа и disagreements.
В отдельной копии `adjudication.template.json` указывает свой ID, для каждого
расхождения — полный label той же схемы и причину. Даже при отсутствии
расхождений требуется явный human signoff всего набора. Подтверждаются human_only,
all_labels_checked, no_test_based_tuning и hashes обоих ответов.

```powershell
.\.venv\Scripts\python.exe -m scripts.research.human_gold finalize --package-a outputs/evaluation/human-review-A-next --answers-a outputs/evaluation/answers-A.json --package-b outputs/evaluation/human-review-B-next --answers-b outputs/evaluation/answers-B.json --decisions outputs/evaluation/adjudication.signed.json --output-dir outputs/evaluation/human-reference-next
```

Только после всех проверок выпускаются private `reference.jsonl`, исходные A/B
ответы, signed decisions, freeze A/B, guideline/plan и provenance/manifest с SHA.
Reference совместим с текущим evaluator v0.1. Runtime-метрики при этом всё равно
N/A: predictions/evaluate отдельно запускаются только на frozen candidate после
контрольного human review происхождения. Доступ к final gold до freeze закрыт.

Флаг independent_reference основан на **заявлениях людей и соблюдении процесса**.
Инструмент не аутентифицирует личность, не доказывает отсутствие общения или
использования ИИ. Reviewer проверяет эти условия отдельно. Нельзя закрывать Issue
только по зелёным synthetic tests или по автоматически подписанному JSON.

## Границы и rollback

Нет реальных model calls, расходов, калибровки, обновления VM или изменения
rules/confidence/decision. Test не пересэмплируется, original raw/gold/splits/
predictions не меняются. Все реальные формы/ответы/manifest остаются вне Git и
не отправляются API. Если нарушена слепота — остановить независимую оценку,
записать exposure и оставить набор development feedback; результат не «очищать»
переименованием reviewer или удалением ledger. Старые файлы сохраняются.
