# Запуск с нуля на своём JSONL

DOCS-003 / [#101](https://github.com/CRUDoshleps/GoodsAI/issues/101).
Один маршрут от `git clone` до ответа HTTP API на собственных карточках, без
packaged demo-файлов, датасетов, ключей и LLM. Что означают ответы и что делать
оператору — в [RESPONSES](RESPONSES.md).

`[DONE]` Linux-вариант выполнен целиком в новом клоне GitHub `main` **`7aec082`**,
Linux, CPython 3.12.3; все выводы ниже взяты из этого прогона. PowerShell-вариант
в этой проверке не запускался; те же шаги на Windows и Ubuntu проходят в CI job
`external-acceptance` (см. [EXTERNAL_ACCEPTANCE](EXTERNAL_ACCEPTANCE.md)).

Сеть нужна только на шагах 1–2: `git clone` и установка зависимостей из PyPI.
Прогноз, проверка и HTTP API работают офлайн.

## 1. Клон и Python

Нужна полная Git-история (без `--depth`): часть comparison tests использует
базовый commit. Нужен Python 3.12+; системный `python3` на VM бывает 3.10.

```bash
git clone https://github.com/CRUDoshleps/GoodsAI.git
cd GoodsAI
python3.12 --version
```

```powershell
git clone https://github.com/CRUDoshleps/GoodsAI.git
Set-Location GoodsAI
py -3.12 --version
```

## 2. Окружение

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m pip check
```

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[serve,test]"
.\.venv\Scripts\python.exe -m pip check
```

Ожидается `No broken requirements found.` Активировать окружение не нужно.
Существующую `.venv` не пересоздавайте поверх рабочей — сначала проверьте её Python.

## 3. Свои карточки

Отдельная папка в `outputs/` (каталог вне Git). Пять строк покрывают все исходы:
полный ответ, конфликт, пропуски, неподдерживаемую категорию и запрещённое поле.

```bash
mkdir -p outputs/my-run
cat > outputs/my-run/cards.jsonl <<'JSON'
{"schema_version":"0.1","sku_id":"own-ok","category_id":"761","title":"Смартфон Samsung Orbit X73 12/512GB белый","description":"Экран 6,4 дюйма. Аккумулятор 4600 мАч."}
{"schema_version":"0.1","sku_id":"own-conflict","category_id":"761","title":"Смартфон Samsung Orbit X73 8/256GB черный","description":"<p>Встроенная память 128 ГБ.</p><p>Экран&nbsp;6,1 дюйма.</p>"}
{"schema_version":"0.1","sku_id":"own-sparse","category_id":"482","title":"Электрочайник Vexa","description":null}
{"schema_version":"0.1","sku_id":"own-unsupported","category_id":"999","title":"Пылесос Vexa VC-10"}
{"schema_version":"0.1","sku_id":"own-invalid","category_id":"761","title":"Смартфон Samsung Orbit X73","vendor":"Samsung"}
JSON
```

PowerShell пишет тот же файл в UTF-8 без BOM (так же в Windows PowerShell 5):

```powershell
New-Item -ItemType Directory -Path outputs/my-run -Force | Out-Null
$cards = @(
  '{"schema_version":"0.1","sku_id":"own-ok","category_id":"761","title":"Смартфон Samsung Orbit X73 12/512GB белый","description":"Экран 6,4 дюйма. Аккумулятор 4600 мАч."}'
  '{"schema_version":"0.1","sku_id":"own-conflict","category_id":"761","title":"Смартфон Samsung Orbit X73 8/256GB черный","description":"<p>Встроенная память 128 ГБ.</p><p>Экран&nbsp;6,1 дюйма.</p>"}'
  '{"schema_version":"0.1","sku_id":"own-sparse","category_id":"482","title":"Электрочайник Vexa","description":null}'
  '{"schema_version":"0.1","sku_id":"own-unsupported","category_id":"999","title":"Пылесос Vexa VC-10"}'
  '{"schema_version":"0.1","sku_id":"own-invalid","category_id":"761","title":"Смартфон Samsung Orbit X73","vendor":"Samsung"}'
)
[IO.File]::WriteAllText((Join-Path $PWD 'outputs/my-run/cards.jsonl'), ($cards -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
```

Разрешённые поля: `schema_version` (`"0.1"`), `sku_id`, `category_id`, `title`,
`description`, `seller_attributes` (только `[]`), `source_flags`. Любое другое
поле — например готовые `vendor`, `model`, `params` — делает строку `invalid_input`.

## 4. Прогноз

```bash
.venv/bin/python -m goodsai.cli predict --input outputs/my-run/cards.jsonl --output outputs/my-run/predictions.jsonl
```

```powershell
.\.venv\Scripts\python.exe -m goodsai.cli predict --input outputs/my-run/cards.jsonl --output outputs/my-run/predictions.jsonl
```

Exit 0. Появляются `predictions.jsonl` (одна строка на входную строку, тот же
порядок) и `predictions.manifest.json`. Повторный запуск с тем же `--output`
атомарно заменяет эту пару; чтобы сохранить прежний результат, укажите новое имя.
Фактический итог прогона:

| `sku_id` | `status` | Что получилось |
| --- | --- | --- |
| `own-ok` | `processed` | 7 из 7 атрибутов `review`: Samsung, Orbit X73, 512 GB, 12 GB, 6.4 inch, 4600 mAh, белый |
| `own-conflict` | `processed` | `storage_gb` — `abstain` / `conflicting_evidence` (256 в title, 128 в description); батарея — `not_found_by_rules`; HTML и `&nbsp;` не мешают offsets |
| `own-sparse` | `processed` | 5 из 5 `abstain` / `not_found_by_rules`: бренда Vexa нет в словаре, чисел нет |
| `own-unsupported` | `unsupported_category` | `attributes: []` |
| `own-invalid` | `invalid_input` | `reason_codes: ["invalid_text_only_input"]`, номер строки в `input_line` |

## 5. Проверка результата

Сводка по файлу:

```bash
.venv/bin/python -c "import json; [print(r['sku_id'], r['status'], *[(a['attribute'], a['value'], a['decision'], a['reason_codes']) for a in r['attributes']]) for r in map(json.loads, open('outputs/my-run/predictions.jsonl', encoding='utf-8'))]"
```

Manifest связывает вход и выход по SHA-256 и считает статусы:

```bash
.venv/bin/python -c "import hashlib, json; m = json.load(open('outputs/my-run/predictions.manifest.json', encoding='utf-8')); sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest(); print(sha('outputs/my-run/cards.jsonl') == m['input_sha256'], sha('outputs/my-run/predictions.jsonl') == m['output_sha256'], m['status_counts'], m['abstention_reasons'], m['llm_calls'])"
```

Фактический вывод:

```text
True True {'processed': 3, 'unsupported_category': 1, 'invalid_input': 1} {'conflicting_evidence': 1, 'not_found_by_rules': 6} 0
```

В PowerShell те же команды с `.\.venv\Scripts\python.exe`; кавычки внутри
`-c` оставить одинарными.

## 6. HTTP API

```bash
.venv/bin/python -m goodsai.api --host 127.0.0.1 --port 8000
```

Во втором терминале:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  --data '{"schema_version":"0.1","sku_id":"own-http","category_id":"482","title":"Электрочайник Vexa KT-17 1,7 л 2200 Вт серебристый"}'
```

В PowerShell используйте `curl.exe` (не алиас `curl`) или:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/predict -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes('{"schema_version":"0.1","sku_id":"own-http","category_id":"482","title":"Электрочайник Vexa KT-17 1,7 л 2200 Вт серебристый"}'))
```

Фактический ответ `/predict` (HTTP 200, сокращено до одного найденного и одного
пропущенного атрибута):

```json
{"schema_version":"0.1","run_id":"http-rules-v0","sku_id":"own-http","category_id":"482","status":"processed","attributes":[
 {"attribute":"brand","value":null,"unit":null,"confidence":null,"confidence_kind":"heuristic","decision":"abstain","method":"rule","rule_id":null,"evidence":null,"reason_codes":["not_found_by_rules"]},
 {"attribute":"capacity_l","value":"1.7","unit":"L","confidence":0.8,"confidence_kind":"heuristic","decision":"review","method":"rule","rule_id":"capacity_l.explicit.v1","evidence":{"field":"title","start":25,"end":30,"text":"1,7 л"},"reason_codes":[]}]}
```

Полный ответ содержит все атрибуты схемы категории: здесь ещё `model=KT-17`,
`power_w=2200 W`, `color=серебристый`. `/health` возвращает
`{"status":"ok", ..., "categories":["482","761"]}` и hashes effective config и
policy. Ошибки запроса — JSON `{"error":{"code","message"}}`, см.
[RESPONSES](RESPONSES.md#ошибки-http-api). Swagger UI — `/docs`.

Экран проверки для оператора — `http://127.0.0.1:8000/review`: вставить карточку или
выбрать пример, нажать «Проверить», для каждого поля принять, исправить или отклонить
предложение и скачать решения в JSONL. Страница вызывает тот же `/predict`, решения
хранятся только во вкладке браузера; формат выгрузки — в
[RESPONSES](RESPONSES.md#экран-проверки-оператора).

## 7. LLM — только по явному opt-in

По умолчанию LLM не вызывается: `llm_calls=0` в manifest. Чтобы включить
маршрут для пропусков правил, на VM задаются переменные (ключ и URL — только
в окружении, не в файлах и не в командной строке):

```bash
export GOODSAI_LLM_BASE_URL=<https URL шлюза организаторов, с /v1>
export GOODSAI_LLM_API_KEY=<ключ>
export GOODSAI_LLM_MODEL=<ID модели шлюза>
.venv/bin/python -m goodsai.cli predict --input outputs/my-run/cards.jsonl --output outputs/my-run/llm-predictions.jsonl --llm
```

Бюджет по умолчанию: 100 логических запросов на запуск, 300 физических
HTTP-попыток в сутки на общий журнал `outputs/llm-budget/ledger.json`, 120 с на
запрос карточки. Ключ и URL не печатаются и не попадают в manifest.

Без ключа запуск не падает: правила отрабатывают как обычно, к пропускам
добавляется `llm_missing_key`, а stderr сообщает одной строкой:

```text
goodsai: LLM fallback disabled during run: llm_missing_key; rule results are unchanged
```

Таймаут, 429, 5xx, превышение дедлайна или бюджета ведут себя так же: значения
правил не меняются, пропуск получает свою причину. Политика данных, лимиты,
причины отказов и живой synthetic trace — в [LLM](LLM.md).

## 8. Отчёты и выпуск

| Что | Команда | Где результат |
| --- | --- | --- |
| Свой batch | шаги 3–5 | `outputs/my-run/predictions.jsonl`, `.manifest.json` |
| Synthetic приёмка внешнего ввода (CLI + HTTP, без `examples/`) | `.venv/bin/python scripts/release/external_acceptance.py --seed 20261020 --output-dir outputs/external-first` | `outputs/external-first/report.md`, ожидается 83/83 |
| Чистый запуск в изолированном окружении | `python3.12 scripts/release/clean_run.py --output-dir outputs/clean-first [--input свой.jsonl]` | `outputs/clean-first/report.json` |
| Шесть артефактов выпуска (smoke без данных) | `build_release.py smoke` → `build_release.py verify` | см. [ARTIFACT_BUNDLE](ARTIFACT_BUNDLE.md) |
| Оценка по каталогу | [SILVER_EVALUATION](SILVER_EVALUATION.md) | `reports/metrics.md` (публичные агрегаты) |

Границы: штатный конфиг поддерживает две категории — смартфоны `761` и чайники
`482`; остальные получают `unsupported_category`. Обученный на train профиль
категорий — отдельный opt-in, см. [CATEGORY_REGISTRY](CATEGORY_REGISTRY.md);
его качество на реальном каталоге не измерено. Confidence — эвристический score,
не вероятность; `auto_accept` выключен. Независимая оценка качества — N/A.
