# GoodsAI: комплект development checkpoint 19.10.2026

Подготовлен реальный комплект шести артефактов на чистом code candidate
`047e1ee4abc5e04b0c3d49da3bfab81760f4376f`. Полная локальная сборка с PDF
имеет `status=complete`, прошла `verify`, затем ZIP был извлечён в новый каталог
и повторно проверен. Это development checkpoint, не финальная сдача всего каталога.
Дополнительно в отдельном чистом candidate worktree без исходных data caches
повторены predict/evaluate только по файлам из ZIP: predictions побайтно
идентичны, метрики полностью совпали; producer replay имеет git_dirty=false.

## Состав

| № | Артефакт | Где находится |
| --- | --- | --- |
| 1 | Воспроизводимый код | [candidate source](https://github.com/CRUDoshleps/GoodsAI/tree/047e1ee4abc5e04b0c3d49da3bfab81760f4376f), `public/code.zip` внутри полного комплекта |
| 2 | README | [основной README](../../../README.md), снимок внутри комплекта |
| 3 | EDA | [агрегированная сводка](eda.md) с fingerprints прежних caches |
| 4 | Extraction pipeline | [descriptor](pipeline.json), [versioned config](../../../src/goodsai/baseline.json), CLI/API в коде |
| 5 | Реальные predictions | 2198 строк JSONL + paired manifest внутри локального комплекта; [метрики](metrics.json), [checksums](bundle.manifest.json) доступны здесь |
| 6 | Техническая презентация | [PDF, 8 слайдов](technical_slides.pdf), [редактируемый Markdown](technical_slides.md) |

Полный ZIP с input/predictions/reference хранится локально:
`outputs/delivery/art-001-20261019-v1/delivery-bundle-pdf.zip` (609529 bytes).
SHA-256: `31690a5fdefe2f3ee7e9059f2855bdc526b87f19f264498e20709bb08b3dc9de`.
Он не включён в публичный GitHub. Отдельная загрузка в разрешённый Gitea/канал
сдачи не выполнялась; для подготовки файлов она не нужна. Агрегаты и слайды
пригодны для публикации в main через review. `release_approval` не является
автоматическим одобрением содержания/качества: человек ещё может проверить слайды.

## Выборка и качество

- E1 содержит 10324 карточки двух категорий. Для нового batch выбраны **2198**:
  1527 смартфонов и 671 чайник из unmixed development families.
- Исключены 4783 SKU других split и 3343 development SKU защищённых/смешанных
  семейств; суммарно 8126. Все 1616 исходных test_reserved SKU исключены.
- Закрытые test tasks не открывались и predictions на них не создавались.
  Лексическая семейная группировка не гарантирует обнаружение всех смысловых дублей.
- 2198/2198 результатов имеют `processed`. Candidate coverage: 7953/14044
  запрошенных пар, **56,6%**. Coverage не является оценкой precision/recall.
- Reviewed M2: **69 TP / 0 FP / 14 FN**, P=100%, R=83,1%, F1=90,8%;
  20 карточек / 115 judged-пар, 5 ambiguous исключены. Метрики воспроизвелись,
  правила не менялись и по этому запуску не подбирались.
- Это AI-assisted human-reviewed development, уже обсуждавшийся при разработке.
  Независимое качество N/A. У model нет judged-негативов на этом reference.

Измерение на Windows/Python 3.12.6: batch 2,87 с, extractor p50/p95
1,017/3,066 мс. Это один локальный запуск, не SLA/benchmark.
LLM calls=0, API-расход=0; стоимость compute в рублях не оценивалась.
Все найденные значения остаются review, confidence heuristic; auto_accept нет.

## EDA-уточнение

Прежнее сокращённое описание неверно называло 148871 размером каталога.
Сохранённые profile/join aggregates и Parquet footer подтверждают **546069**
уникальных карточек. 148871 — число SKU с повторяющимися названиями параметров.
Полный EDA и pickle loading не повторялись. Данные raw, caches, reference,
старые predictions/отчёты не изменены; fingerprints проверены до/после подготовки.

## Воспроизведение

Нужен полный clone с локальными E1/EDA/M2 v2 caches из
[инструкции](../../ARTIFACT_BUNDLE.md#подготовка-реального-development-checkpoint).
На чистом code candidate или новом чистом HEAD с отдельной identity:

```powershell
.\.venv\Scripts\python.exe -m scripts.release.prepare_delivery --report-date 2026-10-19 --output-dir outputs/delivery/checkpoint-next
.\.venv\Scripts\python.exe scripts/release/build_release.py verify --bundle outputs/delivery/checkpoint-next/bundle
```

Эта команда создаёт Markdown-презентацию и полный комплект. PDF в данном
checkpoint получен из того же Markdown локальным Chromium print-to-PDF;
все 8 страниц отрендерены и просмотрены, текст/таблица не обрезаются.
Проверка в PowerPoint не проводилась, PPTX этим этапом не создаётся.
Чтобы включить свой проверенный PDF, создать новый frozen spec с его SHA
и выполнить `assemble` в новый каталог. Исходный Markdown bundle сохранён.

[checkpoint.json](checkpoint.json) содержит batch/selection/metric aggregates,
code/config/input/output/reference hashes и SHA итогового ZIP/PDF.
[bundle.manifest.json](bundle.manifest.json) относится именно к PDF-комплекту,
а не к раннему Markdown ZIP. Private paths в нём описывают файлы внутри архива;
в публичной папке этих текстов нет.

Автотесты: 108 основных (8 новых проверок отбора/агрегатов, плюс 18 ART-003),
3 reader tests. Linux/VM, независимый gold и модельные вызовы не проверялись.
Публикационные документы идут последующим commit: их SHA не нужно подставлять
вместо зафиксированного producer SHA выше. ВМ не обновлялась.
