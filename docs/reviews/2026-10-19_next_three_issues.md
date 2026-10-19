# Три задачи: BASE-003 / ART-002 / QA-001

19 октября 2026. Интеграционная ветка `integration/next-three-74-27-18`.
Проверенный producer: `764dcb691eeb1505eb769c3b8ca69bc217b0a11f`. Последующий documentation commit не
выдаётся за новый runtime-прогон. Это локальная проверка, не VM deployment,
не независимый human gold/test и не решение о выпуске.

| Issue | Реализовано | PR / зависимость |
| --- | --- | --- |
| #74 BASE-003 | Батарея мА*ч/мА⋅ч, raw HTML mapping; пятизначные ёмкости до 30000; остальные numeric grammars не менялись | #86 поверх #79 |
| #27 ART-002 | Demo metrics/report + hashes шести файлов, verify без inference | #87, независим от relation stack |
| #18 QA-001 | 21 expected-output synthetic case через реальный batch, строгие exit codes, corruption/dependency faults | #88 поверх #86 |

Ветки отдельных реализаций: `baseline/base-003-battery-units`,
`artifacts/art-002-demo-kit`, `qa/qa-001-hard-cases`. Claims 7f70a0e/e508678/be970f4.
Изменения VER-001 взяты из ветки автора PR #79 без переписывания его проверки
и владельца. Новые PR ещё не означают merge/default release.

## Проверено совместно

- 190 основных + 3 reader tests PASS, pip check PASS.
- Реальная команда demo: 6/6; verify: 6 payload files PASS. Review 13/24,
  abstain 11/24, API calls/cost 0; compute cost и P/R/F1 N/A.
- Строгая QA-команда: 20/21, **exit 1**. RED внутри RED SOLUTION остаётся
  неверным цветом, tracked #15; known issue не скрывает failure.
- Первоначальная units-only ablation (producer c4648c6, общий VER-001):
  25 synthetic cases, TP/FP/FN 5/0/7 → 12/0/0. Это не качество каталога.
- После выявления пятизначной ёмкости добавлены edge tests на 10000, 29999,
  30000, 30001, 100000. Battery feature suite: 159 + 3 tests.
- ART feature suite: 162 + 3 tests. QA feature suite до five-digit update:
  162 + 3; окончательный общий код проверен 190 + 3 выше.

Fixtures задают value/unit, evidence field/raw start/end/text, decision/reason
или domain status. Invalid/unsupported входы не превращаются в успешную
обработку. Payload исключений не выводится в report. Storage process-kill/
concurrency/recovery и API negative tests использованы из существующих suites.
Provider timeout/budget N/A для отключённого route, не fake PASS.

## Команды

```bash
python -m unittest discover -s tests
python -m unittest discover -s scripts/research -p 'test_*.py'
python -m goodsai.demo --output-dir outputs/demo-new
python -m goodsai.demo --verify-dir outputs/demo-new
python -m goodsai.adversarial --output-dir outputs/qa-new
```

Последняя команда сейчас правильно возвращает exit 1 из-за #15. Unit-test
PASS проверяет harness/границы и отсутствие нетрекированных failures; он не
подменяет strict suite PASS. Каждый output-dir должен быть новым.

Перед merge: #79 → #86 → #88; #87 принимается отдельно. Исправление цвета из
бренда остаётся у #15. Закрытые данные/test не использовались, уверенность
не калибровалась, auto_accept и новая LLM не включались.
