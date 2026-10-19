# GOV-005 / ENV-003 / QA-005: результат технической проверки

Дата: 19 октября 2026 года. Ветка `gov/gov-005-final-acceptance`, PR #85.
Технический producer: `3ad28e4ed0a07f27f61654d70f2e9ff44513ef20`.
Следующие commits фиксируют протокол и статусы; они не выдаются за новый
проверенный producer. Default pipeline не менялся, режим — rules.

## Решение по трём задачам

| Issue | Выполнено | Итог / остаток |
| --- | --- | --- |
| #81 GOV-005 | Очередь, 3 новых Issues, 13 уточнений, роли и зависимости опубликованы; конфликт с main устранён | Оформление плана готово к review в PR #85; merge/DONE — у интегратора |
| #82 ENV-003 | Новый полный clone на VM, новый venv, существующий clean-run, внешний synthetic JSONL, tests, реальный listening HTTP, повтор batch, file-error checks | Технический pre-acceptance выполнен; финальная приёмка BLOCKED: нет независимого исполнителя и официального API, воспроизводятся #74/#15 |
| #83 QA-005 | Проверены корневой ответ API, опубликованные routes и готовность зависимостей; подготовлен checklist передачи | BLOCKED до UI #19, контрактов #17/#37 и независимого участника. UI rehearsal, сохранение после reload и export не выполнены |

Исполнитель технического прогона — Codex (tunaIT), автор runner/прототипа.
Это **не независимый reviewer**. Прямая просьба выполнить задачи разрешает
техническую работу, но не меняет происхождение доказательств. Критерии
независимого участника сохранены; отсутствующие проверки не помечены PASS.

## ENV-003: фактический прогон на VM

Linux x86_64, Python 3.12.15. Новый clone и venv, без изменения работающего
сервиса на порту 8000. Использован существующий `scripts/release/clean_run.py`,
не второй installer. Внешний разрешённый вход создан отдельно от checkout:
7 synthetic записей — 5 processed, 1 unsupported_category, 1 invalid_input.
Raw/gold/test reserve и внешние inference API не использовались.

| Проверка | Фактический результат |
| --- | --- |
| Чистый запуск | 11/11 этапов PASS, 13.39 s с созданием venv и установкой |
| Повтор runner | PASS, 0.41 s; тот же report, проверка ранее сохранённых hashes, не новый inference |
| Основной suite | 160 tests PASS, 7.555 s по unittest |
| Research reader suite | 3 tests PASS |
| HTTP через настоящий loopback socket | 22/22 transport/schema/parity checks PASS |
| Старт изолированного HTTP-сервера | 0.317 s |
| HTTP p50 / p95 | 1.44 / 1.91 ms, 18 synthetic prediction requests; не load/SLA test |
| Server peak RSS | 45.05 MiB, Linux VmHWM |
| Повтор CLI batch в другой output | Predictions побайтно совпали |
| Output поверх input | Отказ; исходный input hash неизменен |
| Directory вместо output-файла | Отказ; каталог сохранён |
| Завершение сервиса | Свой процесс остановлен в finally; рабочий сервис не перезапускался |

`run_id=abd951e72ea2c8bc5367`, `llm_calls=0`.
Input SHA256: `d8904f1ebebbc026df6827177c45d8256cecb2be37fb43dbfe5afdeabb2bb20d`.
Точные code/config/lock/probe fingerprints и агрегаты сохранены в отдельном
обезличенном JSON, private входы/predictions/logs остаются вне Git.
Собранный bundle имеет scope `synthetic_smoke`: это не финальная сдача с
независимыми human-метриками. P/R/F1 без reviewed reference — N/A.

Обычный CLI разрешает явную атомарную замену собственной output/manifest-пары;
повтор с тем же входом в этой проверке дал одинаковые predictions. Первоначальное
ожидание обязательного nonzero exit для любого существующего output не
соответствовало действующему контракту CLI и не объявляется найденным дефектом.
Это отличается от отказа перезаписи input и от cache-проверки clean-run.

## Подтверждённые препятствия финальной приёмке

Две semantic диагностики не прошли, несмотря на 22 успешные транспортные
проверки. Для synthetic `Батарея 5100 мА*ч.` поле остаётся пустым (#74). В
synthetic имени бренда `RED SOLUTION` выделяется цвет (#15, PR #79 ещё открыт
на момент прогона). Это прежние задачи, дубликаты не создавались. Fix не
подменялся изменением expected result и не вносился в чужую ветку в этом audit.

API сообщает `api_status=provisional`. Реальный HTTP подтверждён только по
loopback, внешний ingress платформы и согласование официального интерфейса
не подтверждены. Это не устраняется авторским запуском дополнительных тестов.

## QA-005: readiness и передача

`GET /` вернул service JSON. В `/openapi.json` опубликованы `/`, `/health` и
`/predict`; review/save/export operations не опубликованы. В проверяемом
`create_app` отсутствуют UI routes/static mounts и persistence решений.
Swagger `/docs` не является операторским workflow.

| Сценарий | Статус |
| --- | --- |
| Новая корректная карточка через review UI | NOT RUN — UI отсутствует |
| Отсутствующий бренд/поле, неоднозначная модель | NOT RUN — UI отсутствует |
| Чужая сущность, аксессуар, отрицание | NOT RUN — UI отсутствует |
| HTML/emoji/повтор цитаты и подсветка | NOT RUN — UI отсутствует |
| Unknown category / invalid input в интерфейсе | NOT RUN — UI отсутствует |
| Исправить/отклонить → save → reload → audit/export | NOT RUN — UI/persistence отсутствуют |

Следующий исполнитель получает этот checklist и выполняет его через настоящий
UI после #19/#17/#37. Expected и observed result, SHA, режим, длительность,
разрешённая запись/скриншоты и независимость участника фиксируются отдельно.
API parity из ENV-003 не засчитывается как UI PASS. Упрощённый mock, browser-only
extractor или сохранение только в localStorage не закрывают исходную приёмку.

## Повторение технических проверок

Из полного clean checkout producer SHA, CPython 3.12 и разрешённого внешнего
JSONL выполнить:

```bash
python3.12 scripts/release/clean_run.py --input /private/acceptance-input.jsonl --output-dir outputs/env003
outputs/env003/.venv/bin/python scripts/release/probe_http.py --output outputs/env003/live-http.json
outputs/env003/.venv/bin/python -m unittest discover -s tests -v
outputs/env003/.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

`probe_http.py` использует только встроенные synthetic случаи и временный
loopback-сервис. Он возвращает код transport/schema проверки и отдельно
пишет semantic diagnostics/UI blocker. Нулевой exit не означает готовность
к release, независимое качество или успешную UI-репетицию.

Для окончательного PASS нужны: исправления #74/#15, согласованный API #17,
рабочий review путь #19/#37, independent quality #6/#38/#40 и назначенный
независимый участник. Для принятого hybrid дополнительно нужна реальная
CLI/API интеграция #14; opt-in experiment не выдаётся за штатный API route.
