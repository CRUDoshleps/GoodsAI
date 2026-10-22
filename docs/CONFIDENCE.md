# Confidence: фиксированный и контекстный score

`confidence` в v0.1 — число `[0,1]` с `confidence_kind=heuristic`.
Для `abstain` оно равно `null`. Это оценка кандидата, не вероятность и не
измеренная precision. Наличие точного evidence проверяется отдельно.

По умолчанию `fixed-v1`: бренд 0.85, цвет 0.75, модель/память/числовые поля 0.8.
Правило назначает score; merger сначала разрешает конфликт и выбирает evidence.

## Готовый opt-in learned-v1

Обучаемый advisory score добавлен после продолжения EVAL-012. Вместо ручных
коэффициентов используются logistic weights и отдельная Platt-настройка по
catalog-silver. Модель получает только признаки уже проверенного кандидата и
разрешённого текста. Score оценивает согласованность с каталоговым reference;
это **не калиброванная вероятность человеческой правильности**.

Frozen development: 2 171 карточка; original validation/development_feedback и
test reserve исключены. Роли fit/calibration/diagnostic сохранены по семействам.
Обучение: 1 875 кандидатов из 400 групп, 120 catalog mismatches; calibration:
310/77, 21 mismatch; diagnostic: 3 986/127, 164 mismatches. Unknown/conflict
reference не превращается в отрицательный класс.

| Проверка | Fixed | Learned |
| --- | ---: | ---: |
| Diagnostic catalog-proxy Brier (меньше лучше) | 0.06590 | 0.03283 |
| Diagnostic catalog-proxy ECE | 0.15501 | 0.03648 |
| Доля catalog mismatches в review 10% кандидатов | 12.43% | 89.74% |
| Brier на 107 ранее human-reviewed правильных извлечениях | 0.03937 | 0.00959 |

Review budget использует ожидаемое равномерное включение ties, не выбор по SKU
или labels. Парный family bootstrap: 95% интервал разности Brier learned-fixed
[-0.03471, -0.02399]; это условный development/catalog interval, не human quality.
Обе категории улучшились в этой диагностике. Человеческий sanity check содержит
только правильные извлечения и ранее использовался для правил: он не доказывает
способность находить реальные ошибки. Catalog mismatches включают неверные
данные и расхождения политик (например, суббренд/производитель, состав model,
оттенки цвета), поэтому 89.74% нельзя называть recall галлюцинаций.

Пригодность — **для advisory confidence и приоритизации уже существующего review**.
Новых порогов auto_accept нет. В штатном профиле по-прежнему fixed-v1.

### Область и безопасность

- Только rules-кандидаты; существующие решения, значения и evidence не меняются.
- Поддержаны девять сочетаний category/attribute/rule с ≥30 fit-кандидатами:
  brand/color/model/power для чайников; brand/color/battery/RAM-pair/storage-pair
  для смартфонов. Конкретные rule IDs находятся в model artifact и отчёте.
- Для редких/неизвестных scopes (включая phone model, screen и memory.context
  в данном обучении) сохраняется прежний score. Это явный fallback, не новая
  статистическая оценка; отсутствие поддержки нельзя считать успешной калибровкой.
- Model JSON проверяется по schema, finite weights, feature version, provenance
  и fingerprint правил/верификатора/нормализации/профиля. Несовместимый artifact
  отклоняется до старта сервиса. Pickle/динамические imports не используются.
- `/health.confidence` показывает version, model hash, reference kind, scope
  fallback и `human_probability_calibrated=false`. В ответ predict новые поля
  не добавляются; confidence_kind остаётся heuristic.
- Два одинаковых значения могут иметь разный score: storage=256 в синтетическом
  live smoke получил 0.987701 и 0.988993 при дополнительном ROM evidence.

### Построение и запуск

Модели, входы и готовые приватные configs не коммитятся. Подготовьте matching
checkout и новое имя каждого output directory; ни один этап не заменяет старые
результаты. Нужны исходный frozen silver bundle и confirmed reviewed development
spec формата ниже. Прямые LLM-вызовы и GPU не нужны.

```bash
python -m scripts.research.learn_confidence prepare --bundle /private/frozen-silver --output-dir outputs/confidence-silver
python -m scripts.research.compare_confidence --spec /private/confidence-spec.json --output-dir outputs/confidence-human
python -m scripts.research.learn_confidence finalize --prepared outputs/confidence-silver --human outputs/confidence-human --output-dir outputs/confidence-release
python -m scripts.research.learn_confidence verify-runtime --bundle /private/frozen-silver --prepared outputs/confidence-silver --release outputs/confidence-release --output-dir outputs/confidence-runtime
python -m goodsai.api --config outputs/confidence-release/profile.json --host 0.0.0.0 --port 8000
```

`finalize` проверяет source hashes, обучает модель, оставляет scopes по fit-only
counts, проверяет заранее заданные gates (Brier ≥10% лучше fixed, ECE и review
capture не хуже, reviewed sanity Brier не хуже fixed+0.005), прогоняет реальный
predictor по reviewed карточкам и сравнивает факты/decisions/P/R/F1.
На выходе: model.json, profile.json, report.json, fit-report.json, приватные
объяснения вкладов признаков/предсказания и manifest. `verify-runtime` дополнительно
сверяет runtime scores с offline features на всех выбранных реальных карточках.

Чтобы добавить модель к **существующему** config, сохранив его runtime-настройки:

```bash
python -m goodsai.confidence --base-config /private/base.json --model outputs/confidence-release/model.json --model-sha256 MODEL_SHA256 --output outputs/learned-profile.json
```

