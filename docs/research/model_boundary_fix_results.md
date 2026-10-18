# M1: исправление границ бренда и коммерческого имени

18 октября 2026. Windows 11 / Python 3.12.6, `feature/vlad-model-rules`.
Продолжение [первого M1](model_stage_results.md), разрешённое пользователем
после разбора двух model FP. Исторические результаты и файлы M1 сохранены.

## Изменения

- Последовательные явно написанные обозначения бренда исключаются из model
  смартфона; модельная линейка Galaxy остаётся частью имени телефона.
  Это граница model, существующее значение атрибута brand не изменяется.
- У чайника слова между явно распознанным производителем и индексом больше
  не отбрасываются. При неясной роли этих слов — abstain. Полное коммерческое
  имя со словесной частью по-прежнему извлекается из явного поля «Модель: …».
- Неизвестный многословный префикс производителя тоже считается неясной
  границей; одно слово или составное имя с `&` остаются ограниченной эвристикой.
- `model_brand_aliases=["Galaxy Line"]` используется только как граница model:
  полное имя бренда уже подтверждено пользователем ранее. Это не справочник
  товарных моделей и не изменение словарей других атрибутов.
- Версия правил `rules-0.2.1-model-boundaries`, model rule_id v2. Контракт
  v0.1, confidence heuristic, review/abstain и отсутствие auto_accept сохранены.

Добавлены синтетические регрессии на двойной бренд, сохранение телефонной
линейки, неясную серию чайника и полное имя в явном поле. Реальные карточки
не копировались в tests, target-поля/SKU lookup не используются.

## Происхождение оценки

**Прежний validation использован как обратная связь для исправлений.**
Повторный результат на нём — проверка известных случаев (`development_feedback`),
а не независимый validation/holdout. Метки и исходные файлы со split=validation
не переименовывались и не переписывались; роль среза явно записана в новом
experiment manifest. Независимый test не открывался, M2/M3 не выполнялись.

Инструмент [compare_model_stage.py](../../scripts/research/compare_model_stage.py)
сохраняет baseline A / ablation B / текущий C и дополнительно сравнивает C
с сохранённым первоначальным M1 через `--previous-run`. Проверяются SHA reference,
text-only входа, старых результатов и одинаковые наборы SKU. В отчёте есть
переходы качества, lost_tp/new_fp, frozen package и сырые времена.

## Результат на неизменных reviewed-reference

| Срез / версия | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development: baseline A/B | 18 | 1 | 19 | 94,7% | 48,6% | 64,3% |
| Development: первый M1 | 26 | 1 | 11 | 96,3% | 70,3% | 81,3% |
| Development: исправленный C | 26 | 1 | 11 | 96,3% | 70,3% | 81,3% |
| Бывший validation: baseline A/B | 29 | 1 | 21 | 96,7% | 58,0% | 72,5% |
| Бывший validation: первый M1 | 35 | 3 | 15 | 92,1% | 70,0% | 79,5% |
| Бывший validation: исправленный C | 36 | 1 | 14 | 97,3% | 72,0% | 82,8% |

Development — 10 карточек / 57 judged-пар, model **8 TP / 0 FP / 1 FN**.
Срез обратной связи — 12 карточек / 67 judged-пар, model **7 TP / 0 FP / 5 FN**.
Устранены обе новые ошибки model: **FP+FN→TP** и **FP+FN→FN** (отказ).
Правильных значений из первоначального M1 не потеряно, новых FP нет на обоих
просмотренных срезах. Смена model rule_id не считается улучшением качества.

Все прочие атрибуты совпадают с baseline A и первым M1, включая evidence,
значения, score и причины. Оставшийся один FP — прежний brand на development
и прежний capacity_l на срезе обратной связи; эти правила в данном scope не менялись.
Полные per-attribute/category/category×attribute метрики находятся в локальных
`A|B|C/metrics.json`; остальные срезы по атрибутам совпадают с первым M1.

Покрытие C по judged: dev 27/57, feedback 37/67; correct coverage 26/57 и 36/67.
Для model: dev 8/10, feedback 7/12. Auto-accepted coverage=0.
Пять оставшихся model FN на feedback — отказы на неясных коммерческих именах;
проверка источника не решает автоматически их семантику. Нужен более разнообразный
development и независимый reviewed test, прежде чем заявлять обобщение качества.

