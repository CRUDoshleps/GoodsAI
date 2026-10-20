# VER-001 / BASE-001 / QA-006: приёмка связанных PR

20.10.2026. Выполнено по прямому поручению Владислава подготовить отдельные
исправления, проверить #103 совместно и последовательно принять их в main.
Завершение исходных задач, не новая функциональная ветка или изменение gold.

## Последовательность и происхождение

| Задача | Claim | PR / merge main | Проверки перед merge |
| --- | --- | --- | --- |
| VER-001 #15 | c8e9374 | #104 / d9e279a | 4/4 CI SUCCESS, 7 новых tests, strict QA-001 21/21 |
| BASE-001 #21 | b348248 | #105 / 71cae4b | 4/4 CI SUCCESS после включения #104; model regression и development comparison |
| QA-006 #98 | a7ca1db | #103 / aee1bba | head 1f284af: 6/6 CI SUCCESS, внешний CLI/HTTP 83/83 |

Сначала оба fix проверены в QA-006 feature-кандидате `12ae4c6`, затем
по одному приняты в main. #103 повторно синхронизирован с main и проверен.
Конфликты документа статуса разрешены с сохранением всех этапов/владельцев.
Маркеров конфликтов в принятом snapshot нет. Общий v0.1, единицы, whitespace-only
model normalization, heuristic scores и review/abstain сохранены.

## Что проверено фактически

- Локально Windows / CPython 3.12: 322 основных + 3 reader tests OK,
  pip check OK, locked clean-run 11/11. Windows tests выполнялись с PYTHONUTF8=1.
- QA-001 v2: 21/21, прежний RED SOLUTION case сохранён; изменён только точный
  reason на `relation_name_token`, value=null/abstain не ослаблены.
- QA-006: все 37 карточек через два transport, 74/74 case checks и 9/9 stages,
  итог 83/83, exit 0. Package examples отсутствуют у subprocess runtime.
  Manifest/evidence проверены; malformed JSONL сохраняет прежнюю пару, invalid
  product не обрывает соседние строки. Процесс HTTP завершается.
- Чистый producer `1f284af`: `outputs/qa006-before-main-final/` даёт 83/83.
  `12ae4c6`: `outputs/qa006-integrated-20261020/` также 83/83.
- Перед merge #103 на `1f284af`: invariants, properties, clean-run Ubuntu/Windows,
  external-acceptance Ubuntu/Windows — все SUCCESS.
- PowerShell quickstart из README выполнен: свой UTF-8 JSONL без BOM,
  все семь заявленных значений совпали, LLM calls=0.

Команды:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s scripts/research -p "test_*.py" -v
.\.venv\Scripts\python.exe scripts/release/external_acceptance.py --seed 20261020 --output-dir outputs/external-next
.\.venv\Scripts\python.exe -m goodsai.adversarial --output-dir outputs/adversarial-next
```

Output directories новые; прежние артефакты не перезаписываются.

## Development, границы и доставка

Обе fix вместе сравнили на тех же 40 AI-assisted reviewed development:
model TP/FP/FN 24/0/12 → 33/0/3, 9 FN исправлены; 0 lost TP, 0 новых FP,
0 изменений других атрибутов. На вариант по два byte-identical повтора.
Артефакты: `outputs/evaluation/integrated-fixes-m2/`,
`outputs/evaluation/integrated-fixes-d21/`. Source/reference/config hashes
зафиксированы manifest, реальные тексты и predictions вне Git.

Это не independent test, не измерение реального LLM quality и не обещание
конкретного прироста баллов. Подробные ограничения model и guard остаются
в [результатах](../research/base001_followup_results.md) и
[relation guide](../RELATION_VERIFIER.md). Сложные случаи не угадываются.

GitHub → Gitea: merge `aee1bba` подтверждён успешным workflow
[39384309897](https://github.com/CRUDoshleps/GoodsAI/actions/runs/39384309897).
Для предыдущих merges: runs 39383694890 и 39383986778 SUCCESS.
Workflow проверяет ancestry и публикует fast-forward без force push.
VM не обновлялась, публичные endpoint-ы организаторов остаются provisional;
test reserve, реальные model API, расходы, новые человеческие метки не использованы.

Следующий административный PR синхронизирует DONE/README и добавляет этот
протокол в public source archive. Production extraction после `aee1bba`
этим оформлением не меняется; его собственный merge SHA виден в Git history.
