# BASE-001: исправление подтверждённых границ модели

20.10.2026, Issue #21. Claim `b348248`, ветка
`baseline/base-001-model-boundaries`, база `857115d`.

## Что исправлено

Меняется существующий `model_rules.py`, без второго prototype, SKU lookup
или подсказок из target. Коммерческое имя остаётся точным текстом карточки:
только whitespace normalization, значимые символы и регистр сохраняются.

- Явные `мл/ml` и запятая перед спецификацией больше не ломают границу model.
- Индекс с цифрой в начале должен содержать и буквы, и цифры; `5G` само по
  себе и `256GB` не становятся моделями.
- Split code вроде `PWK 2829CA` сохраняется целиком. Uppercase maker перед
  индексом не поглощается как часть split model.
- После известного brand допустимо одно явное слово линейки перед индексом.
  Unknown multiword manufacturer/series boundary не угадывается.
- Полное split-index имя может сохранять до трёх явно написанных proper-case
  квалификаторов. Color/state/quantity, type/SKU и неопределённые короткие
  uppercase codes не превращаются в суффикс model.
- Явная SIM feature, material phrase и уже согласованные color modifiers
  отделяются от имени; новые цвета/значения из них не выводятся.

Новые синтетические примеры отличаются от реальных code/SKU. Существующие
отрицательные тесты сохранены; конфликт двух имён по-прежнему даёт abstain.
Проверены raw offsets при HTML/entities и отсутствие усечения полного имени.

## Замер на reviewed development

Использован существующий `scripts.research.compare_model_stage`: A — git
snapshot `857115d`, C — frozen текущий пакет, B — прежний ablation с отключённым
model generation. Ни B, ни gold не передаются runtime как подсказки.
Ниже сравниваются A→C. На вариант по два byte-identical повтора.

| Reference | Cards | Model TP/FP/FN, A → C | Model F1, A → C |
| --- | ---: | --- | --- |
| M2 D01–D20 | 20 | 12/0/7 → 18/0/1 | 77,42% → 97,30% |
| D21–D40 | 20 | 12/0/5 → 15/0/2 | 82,76% → 93,75% |
| Вместе | 40 | 24/0/12 → 33/0/3 | 80,00% → 95,65% |

Model recall: 66,67% → 91,67%; precision согласия reference — 100% в обоих
вариантах. Это **AI-assisted human-reviewed development**, уже обсуждавшийся
с разработчиком; не independent test и не доказательство 100% precision каталога.
0 lost TP, 0 новых FP, 0 A→C изменений других атрибутов. Полные per-attribute/
category counts, coverage, snapshots и hashes — в новых private артефактах:

- `outputs/evaluation/base001-final-m2/`;
- `outputs/evaluation/base001-final-d21/`.

Команды (PowerShell, UTF-8 нужен существующим Windows tests/workers):

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m scripts.research.compare_model_stage --gold data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl --output-dir outputs/evaluation/base001-m2-replay --baseline-ref 857115d --repeats 2
.\.venv\Scripts\python.exe -m scripts.research.compare_model_stage --gold outputs/evaluation/development-review-20261019-human-v2/development.human-reviewed.jsonl --output-dir outputs/evaluation/base001-d21-replay --baseline-ref 857115d --repeats 2
```

Manifest фиксирует frozen code, seed/reference/config hashes и происхождение.
Прежние predictions/отчёты/gold не перезаписаны. Промежуточные версии сравнения
сохранены отдельно: выявленный lost TP исправлен до выпуска и покрыт regression.

## Оставшиеся отказы и проверка

Остаются три judged model FN: unitless/неясные единицы памяти рядом с именем
и неоднозначное слово перед повторным brand. Они требуют отдельного решения
о границе имени, а не удаления незнакомого текста ради recall. Заводские/region
codes не обрезаются произвольно; модель из чужой сущности не подставляется.

310 основных tests OK, включая 18 model tests (4 новых метода), demo 6/6.
Интеграция с VER-001 и строгим QA-006 проверяется на общем кандидате перед merge.
Внешних API, расходов, reserve/test, деплоя VM или новых schema/decision policies нет.
