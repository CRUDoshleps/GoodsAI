# CONF-006: отдельная политика и shadow-аудит для каждого атрибута

План покрывает 9 уникальных полей в 12 category×attribute сочетаниях:
смартфоны 761 (brand/model/RAM/storage/screen/battery/color) и чайники 482
(brand/model/capacity/power/color). Это offline-подготовка к EVAL-004, не его
независимая приёмка. Принятый storage-pilot-97-v1 не изменяется; новые поля
не получают runtime auto_accept от этого инструмента.

## Порядок

1. Создать план существующего default extraction config.
2. До predictions задать целевую precision, audit family budget, whitelist
   правил и optional raw score filter отдельно для каждого сочетания.
3. Передать approved frozen catalog-silver development bundle и все доступные
   exposure ledgers. Test/train/protected входы запрещены. Raw pickle не читается.
4. Prepare выполняет существующий CLI/verifier дважды и выбирает одну карточку
   из непросмотренного семейства на каждое поле. Selection фиксируется до
   чтения catalog reference. Каталог оценивается существующим silver evaluator.
5. Человек заполняет форму; начальный статус всегда unreviewed. Assess принимает
   только явно подтверждённый полный пакет с attestation и считает per-field
   bound существующей precision_lower из storage-shadow. Нет автоматической
   подстановки реальных human labels. Blank/pending не означает correct.
6. Результаты требуют решения по runtime и отдельной независимой оценки.

```bash
python -m scripts.research.attribute_shadow plan --output outputs/attribute-plan.json
# Редактировать targets/budgets/rule whitelist в плане ДО следующей команды.
python -m scripts.research.attribute_shadow prepare --bundle /private/approved-development --plan outputs/attribute-plan.json --seen /private/prior-exposure.jsonl --reviewer reviewer-name --output-dir outputs/attribute-audit-new
# Открыть outputs/attribute-audit-new/review.html, проверить и сохранить answers JSON.
python -m scripts.research.attribute_shadow assess --bundle outputs/attribute-audit-new --answers /private/answers-attribute-shadow.json --output-dir outputs/attribute-reviewed-new
```

Используйте .venv/bin/python (Windows: .venv\Scripts\python.exe).
Все выходные каталоги должны быть новыми. Полный review.html сохраняет один
ответный пакет; review-001.html и т.д. удобны для просмотра порциями, их
частичные JSON нужно объединить по уникальным task_id перед assess. Пустой
шаблон answers.blank.json не содержит подтверждений. Локальный HTML сохраняет
ответы в файл и не отправляет тексты на сервер. Пакеты private, не коммитить.

## Значение порогов

`target_precision` — желательная precision группы, а не вероятность отдельного
кандидата и не порог heuristic confidence. `min_rule_score` — только заранее
заданный фильтр исходного heuristic score, не calibrated probability. Изменение
любого поля плана, seed, config или кода после freeze требует нового пакета;
переименовывать подбор по ответам в независимый эксперимент нельзя.

Для каждого поля отчёт показывает requested/found/selected, exclusions,
available unexposed families, sample size, catalog TP/mismatch/unknown/conflict.
Unknown/conflict не становятся отрицательными метками. Human precision до
ответов N/A. Нулевой support — no_audit_cases, а не 100% precision.

После review считаются индивидуальная нижняя односторонняя 95%-граница и
дополнительная Bonferroni-граница для всех 12 заявленных политик. Общая гарантия
не получается из двенадцати отдельных 95%-интервалов. Предположения о
репрезентативности и независимости семейств остаются необходимыми; один
разработчик с видимыми предложениями не образует independent gold.

Для 99% индивидуальной цели даже при нуле ошибок нужно минимум 299 семей
на поле, а для 97% — 99. Требования одновременной границы выше. Поля с меньшим
support остаются insufficient_evidence. Неоднозначные и unjudgeable случаи
консервативно учитываются как неуспехи; непросмотренные оставляют пакет pending.

## Область и воспроизводимость

Только текущие две категории и действующие rule IDs; LLM/модельные кандидаты
не выбираются. Title явно указывает смартфон/чайник, нет accessory/watch
маркеров; общего verifier недостаточно для подделанного rule_id: Selector
восстанавливает реальные rule candidates и проверяет точные value/unit/score/
evidence. Для RAM и storage отбрасывается конфликт любого из этих полей.
Это ограниченная, заранее заданная shadow-гипотеза, а не утверждение качества.

Source/config/code/plan/tool hashes фиксируются, изменение входов и package
tampering отклоняются. Output публикуется целым приватным каталогом. Предыдущие
outputs не перезаписываются. Exposure receipts сохраняют IDs отдельно от
предсказаний и могут быть переданы следующему prepare. При отсутствии журнала
инструмент не утверждает, что ему известна полная история просмотров.

Storage аудит 145/145 нельзя переносить на RAM, бренд или цвет. Изменение runtime
допускается только после проверки конкретной группы и согласования; в текущем
инкременте все `runtime_authorized` равны false. Старые default и storage profiles
CLI/API работают как прежде. Rollback — удалить исследовательский инкремент;
миграция данных/конфигов runtime не нужна.

## Проверяемые группы

| Поле | Категории | Что проверяется сверх наличия значения |
| --- | --- | --- |
| brand | 761 / 482 | Реальный title/subbrand rule и тот же canonical alias; чужой бренд отсекает общий verifier |
| model | 761 / 482 | Реальный labelled/phone/kettle model span; audit нужен отдельно от других полей |
| ram_gb | 761 | Явная роль RAM или title-пара, отсутствие противоречия RAM/storage |
| storage_gb | 761 | Явная роль ROM или title-пара; parity с существующей storage eligibility |
| screen_inches | 761 | Canonical inch, exact span, общий role/secondary-screen gate |
| battery_mah | 761 | Canonical mAh, exact span и существующий verifier |
| capacity_l | 482 | Canonical L и existing quantity gate; малый catalog support не превращается в успех |
| power_w | 482 | Canonical W и existing auxiliary-power exclusions |
| color | 761 / 482 | Реальное dictionary color rule, exact evidence и relation gate для model/material context |

Это гипотезы отбора shadow-кандидатов; semantic verifier имеет ограничения.
Одного synthetic positive на строку недостаточно для включения runtime.

## Воспроизводимое демо без реальных данных

```bash
python scripts/research/demo_attribute_shadow.py --output-dir outputs/attribute-demo-new
```

Шесть вымышленных карточек → 12 групп → 36 заданий (по 3 семейства на группу).
В plan.json показаны разные targets: 97% для RAM/storage, 99% для остальных.
Это настройки примера, не реальные оценённые thresholds. Откройте
`outputs/attribute-demo-new/audit/review.html`. Значения/цитаты предложены
правилами, но ни одного human correct ответа генератор не создаёт.

В Git текущего проекта доступны код и агрегированные отчёты. Готовые реальные
input/reference/metadata и exposure ledgers в проверенных main и evaluation
ветках не найдены; их нужно получить приватным согласованным handoff. Исходный
pickle не является заменой такого frozen bundle. До handoff real per-field
shadow selection и human correctness не измерены.
