# GoodsAI: фактический прогон на командной VM

19 октября 2026 года. Команда tunaIT. Задача [ENV-001 #4](https://github.com/CRUDoshleps/GoodsAI/issues/4).

**Решение работает на Linux VM. Независимая человеческая точность пока не измерена.**
Предварительное согласие с диагностической AI-reference: precision **96,3%**,
recall **70,3%**, F1 **81,25%**.
Это development-диагностика; она не подтверждает 100% precision каталога.

## Что действительно запущено

| Проверка | Результат |
| --- | --- |
| Исходный frozen commit | `1754970c4e0177fa6d3ef7a2dffa71c9a902cbed`, clean |
| Повтор на обновившемся main | `1d53dadbb8760dd0888b6c557fb89ab42ce52bb8`, clean |
| Среда | Linux 5.15 x86_64, Python 3.12.15; VM 4 vCPU / около 8 GB RAM |
| Tests последнего проверенного SHA | **119 основных + 3 reader**, OK; pip check OK |
| Synthetic demo | **6/6**; это функциональная проверка, не точность каталога |
| Настоящий loopback HTTP server frozen runtime | **64/64** проверок: CLI/API parity, invalid JSON, schema, media type, size, unknown endpoint |
| HTTP latency | 60 synthetic requests; p50=1.35 мс, p95=1.81 мс; не нагрузочный SLA |
| Реальный batch | **2171 / 2171 processed SKU**, одинаковые множества input/output; 0 ошибок схемы |
| Повторяемость | По 3 запуска на обоих commits; все 6 predictions побайтно одинаковы |
| Requested pairs | **13855** |
| Candidates / abstain | **7848 review / 6007 abstain**, auto_accept=0 |
| Candidate coverage | **56,6%**; это не precision/recall |
| Exact source spans | **7848 / 7848**, 100%; смысловую принадлежность это не доказывает |
| Batch time на последнем SHA | 2.713–2.787 с; время `predict` из manifest, включая I/O, без подготовки источников/старта Python |
| LLM в GoodsAI runtime | **0 calls**; текущий pipeline — rules |

Code SHA `dc5a0cb4f5d8e904bc4d1d25e580f1436ce9c287f270306a3df8cd7d60ab69ca` и config SHA
`cb7285cb3b83d2584661d5ec8eb4a315d6581148a5c3b1f7d012a0998db19a2b` совпали на обоих commits.
SHA predictions: `e7a99b6ae033c8c02207bf307bc69ca98401d0d127a0defa0581892635174d8c`.

Существующий сервис port 8000 отвечал на /health и остался на checkout `48b45dc`.
Файлы `src/goodsai` между ним и проверенным runtime идентичны. Для аудита созданы
изолированные clean worktrees; действующий сервис не перезапускался.
Снаружи неавторизованный /health перенаправляется на платформенный /login и отдаёт
HTML с HTTP 200. Это не JSON-health и не доказательство неисправности extractor.

## Откуда взята диагностическая оценка

1. На VM перенесены исходные `skus.pkl` и `sku_desc.parquet` из выданного локального
   набора. Pickle сначала прошёл opcode scan, затем штатный restricted reader;
   произвольный `pickle.load` не использовался. Получено 10324 E1 SKU.
2. Восстановлены E1 split и консервативные family links. Из batch исключены все
   1616 test_reserved и mixed-split families; выбран 2171 development SKU.
   Манифест семей пересоздан текущим инструментом и не равен историческому M2 v2.
   Поэтому этот прогон не заявляется воспроизведением официального filtered partition.
3. Выбрано 80 разных неexposed по реконструированному ledger development-семейств:
   40 телефонов / 40 чайников, в каждой категории 20 title-only / 20 с description.
   Seed `goodsai-vm-diagnostic-20261019-v1`. Это стратифицированная диагностика,
   а не репрезентативная оценка всего каталога; история exposure неполна.
4. `openai/gpt-oss-120b` получил только title/description, схему и инструкции по
   разметке. Predictions ему не передавались. Raw reference зафиксирована до
   первого реального predict; `label_source=llm_candidate`, human_reviewed=false.
5. При проверке первого сравнения обнаружены ошибки инструмента оценки:
   `l` против `L`, регистр брендов, English/Russian color aliases. После просмотра
   расхождений reference приведена к уже существующему контракту. Raw ответы и
   исходные показатели сохранены; production rules не менялись. Один конфликт
   parent/subbrand guideline исключён. Это **не blind holdout**.

Первоначальный некорректный по сериализации comparator дал P79,1/R57,6/F166,7;
эти цифры не являются текущей оценкой extraction. Изменения формата reference
затронули 45 пар (color 11, brand 11, screen 1, capacity 16, power 6).
Все изменения сохранены в отдельном журнале; независимость после такого
исправления не заявляется.

## Метрики согласия с AI-reference

Всего 480 запрошенных пар. Оценены **425**: 296 present и 129 absent.
Исключены **49 unjudgeable + 6 ambiguous**. Причины unjudgeable:
28 отсутствующих exact quotes в ответе разметчика, 20 неверных/отсутствующих units,
1 конфликт annotation guideline. Эти дефекты относятся к reference, не к GoodsAI.

Микро: **208 TP / 8 strict FP / 88 FN**. Неверное значение вместо верного
считается FP+FN. Из 89 расхождений: 81 чистый пропуск, 7 несовпадающих значений,
1 значение при reference=absent. В двух из восьми strict FP нет подтверждённой
ошибки extractor: canonical brand в AI-reference и вариант записи model code
с пробелом/без. Потребуется human adjudication; эти пары не исправлялись по ответу системы.

| Атрибут | Judged | TP / strict FP / FN | Precision | Recall | F1 |
| --- | ---: | --- | ---: | ---: | ---: |
| Бренд | 79 | 57 / 1 / 22 | 98,3% | 72,2% | 83,2% |
| Модель | 80 | 47 / 1 / 32 | 97,9% | 59,5% | 74,0% |
| Встроенная память | 25 | 20 / 0 / 2 | 100,0% | 90,9% | 95,2% |
| Оперативная память | 27 | 21 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| Экран | 31 | 5 / 0 / 2 | 100,0% | 71,4% | 83,3% |
| Батарея | 32 | 0 / 0 / 9 | — | 0,0% | 0,0% |
| Объём чайника | 36 | 15 / 0 / 1 | 100,0% | 93,8% | 96,8% |
| Мощность | 36 | 11 / 0 / 2 | 100,0% | 84,6% | 91,7% |
| Цвет | 79 | 32 / 6 / 18 | 84,2% | 64,0% | 72,7% |

Телефоны: P=96,2%, R=73,4%, F1=83,3%.
Чайники: P=96,4%, R=65,9%, F1=78,3%.
Macro-attribute F1=77,4%.
SKU bootstrap 95% для согласия: P 93,7%–98,6%,
R 65,4%–75,0%,
F1 77,7%–84,7%.
Интервалы условны на AI-labels и не учитывают их ошибки, выборку и неполный exposure.
Независимые human P/R/F1 по-прежнему **N/A**. Приватные reviewed development
references из других рабочих окружений в этот прогон не поступали.

## Подтверждённые проблемы и изменения задач

| Приоритет | Наблюдение | Задача / действие |
| --- | --- | --- |
| P0 | Synthetic `Ёмкость аккумулятора 5100 мА*ч.` даёт abstain; battery TP=0/FN=9 в диагностике | Создана [BASE-003 #74](https://github.com/CRUDoshleps/GoodsAI/issues/74), READY: разделители единиц + положительные/отрицательные regressions |
| P0 | Synthetic `Электрочайник RED SOLUTION ZZ-901` ошибочно даёт color=красный из имени бренда | [VER-001 #15](https://github.com/CRUDoshleps/GoodsAI/issues/15) повышена до P0; relation tests, не только exact quote |
| P0 | Штатный inventory требует необязательный для text-only `query_clicks.parquet` и останавливается | Уточнена [DATA-001 #5](https://github.com/CRUDoshleps/GoodsAI/issues/5): обязательные файлы по профилю; не создавать фиктивный clicks |
| P0 | AI-labels содержат ошибки; нет независимого human gold на VM | Уточнены [EVAL-001 #6](https://github.com/CRUDoshleps/GoodsAI/issues/6) и [EVAL-003 #38](https://github.com/CRUDoshleps/GoodsAI/issues/38): review/adjudication, provenance, freeze; продолжать существующий human workflow |
| P0 | Неутверждённые оттенки сводятся к базовому слову; неодинаковые parent/subbrand и model-space conventions | [SPEC-001 #10](https://github.com/CRUDoshleps/GoodsAI/issues/10): зафиксировать правила до следующей разметки; не подгонять по predictions |
| P1 | Основные пропуски: brand 22, model 32; часть вызвана незнакомыми явно написанными именами | [BASE-001 #21](https://github.com/CRUDoshleps/GoodsAI/issues/21) переориентирована на существующий runtime и разбор FN вместо второго прототипа |
| P1 | Шлюз доступен, но model route отсутствует; reference calls столкнулись с 429/502 | [LLM-003 #25](https://github.com/CRUDoshleps/GoodsAI/issues/25): concurrency/backoff/budget/fallback и настоящее сравнение после baseline fixes |
| P1 | HTTP 200 снаружи может быть HTML login; health не содержит build identity | [API-001 #17](https://github.com/CRUDoshleps/GoodsAI/issues/17): проверка JSON/final URL и согласованный release identity |

Сначала исправить воспроизводимые baseline defects и завершить независимую оценку,
затем сравнивать model fallback с тем же frozen контролем. Новые модели/cache/replay
не должны задерживать P0. Владельцы и статусы чужих задач сохранены; изменён
приоритет #15, создана #74. Исправления runtime здесь не реализовывались.

## Шлюз, расходы и артефакты

Шлюз подтвердил models list и настоящий completion с usage. При reference-аннотации:
159 HTTP attempts, 80 успешных reference responses, 78 ответов 429 и один 502;
после уменьшения concurrency до 2 и повторения 502 завершены все 80 карточек.
Это наблюдавшееся поведение, не гарантия постоянной квоты. Reference usage:
94954 input + 79700 output tokens; оценка по предоставленному тарифу — около
**6,37 ₽**, не показание биллинга. Отдельный synthetic ping — 77/87 tokens.
GoodsAI batch: 0 LLM calls и 0 provider spend; compute и труд оператора в рублях не оценены.

Исходная штатная inventory-команда завершилась ошибкой. Продолжение использовало
отдельный честный inventory двух существующих файлов с проверкой sizes/SHA;
необязательный clicks не подменялся. Это зафиксированный workaround, не clean-run pass.

E1 input SHA: `68875ae2ef66c3527915be0e2cca29639c4a1c792e359973ae8623a404b70fe3`.
E1 split SHA: `ad7e8b96ed436c304788021740c65fc545e5a188e8f05fef647dd27092331de2`.
Raw reference SHA: `b5fd50c22360f179f11dad8f7312b4ec1f76b50e55a8fa6dbb60a940807c68dc`.
Canonical reference SHA: `ad393485465028c85c0700a7466e541f4fd43804b4c82fbb699058bcdcff3e89`.
Метрики: `GoodsAI_VM_metrics_2026-10-19.json`, SHA `1803b4d4c023c15db767be08500fb82abc9c7895091e2774dc0c7e4ef3cc3441`.
Инструменты без данных/доступов: `GoodsAI_VM_audit_tools_2026-10-19.zip`, SHA `eeea531ca96f7a3528b6df195b9a0269d88730bd36b57885481b578d4fdefae4`.

Private outputs, source texts, AI answers, per-SKU disagreements и все manifests
сохранены на командной VM в `~/goodsai-audit-20261019/outputs/vm-audit/`;
повтор latest main — `~/goodsai-audit-current-20261019/outputs/vm-audit/`.
В Git входят только протокол, агрегаты и изменения индекса. Секреты, реальные
карточки, raw labels и predictions не опубликованы. `AGENTS.md` дополнен областью
действия для внутренних разработчиков; внешнему проверяющему не задаются выводы.
