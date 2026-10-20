# Измеренный development checkpoint — 20.10.2026

Catalog silver agreement, **не независимое human quality**. Данные и predictions приватные. Auto-accept запрещён. Default model routes выключены.

Новая frozen выборка создана по поручению владельца: 2974 карточки / 1250 семейств; 40 карточек резерва исключены. Это новая версия набора, а не точное повторение исторических 3037 карточек. Прежние отчёты сохранены.

## Baseline на одной выборке

| Runtime | TP | FP | FN | Catalog P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| historical | 7380 | 394 | 4308 | 0.9493 | 0.6314 | 0.7584 |
| candidate | 7399 | 404 | 4289 | 0.9482 | 0.6330 | 0.7592 |

f33e3fc → 1c64463: +25 new TP, +20 new catalog FP, 6 lost TP, 10 removed FP.
Все новые FP и lost TP относятся к `model`; 6 прежних совпадений теперь отклоняет `verifier_unsupported_model`. New FP: 17 чайников / 3 смартфона. Paired 95% CI ΔF1 [-0.000100; 0.002494] включает ноль. Рекомендация кандидата заблокирована: [defect #137](https://github.com/CRUDoshleps/GoodsAI/issues/137).

## Общий model screening — 200 карточек / 200 семейств

Выборка зафиксирована до predictions, одна development-карточка на семейство; одинаковые input/reference/schema/evaluator для всех методов.

| Метод | TP | FP | FN | Catalog P | R | F1 | New TP / new FP / lost TP |
|---|---:|---:|---:|---:|---:|---:|---:|
| rules | 401 | 23 | 297 | 0.9458 | 0.5745 | 0.7148 | — |
| rules + gliner | 449 | 23 | 249 | 0.9513 | 0.6433 | 0.7675 | 48 / 0 / 0 |
| rules + llm | 473 | 43 | 225 | 0.9167 | 0.6777 | 0.7792 | 72 / 20 / 0 |

GLiNER: **keep как opt-in development-кандидат только для бренда**, без включения по умолчанию. 55 обращений к локальной модели, 48 совпадений с catalog, без новых judged FP/lost TP. Cold lazy-load 12.05 s, cold/warm p95 114.13/110.84 ms; RSS high-water ≈2.69 GiB. Это ограничение размещения, не бесплатный compute.

LLM: **drop общего fill для текущего профиля до adjudication**. +72 catalog TP, но +20 catalog FP (19 model, 1 brand), без lost TP. Прирост F1 не снимает regression gate. Combined режим не реализован и не заявляется.

LLM `openai/gpt-oss-120b`: всего 123 физических запроса, без retries; 45572 input / 29965 output tokens. По usage и ценам шлюза **2.55063692 ₽**, или 12.7532 ₽ на 1000 screening SKU. Это provider estimate, не сверенный счёт. Оплата compute N/A. Первый bounded batch сделал 100 запросов; второй использовал проверенную копию кеша и дозаполнил 23. Финальный warm pass сделал 0 новых запросов.

Условия latency: начальный batch p95 2174.86 ms (100 fresh calls + budget skips); completion p95 1586.57 ms (100 cache hits + 23 fresh calls); финальный warm p95 9.95 ms. Нельзя выдавать completion за полностью холодный прогон всех 200 карточек. Полные cold/warm resources и hashes каждого этапа — в JSON.

## Пилот новых категорий

Подготовлены private train/split/family/source hashes и контракт: ноутбуки 987, телевизоры 1682, мониторы 1263 — по 300 train-карточек. Отбор до inference, без vendor/model/params во входе extractor. Params остаются отдельными train labels.

**Inference новых категорий не выполнялся.** #5/#10/#44 и owner mapping/units/required-fields/family review остаются блокерами. Доступный clicks-файл не совпал с прежним fingerprint; он не использован, фиктивные веса не созданы. Registry draft без проверенного traffic handoff не публиковался. Schema preparation не объявляется quality/coverage всего каталога.

## Provenance и ограничения

[Машиночитаемый отчёт](checkpoint_20261020.json): input/bundle/audit/code/config/evaluator/model hashes, per-attribute/category TP/FP/FN, supported recall, unknown/conflict, rare slices, paired grouped CI, ресурсы и keep/drop. История доступов ограничена предоставленными VM ledgers; human support audit и независимые #6/#38/#40 не завершены. Runtime rules/units/confidence/default modes под ответы моделей не изменялись.
