# DOCS-002: текстовый аудит текущих материалов

Дата: 19.10.2026. Автор: Codex (e345ee). База: main `1d53dad`.
Статус: `[DONE]` текстовая сверка; новая документация находится в REVIEW.
Применены [CONTENT_STYLE](../CONTENT_STYLE.md) и
[PRESENTATION_REVIEW](../PRESENTATION_REVIEW.md). Это авторская редакционная
проверка, не независимый human review качества и не разрешение финальной сдачи.

## README

| Проверенный тезис | Источник | Решение |
| --- | --- | --- |
| Работают две категории и rules baseline | [контракт](../../TECHNICAL_SPEC.md), [rules](../../src/goodsai/rules.py) | DONE на указанной базе; не обещает весь каталог |
| LLM не включена, confidence эвристический, auto_accept запрещён | [Extractor](../../src/goodsai/verify.py), [оценка](../EVALUATION.md) | Ограничения явно видны |
| M2 P100/R83,1/F190,8% | [RESULTS](../RESULTS.md), [frozen metrics](../delivery/2026-10-19/metrics.json) | 20 development карточек, provenance AI-assisted human-reviewed указан; независимый test не заявлен |
| Demo 6/6 | [test_demo](../../tests/test_demo.py) | Описано как synthetic smoke, а не P/R/F1 |
| Исторические 82 tests | README раздел проверок | Помечено как прежний прогон Windows; не выдаётся за свежий test count |

В README добавлены ссылки на стиль и checklist защиты. Фактические метрики
и исторические результаты этим docs PR не меняются.

## Delivery report и machine-readable metrics

Проверены [delivery README](../delivery/2026-10-19/README.md),
[metrics.json](../delivery/2026-10-19/metrics.json),
[checkpoint.json](../delivery/2026-10-19/checkpoint.json).

- `[DONE]` В JSON reference помечен ai_assisted_reviewed_development,
  independent_reference=false. Название manual_reference само по себе
  не используется как доказательство независимости.
- `[DONE]` Исторические 69 TP / 0 FP / 14 FN, 20 reviewed карточек и
  исключённые ambiguous не превращаются в обещание качества каталога.
- `[DONE]` Batch 2198 SKU и candidate coverage отделены от P/R/F1.
- `[DONE]` Для времени указаны Windows/Python 3.12.6 и один локальный run.
  Нулевой API-расход отделён от неизвестной денежной стоимости compute.
- `[DONE]` Producer SHA не подменяется SHA последующей публикации документов;
  manifest/checkpoint содержат hashes источников и результатов.

Числа сверены с уже опубликованными агрегатами, predictions/gold не открывались
и evaluator заново не запускался. Это проверка согласованности текста/JSON.

## Markdown-слайды технического checkpoint

Источник: [technical_slides.md](../delivery/2026-10-19/technical_slides.md).

| Слайд | Тип claim | Что проверено |
| --- | --- | --- |
| 1. GoodsAI | DONE | Указан code candidate, rules baseline и две категории |
| 2. Данные | DONE | 2198 development SKU, исключения и закрытый test оговорены |
| 3. Pipeline | DONE | Нет утверждения о готовом model route/auto_accept |
| 4. Оценка | DONE | P/R/F1 сопровождаются 20 карточками, 115 judged-парами и development provenance |
| 5. Атрибуты | DONE | Есть TP/FP/FN; отсутствие model-негативов отмечено |
| 6. Batch | DONE | Timing относится к одному run; compute cost не названа нулевой |
| 7. Комплект | DONE | Команды и условия доступа к private inputs указаны |
| 8. Ограничения | PLAN | Независимая оценка/модельный эксперимент не объявлены сделанными |

Исторические слайды не содержат новых меток на каждом тезисе; таблица выше —
отдельная классификация. В новом export использовать статусы и sources рядом
с результатом. Ссылки `public/quality.json`, `private/eda.md` в этих слайдах
относятся к bundle, а не к соседним файлам Git; при показе использовать
[delivery index](../delivery/2026-10-19/README.md) как карту источников.

В этой задаче просмотрен Markdown и цифры. Рендер/визуальная доступность PDF,
контраст на проекторе и длительность репетиции — **not_checked**. Наличие
текстового audit не является прохождением этих пунктов presentation checklist.
Исторический протокол render не объявляется новым прогоном.

## Целостность frozen материалов

Ни один файл `docs/delivery/2026-10-19/` этим PR не изменяется.

| Файл | SHA-256 |
| --- | --- |
| README.md | 88e616eb4f942a27cc8c4f7098b009a4cab9f1af4bddf699f9372ffd1743b22f |
| technical_slides.md | 2f174c50ba7a94e01d63240fced60a6ab0033b7c28e725af74cbdac8a73ae69b |
| metrics.json | 21541d96d3be12b7ed76fb2d8e7752419b6e936dd8c44b8ef71e0a5c59a601b9 |
| checkpoint.json | adbcc3e82e3b73c840a8788ce72461e53e3df867323f5f4f0eb4ec004e639204 |

Текстовая проверка завершена. Финальная визуальная приёмка/репетиция выполняется
для конкретной версии презентации и записывается в отдельной форме review.
