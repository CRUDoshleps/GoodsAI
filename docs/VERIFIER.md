# VER-002: общий verifier кандидатов

Issue [#37](https://github.com/CRUDoshleps/GoodsAI/issues/37) принят в main через
[PR #118](https://github.com/CRUDoshleps/GoodsAI/pull/118), merge `0a1d134`.
База — `73faf07`, опубликованный claim — `8a55d81` (исправление кодировки — `eddf6a1`).
Это завершение проверки на действующем stage contract v1 / result v0.1.
Официальный контракт #10 и приёмка новых реальных категорий не объявляются
завершёнными. ARCH-001 принят отдельно (PR #119, `88a216b`): фабрика gate входит
в [единую сборку CLI/API](ARCHITECTURE.md). Новые поля JSON не добавлены.

## Порядок проверки

`CandidateVerifier.reason(candidate)` из
[candidate_verifier.py](../src/goodsai/candidate_verifier.py) возвращает `None`
либо фиксированный reason code. Score и имя генератора не дают исключений.
`None` означает отсутствие обнаруженного нарушения, а не доказанную вероятность.

1. Проверяются тип `Candidate`, поле категории, типы offsets/score/value/unit,
   диапазон и точное совпадение raw slice.
2. Применяется общий `RelationVerifier`: видимость HTML, основной товар,
   совместимость, аксессуары, комплектность, отрицания, цвет внутри имени,
   material-role и неизвестные модификаторы цвета.
3. Явные служебные команды и помеченные примеры ответа/JSON отклоняются
   с `relation_instruction_or_example`, даже если число дословно есть в тексте.
4. Каноническое значение подтверждается evidence: единицы и десятичные
   преобразования, словарный alias, точное открытое имя бренда либо пробельная
   нормализация модели. Число из другого фрагмента не подтверждает значение.
5. Для памяти сохраняются роли пары и явные RAM/ROM-маркеры; одиночный объём
   без роли не превращается автоматически в storage. Неясность даёт отказ.
6. У модели проверяются границы токена и пропущенные части имени, когда
   существующая grammar определяет полный span. Бренд, память, цвет и отдельное
   обозначение сети не становятся моделью. `Galaxy` в смартфоне остаётся линейкой.
7. После фильтрации прежний merger сохраняет конфликт разных допустимых
   значений. Приоритет title или высокий score конфликт не разрешает.

Числовые bounds, единицы, словари и confidence не изменялись. Только `review`
и `abstain`; `auto_accept` не появляется.

## Все источники используют один gate

| Источник | Точка подключения | Отказ |
| --- | --- | --- |
| Rules / внедрённый CandidateSource | `Extractor.predict`, до объединения | reason в `abstain`; ошибки структурного инварианта внутреннего генератора остаются fail-fast |
| LLM, свежий ответ и cache replay | `ground`, после привязки цитаты | candidate отклоняется; reason попадает в результат и счётчики LLM |
| Экспериментальный GLiNER | `HybridExtractor.predict`, до выбора бренда | reason в результате и безопасной диагностике; существующие rules не перезаписываются |

`validate_candidate` по прежнему пути `goodsai.verify` сохранён как совместимый
импорт. Структурный дефект внутреннего генератора не маскируется успешным
пустым ответом. Внешний кандидат проверяется gate с безопасным фиксированным кодом.
Операционный manifest уже агрегирует `reason_codes` в `abstention_reasons`;
LLM дополнительно сохраняет `rejected`. Текст карточки в эти счётчики не попадает.
Полноценного интерфейса ручной записи в runtime ещё нет: будущий операторский
route также обязан использовать gate; он здесь не заявляется реализованным.

## Причины отказа

| Группа | Коды |
| --- | --- |
| Структура | `verifier_bad_candidate`, `verifier_unknown_attribute`, `verifier_bad_field`, `verifier_bad_offsets`, `verifier_bad_types`, `verifier_bad_score`, `verifier_bad_unit`, `verifier_bad_evidence` |
| Нормализация и поддержка | `verifier_bad_normalization`, `verifier_bad_number`, `verifier_out_of_range`, `verifier_unsupported_value`, `verifier_uncertain_value` |
| Роль и модель | `verifier_ambiguous_memory_role`, `verifier_incomplete_model`, `verifier_unsupported_model` |
| Принадлежность | прежние `relation_*` и новый `relation_instruction_or_example` |

Поле с отказом не надо заполнять отвергнутым значением вручную автоматически.
Проверяющий уточняет исходный факт и evidence. Изменение источника требует
повторного извлечения; изменение score не обходит проверку.

## Воспроизведение

Из корня checkout с полной Git-историей; директории должны быть новыми:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_candidate_verifier.py -v
.\.venv\Scripts\python.exe -m scripts.research.verify_candidates --baseline-ref 73faf07 --output-dir outputs/verifier-synthetic-check
.\.venv\Scripts\python.exe -m scripts.release.external_acceptance --output-dir outputs/verifier-external-check
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/demo/verifier-check
```

Linux использует `.venv/bin/python`. Синтетический runner замораживает старый и
текущий пакет, input/predictions hashes, expected/observed/reasons и сохраняет
`report.json`. Он считает неверные значения, пропущенные настоящие факты и
потерю прежде правильных фактов. Это targeted regression, не human gold.

Для уже существующих локальных reviewed development, без открытия reserve:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.compare_model_stage --gold data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl --baseline-ref 73faf07 --output-dir outputs/evaluation/verifier-m2-check --repeats 2
.\.venv\Scripts\python.exe -m scripts.research.compare_model_stage --gold outputs/evaluation/development-review-20261019-human-v2/development.human-reviewed.jsonl --baseline-ref 73faf07 --output-dir outputs/evaluation/verifier-d21-check --repeats 2
```

Оценивать **A против C**. B — историческая model-generation ablation этого
инструмента, не отдельный вариант verifier. Pair deltas и per-attribute/category
метрики сохраняются в private output. Любые новые FP или lost TP требуют
разбора до выпуска. Старые gold, predictions и отчёты не заменяются.

## Результаты и ограничения

Целевые synthetic cases: **5/12 → 12/12**, неверные значения **4 → 0**,
пропуски настоящих фактов **3 → 0**, потерянные правильные факты **0**.
Здесь есть два примера из комментария #37, JSON/multiline examples, настоящий
факт после команды, HTML/emoji и настоящий конфликт двух батарей.

Reviewed development (AI-assisted, уже использовался разработчиками):

| Reference | Cards / judged / excluded | TP / FP / FN до = после | F1 до = после |
| --- | --- | --- | --- |
| M2 D01–D20 | 20 / 115 / 5 | 78 / 0 / 5 | 96,89% |
| D21–D40 | 20 / 109 / 11 | 65 / 0 / 17 | 88,44% |
| Вместе | 40 / 224 / 16 | 143 / 0 / 22 | 92,86% |

Новых FP / lost TP / изменённых значений — **0**. Полнота на этом development
не увеличилась; задача устраняет конкретные пути ложного подтверждения.
Нулевой FP на этих карточках не доказывает нулевой риск для каталога.

Unit/integration tests проверяют настоящий rules path, fake LLM + cache replay,
инъекцию model entities без загрузки весов, CLI/API parity и manifest reasons.
В первоначальном эксперименте реальные LLM и GLiNER inference не выполнялись,
ВМ не менялась, candidate ещё не был слит в `main`; test reserve не открывался.
На candidate `9ce6432`: 386 основных + 3 reader
tests OK; external 83/83; demo 6/6 и verify; locked clean-run 11/11; pip check
OK. Все 6 CI checks SUCCESS на Linux/Windows. Последующее изменение этого
документа не меняет проверенный runtime.

Private артефакты: `outputs/ver002-synthetic-candidate/`,
`outputs/ver002-external-candidate/`, `outputs/demo/ver002-candidate/`,
`outputs/evaluation/ver002-m2-candidate/`, `outputs/evaluation/ver002-d21-candidate/`,
`outputs/ver002-clean-9ce6432/`.
Пакет и inputs привязаны hashes внутри отчётов; development тексты не коммитятся.

Это конечные языковые проверки. Произвольные перефразирования команд,
межфразовые ссылки и неизвестные границы имени не распознаются универсально.
Незакрытый явно помеченный JSON example консервативно блокируется до конца
поля. Обычная инструкция в комплекте и JSON с реальными характеристиками
не блокируются только из-за слова «инструкция» или фигурных скобок.
Неполнота модели проверяется для границ, доказуемых текстом и grammar;
полнота произвольного торгового имени этим не гарантируется.
Малые Windows-батчи не заменяют нагрузочный тест или SLA. Прирост баллов
организаторов до нового прогона неизвестен.

Откат — обычный revert реализации через PR. Миграция данных не требуется.