`MODEL_SHA256` — реальный SHA-256 файла model.json (например, `sha256sum` или
`Get-FileHash`). Один hash не доказывает качество: используйте проверенный release.
В живой проверке сочетание с storage-pilot-97-v1 сохранило auto_accept только
для прежней storage-области; остальные поля остались review/abstain.
Для отката используйте исходный config или runtime.confidence version=fixed-v1.

## Исторический экспериментальный контекстный профиль context-v1

По запросу Владислава 22.10 добавлен opt-in `context-v1`. Он учитывает признаки
конкретного выбранного rules-кандидата: явную подпись роли, единицу внутри
цитаты и согласие прошедших verifier кандидатов в заголовке и описании.
Одинаковые нормализованные title/description не дают бонуса согласия.
Скрытые HTML-узлы и подписи из другой строки/предложения не дают бонуса роли.
Вектор также содержит rule_id, категорию, поле и длину span для offline comparator.
SKU, family, targets/gold и внешние сведения в признаки не входят.

Формула: `sigmoid(logit(fixed_score) + 0.35*role + 0.20*unit + 0.40*agreement
- 0.35*no_role_or_unit)`, округление до шести знаков. Прежние 0/1 обрезаются
до `[0.000001,0.999999]` перед logit. Коэффициенты — вручную зафиксированная
экспериментальная эвристика; вариативность числа сама по себе не означает
более точный confidence. Для LLM/encoder этот профиль не вводит новую оценку.

Score меняется **после** выбора значения/evidence. Конфликт остаётся abstain;
низкий score сам не удаляет факт, высокий не разрешает auto_accept. Формат
предсказания и `confidence_kind` не меняются. Конфигурация и версия score входят
в существующие runtime policy/config hashes в `/health` и batch manifest.

```bash
python -m goodsai.confidence --output outputs/context-confidence.json
python -m goodsai --config outputs/context-confidence.json predict --input /private/cards.jsonl --output outputs/context-predictions.jsonl
python -m goodsai.api --config outputs/context-confidence.json --host 0.0.0.0 --port 8000
```

Генератор не перезаписывает существующий профиль. `--base-config /private/base.json`
сохраняет остальные настройки, в том числе уже согласованный storage pilot.
Сочетание не расширяет область принятия: только прежние storage rules/категория.
Возврат к исходному конфигу возвращает fixed-v1. ВМ генератор не изменяет.

Допустимая секция полного профиля:

```json
{"runtime": {"confidence": {"version": "context-v1"}}}
```

Это фрагмент, не самостоятельный config. Допустим также `fixed-v1`; отсутствие
секции сохраняет прежний результат. У context-v1 нет weights/threshold.
В learned-v1 полная проверенная модель передаётся отдельным полем `model`.

## Что показал первый эксперимент context-v1

На 30 ранее reviewed AI-assisted development-карточках: 107 правильных
извлечений, 0 FP, 13 FN. Это не independent test. Score оценивается только
для найденных однозначно размеченных кандидатов; пропуски видны в P/R/F1.
В diagnostic части 32 кандидата из 10 групп, все правильные:
Brier fixed 0.03930 против context 0.05836; ECE 0.19531 против 0.23554.
Меньше — лучше; новая эвристика не улучшила эти показатели и **не рекомендуется
для включения по умолчанию**. На выборке без ошибочных кандидатов нельзя
подтвердить способность ранжировать ошибки; повышение всех чисел этого не решит.

Learned comparator отказался обучаться: fit содержит 60 кандидатов из 15 групп,
0 ошибочных; calibration — 15/4/0, diagnostic — 32/10/0. Для обучения нужны
подтверждённые ошибки и отдельные группы калибровки. Пересмотр коэффициентов
по diagnostic не выполнялся. Полная независимая калибровка остаётся отдельной.

## Воспроизводимое сравнение

```bash
python -m scripts.research.compare_confidence --spec /private/confidence-spec.json --output-dir outputs/confidence-run-1
```

Spec фиксируется **до** прогона; пути относительны к нему:

```json
{
  "version": "confidence-experiment-1",
  "seed": "eval012-context-v1",
  "reference_origin": "ai_assisted_human_reviewed_development",
  "independent_reference": false,
  "references": [{"path": "reviewed-development.jsonl", "sha256": "REPLACE_WITH_ACTUAL_SHA256"}]
}
```

Принимаются только явно подтверждённые manual reviewed development rows
существующего gold-формата с family/group. AI-assisted происхождение остаётся
видимым. Для подготовленного independent human test этот runner не предназначен.
Нельзя подменять provenance, чтобы пропустить draft/test/validation. Исходные
проверки gold/evidence/нормализации выполняет существующий evaluator.

Семейства и точные нормализованные дубли объединяются перед hash-разбиением
60/20/20 на fit/calibration/diagnostic. Near duplicates должны быть учтены
исходным family audit. Seed не перебирается для получения удобного результата.
Support gate: fit ≥200 кандидатов/20 групп, ≥20 правильных и ошибочных;
calibration и diagnostic ≥10 групп и оба класса. Используются существующие
`fit_logistic`, `logit`, `sigmoid`, `reliability`; Platt обучается отдельно.
Полученный этим v1 runner model artifact разрешён только offline, не загружается
runtime. Для пригодного advisory artifact используется отдельный learn_confidence
workflow выше: другие данные, schema, gates и binding к исходному коду.

В новом приватном каталоге: freeze с SHA/группами, fixed/context predictions,
reference, признаки/labels, report с per-attribute/category P/R/F1, FP/FN,
Brier/ECE и пороговой candidate coverage, latency отдельно, manifest с хешами.
Отсутствие support сохраняется как N/A/insufficient_data. Пороги диагностические;
условные IID-границы не учитывают корреляцию и bias и не разрешают auto_accept.
Политика 97% storage не является калибровкой этих новых чисел.
