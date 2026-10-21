# EVAL-009: frozen model disagreements

21.10.2026. Issue #137, входная зависимость #149. Claim `0b84069`, ветка
`eval/eval-009-model-adjudication`. Это внутренний протокол разработки, не
публичный gold и не независимая итоговая оценка.

## Полученные артефакты

По поручению Владислава выполнено только read-only SFTP получение существующих
результатов PR #136. Авторская ветка коллеги, удалённые файлы и работающий сервис
не изменялись. Новые model calls и расходы отсутствуют. Passwords вводились
без echo, в файлы/результаты не сохранялись. Скачано 25 файлов, 50 767 472 bytes.
Все исходные данные и формы остаются под игнорируемым `outputs/`.

Замороженный набор: 2974 карточки / 1250 семейств, только ранее использованные
development/validation с ролью development_feedback. Reserve 40 исключён;
его тексты и ответы не открывались. Это не локальный старый набор 3037 карточек.

Проверены каждый файл обоих inventories и соответствие source report публичному
агрегату из PR #136:

| Артефакт | SHA-256 |
| --- | --- |
| EVAL-006 source `manifest.json` | `fbd0dfd438226f09cdbab8e3bb2d618a215fefb729189094f48fed544777fdae` |
| EVAL-007 comparison `manifest.json` | `1a2669b43b97984ca75d20b1adac7b2fc33902487f9949d52a9cc2600acd9f75` |
| EVAL-007 `run_stats.json` | `de6119ed23b9de764ac286b6ef59603f85805db04df36d2f8d09f9f24769000f` |

Сравнение коллеги: `f33e3fc` → `1c64463`; 20 новых catalog disagreements и
6 lost catalog TP у model. Они не объявляются доказанными human FP/FN.

## Отбор и черновик

Отбираются **все** model new_fp/lost_tp из фиксированного changed-pairs файла.
Никакой выборки только успешных ответов и подмены другим набором. Постоянные
номера M01–M26: сортировка category, lost_tp перед new_fp, lexical SKU.
Metadata/split/family проверяются до интерпретации текста; выбранные test_reserved
карточки и семьи отклоняются. Прежний validation честно становится development
feedback; исходный split сохраняется отдельно.

`prepare_model_adjudication.py` проверяет hashes, producer input/output/code
identity, сравнимый config и полноту flagged model changes. Результат — пустые
model tasks и policy, не автоматическая разметка. Отдельный `draft` проверяет
явно авторские решения существующим `review_m2.make_label`, включая canonical
model/точную цитату/offsets. Изменять символы или регистр модели нельзя.

AI-решения написаны по title/description до чтения catalog/prediction values.
После заморозки draft выполнено сопоставление. Selection использует predictions,
поэтому весь процесс **не слепой и не независимый**, даже если сами ответы
написаны по тексту. Human-reviewed=0, human P/R/F1=N/A до подтверждения Владом.
Draft SHA-256: `3f48ee9aab44c024b45fb21ac3124297b829e0199e5c5d389da78486c672cad8`.

Текущее локальное расположение:

- source: `outputs/eval010/handoff-sftp-20261021/`;
- selection: `outputs/eval010/model-adjudication-20261021/selection/`;
- исходная форма 26: `outputs/eval010/model-adjudication-20261021/draft/review.md`;
- итоговая форма 27: `outputs/eval010/model-adjudication-20261021/draft-all27-v2/review.md`;
- авторские решения: `outputs/eval010/model-decisions-20261021.json`.

