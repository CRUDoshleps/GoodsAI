# Confidence: фиксированный и контекстный score

`confidence` в v0.1 — число `[0,1]` с `confidence_kind=heuristic`.
Для `abstain` оно равно `null`. Это оценка кандидата, не вероятность и не
измеренная precision. Наличие точного evidence проверяется отдельно.

По умолчанию `fixed-v1`: бренд 0.85, цвет 0.75, модель/память/числовые поля 0.8.
Правило назначает score; merger сначала разрешает конфликт и выбирает evidence.

## Экспериментальный контекстный профиль

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
секции сохраняет прежний результат. Порог и learned weights здесь запрещены.

## Что показал первый эксперимент

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
Полученный model artifact разрешён только offline, не загружается runtime.

В новом приватном каталоге: freeze с SHA/группами, fixed/context predictions,
reference, признаки/labels, report с per-attribute/category P/R/F1, FP/FN,
Brier/ECE и пороговой candidate coverage, latency отдельно, manifest с хешами.
Отсутствие support сохраняется как N/A/insufficient_data. Пороги диагностические;
условные IID-границы не учитывают корреляцию и bias и не разрешают auto_accept.
Политика 97% storage не является калибровкой этих новых чисел.
