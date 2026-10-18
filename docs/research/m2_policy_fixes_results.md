# M2: согласованные политики в runtime

19 октября 2026, Europe/Moscow. Локальная ветка `feature/vlad-m2-policy-fixes`
от проверенного `origin/main=5adab92` (M2, PR #11); рабочее дерево перед
началом было чистым. Основание — [разбор M2](m2_evaluation_results.md),
[политика v3](m2_annotation_policy_v2.md) и прежние подтверждения цветов.
Контракт v0.1, единицы, heuristic confidence и review/abstain сохранены.
Новых общих решений разметки не вводилось. Независимого gold/test пока нет.

## Что исправлено

- Одиночная ёмкость без роли больше не становится storage из-за величины
  числа. Нужна явная роль или согласованная связная RAM/ROM-пара с единицей.
  Поддержаны также пары `8GB/256GB`: единица может стоять у обоих чисел.
  Это необходимая часть исправления: иначе удаление default теряло старый
  storage TP. Несвязанные числа и пары без единиц не получают роль догадкой.
- В соседней явно написанной последовательности Xiaomi Redmi выбирается
  Redmi. Единственная настроенная связь — Xiaomi → Redmi; позднее упоминание
  другого товара/совместимости не получает приоритет. Полное Galaxy Line
  выбирается по длинному совпадению; из одного Galaxy оно не достраивается.
  Добавлены явно написанные и ранее reviewed марки Sonnen, Weissgauff, Аксинья.
- Словарь цветов сохраняет утверждённые оттенки и составные названия:
  глубокий синий, бронзовый, ультрамарин, титановый, лавандовый,
  серо-зеленый, серебристо-голубой, серебристо-черный и ограниченные алиасы.
  Полное Titanium Silverblue имеет приоритет над отдельным Titanium.
  Незнакомый квалификатор после Titanium не отбрасывается ради базового цвета.
- Prestige/Misty и текстура Matte сохраняются в span, но не определяют
  новый оттенок. Это небольшой явный список, не универсальный перевод
  маркетинговых названий. Ближайшая общая пометка «многоцветный» включается
  в тот же span; единственный конкретный цвет остаётся кандидатом.
  Два конкретных противоречащих цвета по-прежнему дают abstain.
- Titanium не извлекается из сообщения о материале корпуса. В description
  нужен явный цветовой контекст; в title допускается самостоятельный вариант.
  Составные алиасы допускают обычные пробелы/NBSP и видимые inline HTML-теги,
  evidence сохраняет точные исходные координаты. Script/атрибуты не читаются.

Схема v0.1 допускает один непрерывный evidence-span одного поля. Два сигнала
цвета в разных полях нельзя объединить в одно evidence без изменения контракта:
при конкретном цвете и общей пометке возвращается span конкретного цвета,
общая пометка остаётся во входе. Полная фраза сохраняется для поддержанных
соседних модификаторов; для произвольных неизвестных слов это не обещается.
Новые массивы evidence и интерфейс ручной очереди не добавлены.

`rules_version=rules-0.3.0-m2-policy`,
`dictionary_version=manual-reviewed-brand-and-color-names-v2`.
Model grammar не расширена; её prefix использует новые алиасы и нормализуемые
пробелы только для определения границ. Количество model TP/FP/FN не изменилось
на всех трёх проверенных срезах. Другие числовые правила не расширялись.
Синтетический demo-conflict теперь содержит явный ROM в title, чтобы проверять
конфликт двух подписанных объёмов, а не отменённую догадку; demo version v3.

## Парное сравнение

Один неизменный AI-assisted human-reviewed reference M2: 20 карточек,
120 полей, 83 present / 32 absent / 5 ambiguous, judged 115. SHA256:
`2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337`.
Тексты проецируются в Product через allowlist; gold/group metadata не передаются
extractor. Нет target/vendor/model-подсказок, lookup по SKU и внешних вызовов.
Правила подбирались по development; это оценка разработки, не обобщения.

A — снимок main `5adab92` с M1 rules-0.2.1 (совпадает по доменным результатам
с прежним M2 C); C — исправленная версия. Имена A/C относятся к **этому**
эксперименту, не к старому M2, где A был baseline до model. B — технический
ablation нового C без generation model, не промежуточная версия правок.

| Версия / M2 | TP / FP / FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| A: прежний M1 | 58 / 3 / 25 | 95,1% | 69,9% | 80,6% |
| C: policy fixes | 69 / 0 / 14 | 100,0% | 83,1% | 90,8% |

Дельта: 3 FP+FN→TP, 8 FN→TP, **lost_tp=0, new_fp=0**.
Две storage-выдачи на ambiguous исчезли: excluded_with_candidate **2→0**.
Это отдельное исправление риска; abstain на ambiguous не засчитан TP/TN.
Изменения только rule_id/evidence у сохранённых TP не считаются приростом.

| Атрибут C | TP / FP / FN | P | R | F1 |
| --- | --- | --- | --- | --- |
| brand | 20 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| model | 12 / 0 / 7 | 100,0% | 63,2% | 77,4% |
| storage_gb | 5 / 0 / 1 | 100,0% | 83,3% | 90,9% |
| ram_gb | 6 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| screen_inches | 3 / 0 / 1 | 100,0% | 75,0% | 85,7% |
| battery_mah | 1 / 0 / 3 | 100,0% | 25,0% | 40,0% |
| capacity_l | 2 / 0 / 2 | 100,0% | 50,0% | 66,7% |
| power_w | 4 / 0 / 0 | 100,0% | 100,0% | 100,0% |
| color | 16 / 0 / 0 | 100,0% | 100,0% | 100,0% |

| Категория C | Judged | TP / FP / FN | P | R | F1 |
| --- | --- | --- | --- | --- | --- |
| Смартфоны 761 | 66 | 41 / 0 / 8 | 100,0% | 83,7% | 91,1% |
| Чайники 482 | 49 | 28 / 0 / 6 | 100,0% | 82,4% | 90,3% |

Judged coverage **61/115→69/115 (53,0→60,0%)**; all-pair coverage
**63/120→69/120 (52,5→57,5%)**; card coverage **19/20→20/20**.
Correct coverage 58/115→69/115. Auto-accepted coverage=0, все кандидаты review.
Полные category×attribute, score bins и 17 заранее заданных срезов — в outputs.

Дополнительная проверка на прежних frozen reviewed-v2 без изменения меток:

| Исторический срез | До: TP / FP / FN; F1 | После: TP / FP / FN; F1 | lost TP / new FP |
| --- | --- | --- | --- |
| Development, 10 карточек / 57 judged | 26 / 1 / 11; 81,3% | 28 / 0 / 9; 86,2% | 0 / 0 |
| Development-feedback, 12 / 67 | 36 / 1 / 14; 82,8% | 39 / 1 / 11; 86,7% | 0 / 0 |

Бывший validation остаётся development_feedback; использован после заморозки
исправленной реализации, правила после этого не подбирались. Отдельные метрики
двух reference не объединяем. Один старый capacity FP остаётся вне этого scope.
100% precision на M2 — 69 кандидатов небольшой обсуждённой выборки, не гарантия
нулевых ошибок на каталоге. У M2 model нет judged-негативов. Нельзя обещать
качество редких продавцов/категорий, holdout F1 или конкретные баллы прогона.

## Проверки и воспроизведение

82 основных теста на Windows / Python 3.12.6: правила/контракт/evidence,
негативы памяти и цветов, CLI/API parity, demo, comparison guard и R3 storage.
Новый пакет содержит 11 policy tests, 1 HTTP policy test и 1 dictionary guard;
остальные регрессии сохранены. Reader не менялся и повторно не запускался.
Demo 6/6. CLI/API используют тот же Extractor; demo идёт через реальный CLI.
Реальных карточек в fixtures нет. Эта runtime-версия на Linux/ВМ не проверена.
Пользователь отдельно показал 69 OK / active / health ok на ВМ для прежнего M2.

В comparison добавлен явный `--allow-dictionary-changes`: без него изменение
справочников/политики отвергается; schema/categories менять по-прежнему нельзя.
Изменённые ключи, версии, SHA, text-only input и snapshots записаны в manifest.
По 3 запуска A/B/C на каждом срезе: внутри варианта predictions побайтно одинаковы.
Gold, старые predictions/manifests/отчёты не перезаписаны; SHA защищённых
источников проверяются runner. Test reserve не открывался и не предсказывался.

Фактические новые локальные каталоги `outputs/experiments/model-stage/`:

- `m2-policy-fixes-v2/`, `m2-policy-fixes-v2-slices/` — итоговый M2;
- `m2-policy-legacy-development-v2/`, `m2-policy-legacy-feedback-v2/` — регрессии;
- `m2-policy-fixes-v1/`, `m2-policy-legacy-development-v1/` — сохранённая
  промежуточная попытка, не принятая из-за потери TP пары с двумя единицами
  и нового FP на составном цвете. Исправления подтверждены итоговым v2.

Идентичность итогового C (dirty working tree, до commit):

- code SHA256 `392747b47cf2d479f0b8b59bce8db9a716b8f3193071eb0573bd021110a2de7c`;
- config SHA256 `cb7285cb3b83d2584661d5ec8eb4a315d6581148a5c3b1f7d012a0998db19a2b`.

Медиана extractor p50 A/C на M2: 0,971/1,346 мс; диапазон p95
2,761–2,776 / 3,651–3,820 мс; медиана batch 185,8/193,5 мс.
Малые batch, процессы development запускались параллельно: цифры описательные,
не контролируемый benchmark и не SLA. LLM calls/tokens/API cost = 0.
M3, расходы и обновление ВМ не выполнялись. После проверки пользователь
разрешил публикацию feature-ветки через PR в main; SHA/merge проверять через Git/PR.

Повтор из корня checkout с локальным reference, **новыми** output-каталогами:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/demo/m2-policy-next
.\.venv\Scripts\python.exe scripts/research/compare_model_stage.py --gold data/gold/e1/m2/v2/reviewed/development.human-reviewed.jsonl --split development --baseline-ref 5adab92 --allow-dictionary-changes --repeats 3 --output-dir outputs/experiments/model-stage/m2-policy-next
.\.venv\Scripts\python.exe scripts/research/summarize_m2.py --experiment outputs/experiments/model-stage/m2-policy-next --bundle data/gold/e1/m2/v2 --output outputs/experiments/model-stage/m2-policy-next-slices
```

`--previous-run outputs/experiments/model-stage/m2-reviewed-development-v1`
необязателен для A/C и добавляет сравнение с сохранённым прежним M2 C.
На Linux заменить Python-путь на `.venv/bin/python`. Для исторических срезов
использованы reviewed-v2/development.jsonl и validation.jsonl, baseline 5adab92,
тот же flag словарей, previous-run m1-boundaries-development/feedback и
freeze-from нового development для validation плюс `--feedback-reference`.
Без локальных data/gold доступны синтетические tests/demo, реальные P/R/F1 N/A.

## Следующие задачи

1. Передача исправленного runtime через PR и отдельно проверенное обновление ВМ.
2. Небольшие улучшения явных форматов: батарея с нестандартным разделителем,
   контекст экрана/вместимости, внешняя карта отдельно от storage; границы
   model только с отрицательными регрессиями и новым сравнением development.
3. Отдельно разрешённый реальный M3 через шлюз организаторов: model fallback,
   проверка схемы/источника/конфликтов, маршрутизация, latency и бюджет.
4. После фиксации методов — отдельный слепой reviewer 40 зарезервированных test.

Исправления дают доказательства по R4/R5/R6, но не закрывают модельный слой R7,
независимую оценку, итоговый файл всего каталога и финальную презентацию.
