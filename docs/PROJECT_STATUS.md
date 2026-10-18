# Состояние проекта

Актуально на 19 октября 2026 года.

## Версии

| Назначение | Репозиторий/ветка | Commit |
| --- | --- | --- |
| опубликованный технический baseline | Gitea `main` | `48b45dc` |
| рабочая интеграционная база | GitHub `integration/current` | ветка от `48b45dc` с новой документацией |
| реорганизация командной работы | GitHub `docs/gov-001-team-workflow` | `dab5a48` + status handoff |
| runtime schema | `0.1` | — |
| rules | `rules-0.3.0-m2-policy` | — |
| dictionaries | `manual-reviewed-brand-and-color-names-v2` | — |

GitHub и Gitea имели независимые истории. Актуальный код Gitea перенесён в
GitHub `integration/current` без переписывания существующих `main`/`dev`.

## Реализовано

- Python 3.12 package, CLI и временный FastAPI service;
- text-only вход с запретом неизвестных и target-подобных полей;
- смартфоны `761` и чайники `482`;
- rules extraction бренда, явной модели, памяти, экрана, батареи, цвета,
  мощности и объёма в соответствии со схемой категории;
- normalizer для единиц, чисел, модели и aliases;
- точные raw evidence spans и schema validation;
- конфликт → abstain, кандидат → review;
- атомарная запись predictions/manifest и блокировка writers;
- run identity: hashes кода/конфига/входа/выхода, Git SHA и ресурсы;
- синтетическое демо на шести сценариях;
- evaluator с per-attribute метриками и coverage;
- systemd unit и runbook для VM.

## Не реализовано

- реальный LLM или обученный encoder в основном inference path;
- cost-aware router между правилами и моделями;
- калиброванный confidence и `auto_accept`;
- независимый human gold/test;
- полная поддержка ноутбуков и новых категорий;
- обработка непустых seller attributes;
- финальный официальный API contract;
- готовый release predictions-файл, доступный вместе с metrics/manifest;
- финальная техническая презентация по фактическому результату.

## Данные и оценка

Рабочий пилот содержит 10 324 SKU двух категорий. Реальные данные, reference и
predictions хранятся локально и исключены из Git.

Последний development-набор M2: 20 карточек, 120 полей, из них 83 present,
32 absent и 5 ambiguous; 115 judged-пар. После policy fixes rules получили
`69 TP / 0 FP / 14 FN`, `P=100%`, `R=83,1%`, `F1=90,8%`.

Это AI-assisted human-reviewed development, просмотренный во время настройки.
Он доказывает исправление известных примеров, но не качество на независимом
test и не перенос на весь каталог.

Более ранний reviewed-v2 validation: 12 карточек / 67 judged-пар,
`P=96,7%`, `R=58,0%`, `F1=72,5%`. Выборка также мала и не полностью
независима. Единый источник трактовки: [EVALUATION.md](EVALUATION.md).

## Проверки

Последний сохранённый отчёт команды для опубликованного функционала:

- 82 tests на Windows/Python 3.12.6;
- demo 6/6;
- CLI/API parity на синтетических входах;
- предыдущая версия сервиса запускалась на VM и отвечала на health/predict.

Это исторический результат из ветки Gitea. Для текущей GitHub-ветки проверка
документации выполняется отдельно; перед любым релизом нужен новый полный прогон
на том же SHA, который пойдёт в Gitea.

## Результат организаторского review

По скриншотам первого технического прогона оценённые критерии дали 17,17/20.
Неоценённый блок качества результата оставался пустым. Product checkpoint —
10/10, но способ его включения в общий балл не описан.

Организаторы подтвердили сильные стороны: работающий end-to-end baseline,
модульность, тесты, JSONL output и документация. Основной долг:

1. модельный/LLM слой в runtime;
2. конфигурируемые решения и thresholds;
3. готовые predictions и metrics, связанные с одним запуском;
4. более простой воспроизводимый сценарий для пользователя;
5. эксплуатационные проверки и явные fallback.

Атомарная запись, явная model grammar и часть policy problems уже исправлены.
Остальные пункты находятся в [TASKS.md](../TASKS.md).

## Приоритеты

### P0 — доказать результат

1. Независимый blind human gold/test.
2. Аудит split, дублей и leakage.
3. Официальный predictions-файл + manifest + metrics.
4. Вынести конфигурацию и подтвердить contract.
5. Воспроизвести последний SHA на VM.
6. Настроить безопасный GitHub → Gitea release.

### P1 — добавить гибрид

1. Подключить OpenAI-compatible LLM gateway за adapter.
2. Сравнить rules, LLM-only и rules→LLM на frozen validation.
3. Добавить общий relation verifier и budget guard.
4. Проверить компактный encoder только при наличии достаточной разметки.

### P2 — продуктовый контур

1. Review UI с evidence и причинами.
2. Active learning из проверенных исправлений.
3. Seller/category quality dashboard и downstream A/B.

## Риски

| Риск | Текущее снижение | Следующее действие |
| --- | --- | --- |
| галлюцинации | no evidence → reject | общий verifier для LLM |
| завышенная метрика | provenance и честная пометка development | независимый test |
| утечка target | строгий text-only contract | split/leakage audit |
| стоимость LLM | вызовов сейчас нет | budget и cost metrics |
| конфликт участников | task claim и один owner | PR review и интегратор |
| расхождение репозиториев | отдельные work/release remotes | release manifest с source SHA |
| секреты в истории | `.gitignore`, env-only | немедленная ротация показанных секретов |

## Следующее решение команды

Не выбирать большую модель до готовности EVAL-001. Сначала получить честный
gold и release artifact, затем измерить самый простой гибрид rules → fast LLM.
Encoder добавлять, если эксперимент покажет пользу по качеству, цене или latency.