## Проверки и ограничения

- **59 основных тестов прошли**, включая 14 model tests, HTTP/CLI parity,
  ablation/freeze, сравнение с прошлым M1, пометку feedback и R3-сценарии сбоев.
- Demo **6/6**, 13 review / 11 abstain. Правила работают без LLM/сети.
- Собран wheel и установлен в отдельный каталог через pip без зависимостей;
  изолированный Python вне checkout загрузил именно этот пакет и выполнил
  demo 6/6 с тем же code SHA. Это не установка всех зависимостей в новой ВМ.
- A/B/C предсказания повторены трижды, внутри варианта побайтно одинаковы.
  A по доменным полям совпадает с историческими predictions без run_id.
- Локальные gold, исторические predictions и первоначальные M1-предсказания
  проверены SHA до/после; не перезаписаны.
- Для C медиана p50/p95 из трёх batch-процессов: dev 1,470/2,641 мс,
  feedback 0,581/3,775 мс. Это описательные числа на 10/12 карточках, не SLA.
- LLM calls=0, tokens=0, API-расход=0 ₽. Linux/ВМ и независимый test не проверены;
  расходы compute не оценивались по денежному тарифу.

Первоначальные ограничения M1 нельзя считать закрытыми на всём каталоге:
исправление просмотренных ошибок проверено, независимое обобщение ещё неизвестно.
Публикация такого ограниченного review-only baseline допустима с этим описанием;
она не означает разрешение автоматической записи характеристик в каталог.

## Воспроизведение

Нужны локальные reviewed-v2 и, для сравнения с первым M1, его сохранённые outputs.
Без `--previous-run` A/B/C воспроизводится из кода/reference и baseline Git-коммита.
Выбирайте новые каталоги:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m goodsai.demo --output-dir outputs/model-boundaries-demo-next
.\.venv\Scripts\python.exe scripts/research/compare_model_stage.py --gold data/gold/e1/reviewed/reviewed-v2/development.jsonl --output-dir outputs/experiments/model-stage/boundaries-dev-next --historical outputs/baseline/predictions.jsonl --previous-run outputs/experiments/model-stage/m1-development
.\.venv\Scripts\python.exe scripts/research/compare_model_stage.py --gold data/gold/e1/reviewed/reviewed-v2/validation.jsonl --split validation --freeze-from outputs/experiments/model-stage/boundaries-dev-next --output-dir outputs/experiments/model-stage/boundaries-feedback-next --historical outputs/baseline/predictions.jsonl --previous-run outputs/experiments/model-stage/m1-validation --feedback-reference
```

Фактические каталоги этого этапа: `outputs/experiments/model-stage/` →
`m1-boundaries-development/`, `m1-boundaries-feedback/`; demo —
`outputs/model-boundaries-demo/`. Per-SKU данные/дельты и frozen пакеты в Git не входят.

| Артефакт | SHA-256 |
| --- | --- |
| C code | `3fa9972c690370806c0ad42ad1e90d8174cce920f4c7c33a5dc8d0f2728fee85` |
| C config | `974ffffb9f56d30386ea41b456c5d78b1ff72ebbb40cd33ca3779af2c88e3b98` |
| Dev C predictions | `5879e0e9de6d17d1177ceefbf1fc2d1090bede60e04c4832259604b8513552ae` |
| Feedback C predictions | `77a3e707a507d30c1e5fe7e5410e05df65f6eeb600280ef047a7668f4371b7a9` |
| Dev experiment manifest | `615e2c2d1add8e13faf2ed5e714b0a434b383f5c2189021fd4755c7b835f434b` |
| Feedback experiment manifest | `5cdaea97ea605f403f234d06078c41b95e197dafd420c5a9281a80e6ac45e474` |

SHA Python-кода зависит от байтов/переносов строк. Историю публикации проверять
по Git/PR; эти experimental manifests фиксируют проверенную рабочую версию до commit.
Wheel SHA: `77b01305450594a0be54b3eb4a0a91b8c47560533057693b204a739f3240e5d5`;
локальный протокол — `outputs/release/model-wheel-verification.json`.
