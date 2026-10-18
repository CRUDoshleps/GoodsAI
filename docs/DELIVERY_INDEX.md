# GoodsAI — индекс воспроизведения и сдачи

18 октября 2026, demo из `feature/vlad-reproducible-demo` (main через PR #8),
публикация outputs R3 из `feature/vlad-atomic-output`, пакет 0.1.0,
контракт E1 v0.1; M1 с исправлениями — правила rules-0.2.1-model-boundaries.
[Сравнение M1](research/model_stage_results.md) сохранено;
[две ошибки обработаны](research/model_boundary_fix_results.md) без потери прежних TP
на просмотренных карточках. Этот feedback не является независимой оценкой.
Дополнительно подготовлен [M2: 20 новых reviewed development и A/B/C](research/m2_evaluation_results.md):
C P/R/F1 95,1/69,9/80,6%, 12 новых model TP без новых FP относительно A.
Реальные reference/predictions локальны; 40 test-карточек только зарезервированы.
M2 не является ML/LLM-экспериментом или независимой оценкой; runtime не менялся.
Индекс описывает фактически существующее
и открытые пункты. Изменения передаются через указанные feature-ветки;
фактический commit проверяется через Git. На ВМ эта demo-версия не устанавливалась.
Требования: [REQUIREMENTS_AND_DELIVERY](REQUIREMENTS_AND_DELIVERY.md).

## Шесть артефактов

| Артефакт | Где / воспроизведение | Состояние |
| --- | --- | --- |
| 1. Воспроизводимый код/ноутбук | [src/goodsai](../src/goodsai/), [pyproject](../pyproject.toml), [tests](../tests/); установка и demo-команда в README | Rules CLI + временный HTTP работают, model извлекается правилами; ML/LLM ещё нет |
| 2. README | [README](../README.md): установка Windows/Linux, одна команда демо, полный пример входа/выхода, HTTP и ограничения | Демо не требует raw/gold; установка из wheel проверяется отдельно от editable |
| 3. EDA | [dataset_findings](research/dataset_findings.md), [baseline_results](baseline_results.md), [research scripts](../scripts/research/) | Сохранённый анализ и происхождение; сырые данные/проекция не передаются Git. Точный порядок получения проекции — в baseline.md, повторный полный EDA для демо не нужен |
| 4. Pipeline | [baseline](baseline.md), [контракт](research/architecture_and_contract.md), [cli](../src/goodsai/cli.py), [extractor](../src/goodsai/verify.py), [API](../src/goodsai/api.py) | title/description → rules → нормализация → verifier → JSONL/JSON; seller_attributes только [] |
| 5. Файл предсказаний | Синтетический: `outputs/demo/predictions.jsonl` после demo; реальный пилот: локальный `outputs/baseline/predictions.jsonl`, 10 324 строки | Синтетический файл воспроизводится из Git; реальный файл существует локально, канал выдачи организаторам и полный scope каталога не согласованы |
| 6. Финальная презентация | [Материалы продуктового этапа](product-stage/README.md) уже есть | Финальной технической презентации с измеренным сравнением методов нет. Продуктовая презентация её не заменяет |

## Запуск без исходных данных

После установки из README (Python 3.12+):

```bash
python -m goodsai.demo --output-dir outputs/demo
```

Команда создаёт только новый каталог; для повтора выбирается другое имя.
Исходники вымышленных примеров и ожиданий поставляются **один раз** внутри
`goodsai/examples/synthetic/`, включены в wheel. Это выбранный вместо
верхнеуровневого examples/ источник, чтобы работать вне checkout без дубликатов.

| Выход | Содержание / проверка |
| --- | --- |
| input.jsonl | Байтовая копия встроенных шести синтетических строк; SHA в manifest и summary |
| predictions.jsonl | Реальный batch predict; 4 processed, 1 unsupported_category, 1 invalid_input; SHA в manifest и summary |
| predictions.manifest.json | Динамические input/output/code/config SHA, run_id, версии/среда, статусы/причины, время/RSS |
| summary.json | 6 проверок сценариев, значения/единицы/review/abstain/raw evidence проверены; SHA и относительные пути трёх остальных файлов; SHA ресурса ожиданий |

Все пути в summary.artifacts относительны к каталогу summary. Файл не содержит
собственного SHA: это потребовало бы внешнего manifest. Фиксированный hash
предсказаний не используется как критерий успеха. Байты predictions одинаковы
при одинаковых входе/code/config; времена/RSS и SHA manifest ожидаемо меняются.
Добавление demo.py меняет code identity, не правила. Полный SHA кода/config и
git_dirty важнее одного commit ID незакоммиченной версии. В установленном wheel
вне Git git_commit/git_dirty могут быть null; код/config SHA всё равно вычисляются.

Пример отдельного batch-вызова после demo (в новый файл):

```bash
python -m goodsai.cli predict --input outputs/demo/input.jsonl --output outputs/demo/predictions.repeat.jsonl
```

Проверки примеров не являются оценкой качества реального каталога и не дают
P/R/F1. Не переносить их ожидания в gold; lookup по SKU в extractor отсутствует.

## Реальные данные, оценки и версии

Подготовка входа из доверенной проекции описана в
[baseline: воспроизведение на другом компьютере](baseline.md#как-воспроизвести-на-другом-компьютере).
Нужны официальные локальные raw, inventory и доверенная Parquet-проекция;
target-поля не передаются extractor. API/demo/predict не десериализуют pickle.

Для нового реального запуска при наличии входа выбирать новый output:

```bash
python -m goodsai.cli predict --input data/processed/e1/pilot.jsonl --output outputs/baseline/new-run/predictions.jsonl
python -m goodsai.cli evaluate --predictions outputs/baseline/new-run/predictions.jsonl --gold data/gold/e1/reviewed/reviewed-v2/validation.jsonl --output outputs/baseline/new-run/validation.metrics.json
```

Эти команды не выполняются демо и не работают в чистом checkout без данных.
Они создадут **новый** run, не побайтную копию исторического benchmark.
CLI predict/evaluate умеют перезаписывать производный output: для сохранения
прежнего запуска выбирать новый путь. R3 добавляет OS-блокировки и уникальные
tempfiles; predict публикует пару с журналом восстановления, evaluator читает
через проверку SHA под блокировкой. Одновременный конкурент получает ошибку.
Подробности и границы: [восстановление output](runbooks/output_recovery.md).

| Результат | Версия, происхождение / ссылка |
| --- | --- |
| E1 полный пилот, 10 324 predictions | Локально `outputs/baseline/predictions.jsonl` + `.manifest.json`; [агрегаты](baseline_results.md), прежний run_id `8a72d1342ed8e7a6f13d` |
| Исторический вход E1 | input SHA `68875ae2ef66c3527915be0e2cca29639c4a1c792e359973ae8623a404b70fe3` |
| Исторические predictions | SHA `5febad69819ec45c779e1692cd0766ad55734577b0feff1c77a72fa1f2f6f3b5` |
| Историческая реализация/config | code SHA `984d1df97bfb2c329c36581b726ad0a87f47c5ecb168b80bd2b80fd543ae0a05`; config SHA `38a0167cb90ecc9f63122014d6acac8534ef5fed74f3b031ab1c9c9a969feb41` |
| Reviewed reference v2 | 22 полные AI-assisted human-reviewed карточки: 10 development / 12 validation; локально `data/gold/e1/reviewed/reviewed-v2/manifest.json` |
| Reference manifest | SHA `c79b634da8c6d1997b57740d40a59ce9d1aca00302d223471f6fab1c5e399cc2`; источники и SHA split/метрик — в [reviewed-v2](research/baseline_evaluation_v2.md#воспроизведение-и-hashes) |
| Оценка reviewed-v2 | Локально `outputs/evaluation/reviewed-v2/run.manifest.json` и `development.metrics.json`, `validation.metrics.json`; [неизменный отчёт](research/baseline_evaluation_v2.md) с командами и всеми per-attribute/per-category срезами |

Validation: 12 карточек, 67 judged-пар, TP=29, FP=1, FN=21,
P=96,7%, R=58,0%, F1=72,5%. Ambiguous/unjudgeable исключены с учётом знаменателей;
development не входит в validation. Обсуждение политики затронуло validation:
это маленький неслучайный AI-assisted reference, не независимый holdout.
Candidate coverage в отчёте — 30/67 judged-пар; auto-accepted coverage — 0/67.
Наличие score и evidence не доказывает истинность атрибута.

Первый prediction manifest создан до reviewed-reference и содержит статус
`not_evaluated_without_manual_gold`. Последующая оценка хранится отдельно в
reviewed-v2; исторический manifest ради нового текста не переписывается.

## Что осталось для полного комплекта

Реальные predictions/reference/raw остаются вне Git. Нужен согласованный
канал передачи итогового файла/manifest организаторам; если нужен именно Git,
сначала согласовать исключение из политики публикации данных. До этого артефакт
5 закрыт только для воспроизводимого синтетического демо, не для всего каталога.
Нужны модельный эксперимент, расширение независимого reference, финальная
техническая презентация и официальный API после выдачи требований.
Детали: [план после ревью](research/post_review_plan.md).

ВМ: пользователь подтвердил прежний HTTP/systemd smoke. Этот demo-релиз на ВМ
не устанавливался; его Windows/wheel-проверки не являются Linux-проверкой.
