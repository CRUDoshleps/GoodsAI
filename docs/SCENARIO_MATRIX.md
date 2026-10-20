# SPEC-002: исполняемая матрица сценариев

Матрица `spec-002-v1` проверяет, что заявленные работающие сценарии имеют
исполняемое доказательство. Основание — [политика spec-team-v1](../TECHNICAL_SPEC.md#0-действующая-политика-команды--spec-001)
и [требования кейса](REQUIREMENTS.md). Сценарии не являются эталоном качества
каталога и не воспроизводят систему выставления баллов организаторов.

## Запуск

Из полного Git clone с Python 3.12 и установленным `.[serve,test]`:

```bash
.venv/bin/python scripts/release/scenario_matrix.py --seed 20261020 --output-dir outputs/scenarios-20261020
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/release/scenario_matrix.py --seed 20261020 --output-dir outputs/scenarios-20261020
```

Одна команда запускает внешний batch и настоящий loopback HTTP, offline-проверки
общего verifier/LLM и отдельный packaged smoke. После успешного запуска она
проверяет manifest и пару predictions/manifest. Откройте
`outputs/scenarios-20261020/report.md`; подробности — в `report.json`.
Для повторного запуска используйте новый каталог: прежние результаты, включая
неуспешные, не перезаписываются. Другой seed меняет вымышленные названия/значения
при тех же постоянных ID и заранее заданных ожиданиях.

Проверка сохранённого комплекта без нового извлечения:

```bash
.venv/bin/python scripts/release/scenario_matrix.py --verify outputs/scenarios-20261020
```

## Что исполняется

- [scenario_catalog.py](../scripts/release/scenario_catalog.py) содержит отдельный
  inventory `REQ-*` и привязки `SCN-*`. Для каждой группы указаны источник,
  раздел, статус `case_requirement` / `team_policy` / `unknown_condition`,
  ожидаемое поведение и ссылки на доказательства либо открытые Issues.
- [Внешний acceptance](EXTERNAL_ACCEPTANCE.md) получает 16 generated и 21
  legacy adversarial case; SPEC-002 добавляет 9 source-authored policy cases.
  Harness может читать legacy fixture перед запуском. **Копия runtime не
  содержит `goodsai/examples`**, а отдельные CLI/HTTP процессы запускаются вне
  рабочего checkout с очищенными model env. Проверяется место импорта.
- Ожидаемые значения/единицы/decisions/evidence задаются до prediction, не
  извлекаются из ответа системы. Для новых cases заполнены все поля категории;
  общий checker сверяет ожидания и контракт. CLI/API parity дополняет эту
  проверку, а не заменяет её. Проверяются все 46 cases в обоих transport.
- `test_candidate_verifier.py`, `test_llm.py`, `test_llm_bounds.py` и
  `test_llm_validation.py` и `test_api.py` запускаются отдельными child-процессами. Провайдеры
  fake или loopback, платных/внешних вызовов нет. Нулевой набор тестов и skips
  не считаются успешным доказательством. Это не live gateway benchmark.
- Packaged demo 6/6 проверяется **отдельно**, вместе с hashes. Его успех не
  закрывает внешний ввод, реальный каталог или шесть финальных артефактов.

Внешний набор включает title-only/description, все поля default-схемы смартфона
и чайника, Unicode/HTML/emoji, единицы, пропуски, отрицания, чужие сущности,
конфликты, неоднозначную память/модель, invalid Product, malformed JSONL и
HTTP 400/413/415/422 с восстановлением. Offline API test дополнительно проверяет
500 без утечки входа/деталей исключения. Точные ожидания лежат в
`external/expected.json`, исходный JSONL — рядом. Offline gate дополнительно
проверяет неверные значения, offsets, нормализацию и LLM failures/budgets.

## Как читать результат

При штатном текущем профиле отслеживаются **29 групп сценариев**:

| Исход | Число | Значение |
| --- | ---: | --- |
| passed | 17 | группы с исполненными synthetic доказательствами |
| not_implemented | 4 | seller input, ноутбуки, калиброванный порог, общая очередь оператора |
| not_verified | 7 | реальные категории, независимый human test, model comparison, traffic/seller slices, полный комплект, подготовка реальных данных, целевая VM |
| unknown | 1 | окончательные endpoints/транзакции организаторов |

`executable_gate: 17/17` и exit 0 означают, что все **заявленные исполняемые**
группы прошли. Поле `complete_case_evidence` остаётся **false**. Общая таблица
сохраняет все 29 групп; пробелы не входят в число успешных. Эти количества —
не P/R/F1, не заполненность каталога и не процент выполнения официальной оценки.

Внешняя часть содержит 101 check: 46 × CLI/HTTP + 9 технических стадий.
Offline-наборы записывают свои counts отдельно; packaged smoke — ещё 6 checks.
`positive_attribute_evidence` связывает каждое поле каждой default-категории с
положительными oracle cases. Это наличие synthetic примера, не качество категории.

## Строгий gate и происхождение

Удаление обязательной группы, dangling/duplicate ID, пустая/неизвестная привязка,
ослабленное ожидание или отсутствие положительного примера поддерживаемого
атрибута отклоняются. Понижение обязательного implemented-сценария до gap не
разрешается без изменения inventory и явного решения о scope. Отсутствующая,
дублированная или неуспешная CLI/HTTP/stage/suite проверка даёт failure; даже
case вне индивидуальных строк проверяется общей полнотой внешнего набора.

Exit codes: **0** — executable gate/verify успешен; **1** — наблюдаемая регрессия;
**2** — ошибка каталога, исполнения, destination или проверки manifest. Текст
исключения/вывод subprocess не публикуется. Неуспешные отчёты сохраняются;
после сбоя валидного каталога неполученные доказательства остаются failure.

`scenario.manifest.json` содержит Git/source identity, seed, hashes источников
и всех созданных файлов, строку для каждого SCN и пути к его доказательствам.
`release_artifacts` связывает эти доказательства с кодом/pipeline/predictions;
`final_six_artifact_delivery=false` не позволяет считать их финальной сдачей.
Для [ART-003](ARTIFACT_BUNDLE.md) этот manifest — дополнительный протокол:
он не заменяет его `release.manifest.json`, реальный predictions или финальные
EDA/слайды. Публичный Gitea-код содержит runner/catalog/tests и это руководство;
результаты запусков остаются в ignored outputs, CI сохраняет synthetic evidence
отдельным artifact. ВМ, реальные данные, gold/test и веса не используются.

При общей Windows-регрессии SPEC-002 был обнаружен отдельный дефект
[QueueAudit SQLite lifecycle #142](https://github.com/CRUDoshleps/GoodsAI/issues/142):
WinError 32 при очистке БД воспроизведён также на неизменённом main `d4ff5f6`.
В OPS-004 добавлено гарантированное закрытие курсоров/соединений QueueAudit и
регрессии успешных/ошибочных операций на Windows/Linux; исходный тест сохранён.
SCN-109 по-прежнему отмечает отсутствие общей очереди проверки атрибутов #19/#50.
Исправление SQLite не означает готовность этого workflow. Для общей Windows-регрессии
нужен `PYTHONUTF8=1`; runner задаёт UTF-8 своим child-процессам самостоятельно.

CI запускает ту же команду на Linux и Windows. При изменении контракта или
реализации обновите inventory, bindings и независимые ожидания осмысленно;
не копируйте фактический ответ в expected ради зелёной проверки.
