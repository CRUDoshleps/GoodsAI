# Очередь финальной приёмки

План согласован по поручению пользователя 19 октября 2026 года. Задача
оформления плана — [GOV-005 #81](https://github.com/CRUDoshleps/GoodsAI/issues/81).
Приоритеты задают порядок работы, а не обещают место в рейтинге. Владельцы
существующих claims сохраняются; независимую разметку и приёмку выполняют
реально назначенные участники команды.

## Первые действия

1. NLP/baseline берёт свободную [BASE-003 #74](https://github.com/CRUDoshleps/GoodsAI/issues/74):
   grammar батареи `мА*ч` с exact evidence и контролем новых ошибок.
2. Reviewer проверяет существующие [VER-001 #15](https://github.com/CRUDoshleps/GoodsAI/issues/15)
   / [PR #79](https://github.com/CRUDoshleps/GoodsAI/pull/79) и
   [ML-001 #16](https://github.com/CRUDoshleps/GoodsAI/issues/16)
   / [PR #80](https://github.com/CRUDoshleps/GoodsAI/pull/80).
   Review кода не доказывает независимое качество.
3. Ответственный за [EVAL-001 #6](https://github.com/CRUDoshleps/GoodsAI/issues/6)
   назначает двух независимых человеческих разметчиков и adjudicator для
   незавершённого blind-подэтапа. Reviewed development D21–D40 не размечается
   повторно и не переименовывается в independent gold.
4. Release engineer фиксирует candidate SHA/режим и передаёт независимому QA
   входы для [ENV-003 #82](https://github.com/CRUDoshleps/GoodsAI/issues/82).
   Runner [ENV-002 #41](https://github.com/CRUDoshleps/GoodsAI/issues/41) уже
   реализован и merged; новый runner не нужен.
5. Product/backend готовит одиночный UI по [PRODUCT-001 #19](https://github.com/CRUDoshleps/GoodsAI/issues/19),
   P1. API и verifier согласуются до реализации; пакетная очередь #50 не
   блокирует базовый одиночный путь.

Эти направления можно выполнять параллельно разными владельцами. Один
исполнитель сначала публикует claim только одной реализации, затем начинает
изменения. BLOCKED не означает готовность к claim: сначала снимается указанная
в соответствующем Issue зависимость.

## Приоритеты, роли и доказательства

| Направление | Issues | Роль | Приёмочное доказательство |
| --- | --- | --- | --- |
| P0: независимый запуск | [#82](https://github.com/CRUDoshleps/GoodsAI/issues/82) → [#42](https://github.com/CRUDoshleps/GoodsAI/issues/42) | независимый QA/MLOps, release engineer | Чистый checkout/venv на VM, внешний JSONL, инструкция без ручных правок, exit codes, cold/warm/RSS, полный комплект одного run ID |
| P0/P1: подтверждённые дефекты | [#74](https://github.com/CRUDoshleps/GoodsAI/issues/74), [#15](https://github.com/CRUDoshleps/GoodsAI/issues/15), [#21](https://github.com/CRUDoshleps/GoodsAI/issues/21) | NLP/baseline, reviewer | Исправленные FN и новые FP на одном development-входе; synthetic regressions; остальные атрибуты и evidence не испорчены |
| P0: независимые метки | [#6](https://github.com/CRUDoshleps/GoodsAI/issues/6) → [#38](https://github.com/CRUDoshleps/GoodsAI/issues/38), с проверками [#7](https://github.com/CRUDoshleps/GoodsAI/issues/7) | человеческие разметчики, adjudicator, аналитик | Source-only разметка, family-safe split, agreement, frozen hashes, provenance и support по present/absent/ambiguous |
| P0: сравнение гибрида | [#40](https://github.com/CRUDoshleps/GoodsAI/issues/40), этап A; candidate [#16](https://github.com/CRUDoshleps/GoodsAI/issues/16) | ML/evaluation | Rules и узкий hybrid на одинаковых независимых данных; ΔTP/FP/FN/P/R/F1, интервалы, ресурсы и заранее заданное keep/drop |
| P0: общая проверка и калибровка | [#37](https://github.com/CRUDoshleps/GoodsAI/issues/37) → [#39](https://github.com/CRUDoshleps/GoodsAI/issues/39) | NLP/QA, ML/evaluation | Один verifier для всех источников; precision/coverage и риск среди принятых; review/abstain при недостаточной поддержке |
| P1: рабочая демонстрация | [#19](https://github.com/CRUDoshleps/GoodsAI/issues/19) → [#83](https://github.com/CRUDoshleps/GoodsAI/issues/83) → [#54](https://github.com/CRUDoshleps/GoodsAI/issues/54) | product/backend, независимый QA | UI → настоящий backend → evidence → сохранённое решение после reload → export; разрешённая репетиция и проверяемый питч |

Более высокая приоритетность независимой оценки не означает, что разметка
должна ждать завершения всех исправлений: готовить source-only labels можно
раньше. Методы/пороги замораживаются до раскрытия независимых ответов и открытия
защищённого test. Достаточность поддержки и практически значимые допуски
задаются до validation, а не по получившимся результатам.

## Границы этапов

- **Запуск:** #82 проверяет candidate, подготовленный после нужных изменений;
  он не зависит от публикации #42 и поставляет ей доказательство. Старый PASS
  другого SHA и merged runner не заменяют этот прогон.
- **Гибрид:** этап A в #40 сравнивает уже доступную пару rules/GLiNER. Для него
  не нужны ещё не реализованные LLM или полный router. Этап B сохраняет полную
  матрицу сравнения по готовности компонентов. Нет выигрыша или мощности —
  drop/insufficient evidence, а не автоматическое включение модели.
- **Интеграция:** после keep по этапу A [ROUTE-001 #14](https://github.com/CRUDoshleps/GoodsAI/issues/14)
  подключает принятую rules/ML-пару к настоящим CLI/API через согласованные
  config/контракты. Только затем #82 принимает такой hybrid candidate.
  Отдельный experimental CLI из PR #80 не доказывает работу модели в API.
  Input/reference и их provenance готовятся в #6/#38 до A; финальный пакет
  predictions/report в #38 собирается после A и не создаёт обратной зависимости.
- **Уверенность:** learned correctness score, calibration и decision threshold
  разделены. Необоснованный auto_accept не требуется для красивой демонстрации;
  безопасные review/abstain допустимы и должны быть понятны пользователю.
- **Интерфейс:** #19 реализует одиночный путь, #50 — пакетную очередь. #83
  проверяет существующую реализацию и не создаёт вторую. Пакетная репетиция
  проводится отдельно, если сценарий обязателен по #35.
- **Выпуск:** #42 связывает выбранный режим, согласованные обязательные сценарии,
  GitHub/Gitea SHA и hashes комплекта; отсутствие незавершённой необязательной
  модели не оправдывает ложный claim о работающем гибриде.

## Три комплекта доказательств

1. **Качество:** независимые frozen input/reference/predictions, одна schema и
   evaluator; micro/per-attribute/category P/R/F1, coverage, corrected FN/new FP,
   критические ошибки и исключения с числителями/знаменателями. Данные остаются
   в разрешённом закрытом окружении; публикуются агрегаты и hashes.
2. **Работоспособность:** другой участник запускает точный candidate SHA на VM
   по README; известны ошибки, exit codes, cold setup/load, warm latency, RSS,
   фактический режим и один run ID полного комплекта. Workaround означает
   дефект и повтор приёмки нового SHA, а не успешный прогон старого.
3. **Практическая польза:** число корректных предложений и остаток review/abstain,
   время действий оператора относительно измеренного manual baseline,
   compute/API расходы с раскрытыми допущениями. Неизмеренная экономия и влияние
   на продажи остаются гипотезами. Две репетиции питча — в #54.

## Что нельзя считать выполненной приёмкой

85.07% F1 из PR #80 — согласие с просмотренным development AI-reference после
доработки guards. Это не независимое качество, не критерий успешности новой
выборки и не разрешение auto_accept. В judged development-наборе не было
absent-брендов. Test reserve не используется для настройки. Synthetic PASS,
точная цитата, число тестов, успешный запуск и качество разметки измеряют разные
свойства; ни одно из них не заменяет остальные.

План не объявляет реализацию новых Issues завершённой, не назначает людей без
их claim и не разрешает merge/release в обход действующего процесса.
