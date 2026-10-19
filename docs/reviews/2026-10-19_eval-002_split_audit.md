# EVAL-002: аудит split, дублей и exposure

Задача [#7](https://github.com/CRUDoshleps/GoodsAI/issues/7), 19.10.2026.
Метод и команды: [SPLIT_AUDIT.md](../SPLIT_AUDIT.md).

## Вывод

Исходный E1 split **нельзя использовать целиком как независимое разбиение**:
632 консервативных семейных компонента пересекают splits. Это подтверждает
необходимость уже существовавшего карантина M2, а не обнаружение утечки во всех
40 текущих test-заданиях. Действующий резерв M2 v2 проверен: **40 SKU / 40
семейств, 0 проблем по заданным детекторам и известному exposure ledger**.
Это кандидаты для blind human review, не готовый gold и не доказательство F1.

Выпущен отдельный filtered partition `eval-002-quarantine-v1`. Из него целиком
исключены пересекающиеся семейства. Исходные данные, split, gold, резерв и старые
предсказания не заменены. Новый partition не подключается к runtime автоматически.

## Объём и provenance

- 10324 E1 SKU, смартфоны `761` и чайники `482`; полный каталог не анализировался.
- Producer: `62388ad8233c5776f6e7f368721061ff4919d35e`, `git_dirty=false`.
- Claim: `697148c`, база `1754970`, ветка `eval/eval-002-split-leakage`.
- Windows / Python 3.12.6. Linux/VM не проверены в этой задаче.
- Вход SHA: `68875ae2ef66c3527915be0e2cca29639c4a1c792e359973ae8623a404b70fe3`.
- Исходный split SHA: `ad7e8b96ed436c304788021740c65fc545e5a188e8f05fef647dd27092331de2`.
- M2 family SHA: `61f3d35b4d2b7dd46b313d62e1adb73b545f9e87e337cc2dff665817792f7de7`.
- M2 selection summary SHA: `be0f7972e25b75208bb6576b2ce0b2c60789a6cdb2f5e4d01ba1e317f9287dea`.
- Blank reserve SHA: `beb9651b16718e3739e5115dafbea9a5dce4cf79e551096509a24e5bd94fa02c`.

Политика заморожена до fingerprinting. Пороги 0.90/0.90 наследуются из прежней
M2 policy; по test не настраивались. Target/vendor/model/gold значения не
используются для извлечения или настройки. Frozen M2 family links наследуются
как split metadata. Вызовов LLM и новых predictions нет. Тексты test не выведены,
не экспортированы и семантически не анализировались; выполнялся автоматический
fingerprinting и проверка metadata/пустоты labels.

## Исходные пересечения

| Детектор | Группы дублей | Пересекающиеся группы | Строки в пересекающихся группах |
| --- | ---: | ---: | ---: |
| Original group ID | 1340 | 0 | 0 |
| Frozen M2 family | 1004 | 632 | 6913 |
| Raw title | 1234 | 0 | 0 |
| Raw description | 118 | 0 | 0 |
| Raw title+description | 902 | 0 | 0 |
| Normalized title | 1330 | 0 | 0 |
| Normalized description | 139 | 7 | 40 |
| Normalized title+description | 953 | 0 | 0 |

| Near detector | Проверено пар | Совпадения >= 0.90 | Между splits | Различных SKU в межsplit-парах |
| --- | ---: | ---: | ---: | ---: |
| Title, char trigrams | 243213 | 18196 | 2939 | 1541 |
| Description, word 5-shingles | 217219 | 215624 | 1733 | 1142 |

Счётчики разных детекторов пересекаются: их нельзя суммировать как число
уникальных утечек. Empty description не создаёт связи. Нормализация включает
NFKC/HTML/casefold/ё; near join проверяет все пары выше фиксированного порога,
даже если их семейство уже объединено другим детектором.

Всего получено **2196** компонентов — столько же, сколько frozen M2 v2.
Из **552** известных exposed SKU 532 наследованы от M2, ещё 20 добавлены из
development tasks M2 v2. Проверены exposure sources: E1 tasks, AI v4, M2 v1/v2
development tasks; из них читается только SKU. В 82 компонентах exposure
соседствует с test_reserved; эти компоненты также полностью исключены.

Большие компоненты могут содержать общие описания/шаблоны. Аудит **не** утверждает,
что 6913 исключённых строк — 6913 доказанных дублей. Безопасное действие для
независимой оценки — консервативный карантин; семантическое разделение таких
компонентов потребует отдельного разрешённого review.

## Исправленная версия partition

| Split | Исходно | Сохранено | Исключено |
| --- | ---: | ---: | ---: |
| development | 5541 | 2198 | 3343 |
| validation | 3167 | 882 | 2285 |
| test_reserved | 1616 | 331 | 1285 |
| **Всего** | **10324** | **3411** | **6913** |

Сохранено по категориям:

| Категория | development | validation | test_reserved |
| --- | ---: | ---: | ---: |
| Смартфоны `761` | 1527 | 408 | 122 |
| Чайники `482` | 671 | 474 | 209 |

В filtered partition **0 обнаруженных межsplit-компонентов** и **0 exposed
test-компонентов**. Group ID теперь соответствует полному компоненту; исходный
ID сохранён отдельно. Quarantine ledger содержит все причины и дополняет
eligible manifest до исходных 10324 SKU. Никакие строки не переназначены.

Оставшиеся 882 validation-карточки всё равно имеют роль `development_feedback`:
обсуждение validation и настройка правил не отменяются очисткой split.
331 test_reserved-карточка — допустимый пул по известным детекторам/ledger,
не автоматически утверждённый новый test. Действующие 40 заданий входят в него,
не пересекаются семьями с development и не были пересэмплированы.

## Проверки и локальные файлы

- **119 основных тестов**, включая 11 новых synthetic split-audit tests — OK.
- **3 reader tests**, `pip check`, CLI help и `git diff --check` — OK.
- Near join сравнён с brute force на synthetic данных при thresholds 0.5/0.9/1.0;
  проверяются именно пары, а не только компоненты.
- Проверены HTML/NFKC/Unicode, пустые описания, транзитивные связи, exposure,
  лимит сравнений, изменённые sources/artifacts, неblank reserve и полный карантин.
- Финальный run и повтор из одного чистого producer: **все 9 файлов побайтно
  идентичны**. Оба комплекта прошли verify, hashes всех входов сохранились.
- Reviewed M2 reference SHA остаётся
  `2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337`.

Приватный комплект: `outputs/evaluation/eval-002-20261019-final/`.
Повтор: `outputs/evaluation/eval-002-20261019-repeat/`.
Предварительный run `eval-002-20261019-v1/` сохранён, но финальный — `final`.
SKU/fingerprints/membership/violation lists в Git не включены.

| Файл финального комплекта | SHA-256 |
| --- | --- |
| `audit.summary.json` | `5066f7a884631833d3d52589713d09d8fd94de89e6914301aaac4fbe2ee10da7` |
| `audit.policy.json` | `720e29871bd1c41aae72cc9a66d75ef25cce82e2744dbe8447c1f9573c4d322e` |
| `eligible.split_manifest.jsonl` | `8ce0d73e9c827b5410b86190d5588526c23cdb769fa3a81b63ad8f13ff1a5832` |
| `quarantine.manifest.jsonl` | `254d8031980e6513335029a1d0f666d6c73d1894213ef973daec990a717a5a39` |
| `membership.jsonl` | `246fdd4c57abbf9f6dd7e8ee1bdfca4afdc94fa526a13ab50236b8a54cd1e6cf` |

SHA policy включает локальные пути sources. На другой машине этот hash может
отличаться, как и producer metadata; membership/eligible/quarantine воспроизводятся
по идентичным source bytes и версии алгоритма. Локальная побайтная проверка
относится к двум указанным run одного producer/environment.

## Что дальше

Reviewer проверяет метод, полноту exposure ledger и отдельную версию partition.
После review EVAL-001 может готовить blind human review текущих 40 reserve tasks,
не показывая их разработчикам до freeze. Нужны два независимых человека и
adjudication; инструмент их не заменяет. Метрики качества в EVAL-002 не считались.
Runtime, зависимости, VM и main этой задачей не менялись.
