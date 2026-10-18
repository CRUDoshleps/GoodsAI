# M1: извлечение model и проверка результата

Исторический отчёт первого снимка M1. Последующее разрешённое пользователем
исправление двух ошибок и новая роль validation описаны в
[отдельном отчёте](model_boundary_fix_results.md); таблицы/SHA ниже не переписаны.

18 октября 2026, Windows 11 / Python 3.12.6. Ветка `feature/vlad-model-rules`,
база `5f77d81`, изменения не закоммичены. Основание —
[согласованный M1](model_extraction_stage_plan.md); M2/M3 не выполнялись.

**Результат смешанный:** на development исправлены 8 model FN без новых FP.
На диагностическом validation вырос recall/F1, но появились 2 новых model FP
и снизилась precision. M1 реализован и измерен; автоматическую готовность
к выпуску это не доказывает. Перед выпуском нужен разбор границ имени и
расширенная проверка. Правила после просмотра validation не менялись.

## Что реализовано

- [ModelRules](../../src/goodsai/model_rules.py): явно написанные имена/индексы
  смартфонов после известного бренда, однозначный код чайника после названия
  производителя, явное поле «Модель:» в title/description. Это синтаксические
  конструкции, без whitelist готовых моделей или lookup по SKU.
- Сохраняются серия/значимые суффиксы/явные 4G/5G/LTE, регистр, дефисы и цифры;
  нормализуются пробелы. Отдельное упоминание поддержки 5G не дописывается.
  Неясные хвосты, два индекса, совместимость и отрицание дают отказ. Область
  этих проверок ограничена реализованными конструкциями, не всей семантикой языка.
- Rules передаёт кандидатов в прежний Extractor. Проверяются типы/field/offsets,
  unit, конечный score без bool, raw evidence, границы чисел. Для model видимый
  фрагмент восстанавливается в контексте **исходного поля**; value должно
  совпасть с согласованной нормализацией. Совпадающие кандидаты объединяются,
  разные — `conflicting_evidence`; отсутствие — `not_found_by_rules`.
- Контракт v0.1, method=rule, heuristic confidence, review/abstain сохранены.
  Изменение значения score не выдаётся за калибровку. Правила остальных
  атрибутов, единицы и словари не расширялись. Ложный span/value отклоняется,
  но настоящий span не гарантирует верного выделения коммерческого имени.
- Синтетическое demo обновлено: model у смартфона и чайника, 6/6 сценариев,
  13 review / 11 abstain. Ожидания отделены от входа, ресурсы входят в пакет.

## Сравнение A/B/C и защита данных

[compare_model_stage.py](../../scripts/research/compare_model_stage.py) создаёт
новый каталог и фиксирует пакеты кода/данные/эффективный config/SHA:

- A — пакет `src/goodsai` из Git-коммита `5f77d81`.
- B — замороженный текущий пакет с выключенным **только генератором model**
  через экспериментальный mock внутри отдельного процесса. Никакого такого
  переключателя в production CLI/API нет. Дополнительные проверки работают;
  отдельный effective config/rules_version отличает run_id B от C.
- C — тот же замороженный пакет, model-правила включены.

Для predict создаётся allowlist-проекция Product без attributes/gold/group/split.
Gold используется только для отбора среза и evaluate. Один и тот же evaluator
и неизменный reference применены ко всем вариантам. Он проверяет exact value+unit
и raw evidence, не вызывает правила заново. Неверное значение даёт **FP+FN**.
Ambiguous/unjudgeable исключены явно и одинаково для A/B/C.

Каждый вариант выполнен трижды; predictions побайтно детерминированы внутри
варианта. Исторические predictions совпали с A на обоих срезах по всем полям,
кроме изменившегося run_id. Gold и исторический файл проверены SHA до/после;
они не перезаписывались. B не изменил качество A; его причины отсутствия model
уже `not_found_by_rules` вместо исторического `rule_not_implemented`.
**Все остальные атрибуты A и C побайтно совпали как объекты атрибутов**, включая
evidence/score/причины. Все новые TP/FP относятся к model.

Development проверен первым; перед validation сохранён полный снимок C.
Диагностический validation выполнялся с `--freeze-from` именно этого снимка.
Инструмент проверяет целостность пакета, совпадение текущего кода с ним,
непересечение SKU/group двух reference и одинаковые наборы выходных SKU.
Проверка не заменяет ещё не выполненный аудит близких дублей.

## Общие метрики

Все непустые значения — review. Precision на всём каталоге, calibration,
fairness/traffic weighting и независимый test здесь не измерены.

