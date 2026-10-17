# Повторная оценка на расширенном reviewed-reference v2

17 октября 2026 года. Оценка на AI-assisted human-reviewed validation subset:
**12 карточек / 67 judged-пар**, TP=29, FP=1, FN=21, precision **96,7%**,
recall **58,0%**, micro-F1 **72,5%**. Rules baseline и evaluator не изменились.
Изменился состав reference: это не сравнение двух моделей или улучшение качества.
[Первый замер reviewed-v1](first_baseline_evaluation.md) сохранён без изменений.

## Что подтверждено

Пользователь явно закрыл R17/R19/R21/R22/R23: бренд, два составных цвета,
модели и статус ошибочной единицы. Для этих пяти карточек завершена накопленная
проверка; аналогичные непроверенные AI-карточки не повышались до manual.
Итого 22 полные проверки / 130 пар в `review.human-reviewed.v6.jsonl`.
Полный AI-набор v4 не переписывался; round5 feedback/manifest и новая ручная часть
сохраняются отдельно. Точный журнал — локальный `data/gold/e1/ai/review.round5.feedback.json`.

Согласовано **1 TB = 1000 GB**. Никакой обязательной замены Tb→TB или
безусловного «RAM без единицы всегда GB» не утверждено. Для R03/R04 сохранены
частичные статусы; предлагаемые значения памяти остаются контекстными.
Ошибочная масса вместо объёма — unjudgeable/review; через плотность не переводится.
Рекомендация отправлять отсутствующие/неправильные единицы на review согласуется
с текущей инструкцией, но новые runtime-механизмы этим этапом не реализованы.

## Замороженный состав

| Split | Карточки | Смартфоны / чайники | Пары | Present | Absent | Ambiguous | Unjudgeable | Judged |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | 10 | 4 / 6 | 58 | 37 | 20 | 1 | 0 | 57 |
| Validation | 12 | 6 / 6 | 72 | 50 | 17 | 4 | 1 | 67 |

Reference: `data/gold/e1/reviewed/reviewed-v2/` с отдельными split JSONL,
manifest и canonicalization ledger. Пять ambiguous и одна unjudgeable-пара
исключены из P/R/F1; два частичных review исключены целиком. Прежние 17 карточек
имеют те же значения и spans после прежней канонизации регистра брендов.
В v2 только четыре изменения регистра по существующему config, включая одно
добавленное в расширении; новых алиасов и unit defaults нет.

Проверены source/artifact SHA, исходные тексты, category/SKU/split/group,
порядок атрибутов, числа, единицы и raw evidence. Использован прежний predict:
10 324 строки, все processed; code/config hashes совпали. Missing и unprocessed
на обоих оцениваемых split равны 0. Аудит точных/нормализованных дублей из v1
переиспользован с проверкой неизменности всего входа; аудит близких дублей ожидается.
Test_reserved не оценивался, правила и пороги не подбирались по validation.

## Метрики

Единица — SKU×атрибут. Judged — present/absent; support — present. Неверное
value+unit даёт FP+FN, пропуск present — FN, выдача на absent — FP. Неопределённые
метрики остаются null/N/A. Coverage в таблицах — кандидаты/judged, все кандидаты
остаются review с heuristic confidence. Auto-accepted=0. Coverage не равно точности.

| Split | Срез | Judged | Present | TP | FP | FN | P | R | F1 | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | `482` | 30 | 16 | 4 | 1 | 12 | 80.0% | 25.0% | 38.1% | 5/30 |
| development | `761` | 27 | 21 | 14 | 0 | 7 | 100.0% | 66.7% | 80.0% | 14/27 |
| development | `micro` | 57 | 37 | 18 | 1 | 19 | 94.7% | 48.6% | 64.3% | 19/57 |
| validation | `482` | 29 | 20 | 10 | 1 | 10 | 90.9% | 50.0% | 64.5% | 11/29 |
| validation | `761` | 38 | 30 | 19 | 0 | 11 | 100.0% | 63.3% | 77.6% | 19/38 |
| validation | `micro` | 67 | 50 | 29 | 1 | 21 | 96.7% | 58.0% | 72.5% | 30/67 |

### По атрибутам

