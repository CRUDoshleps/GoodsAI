# Ограниченный storage pilot: precision target 97%

22.10.2026. Runtime source `ba5fd5cbad1ca4ea0a88475b8ecb49f4bad3de56`.
[JSON и provenance](storage_pilot_20261022.json), [контракт и команды](../docs/STORAGE_PILOT.md).

Владислав согласовал новую цель **после** аудита: 97% вместо исходных 99%.
Это решение о риске ограниченного opt-in пилота, не новый prospective эксперимент
и не завершённая независимая калибровка. [Исходный 99%-отчёт](storage_shadow_20261022.md)
не изменён. Default остаётся review/abstain, ВМ не обновлялась.

## Аудит и gate

145/145 предложений правил проверены и подтверждены человеком. Ошибок,
pending/unresolved нет. Наблюдаемая precision 100%; условная нижняя односторонняя
95%-граница — 97,955%. С target 97% численный gate выполнен, с 99% — нет.
Один reviewer участвовал в разработке и видел предложения: independent=false.
Выборка family-balanced, не SKU-weighted; биномиальная граница не устраняет bias
и не гарантирует precision нового потока. Confidence остаётся heuristic.

## Фактическое исполнение на прежнем development

2974 карточки, 18592 запрошенных поля. Ни reference, ни reserve для replay не
открывались. Проверены default, opt-in 97%, opt-in 99% и повтор 97%.

| Решение | Default | Pilot 97% | Pilot 99% |
| --- | ---: | ---: | ---: |
| auto_accept | 0 | 1528 | 0 |
| review | 10320 | 8792 | 10320 |
| abstain | 8272 | 8272 | 8272 |

Все переходы — review → auto_accept, только category 761 / storage_gb:
1511 от memory.title-pair.v1, 17 от memory.context.v1. Значения, единицы,
scores, method/rule_id, evidence/offsets и reason_codes побайтно эквивалентны
прежним extraction-результатам после исключения run_id/decision. Строгий профиль
99% сохраняет исходные решения. Два прогона 97% дали идентичные prediction bytes.

Это 8,22% всех запрошенных полей и 14,81% прежних review-кандидатов.
Такая доля не является измеренной экономией труда или deployment на ВМ.
Новые независимые precision/recall/F1 — N/A; качество извлечения этим этапом
не изменялось и не переоценивалось.

Исторический screening той же eligible-группы по шумному каталогу: 1513 TP,
2 mismatch, 10 unknown, 3 catalog conflict. Эти два mismatch не входят в
145 human-проверок и не adjudicated. Catalog conflict не равен конфликту
текстовых кандидатов; текстовые конфликты запрещают auto_accept.
Catalog agreement не объявляется human precision всего принятого потока.

## Проверки и стоимость

- 525 основных tests PASS, включая 14 новых pilot tests; 3 reader tests PASS.
- Реальный локальный Uvicorn: health/predict при 97% дают active/auto_accept,
  при 99% inactive/review; оба собственных процесса остановлены после проверки.
- Default synthetic demo 6/6 PASS; никакое его значение не стало auto_accept.
- CLI/API используют одну policy/config; false enable, неизвестная policy,
  изменённая extraction config, поддельный value/evidence, конфликты и LLM
  проверены отрицательными тестами. Rollback возвращает review.
- pip check PASS. LLM calls/API cost: 0 / 0 RUB. Compute cost не измерена.

Локальная extractor latency: default p50/p95 2,36/8,58 ms,
pilot 4,71/9,79 ms. Это один локальный прогон при параллельной проверке тестов,
не SLA и не benchmark ВМ. Дополнительная grounding-проверка имеет измеримую цену.

Runtime source LF совпадает с Git archive. Ранние неуспешные Windows-прогоны
с системной кодировкой/CRLF сохранены приватно; проверки fingerprints не ослаблены.
Реальные тексты, ответы, predictions, manifests и полные логи остаются вне Git.
