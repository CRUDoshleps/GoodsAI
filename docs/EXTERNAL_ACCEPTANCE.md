# QA-006: внешний ввод без packaged demo

Команда проверяет текущий text-only v0.1 rules pipeline на внешнем синтетическом
JSONL. Это проверка исполнимости и ожидаемого поведения, не независимые P/R/F1
каталога и не подтверждение требований, которые организаторы ещё не опубликовали.

## Запуск

Используйте установленное окружение Python >=3.12 с `.[serve,test]` из README.
Пакет не переустанавливается; sandbox использует те же установленные зависимости.
Исходный checkout и его demo-файлы не меняются. Команды из корня репозитория:

```bash
.venv/bin/python scripts/release/external_acceptance.py --seed 20261020 --output-dir outputs/external-first
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/release/external_acceptance.py --seed 20261020 --output-dir outputs/external-first
$LASTEXITCODE
```

Директория должна быть новой, игнорируемой Git, внутри `outputs/`, без symlink
в пути. Старые результаты не перезаписываются. Для другого seed/повтора укажите
новый `--output-dir`. Версия grammar и seed фиксируются до запуска предсказаний.

Коды завершения:

| Exit | Значение | Следующее действие |
| --- | --- | --- |
| 0 | все смысловые, transport и integrity проверки пройдены | сохранить SHA и отчёт |
| 1 | минимум одна проверка не выполнена, включая известные дефекты | открыть failed cases в report и соответствующий Issue |
| 2 | ошибка исполнения, timeout, нарушенная manifest-пара или preflight | устранить причину, повторить в новом каталоге |

Ни один known issue не исключается и не превращается в xfail/continue-on-error.
Сохранённый отчёт сохраняет реальные passed/failed, даже если общий итог красный.

## Что именно запускается

1. `external_cases.py` по фиксированной грамматике создаёт 16 новых карточек:
   смартфоны и чайники, title-only и description, новые имена модели и числа,
   Unicode/emoji/HTML/entities, единицы и роли, отсутствующие характеристики,
   отрицание, конфликт, неизвестная категория, запрещённое seller-поле и
   корректная строка после неё. Ожидания задаются грамматикой, не predictor-ом.
2. Harness добавляет все 21 прежних QA-001 probe без изменения expected output.
   Они читаются до изоляции. Генератор и reference находятся у проверяющего;
   extractor получает только разрешённый input, без ожидаемых значений.
3. Временная копия `goodsai` содержит исходники и `baseline.json`, но не содержит
   `examples/` и bytecode. CWD также перенесён во временный каталог. Отдельный
   процесс подтверждает путь импорта; manifest проверяет тот же code/config hash.
   Установленная editable-версия не должна незаметно стать источником импорта.
4. Настоящий `python -m goodsai.cli predict` читает внешний `input.jsonl` из output.
   `clean_run.verify_pair` и общий QA-001 `case_errors` проверяют manifest,
   raw offsets, value/unit, review/abstain и причины по expected output.
5. Повреждённый JSONL с синтаксической ошибкой даёт exit 2 и сохраняет предыдущую
   пару predictions/manifest побайтно. Это отличается от schema-invalid строки:
   она получает `invalid_input`, а остальные строки batch обрабатываются.
6. Из этой же копии запускается настоящий HTTP процесс на свободном loopback-порту.
   Те же случаи проверяются по смыслу и CLI/HTTP parity (исключается только run_id).
   Для schema-invalid записи API должен вернуть 422, batch — invalid_input.
   Проверяются 400, 413, 415 и работоспособность после неверных запросов.
7. HTTP процесс останавливается и ожидается его завершение; временная копия удаляется
   и при ошибке readiness. Действующий сервис на 8000 не затрагивается.

Используются общие contract/assertions, manifest verification и socket probe;
второй evaluator качества не создаётся. Переменные `GOODSAI_*`, `OPENAI_*`
и влияющие на Python окружение очищены в дочерних процессах; LLM выключена.
HTTP client обходит proxy для локального запроса. Ключи и реальные данные не нужны.

## Артефакты и воспроизведение

- `input.jsonl`, `expected.json`: seed/grammar и внешние тестовые карточки;
- `predictions.jsonl`, `predictions.manifest.json`: обычные CLI результаты;
- `http_predictions.json`: фактические HTTP статусы/ответы;
- `malformed.jsonl`: отдельный синтаксически ошибочный вход;
- `report.json`, `report.md`: source SHA/dirty flag, seed, input/config/code hashes,
  SHA runner/grammar/legacy fixture, стадии и каждая проверка с причиной ошибки.

`checks_passed/total` считают проверки случаев плюс стадии; отдельные
`case_checks_passed/total` — проверки карточек по двум transport. Эти отношения
не являются precision/recall или оценкой обобщённости на реальных товарах.

Новый seed изменяет имена/значения и input hash. При том же seed, grammar и
legacy fixture вход и expected совпадают; предсказания сравнимы на одном code/config.
Тексты и результаты полностью вымышлены; все локальные артефакты остаются вне Git.

## Подтверждённые дефекты текущего baseline

Первый запуск на QA-006 обнаружил 8 проваленных проверок случаев из 74 (оба transport):

- 3 новых чайника с моделью `PX-число`, за которой стоит `1200/1500 мл` и мощность:
  model остаётся abstain вместо явно написанного кода. Связано с BASE-001 #21;
  граница количества в `model_rules.QUANTITY` не включает мл/ml.
- `qa-001/brand_is_not_color`: RED SOLUTION даёт ложный цвет (#15).

9/9 технических стадий прошли. Общее 75/83, exit 1. Пропуск model — новое
наблюдение, не регрессия runtime от QA-006: эта задача не меняет правила.
Ожидания не ослаблены. После профильных исправлений те же проверки должны позеленеть.
Перед финальным доказательством фиксируется producer commit и повторяется команда.

## CI и границы приёмки

Workflow `external-acceptance.yml` выполняет строгую команду на Ubuntu и Windows,
всегда сохраняет synthetic evidence. Известные дефекты тоже делают job красным;
доставка harness не означает зелёную функциональную приёмку продукта.
Unit tests отдельно проверяют, что одинаковая ошибочная выдача CLI/API не
считается успехом, неверный evidence отклоняется, seed меняет факты, timeout
не раскрывает payload, server cleanup и отказ от перезаписи работают.

Регрессия harness и проекта:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s scripts/research -p "test_*.py" -v
```

UTF-8 требуется также существующим Windows tests конфигурации/registry,
которые создают временные файлы с системной кодировкой. Сам QA-006 runner
устанавливает UTF-8 для своих дочерних процессов независимо от shell.

Не покрыты независимое качество каталога, все категории, непустые seller
attributes, live LLM/cost, окончательный официальный API, UI и сохранение
решений оператора. Это остаётся в #35/#37/#40/#19 и связанных задачах.