| Split | Срез | Judged | Present | TP | FP | FN | P | R | F1 | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | `battery_mah` | 4 | 1 | 0 | 0 | 1 | N/A | 0.0% | 0.0% | 0/4 |
| development | `brand` | 10 | 10 | 6 | 1 | 4 | 85.7% | 60.0% | 70.6% | 7/10 |
| development | `capacity_l` | 6 | 3 | 1 | 0 | 2 | 100.0% | 33.3% | 50.0% | 1/6 |
| development | `color` | 9 | 4 | 1 | 0 | 3 | 100.0% | 25.0% | 40.0% | 1/9 |
| development | `model` | 10 | 9 | 0 | 0 | 9 | N/A | 0.0% | 0.0% | 0/10 |
| development | `power_w` | 6 | 1 | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1/6 |
| development | `ram_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| development | `screen_inches` | 4 | 1 | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1/4 |
| development | `storage_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| validation | `battery_mah` | 6 | 2 | 1 | 0 | 1 | 100.0% | 50.0% | 66.7% | 1/6 |
| validation | `brand` | 12 | 12 | 11 | 0 | 1 | 100.0% | 91.7% | 95.7% | 11/12 |
| validation | `capacity_l` | 5 | 3 | 2 | 1 | 1 | 66.7% | 66.7% | 66.7% | 3/5 |
| validation | `color` | 12 | 8 | 3 | 0 | 5 | 100.0% | 37.5% | 54.5% | 3/12 |
| validation | `model` | 12 | 12 | 0 | 0 | 12 | N/A | 0.0% | 0.0% | 0/12 |
| validation | `power_w` | 6 | 3 | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% | 3/6 |
| validation | `ram_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| validation | `screen_inches` | 6 | 2 | 1 | 0 | 1 | 100.0% | 50.0% | 66.7% | 1/6 |
| validation | `storage_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |

### Категория × атрибут

761 — смартфоны, 482 — чайники.