Протокол можно повторить новым output-dir, не перезаписывая предыдущие файлы:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.prepare_model_adjudication prepare --bundle outputs/eval010/handoff-sftp-20261021/eval-006-silver-20261020-rebuilt --comparison outputs/eval010/handoff-sftp-20261021/eval-007-20261020-rebuilt-comparison --bundle-sha256 fbd0dfd438226f09cdbab8e3bb2d618a215fefb729189094f48fed544777fdae --comparison-sha256 1a2669b43b97984ca75d20b1adac7b2fc33902487f9949d52a9cc2600acd9f75 --output-dir outputs/eval010/model-selection-next
.\.venv\Scripts\python.exe -m scripts.research.prepare_model_adjudication draft --selection outputs/eval010/model-selection-next --decisions outputs/eval010/model-decisions-20261021.json --output-dir outputs/eval010/model-draft-next
```

## Предварительный разбор, требует подтверждения человека

- **M01–M06**: AI draft совпадает с исходным catalog code; новый producer
  отказался `verifier_unsupported_model`. Синтетика воспроизводит два механизма:
  numeric suffix внутри цельного кода ошибочно считается отдельной мерой;
  начало цельного дефисного кода ошибочно считается отдельным брендом.
- **M07–M26**: AI draft совпадает с новым producer. В catalog model дополнительно
  записаны цвет/материал/память/состояние/SIM либо разделители. Это предварительная
  гипотеза reference-boundary noise по действующей P06/P07, не 20 подтверждённых
  человеческой разметкой побед extractor.

Catalog reference и исходные predictions **не исправляются**. Подтверждения и
изменения человека сохраняются новой версией существующим development workflow.
Проверяем только model; полученный partial reference не следует подавать напрямую
как full-card gold в evaluator. Перед расчётом нужна явная model-only projection
с видимыми exclusions остальных полей. Отобранные ошибки не доказывают качество
на всём каталоге.

## Узкое runtime исправление

`31c4590` / финальный `9ebba1d`: power measurement matching учитывает левую границу токена и знак, поэтому
не ищет `731W` внутри вымышленного `QZ-731W`. Настоящие отдельные `2200W`,
`-2200W`, `256GB`, `8/256GB`, `1.7L` по-прежнему исключаются из model.
Прежний отказ для слитных memory/battery/capacity suffixes сохранён: слитное
имя с `256GB` не становится доказанной моделью. Добавлена отдельная отрицательная
регрессия; первоначально более широкий boundary matcher не интегрировался.

Brand-like prefix допускается лишь внутри цельного буквенно-цифрового дефисного
кода и при точном подтверждении полного span существующим ModelRules. Без
этого доказательства бренд/неясная граница остаются отклонёнными. Не вводятся
SKU/vendor/model lookups или исключения для конкретного реального товара.
Shared verifier version: 1.2. Contract v0.1, heuristic score и review/abstain
сохранены; auto_accept не включён.

Добавлены вымышленные positive/negative regressions. До фикса новый positive
test падал в четырёх subtests, после проходит; negative controls проходят до и
после. `outputs/eval010/model-regression-before.log` сохраняет исходный RED.

## Повтор текущего baseline до/после

Заморожены одинаковые input/reference/metadata/config из полученного пакета.
Сравнены main `7a95c59` и финальный candidate `9ebba1d`, isolated runtime, cold/warm
повтор внутри каждого процесса. Использован существующий `runtime_run` и silver
evaluator из read-only checkout PR #136 (`b3941ce`); код коллеги не копировался
в main. Private orchestration/protocol:
`outputs/eval010/run_eval009_comparison_final.py` → `outputs/eval010/model-replay-9ebba1d/`.
Это локальный Windows-повтор, не обновление ВМ и не production latency benchmark.
Первичный протокол `185e053` сохранён отдельно. В финальном повторе неизменные
baseline outputs переиспользованы с исходными hashes, новый candidate реально
пересчитан. Все 2974 результата candidate совпадают с первичным, кроме run_id;
equivalence proof — `outputs/eval010/model-replay-equivalence-final.json`.

| Catalog agreement | До | После |
| --- | ---: | ---: |
| model TP / FP / FN | 570 / 158 / 548 | 576 / 158 / 542 |
| model F1 | 0,617551 | 0,622030 |
| общий TP / FP / FN | 7399 / 404 / 4289 | 7405 / 404 / 4283 |
| общий F1 | 0,759222 | 0,759604 |
| coverage всех requested пар | 10313 / 18592 | 10320 / 18592 |

Парные assessed изменения: 6 new catalog TP, 0 new FP, 0 lost TP; только model.
Другие поля не изменились. Парный family bootstrap (1250 групп, 1000 повторов)
для delta общего F1: 95% CI [0,00008142; 0,00106007]. Это uncertainty для noisy
catalog agreement, не human correctness и не прогноз баллов.

Полный diff значений содержит **7**, а не 6 изменений: ещё один model candidate
при catalog conflict, исключённый из judged TP/FP. Он сохранён отдельно и добавлен
как **M27**, не подменяя исходные M01–M26. Его текст просмотрен после predictions:
это явно post-prediction диагностика. Supplement selection/policy ссылаются на
hash исходных 26 и полный diff. Никакого нового результата human quality нет.
Первый draft-all27 сохранён; в v2 исправлена кодировка только пояснения M27,
значения и evidence не менялись. Текущий draft-all27-v2 SHA:
`63e32bac29af6018f20b19265108d477ff4d7966820ac4144470406ce4f973b3`.

Private replay report SHA-256:
`7b5979ef38be3bf1a97efe48eb58ddd78224354278af714ac7bb8b8c15310d11`.
Исходные silver labels, predictions и протокол PR #136 сохранены без изменений.
Данные этого разбора уже development feedback; не объявлять его новым holdout.

Проверки финального candidate: 487 основных unittest PASS (149,949 s), research reader 3/3,
pip check PASS. Пять новых adjudication tests проверяют порчу/неполноту inventory,
неверный producer input, запрет test families, происхождение draft/feedback и
запрет выдуманной модели вне witness. Три verifier tests проверяют положительные
коды и сохранение отрицательных ограничений. Model tests 18/18,
development_review 9/9 PASS. Финальный matrix: 17/17 executable групп,
103/103 внешних checks и verify PASS; оставшиеся 4 not_implemented,
7 not_verified и 1 unknown не скрыты. Отдельный вымышленный полный code с
unit-like ending и brand-like prefix проходит CLI/API с одинаковыми attributes,
точным evidence и decision=review. Протоколы:
`outputs/eval010/eval009-scenarios-9ebba1d/` и `model-cli-api-parity.json`.
CI и интеграция кода — PR #154; даже merge подготовительного инкремента
не подтверждает человеческую разметку M01–M27 и не закрывает Issue #137.

## Что ещё нужно

Владислав подтвердил участие в AI-assisted review без привлечения дополнительных
людей. Нужны его ответы M01–M27, затем существующий `development_review feedback`
фиксирует explicit confirmation/overrides с AI-origin и independent_reference=false.
Отбор по predictions также сохраняется в provenance, не затирается при feedback.

Полное независимое доказательство #6/#38 этим процессом не выполняется. Оно
остаётся N/A; reserve не превращается в новый AI-draft. #149 нельзя закрывать
как выполненную независимую оценку. PR #136 не сливается этой сессией: доступный
frozen handoff использован по hashes, код коллеги не переписывается.
