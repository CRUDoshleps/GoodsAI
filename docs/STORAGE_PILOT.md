# Ограниченный opt-in storage auto_accept

22.10.2026 Владислав согласовал цель precision **97%** для пилота `storage_gb`
смартфонов. Политика `storage-pilot-97-v1` — узкое исключение из default review.
Она добавляет решение `auto_accept` в существующий объект v0.1; поля, units,
числовые значения, evidence и heuristic confidence остаются прежними.
Сервис возвращает предложение решения, в боевой каталог ничего не записывает.

## Что подтверждено и что остаётся ограничением

В завершённом аудите 145 предложений правил проверены человеком: 145 correct,
0 incorrect/pending/unresolved. Условная нижняя односторонняя 95%-граница —
97,955%. Этот аудит был family-balanced, с видимыми предложениями, одним
разработчиком-reviewer; это не independent calibration и не оценка всех продавцов.
Граница опирается на биномиальные предпосылки, не устраняет selection/reviewer bias.

Изначальная цель 99% не выполнена. [Исходный отчёт](../reports/storage_shadow_20261022.md)
и [протокол](STORAGE_SHADOW.md) остаются неизменными. Новая цель выбрана **после
результатов**, это решение о допустимом риске пилота, а не новый заранее
зафиксированный эксперимент. Независимая калибровка остаётся незавершённой.

97% означает целевую precision группы принятых значений, а не cutoff score=0.97
или вероятность конкретного значения. Эвристический score, например 0.8, не
переименовывается в calibrated confidence. При target=0.99 та же группа
возвращается в review, поскольку 97,955% < 99%. Ни один target не обещает
гарантированного качества нового потока.

## Область и проверки

Только category `761`, `storage_gb`, нормализованная единица GB, method=rule,
правило `memory.context.v1` либо `memory.title-pair.v1`. В title явно указан
смартфон/smartphone, нет маркеров аксессуара/часов; нет memory conflicts или
reason_codes кандидата. Это та же область, что у storage-shadow-1.

Сначала действуют обычные schema, canonical value, exact evidence и semantic
verifier. Затем применяется pilot policy. При проверке auto_accept с исходным
Product дополнительно восстанавливаются допустимые rule-кандидаты: ложный
rule_id, чужое значение/цитата, несовместимые RAM/storage не проходят.
Проверка сохранённого результата без Product только структурная; для полной
проверки grounding необходимо передать исходный текст.

LLM-кандидаты и другие атрибуты автоматически не принимаются. Default pipeline
не меняет решений. Профиль с изменёнными правилами, aliases, bounds, категориями
или ablation не может повторно использовать этот аудит: включение отклоняется
до inference. Настройки API/LLM можно менять отдельно, но LLM не получает права
auto_accept. Изменение runtime-правил требует нового аудита и версии политики.

## Запуск

Из checkout после установки проекта; outputs — приватный каталог вне Git:

```bash
python -m goodsai.storage_acceptance --target-precision 0.97 --output outputs/storage-pilot-97.json
python -m goodsai --config outputs/storage-pilot-97.json predict --input /private/cards.jsonl --output outputs/pilot-predictions.jsonl
python -m goodsai.api --config outputs/storage-pilot-97.json --host 0.0.0.0 --port 8000
```

Используйте интерпретатор установленного окружения: `.venv/bin/python` на Linux
или `.\.venv\Scripts\python.exe` в PowerShell. Последняя команда запускает
новый процесс; существующий сервис и ВМ инструмент не меняет.

Генератор пишет полный валидированный профиль, отказывается перезаписывать файл.
Настройки (общие для CLI/API):

```json
{
  "auto_accept_enabled": true,
  "auto_accept": {
    "policy_version": "storage-pilot-97-v1",
    "target_precision": 0.97
  }
}
```

Ячейка `runtime.auto_accept_policies["761"]["storage_gb"]` в штатном профиле
уже привязана к `storage-pilot-97-v1`; остальные ячейки обеих категорий — `review`
и включены быть не могут ([матрица](CONFIGURATION.md#матрица-auto_accept-по-категориям-conf-007)).
Это фрагмент `runtime`, не самостоятельный конфиг. Допустимый target `[0.97,1]`.
Более строгая цель может отключить принятие; более слабая, неизвестная версия,
пустая политика или один флаг без политики отклоняются. API `/health` и batch
manifest показывают enabled/active, target, причину, audit hash и independent=false.
Сам API request не может включить режим или передать порог.

Для rollback запустите с исходным default config либо установите
`runtime.auto_accept_enabled=false`. Все прежние значения снова review.
Ошибки/неоднозначность по-прежнему abstain. Смена настройки требует перезапуска
процесса; публичного endpoint управления политикой нет.

## Воспроизведение измерений

```bash
python -m scripts.research.storage_pilot reassess --audit-dir /private/completed-audit --target-precision 0.97 --output-dir outputs/pilot-reassessment-new
python -m scripts.research.storage_pilot compare --input /private/frozen-development/input.jsonl --previous-predictions /private/storage-shadow/predictions.jsonl --output-dir outputs/pilot-comparison-new
```

Первый вызов проверяет sealed пакет, ответы/числа известного аудита и заново
считает границу; старые метрики не меняются. Второй сравнивает default, 97% и
99%, каждое значение/unit/score/evidence/reason и решения, повторяет 97% для
проверки идентичности bytes. Это проверка выполнения политики, не новая human
precision. Каталог, reserve и внешние модели для неё не нужны. Реальные inputs,
predictions, формы, labels и manifests остаются приватными; в Git только агрегаты.

## Условия остановки

Новая ошибка в auto-accepted storage, иной домен/категория/grammar, изменение
правил или неподтверждённая область — отключить профиль, вернуть review и
провести новый аудит. Не расширять приёмку на все поля или незнакомые категории.
Независимое качество, drift monitoring и production SLA этим пилотом не доказаны.

## Фактический прогон

[Числовой отчёт](../reports/storage_pilot_20261022.md) и
[JSON](../reports/storage_pilot_20261022.json): на прежних 2974 карточках
1528 полей перешли из review в auto_accept. Извлечение не изменилось; это
выполнение политики на development, не новый независимый quality benchmark.
