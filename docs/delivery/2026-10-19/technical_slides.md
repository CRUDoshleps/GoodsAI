# GoodsAI

Технический checkpoint · 2026-10-19

Rules baseline для смартфонов и чайников.
Code candidate: `047e1ee4abc5e04b0c3d49da3bfab81760f4376f`.

---

# Данные и границы прогноза

- Каталог: 546069 SKU. Подготовленный E1: 10324 SKU.
- Новый batch: **2198 development SKU** двух категорий.
- 8126 E1 SKU исключены: другие split и защищённые/смешанные семейства.
- Закрытый test не предсказывался. Данные — только title/description; изображения и target params не используются.

Источник: private/eda.md в комплекте, selection policy `development-only-unmixed-families-v1`.

---

# Пайплайн

Text-only Product → правила и словари → проверка кандидата → нормализация → проверка конфликта и выхода → JSONL + manifest.

- Значение сопровождается исходным evidence span.
- Конфликт/отсутствие → abstain; найденный кандидат → review.
- Confidence эвристический. Автоматического принятия нет.
- Реальная ML/LLM-ветка пока отсутствует.

Источник: src/goodsai/contracts.py, verify.py, rules.py, model_rules.py.

---

# Оценка на reviewed development

**P 100,0% · R 83,1% · F1 90,8%**

TP 69, FP 0, FN 14 · 20 карточек, 115 judged-пар.

AI-assisted human-reviewed M2, использованный при разработке.
Это **не независимый holdout** и не оценка качества всего каталога.
Бывший validation также является development_feedback.

Источник: public/quality.json; frozen reference SHA в release.manifest.json.

---

# Качество по атрибутам

| Поле | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| battery_mah | 1 | 0 | 3 | 40,0% |
| brand | 20 | 0 | 0 | 100,0% |
| capacity_l | 2 | 0 | 2 | 66,7% |
| color | 16 | 0 | 0 | 100,0% |
| model | 12 | 0 | 7 | 77,4% |
| power_w | 4 | 0 | 0 | 100,0% |
| ram_gb | 6 | 0 | 0 | 100,0% |
| screen_inches | 3 | 0 | 1 | 85,7% |
| storage_gb | 5 | 0 | 1 | 90,9% |

У model в M2 нет judged-примеров с отсутствующей моделью: model-FP на таких случаях не измерен.
Неверное значение вместо present gold = FP+FN; ambiguous исключаются явно.

---

# Работа на batch

- Строк результата: 2198, ровно одна на каждую входную карточку.
- Статусы: {"processed": 2198}.
- Измеренные extractor p50/p95: 1.017/3.066 мс.
- Полное локальное время batch: 2.87 с.
- LLM calls: 0; API-расход: 0 ₽. Денежная стоимость compute не оценивалась.

Windows/Python 3.12.6; один локальный запуск, без гарантий SLA.
Coverage показывает заполнение кандидатов, а не precision.

---

# Комплект и воспроизведение

Код/README, EDA-сводка, pipeline/config, реальные development predictions,
reviewed-метрики, технические Markdown-слайды и frozen manifest.

Сборка: `python -m scripts.release.prepare_delivery --report-date 2026-10-19 --output-dir outputs/delivery/new-run`

Проверка: `python scripts/release/build_release.py verify --bundle outputs/delivery/new-run/bundle`

Нужны локальные данные и frozen metadata. Private input/gold/predictions не публикуются автоматически.

---

# Ограничения и дальнейшая работа

- Не выполнена независимая blind human-оценка; test остаётся закрытым.
- Поддерживаются две категории; длинный хвост и ноутбуки ещё не закрыты.
- Нет ML/LLM-сравнения, калибровки confidence и auto_accept.
- Дальше: release gate и проверка VM, независимый gold, затем измеряемый модельный эксперимент.

Технический черновик checkpoint; финальные выводы защиты обновляются после независимой оценки.
