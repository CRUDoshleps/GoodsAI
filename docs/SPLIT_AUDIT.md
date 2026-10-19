# Аудит split и утечек E1 — EVAL-002

Задача [#7](https://github.com/CRUDoshleps/GoodsAI/issues/7). Инструмент:
`scripts/research/audit_splits.py`. Это offline-проверка разбиения, не оценка
extractor и не независимая разметка. Runtime, schema v0.1 и predictions не меняются.

## Воспроизведение

Нужны Python 3.12+, установленный проект, локальные E1 input/split и frozen M2 v2.
Реальных данных в clone нет. Команды из корня проекта, новый output-dir:

```powershell
.\.venv\Scripts\python.exe -m scripts.research.audit_splits --output-dir outputs/evaluation/eval-002-next
.\.venv\Scripts\python.exe -m scripts.research.audit_splits --verify-bundle outputs/evaluation/eval-002-next
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_split_audit.py -v
```

На Linux использовать `.venv/bin/python`. Linux/VM-прогон выполняется отдельно;
локальный Windows-прогон его не заменяет. Все аргументы доступны через `--help`.
CLI разрешает новые результаты только внутри игнорируемого `outputs/`;
существующие каталоги не перезаписываются.

Входы по умолчанию:

- `data/processed/e1/pilot.jsonl` — только identity/category/title/description;
- `data/gold/e1/split_manifest.jsonl` — исходные назначения;
- `data/gold/e1/m2/v2/family.manifest.jsonl` — замороженные консервативные связи;
- `data/gold/e1/m2/v2/selection.summary.json` — проверка input/split/family/reserve SHA;
- `data/gold/e1/m2/v2/test_reserve.blank.jsonl` — только metadata и пустота заданий;
- exposure ledger: frozen `known_exposure` M2 плюс исходные E1 tasks,
  `ai/full.annotations.v4.jsonl`, development tasks M2 v1/v2. Из annotation-файлов
  используется только `sku_id`, значения атрибутов не участвуют в аудите.

`--exposure-source` можно повторять; явные аргументы **заменяют** дополнительный
список по умолчанию. Frozen known exposure остаётся обязательным. Для новой
версии состава источников нужно зафиксировать полный ledger, а не удалить
неудобные источники. Пропущенный файл/неизвестный SKU/изменённый SHA — ошибка.

## Политика, замороженная до проверки текстов

`audit.policy.json` создаётся до чтения текста/построения связей, содержит
версию алгоритма и SHA всех входов. Числовые пороги взяты из прежней M2 policy,
по test они не подбираются. Инструмент не импортирует predictor/evaluator/LLM.

1. Проверяются уникальность SKU, совпадение множеств input/split/families,
   category/group/split metadata и принадлежность резервных заданий.
2. Сравниваются SHA исходных title/description и пары полей целиком.
3. Нормализация: Unicode NFKC → видимый HTML-текст → casefold → ё/е → пробелы
   вместо nonword → strip. Поля не склеиваются без сохранения границы.
   Пустые значения не создают связи дублей.
4. Near title: Jaccard множеств символьных триграмм, threshold 0.90.
   Near description: Jaccard множеств пятисловных shingles, threshold 0.90.
   Полный threshold join использует частотный prefix filter; сравниваются и пары
   внутри уже связанных семейств, поэтому диагностика не теряет их из счётчиков.
   Более 5 млн сравнений на поле останавливают аудит; частичный pass не выдаётся.
5. Компоненты объединяют original groups, frozen M2 families и все найденные
   связи текста. M2 family links наследуют прежнюю группировку, включая
   vendor/model как metadata split; эти поля не являются inference-подсказками.
6. Все строки смешанного компонента исключаются целиком. Семейство с известным
   exposure и test_reserved также исключается целиком. Назначения не меняются,
   новый test не выбирается и тексты test не выводятся/не экспортируются.

Совпадение описаний может быть шаблоном продавца, близость текста — случайной.
Поэтому это **консервативный карантин кандидатов**, а не утверждение, что все
6913 исключённых строк — доказанные семантические дубли. Нет гарантии обнаружения
семейств ниже порога сходства. История просмотров ограничена записанным ledger.

## Новый partition и границы использования

Старые split, M2 v1/v2, gold и результаты не заменяются. Новая версия partition —
два взаимодополняющих файла с lineage в `audit.summary.json`:

| Файл | Назначение |
| --- | --- |
| `eligible.split_manifest.jsonl` | только целиком сохранённые непересекающиеся компоненты |
| `quarantine.manifest.jsonl` | исключённые компоненты и причины; использовать для независимой оценки нельзя |
| `membership.jsonl` | все исходные SKU, исходный group ID, новый family/group ID, split, exposure и причины |
| `fingerprints.jsonl` | только SKU и SHA текстов, без самих текстов |
| `violations.jsonl` | локальные списки исходных пересечений, идентификаторы, detector и similarity |
| `family.edges.jsonl` | лес связей компонентов; не полный список всех near pairs |
| `reserve.violations.jsonl` | проблемы действующего резерва; пустой при успешной проверке |
| `audit.policy.json`, `audit.summary.json` | параметры, provenance, агрегаты, producer SHA/dirty и checksums |

Формат и значения `split` сохранены. Новый `group_id` — ID полного компонента,
старый доступен как `original_group_id`. Это отдельный audit metadata format,
не изменение runtime-контракта. В последующие sampling/evaluation-процессы новый
partition подключается явно после review; старый input нельзя автоматически
оценивать целиком по отфильтрованному manifest.

`validation` имеет роль `development_feedback`. Только сохранённые непоказанные
test_reserved — кандидаты независимого резерва, но ещё не gold. Проверка всех
40 текущих заданий не читает их тексты и не генерирует predictions; проверяется
также, что labels пустые. При проблеме задача не заменяется автоматически.

Verifier сверяет исходные SHA, состав/целостность файлов, полноту partition,
связи и отсутствие mixed/exposed test-компонентов среди eligible. Статус
`verified` подтверждает целостность комплекта, **не** пригодность всего исходного
split или безопасность резерва: отдельно смотреть `reserve.status` и отчёт.
Hashes защищают от случайного изменения, не аутентифицируют недоверенный bundle.

Реальные SKU, group/family ID, fingerprints, задания и списки пересечений остаются
вне Git. Публикуются только фиксированные агрегаты и hashes в отчёте EVAL-002.
