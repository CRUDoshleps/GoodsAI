# EVAL-010: доступный инкремент аудита качества

Issue #149, 21.10.2026, claim `d2f5321`, база `7542d0087f17d177b7506a0727c67f06371c4ffa`.
Подготовка #38 уже принята через PR #150/151. Нового evaluator, human UI,
разметки, model screening или релизного runner этот этап не создаёт.
PR этого этапа готовится без merge; полный #149 не закрывается.

## Источник и неопределённость

Скриншоты организаторского прогона, переданные Владиславом: качество 4,87/5,
в том числе domain logic 1,95/2, validation 1,95/2, reproducibility 0,97/1.
Оценённый SHA = **unknown**: скриншоты не содержат submission identity.
Нельзя приписывать этот результат базе `7542d00` или обещать 5/5 после правки.
Общий текст ревью не совпадает с численной таблицей в остальных блоках.

## Проверка кода и выполненная работа

| Подкритерий | Подтверждено кодом | Доступная доработка | Что остаётся непроверенным |
| --- | --- | --- | --- |
| Доменная логика | Default смартфоны/чайники, canonical units/aliases, model grammar, memory roles, сохранение конфликтов | Переиспользовать существующие исключения вспомогательных числовых характеристик для всех candidate sources; positive/negative tests | Каталожные расхождения model в #137, длинный хвост/новые категории/продавцы |
| Валидация | Общий gate, exact evidence, bounds/units/relations, review-only; fresh/cache и ошибки LLM проверяются offline | Закрыт найденный путь numeric-role bypass; таблица решений QV-* привязана к реальным suite/case artifacts. Пропавшие обязательные test IDs не дают PASS | Полная семантика произвольного текста, независимая оценка остаточного риска, калибровка #39 |
| Воспроизводимость | Матрица #35, source/output hashes, offline quality bundle из PR #150, public allowlist | Использовать один существующий matrix runner, дополнить его внешним кейсом и точной проверкой исполненных test IDs; обновить публичные claims без подмены исторических цифр | Независимые reference/metrics #6/#38, готовый model comparison #136, окончательная VM/release приёмка |

## Найденный дефект и границы исправления

До исправления на синтетическом тексте «Мощность подогрева 300 Вт.» rules
возвращает power_w=null, но fake LLM proposal `300`/`300 Вт` проходит grounding
и общий gate, становясь power_w=300. Это другой режим того же товара, не
основная мощность. Проблема не в отсутствии цитаты или неверной единице.

До правки новые tests `test_auxiliary_quantities_are_rejected_regardless_of_producing_method`
и `test_auxiliary_llm_quantity_stays_rejected_on_fresh_response_and_cache_replay`
падают; позитивный fallback «Потребляет 2200 Вт» проходит. После правки
исключения ожидания/подогрева, дополнительного экрана и чужого объёма вынесены
в один `excluded_quantity_context`, который вызывают rules и общий numeric gate.
Rules-only сохраняет прежние ограничения; новый reason не добавляется:
используется `verifier_unsupported_value`. Версия gate — candidate-verifier-1.1.

Не добавлены справочники/пороги/lookup по SKU, не изменены model rules,
canonical units, heuristic scores, decisions или result v0.1. Полнота LLM
не ограничена требованием «кандидат уже обязан быть найден rules»: существующий
позитивный fallback без rules label сохраняется. Это конечные lexical guard,
не универсальный entity/attribute linking. Контекстное окно и словарь исключений
унаследованы от прежнего rules, новые синонимы не заявляются поддержанными.

## Доказательства и воспроизведение

Публичная таблица решений: `docs/VERIFIER.md`, QV-01–09/QE-01–03. Команда:

```powershell
.\.venv\Scripts\python.exe scripts/release/scenario_matrix.py --seed 20261021 --output-dir outputs/eval010/scenarios-next
.\.venv\Scripts\python.exe scripts/release/scenario_matrix.py --verify outputs/eval010/scenarios-next
```

`scenario.manifest.json` связывает `identity.git_commit`, runtime/config SHA,
sources/test hashes и report/offline/external артефакты. Без source/out hashes
плавающая ссылка main не является доказательством этого прогона. Матрица
сохраняет 29 групп: 17 executable, 4 not_implemented, 7 not_verified, 1 unknown;
внешний набор теперь 47 кейсов × CLI/HTTP + 9 стадий = 103 checks. Состояние
SCN-110 относится к этому synthetic runner, не отменяет отдельную завершённую
подготовку реальных данных DATA-001.

До PR проверены 20 verifier tests, 64 LLM tests, 13 matrix harness tests.
Окончательный общий прогон, baseline/candidate и CI результаты фиксируются
после freeze commit в статусе/PR; real quality P/R/F1 на этом этапе = N/A.
Новая синтетика не заменяет оценку реальных данных и не доказывает улучшение
P/R/F1 или баллов организаторов.

## Незавершённые зависимости и следующий шаг

- **#6** — независимые человеческие ответы и adjudication. Текущий reserve
  не открывался; прежний AI-assisted development не переименовывается в gold.
- **#38** — инструменты уже merged, но нужна реальная независимая оценка
  и проверка процесса/model freeze. Prepare/verify с N/A не закрывает этап.
- **PR #136** — коллега e345ee завершает frozen baseline/model measurement.
  Его ветка и приватные пакеты не меняются; новые результаты не копируются
  в актуальные main claims до готовности.
- **#137** — после handoff #136 нужен adjudication 20 catalog disagreements
  и 6 lost TP модели; здесь разбор не выполнялся, правила model не менялись.

До этих результатов доступный инкремент можно принять отдельно, весь #149
остаётся blocked для окончательной приёмки. Model/API costs, полный EDA,
новые категории, VM и release не запускаются этим этапом.
