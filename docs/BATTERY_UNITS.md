# BASE-003: единицы батареи

Поддержаны `мА*ч`, `мА⋅ч` вместе с прежними `мАч`, `мА·ч`, `mAh`, пробелами,
NBSP/narrow NBSP и латинской `a` внутри кириллической записи. Допустим один
разделитель; `мА**ч`, другая размерность и суффикс `мА*час` не принимаются.
BOUNDS, canonical unit `mAh`, confidence и schema не менялись.

Ветка `baseline/base-003-battery-units` основана на VER-001 PR #79: его проверка
принадлежности основному товару необходима для новых battery candidates.
Она не переписана в этой задаче; merge BASE-003 выполняется после VER-001.
Авторство/claim VER-001 сохраняется. Структурно ветка имеет предыдущую базу
этого PR, поэтому финальная интеграция с актуальным main проверяется отдельно.

Точные raw offsets сохраняются через существующий visible mapping, включая
inline HTML и entities. Hidden/block boundaries, отрицания, диапазоны,
конфликт ёмкостей, чужая батарея и другой объект не становятся значением.
Все найденные значения остаются review; без факта в тексте ёмкость не выводится.

## Проверка 19 октября 2026

158 основных + 3 reader tests прошли на ветке с VER-001, включая 7 новых
battery tests и их subcases. Контрольная synthetic pattern ablation использует
одинаковые verifier/config и 25 случаев (12 present, 13 absent):

| Grammar | TP | FP | FN |
| --- | ---: | ---: | ---: |
| Прежняя | 5 | 0 | 7 |
| Новая | 12 | 0 | 0 |

Это assistant-curated synthetic regression, не human reference и не качество
каталога. Сравнение меняет только regex батареи; не-battery поля двух контрольных
карточек совпали полностью. Дополнительно проверены конфликт и HTML boundaries.
Input SHA256 synthetic comparison:
`1f2d71fa646d3e8b90575e504e44f3ffd5be711fed76796c1877b4f7c8ec92eb`.
Config SHA256:
`cb7285cb3b83d2584661d5ec8eb4a315d6581148a5c3b1f7d012a0998db19a2b`.
Rules file SHA256:
`c7b0bb6091051900da7b1a2eb8058a8e3f347035d3c94b6c45ba04d1d37fa243`.
Test reserve и реальные тексты не использовались. Human quality остаётся gate
EVAL-001/003; прежние AI-labels не считались подтверждёнными людьми.

```bash
python -m unittest discover -s tests -p 'test_battery_units.py' -v
python -m unittest discover -s tests -v
python -m unittest discover -s scripts/research -p 'test_*.py' -v
```


Дополнительно при integration review исправлено прежнее ограничение четырьмя
цифрами: battery-specific grammar распознаёт 10000–30000 без пробела-разделителя,
а 30001/100000 отклоняются. Общий NUMBER для других атрибутов не изменён.
Пять границ/вариантов проверены отдельным восьмым regression test. Приведённая
выше 25-case ablation и её rules hash относятся к первому units-only producer
c4648c6; последующая совместная проверка фиксируется в интеграционном протоколе.
