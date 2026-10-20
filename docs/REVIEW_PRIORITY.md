# Приоритет проверки оператором

`goodsai.review_priority` меняет только порядок человеческой работы. Он не
получает Product/raw text, не меняет value/confidence/decision и не формирует gold.

`ReviewTask`: task_id, category_id, attribute, created_at (UTC epoch seconds),
reason_codes, required, decision (review/abstain). Конфликт/evidence/verifier
failure идут первыми, затем обязательные пропуски, затем остальные review.
Внутри band учитываются возраст по часам, bounded demand и стабильный task_id.
Heuristic confidence не используется как P(error).

В каждом cycle (по умолчанию 10) последние три позиции резервируются для
старейшей задачи, редкой категории и воспроизводимого случайного audit sample.
Cursor сохраняется между вызовами: маленькие batches тоже доходят до квот.
Это квоты очереди, не обещание максимального wall-clock ожидания без оператора.

Отсутствие demand даёт равные веса. Внешние clicks не принимаются в ReviewTask
или Product. Только отдельный агрегатный профиль `{"approval":"...","weights":
{"761:brand":2}}` и совпадающий `RankPolicy.demand_approval` разрешают weighting.
Максимальный вес policy 1–3 (default 2), severity и fairness quotas сохраняются.
Это явное аналитическое решение владельца, не разрешение подмешивать clicks
в inference/prompt/reference. Без согласования используйте default null approval.

```bash
.venv/bin/python -m goodsai.review_priority rank --input outputs/review-tasks.json --policy outputs/rank-policy.json --now 1792500000 --limit 20 --state outputs/rank-state.json --output outputs/ranked-first.json
.venv/bin/python -m goodsai.review_priority begin --ranking outputs/ranked-first.json --task-id task-1 --actor operator --db outputs/operator.sqlite
.venv/bin/python -m goodsai.review_priority finish --action-id 1 --correct true --db outputs/operator.sqlite
.venv/bin/python -m goodsai.review_priority report --db outputs/operator.sqlite
```

Policy `{}` использует прозрачный baseline. Для повторов используйте тот же
state; policy hash mismatch отклоняется. Каждый rank содержит band, age,
demand_weight, rare, quota/selected_by и policy version/hash. Файл результата
создаётся новым, обновление cursor защищено OS-lock. Queue IDs/audit остаются
локальными: это рабочие данные оператора, не публичная operational telemetry.

Begin/finish сохраняют отдельную immutable audit session с реальным временем;
повторное finish отклоняется. Report считает время, declared-correct mandatory
pairs/minute, declared-correct critical errors, p90 ожидания и rare served share.
Корректность отмечает оператор: отчёт явно `operator_declared_development`,
`independent_reference=false`, sales_impact=null. Он не доказывает причинный
выигрыш, CTR/GMV или качество модели.

Synthetic tests проверяют порядок, decomposition, стабильность, equal weights,
approval/cap, квоты при batch size 1 и audit. Для keep #62 нужен реальный
контролируемый FIFO/severity+age/demand UX benchmark с одинаковым бюджетом
человеко-минут. PRODUCT-002 подключает этот модуль к своей очереди без второго UI.