| Split | Срез | Judged | Present | TP | FP | FN | P | R | F1 | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | `482:brand` | 6 | 6 | 2 | 1 | 4 | 66.7% | 33.3% | 44.4% | 3/6 |
| development | `482:capacity_l` | 6 | 3 | 1 | 0 | 2 | 100.0% | 33.3% | 50.0% | 1/6 |
| development | `482:color` | 6 | 1 | 0 | 0 | 1 | N/A | 0.0% | 0.0% | 0/6 |
| development | `482:model` | 6 | 5 | 0 | 0 | 5 | N/A | 0.0% | 0.0% | 0/6 |
| development | `482:power_w` | 6 | 1 | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1/6 |
| development | `761:battery_mah` | 4 | 1 | 0 | 0 | 1 | N/A | 0.0% | 0.0% | 0/4 |
| development | `761:brand` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| development | `761:color` | 3 | 3 | 1 | 0 | 2 | 100.0% | 33.3% | 50.0% | 1/3 |
| development | `761:model` | 4 | 4 | 0 | 0 | 4 | N/A | 0.0% | 0.0% | 0/4 |
| development | `761:ram_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| development | `761:screen_inches` | 4 | 1 | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% | 1/4 |
| development | `761:storage_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| validation | `482:brand` | 6 | 6 | 5 | 0 | 1 | 100.0% | 83.3% | 90.9% | 5/6 |
| validation | `482:capacity_l` | 5 | 3 | 2 | 1 | 1 | 66.7% | 66.7% | 66.7% | 3/5 |
| validation | `482:color` | 6 | 2 | 0 | 0 | 2 | N/A | 0.0% | 0.0% | 0/6 |
| validation | `482:model` | 6 | 6 | 0 | 0 | 6 | N/A | 0.0% | 0.0% | 0/6 |
| validation | `482:power_w` | 6 | 3 | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% | 3/6 |
| validation | `761:battery_mah` | 6 | 2 | 1 | 0 | 1 | 100.0% | 50.0% | 66.7% | 1/6 |
| validation | `761:brand` | 6 | 6 | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% | 6/6 |
| validation | `761:color` | 6 | 6 | 3 | 0 | 3 | 100.0% | 50.0% | 66.7% | 3/6 |
| validation | `761:model` | 6 | 6 | 0 | 0 | 6 | N/A | 0.0% | 0.0% | 0/6 |
| validation | `761:ram_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |
| validation | `761:screen_inches` | 6 | 2 | 1 | 0 | 1 | 100.0% | 50.0% | 66.7% | 1/6 |
| validation | `761:storage_gb` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% | 4/4 |

development: macro-F1 по определённым атрибутам 62.3%; correct coverage 18/57; кандидаты по всем применимым парам 20/58; card coverage 7/10; все атрибуты заполнены на 0 карточек.

validation: macro-F1 по определённым атрибутам 72.2%; correct coverage 29/67; кандидаты по всем применимым парам 31/72; card coverage 12/12; все атрибуты заполнены на 0 карточек.

## Выводы и ограничения

В development добавились два FN и один FP: модель по-прежнему не извлекается,
а укороченный бренд не совпадает с явно подтверждённым полным брендом. Это
семантическое отличие, его нельзя скрыть приведением регистра или изменением gold.
Всего development: 19 FN, 1 FP, из FN **9 относятся к model**. Приоритеты прежние:
model-прототип участника B, затем согласованные цвета/бренды и числовой разбор.
Текущая работа лишь фиксирует исходную точку, исправлений extractor здесь нет.

Реальные по-SKU решения и ошибки сохранены только в локальных
`outputs/evaluation/reviewed-v2/{development,validation}.pairs.jsonl`, исключённые
пары — в `*.excluded.jsonl`. Два вопроса памяти — в `pending_review.md` того же
каталога. Результат с другой выборкой нельзя интерпретировать как деградацию
или прирост метода. Нужны отдельная слепая разметка, аудит близких дублей,
Linux-воспроизводимость и последующий ML или LLM-эксперимент.

Это маленькая неслучайная выборка с AI-assisted происхождением и участием автора
baseline. Validation участвовал в обсуждении инструкции, не независимый holdout.
Интервалы, calibration, трафиковые веса и fairness по продавцам не оценены.
Наличие точного span не делает неправильное число/единицу истинным свойством.
Внешние API, VM, обучение, commit/push/PR не запускались.

## Воспроизведение и hashes

Локальные `record_round5.py` и `report_and_verify.py` в каталоге результатов
сохраняют алгоритм записи подтверждений и проверки. Первый использует неизменный
helper reviewed-v1, его hash входит в lineage. Исходные артефакты не перезаписаны.
Оценка CLI выполнялась с кодом без изменений (Windows 11 / Python 3.12.6):

```powershell
.\.venv\Scripts\python.exe -m goodsai.cli evaluate --predictions outputs/baseline/predictions.jsonl --gold data/gold/e1/reviewed/reviewed-v2/development.jsonl --output outputs/evaluation/reviewed-v2/development.check.json
.\.venv\Scripts\python.exe -m goodsai.cli evaluate --predictions outputs/baseline/predictions.jsonl --gold data/gold/e1/reviewed/reviewed-v2/validation.jsonl --output outputs/evaluation/reviewed-v2/validation.check.json
```

Для повторного прогона выбирайте новый output: CLI сам не защищает прежний
производный файл от перезаписи. На машине без локальных data/outputs reference
отсутствует; Git его не передаёт. Подробные P/R/F1, support, score bins и все
числовые метрики — в `*.metrics.json`, identity/CLI exit codes — в `run.manifest.json`.
Независимым пересчётом через множества проверены все 24 среза каждого split;
shared runtime/tests не менялись.

| Артефакт | SHA-256 |
| --- | --- |
| `review.round5.feedback.json` | `6b006670017beb49eee8d2cc976eea350367e049d36709583ecf96431556edf7` |
| `review.human-reviewed.v6.jsonl` | `6c1ff2b5a38508205145813795c0d2e7af5d63b24f3a51579fd283474007bddc` |
| `review.manifest.v6.json` | `60954dec1379ebbb51f3f6f4296cd3b648ab45005d58fc018d9cc21fb86ee1a5` |
| `manifest.json` | `c79b634da8c6d1997b57740d40a59ce9d1aca00302d223471f6fab1c5e399cc2` |
| `development.jsonl` | `f074c56caccff60cbb8214ce5fb64e8da37822e26ba14ef3932702bb97ebc23f` |
| `validation.jsonl` | `d631947c81f1afada22be842ed95c5c305a26a34f7800ce237e4cebd9404bb44` |
| `development.metrics.json` | `0bea3026f1c25b5faeb29230834954e65fcbc7aa2d43df9fc07e59cab6ee61a8` |
| `validation.metrics.json` | `3281691319aae32374b2c3432f85d30d541c27753bc3c38bc42ff4e89bf7065a` |
| `run.manifest.json` | `698c621503dc1828143590f1f0c5015e520da6ec3efff6253e6cb97de9260337` |
| `predictions.jsonl` | `5febad69819ec45c779e1692cd0766ad55734577b0feff1c77a72fa1f2f6f3b5` |
| `code_sha256` | `984d1df97bfb2c329c36581b726ad0a87f47c5ecb168b80bd2b80fd543ae0a05` |
| `config_sha256` | `38a0167cb90ecc9f63122014d6acac8534ef5fed74f3b031ab1c9c9a969feb41` |