| Split | Вариант | Judged / present | TP | FP | FN | Precision | Recall | F1 | Candidate coverage |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Development | A | 57 / 37 | 18 | 1 | 19 | 94,7% | 48,6% | 64,3% | 19/57 |
| Development | B | 57 / 37 | 18 | 1 | 19 | 94,7% | 48,6% | 64,3% | 19/57 |
| Development | C | 57 / 37 | 26 | 1 | 11 | 96,3% | 70,3% | 81,3% | 27/57 |
| Validation | A | 67 / 50 | 29 | 1 | 21 | 96,7% | 58,0% | 72,5% | 30/67 |
| Validation | B | 67 / 50 | 29 | 1 | 21 | 96,7% | 58,0% | 72,5% | 30/67 |
| Validation | C | 67 / 50 | 35 | 3 | 15 | 92,1% | 70,0% | 79,5% | 38/67 |

Development — 10 карточек, 58 применимых пар, 1 ambiguous; validation — 12
карточек, 72 применимые пары, 4 ambiguous + 1 unjudgeable. Coverage по всем
применимым парам у C — 28/58 и 39/72; не путать со знаменателем judged выше.
Correct coverage C — 26/57 и 35/67. Auto-accepted coverage = 0.

### C по атрибутам

Для всех строк, кроме model, A/B имеют те же TP/FP/FN/P/R/F1, что C.
Для model у A/B: development 0/0/9, validation 0/0/12; precision N/A.

| Split | Атрибут | Judged / present | TP / FP / FN | Precision | Recall | F1 |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Dev | brand | 10 / 10 | 6 / 1 / 4 | 85,7% | 60,0% | 70,6% |
| Dev | model | 10 / 9 | 8 / 0 / 1 | 100,0% | 88,9% | 94,1% |
| Dev | storage_gb | 4 / 4 | 4 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Dev | ram_gb | 4 / 4 | 4 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Dev | screen_inches | 4 / 1 | 1 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Dev | battery_mah | 4 / 1 | 0 / 0 / 1 | N/A | 0,0% | 0,0% |
| Dev | capacity_l | 6 / 3 | 1 / 0 / 2 | 100,0% | 33,3% | 50,0% |
| Dev | power_w | 6 / 1 | 1 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Dev | color | 9 / 4 | 1 / 0 / 3 | 100,0% | 25,0% | 40,0% |
| Val | brand | 12 / 12 | 11 / 0 / 1 | 100,0% | 91,7% | 95,7% |
| Val | model | 12 / 12 | 6 / 2 / 6 | 75,0% | 50,0% | 60,0% |
| Val | storage_gb | 4 / 4 | 4 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Val | ram_gb | 4 / 4 | 4 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Val | screen_inches | 6 / 2 | 1 / 0 / 1 | 100,0% | 50,0% | 66,7% |
| Val | battery_mah | 6 / 2 | 1 / 0 / 1 | 100,0% | 50,0% | 66,7% |
| Val | capacity_l | 5 / 3 | 2 / 1 / 1 | 66,7% | 66,7% | 66,7% |
| Val | power_w | 6 / 3 | 3 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Val | color | 12 / 8 | 3 / 0 / 5 | 100,0% | 37,5% | 54,5% |

### Категории, C

| Split | Категория | Judged / present | TP / FP / FN | Precision | Recall | F1 |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Dev | 761 | 27 / 21 | 18 / 0 / 3 | 100,0% | 85,7% | 92,3% |
| Dev | 482 | 30 / 16 | 8 / 1 / 8 | 88,9% | 50,0% | 64,0% |
| Val | 761 | 38 / 30 | 24 / 1 / 6 | 96,0% | 80,0% | 87,3% |
| Val | 482 | 29 / 20 | 11 / 2 / 9 | 84,6% | 55,0% | 66,7% |

Срез category×model: dev 761 — 4/0/0, dev 482 — 4/0/1;
val 761 — 5/1/1, val 482 — 1/1/5 (TP/FP/FN). На чайниках перенос особенно
слабый. Остальные category×attribute не изменились относительно A/B;
полные таблицы есть в локальных `A|B|C/metrics.json`, исходные A — в
[reviewed-v2](baseline_evaluation_v2.md).

## Ошибки и решение о выпуске

Development: 8 FN→TP для model, ни одного нового FP. Остался один model FN
из-за неизвестного словесного хвоста. Его не объявляли цветом по догадке и
не добавляли в словарь ради конкретной карточки. Другие 10 FN: brand=4,
color=3, capacity_l=2, battery_mah=1; прежний FP бренда сохранён.

Validation: 6 FN→TP, ещё 2 FN→FP+FN; четыре model-отказа сохранены.
Два неверных значения имеют **настоящий raw span**:

1. Заголовок содержит два обозначения бренда; после удаления одного второе
   попало в model. Связь с текстом верна, граница бренда/модели неверна.
2. У чайника взят индекс, но отброшена словесная часть коммерческого имени.
   Универсальная эвристика «производитель + один код» не отделяет серию от бренда.

Это не исправлено по validation: исходный снимок/результаты сохранены.
Четыре отказа на чайниках связаны с более сложными именами/дополнительными
обозначениями и границами; их точные тексты остаются в локальном reference.
Из остальных FN: color=5, brand=1, battery_mah=1, capacity_l=1, screen_inches=1.
Прежний FP capacity_l не исправлялся в этом scope.

