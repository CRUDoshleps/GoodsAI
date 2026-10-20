# VER-001: связь evidence с основным товаром

Статус: **REVIEW**, реализация в `qa/ver-001-relation-verifier`, claim `9400302`.
Основание: [Issue #15](https://github.com/CRUDoshleps/GoodsAI/issues/15), FR-4
[TECHNICAL_SPEC.md](../TECHNICAL_SPEC.md). Это дополнение к проверкам raw evidence,
не новый extractor и не классификатор категории.

## Реализация и границы

[relation.py](../src/goodsai/relation.py), версия `relation-1.0`, готовит visible/raw
карты один раз на товар. После структурной проверки каждого кандидата
[verify.py](../src/goodsai/verify.py) вызывает `RelationVerifier.reason(candidate)`.
Метод не использует score, имя правила, SKU или готовые атрибуты каталога.
Его можно вызвать для структурно проверенного кандидата будущего encoder/LLM;
такие источники в runtime пока не подключены.

Проверки отклоняют:

- evidence в скрытом HTML или через границу блока;
- характеристики аксессуара, если title явно начинается с его названия;
- значения в локальном контексте совместимости, сравнения, комплекта;
- характеристики явно другого телефона, упаковки, внешнего аккумулятора,
  аксессуара или заварочного чайника;
- отрицание, которое непосредственно относится к значению/названию атрибута.

Контекст ограничен текущей фразой и 240 видимыми символами с каждой стороны.
Точка между цифрами не завершает фразу; HTML-блок, предложение, `;`, перенос и
контрастный союз завершают её. Явное «этот смартфон» возвращает контекст к
основному товару. Упоминание отсутствующего кабеля не отрицает диагональ экрана.

Отфильтрованные кандидаты не создают ложный конфликт с положительным фактом
об основном товаре. Несколько разных оставшихся значений по-прежнему дают
`conflicting_evidence`, в том числе между title и description. Если все кандидаты
поля отклонены, `abstain` содержит отсортированные причины `relation_*`:
`nonvisible_evidence`, `accessory_product`, `foreign_entity`, `bundle_item`,
`other_object`, `negated` (каждая с префиксом `relation_`). Если генератор вообще
не создал кандидата, остаётся `not_found_by_rules`.

Публичный формат v0.1, единицы, нормализация, confidence и decision сохранены.
Migration не требуется; потребители reason codes должны допускать новые строки.
Найденное значение остаётся `heuristic/review`, auto-accept не добавлен.

Это ограниченные языковые шаблоны: отсутствие отказа не доказывает правильность
связи. Не покрыты произвольные перефразирования, длинные межфразовые ссылки,
полное разрешение сущностей и всех отрицательных/положительных утверждений.
Например, маркер за пределами окна может остаться незамеченным. Сложное перечисление
основного товара вместе с аксессуаром в одной фразе может дать лишний отказ.
Ошибочная категория часов D24 не исправляется этой задачей: это отдельная ML-002.

## Продолжение VER-001, 20.10.2026: relation 1.1

Исправляется оставшийся RED SOLUTION/color defect без добавления бренда в lookup.
Защищаются явные brand/model labels, модели из существующей grammar, начальный
известный brand span и uppercase multiword name перед кодом товара. Guard
применяется к raw evidence через visible mapping, поэтому отдельный настоящий
цвет после имени или в другом предложении сохраняется. Material-label не
выдаётся за цвет; неизвестный qualifier не обрезается до basic color в LLM.
Это консервативная синтаксика, не универсальное распознавание имён.

`llm.ground` теперь вызывает общий relation guard после structural validation.
Чужая сущность, аксессуар и bundle не проходят только за счёт точной цитаты.
Действующий ранний `llm_uncertain_context` сохраняется. Новые причины отказа:
`relation_name_token`, `relation_material_not_color`, `relation_unknown_color_modifier`.
Review/abstain, heuristic score, единицы и v0.1 остаются прежними.

В QA-001 v2 изменена **только причина** для brand_is_not_color:
`not_found_by_rules` → `relation_name_token`; value=null/decision=abstain
не ослаблены. Все 21 strict cases проходят, известный дефект не исключается.
7 новых tests проверяют неизвестное uppercase имя, HTML, model labels,
отдельные настоящие цвета, конфликты, material, LLM и CLI/API parity.

Сравнение с `857115d` через существующий compare_model_stage (A против C,
по 2 повтора) на двух прежних reviewed development по 20 карточек:
M2 TP/FP/FN 72/0/11 → 72/0/11; D21–D40 62/0/20 → 62/0/20.
0 изменённых A→C пар, 0 lost TP / new FP. Это AI-assisted development,
не blind test. Артефакты не перезаписывались: `outputs/evaluation/ver001-followup-m2/`
и `outputs/evaluation/ver001-followup-d21/`; snapshots и reference SHA внутри manifest.
Резерв test, внешние API, расходы и VM не использованы.

## Проверки

[test_relation.py](../tests/test_relation.py) проверяет отказы и сохранение
положительных фактов, повторные цитаты, конфликты, кириллицу/emoji, HTML/entities,
скрытый текст, границы контекста, порядок structural validation и CLI parity.
[test_api.py](../tests/test_api.py) проверяет API/core parity на отвергаемом контексте.
Неверный structural evidence по-прежнему вызывает ошибку до semantic filtering.

Фактическая проверка этой ветки, Windows/Python 3.12.6: **151 основной тест +
3 reader tests — OK**, `pip check` — OK; synthetic demo **6/6**. CLI и API parity
входят в основной suite. Логи: `outputs/ver-001-tests-complete.log` (private).
Linux, VM, реальные model providers и будущие чужие PR этим прогоном не проверялись.

[relation_fixtures.py](../tests/relation_fixtures.py) содержит 20 авторских
synthetic probes: 10 отрицательных и 10 положительных фактов диагонали.
При отключении только новой проверки получаем **8 ложных извлечений из 10**;
с проверкой **0 из 10**. Два отрицательных случая уже закрывали прежние rules.
Все 10 положительных фактов сохранены в обоих вариантах. Это целевой regression
набор, не репрезентативная оценка каталога и не независимый gold.

## Development: воспроизводимый guard ablation

[compare_relation.py](../scripts/research/compare_relation.py) замораживает текущий
пакет, запускает каждый вариант в отдельном процессе и сохраняет predictions,
manifest, per-attribute/category метрики, provenance-срезы и private pair deltas.
`before` отключает только построение/проверку relation guard в экспериментальном
worker, `after` использует его. Extractor и normalizers одинаковы. Это ablation,
а не сравнение разных старых Git-версий. В runtime нет флага отключения защиты.

Разрешён только явно указанный reviewed/manual development с группами.
Test/validation/draft отвергаются; другие наборы автоматически не открываются.
Новый output-dir обязателен. Reference hashes проверяются до/после, старые
артефакты не перезаписываются. Потеря TP или новый FP устанавливает
`regression_gate=review_required`; автор должен остановить выпуск и разобрать
деградацию, а не подбирать правила на test.

Команды из корня, Windows/Python 3.12.6:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.compare_relation --reference data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl --output-dir outputs/evaluation/ver-001-m2-replay --repeats 3
.\.venv\Scripts\python.exe -m scripts.research.compare_relation --reference outputs/evaluation/development-review-20261019-human-v2/development.human-reviewed.jsonl --output-dir outputs/evaluation/ver-001-d21-d40-replay --repeats 3
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/demo/ver-001-replay
```

Данные для второй команды локальны, подготовлены в PR #71; эта ветка не требует
его кода для runtime. Linux: executable `.venv/bin/python`; здесь Linux не проверен.

### Результат 19.10.2026

Оба набора — AI-assisted human-reviewed development, не независимая оценка.
В каждом варианте по три запуска; predictions внутри варианта byte-identical.
В обоих наборах **0 потерянных TP, 0 новых FP, 0 изменённых пар**, guard regression
gate pass. Нулевой FP на малом development не означает нулевой риск на каталоге.

| Reference | Cards / judged / excluded | TP / FP / FN, до = после | P / R / F1, до = после | Judged coverage |
| --- | --- | --- | --- | --- |
| M2 D01–D20 | 20 / 115 / 5 | 69 / 0 / 14 | 100 / 83,13 / 90,79% | 60,00% |
| D21–D40 | 20 / 109 / 11 | 59 / 0 / 23 | 100 / 71,95 / 83,69% | 54,13% |

В D21–D40 отдельно: `ai_draft_human_confirmed` — 107 judged, 59 TP/0 FP/21 FN;
`manual_contextual_correction` — 2 judged, 0 TP/0 FP/2 FN. Контекстные коррекции
памяти не превратились в runtime-правило. Все 11 исключённых пар, включая
ошибочную категорию, остаются в диагностике.

| Поле | M2 TP / FP / FN | D21–D40 TP / FP / FN |
| --- | --- | --- |
| brand | 20 / 0 / 0 | 16 / 0 / 3 |
| model | 12 / 0 / 7 | 12 / 0 / 5 |
| storage_gb | 5 / 0 / 1 | 5 / 0 / 3 |
| ram_gb | 6 / 0 / 0 | 6 / 0 / 1 |
| screen_inches | 3 / 0 / 1 | 3 / 0 / 1 |
| battery_mah | 1 / 0 / 3 | 0 / 0 / 3 |
| color | 16 / 0 / 0 | 10 / 0 / 4 |
| capacity_l | 2 / 0 / 2 | 5 / 0 / 0 |
| power_w | 4 / 0 / 0 | 2 / 0 / 3 |

По категориям, до = после: M2 смартфоны — 41/0/8, чайники — 28/0/6;
D21–D40 смартфоны — 37/0/12, чайники — 22/0/11 (TP/FP/FN).
Полные P/R/F1 и coverage каждого поля/категории — в private `before/report.json`
и `after/report.json`; `pair-deltas.jsonl` пуст в обоих development runs.

Медиана трёх измерений extractor p50/p95, мс: M2 before 1,501/4,178,
after 1,802/4,254; D21–D40 before 1,890/4,688, after 1,627/5,343.
Пик процесса во всех вариантах менее 36 MB. Малые батчи, параллельный запуск
экспериментов и шум Windows не позволяют делать вывод об ускорении или SLA.
Вызовы LLM — 0, расходы API — 0; compute в рублях не оценивался.

Private артефакты: `outputs/evaluation/ver-001-m2-final/` и
`outputs/evaluation/ver-001-d21-d40-final/`. Базовый Git SHA замеров `9400302`,
dirty=true: реализация ещё не была закоммичена; frozen package hashes в
`comparison.json` фиксируют фактический код. Relation SHA-256:
`162a83607a66c110eb72cffb2a6d8b6f0f4d0e7a0d696d35f0c7c4300e469953`.
Default config SHA: `cb7285cb3b83d2584661d5ec8eb4a315d6581148a5c3b1f7d012a0998db19a2b`;
экспериментальные варианты дополнительно имеют разные `experiment_ablation`
и свои config hashes в prediction manifests.

Reference SHA-256:

- M2: `2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337`.
- D21–D40: `9f8a2ef601bd76704551340cedfe0aef7c8d42677446044cb4dfe37b8ee443ae`.

Связь с review организаторов: предотвращение чужих характеристик и ложных
конфликтов адресует соблюдение ограничений и валидацию результата. На reviewed
development прироста P/R/F1 нет; синтетические исправления и сохранение TP
подтверждены тестами. Конкретный прирост баллов не предсказывается.

## Review и откат

Reviewer проверяет отрицательные и положительные probes, сравнивает guard
ablation и оценивает recall loss на последующих разрешённых development-наборах.
Отдельный QA-001 Issue этой работой не закрывается. Независимая итоговая оценка
остаётся отдельным этапом после заморозки методов.
Для отката отменить runtime-изменение VER-001 через обычный revert PR; новых
миграций/записей в raw/gold и изменения VM нет. Merge выполняет команда отдельно.
