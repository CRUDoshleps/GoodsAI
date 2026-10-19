# EVAL-006: результат и дальнейшие проверки

Владислав / urasha. Frozen baseline `977c5ed`; итоговый producer `f33e3fc`
после включения текущего main `62898fb` с LLM-003 коллеги.
Реализация отдельного silver-этапа; runtime v0.1 и manual evaluator не менялись.

PR Глеба #90 принят коллегой в main во время подготовки нашего PR #95.
Новый main включён в рабочую ветку; сохранены обе стороны конфликтов в статусе
и allowlist. Повторены 3037 predictions: значения/decisions/evidence совпали
с доинтеграционными побайтно после исключения одного поля run_id.
266 основных tests и 3 reader tests прошли; новый clean-run 11/11 passed.
Данные и frozen reference повторно не подбирались. В main/Gitea наш PR не слит.

## Фактический результат

- 3037 карточек / 1270 семейств из audited development/validation-feedback.
- 7244 исходные строки исключены как quarantine/test/protected; ещё 43 как
  exposed validation-family из дополнительных ledgers. 40 резервных карточек
  не выводились и не предсказывались.
- Input/ref/metadata разделены. Каталожные bins ограничивают точные значения,
  не превращаются в выдуманный point label. Нет source gold в input.
- 19 033 обязательные пары; 11 935 known, 5065 unknown, 2033 conflict.
- Agreement: 7522 TP / 425 FP / 4413 FN; P 94,65%, R 63,02%, F1 75,67%.
- Supported recall 75,75%; candidate coverage 54,31%; оценимы по reference
  76,88% найденных кандидатов. Traffic F1 77,56% (число query_clicks-строк).
- 95% family-bootstrap CI F1: 70,58–78,18%. Это неопределённость agreement,
  не независимой human quality. Большие семейства влияют на итог.
- Rare-reference F1 50,09% против frequent 80,98%; rare определены по fit,
  это подтверждает необходимость проверки длинного хвоста.
- Модель остаётся сложной: 1902 catalog conflicts; несовпадение коммерческого
  имени с кодом и brand/subbrand требует adjudication, не исправления наугад.
- Большая часть battery reference не подтверждена matcher в исходном тексте.
  Недостающие в тексте характеристики нельзя восполнить угадыванием LLM.
- Brier raw 0,06575 → fitted 0,03865 → Platt 0,03870. Platt не улучшил fitted;
  ECE меняется с bins/reference. Все результаты offline на silver-development,
  вероятность истинной правильности не доказана; auto_accept запрещён.
- API calls 0; compute cost в рублях N/A. Первый/повторный inference и timing
  зафиксированы в run_stats; значения predictions идентичны.

Первый черновой F1 84,22% в outputs использовал неполный reference из-за
неразличения bins и exact. Итоговый reference добавил оцениваемые числовые поля.
Изменение F1 не является регрессией/улучшением extractor: правила не менялись.
Исторические каталоги v1/v2 сохранены; публикуется итоговый v3/final.

## Состояние частей плана

| Часть | Доказательство | Граница |
|---|---|---|
| V0 | Протокол, seed, SHA, mapping и metric definitions | Review команды через PR; deadline остаётся предположением PDF |
| V1 | Private bundle с source/output SHA, auditable split и train handoff | Две категории; seller/brand crossings раскрыты; история exposure не объявляется полной |
| V2 | Повторяемые reports и synthetic tests; exact evidence validated | Support matcher ожидает ручного аудита |
| V3 | Logistic + Platt с отдельными группами и measured Brier/ECE | Только offline; независимый probability/threshold gate не пройден |
| V4 | Full/subset paired comparison tool, usage adapter PR #90, frozen 200-card packet | Живые registry/GLiNER/LLM candidate predictions не предоставлены: not_run, качество не выдумано |

## Передача команде

- Тимуру: `train.jsonl`, `train.split.json`, `train.traffic.json` из приватного
  bundle v3, плюс manifest. Только fit, без test/validation текста. Это ещё не
  top-30 выгрузка. Для масштабирования нужен agreed mapping новых схем.
- Глебу: `llm_screening.input.jsonl` и manifest v3, 200 dev-карточек по 200
  семействам, 100 каждой категории. На VM использовать policy/ledger PR #90,
  100 calls/run, 300/day, concurrency 2 и фактический общий остаток бюджета.
  В ответ нужны predictions/manifest с hashes, usage/cost/failures. Здесь вызовов нет.
- Грише: только публичные `reports/metrics.md`, `reports/run_stats.json`,
  README-команды и существующий release builder. Исходные карточки не публиковать.
- Reviewer: проверить `support_review.blank.jsonl`, фиксированные S001…,
  заполнить human_support/human_correctness/reviewer либо сообщить S-номер и
  исправление. Не переименовывать эти проверки в независимый gold.

EVAL-001/003/004/005 не закрываются этой задачей. После готовности методов —
frozen сравнительный прогон; независимый test только после общего freeze.
Исправление известного RED SOLUTION остаётся VER-001 #15, отдельно от evaluation.