**Итог приёмки:** M1 исполняется, dev-критерий выполнен, но выпуск требует
дальнейшего разбора: FP на validation выросли с 1 до 3. Не выбирать релиз
только по F1. Следующий шаг — явно согласованный разбор границ имени,
разнообразный development и M2; validation больше не считать скрытым набором.
Независимый test не открывался, независимая разметка не создавалась.
Модельный шлюз не вызывался; rules model не является экспериментом с ML/LLM.

## Время, стоимость и проверки

Каждая строка ниже — медиана p50/p95 из трёх отдельных batch-процессов,
максимальный peak RSS среди них. p50/p95 — определение штатного CLI, не
время HTTP или загрузки внешней модели. При 10/12 карточках хвостовая оценка
неустойчива; Windows/нагрузка различаются, это не SLA и не доказательство ускорения.

| Split | Вариант | p50, мс | p95, мс | peak RSS, МиБ |
| --- | --- | ---: | ---: | ---: |
| Dev | A | 0,423 | 2,431 | 34,45 |
| Dev | B | 0,333 | 2,473 | 34,38 |
| Dev | C | 1,462 | 2,606 | 33,71 |
| Val | A | 0,336 | 3,771 | 34,38 |
| Val | B | 0,413 | 3,514 | 34,50 |
| Val | C | 0,671 | 4,319 | 33,73 |

LLM calls=0, tokens=0, API-расход=0 ₽ для A/B/C. CPU-время ненулевое;
денежная стоимость compute N/A без тарифа. Полные batch/process времена в summary.

Реально выполнены: **57 tests**, включая 12 model-тестов и 3 сравнения,
API/CLI parity с положительным model в двух категориях, HTML/evidence,
конфликты, ошибки кандидата, R3-сценарии; demo **6/6** и CLI help.
Повторные Windows batch-предсказания детерминированы; Linux/ВМ, новый wheel,
reader suite и LLM в M1 не проверялись. Проверка wheel прежнего релиза не
подменяет проверку нынешней версии.

## Воспроизведение

Нужны checkout с M1, Python 3.12+, локальный reviewed-v2, baseline Git-коммит.
Без локального reference работает синтетическое demo, реальные метрики N/A.
Команды из корня репозитория; output-каталоги должны быть новыми:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/model-stage-demo-next
.\.venv\Scripts\python.exe scripts/research/compare_model_stage.py --gold data/gold/e1/reviewed/reviewed-v2/development.jsonl --output-dir outputs/experiments/model-stage/m1-development-next --historical outputs/baseline/predictions.jsonl
.\.venv\Scripts\python.exe scripts/research/compare_model_stage.py --gold data/gold/e1/reviewed/reviewed-v2/validation.jsonl --split validation --freeze-from outputs/experiments/model-stage/m1-development-next --output-dir outputs/experiments/model-stage/m1-validation-next --historical outputs/baseline/predictions.jsonl
```

На Linux заменить Python-путь на `.venv/bin/python`; это инструкция, не
подтверждённый Linux-прогон. `--historical` необязателен и только проверяет
предыдущие predictions; для непосредственного A/B/C нужен Git baseline,
не старые predictions. Из существующих каталогов этой задачи воспроизводимы
снимки A/C; B отключает только model, не ослабляет verifier.

Фактические результаты: локальные `outputs/experiments/model-stage/m1-development/`
и `m1-validation/`: input, snapshots, A/B/C predictions+manifest+metrics,
repeats, pair-deltas, summary, experiment.manifest. Данные и per-SKU ошибки в Git
не добавлены. Служебные lock-файлы R3 штатны.

| Идентичность | SHA-256 |
| --- | --- |
| A code | `2c76c5dc4cb87aea0ba486e43f76cb5ff8e11934cbf9041171aa4b09b90a905b` |
| C code | `7f48a1e937a510cb9a5b4ca8b685941ce8ba332954f6583b6a850489a033bffd` |
| C config | `ba1367937e5da2ee8adf1fcc9736458cfda6d25073bdc4dae4895e1a97af0605` |
| Dev C predictions | `ef8d5b4177f9b9f3fdf21428a72186a8afa4fb77ce2fd938a9ba4e96e46391d6` |
| Val C predictions | `19b73c9cfaff3e592e9f59fa34258e081c98f1b547be311020586f76e84e94df` |
| Dev experiment manifest | `4e0959aaa0b28ed41147d2d49320981b1c000e6cada1199532d9bcd052303156` |
| Val experiment manifest | `30f5cab21f99d4ca04461807ca7fc1fea0f41e3659c38ae591890b0b341c5099` |

Code SHA включает байты Python-файлов; переносы строк могут изменить SHA/run_id.
Source SHA каждого файла дополнительно записан в experiment manifest. База Git
одна, рабочий код dirty; один commit `5f77d81` не идентифицирует реализацию M1.
