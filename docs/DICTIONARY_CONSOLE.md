# Консоль словарей: draft, impact, review, publish, rollback

Отдельный локальный интерфейс над **существующими** brands/colors в versioned
профиле GoodsAI. Это не второй train registry. Numeric/unit/catalog schema
изменения CONF-003 требуют отдельного schema review и через этот adapter
отклоняются. Глобальный alias требует явного scope всех затронутых категорий.

```bash
.venv/bin/python -m goodsai.dictionary_app --db outputs/dictionary.sqlite --development outputs/approved-development.jsonl
# Открыть http://127.0.0.1:8001/
```

Установите секретную переменную `GOODSAI_DICTIONARY_ACCOUNTS`: JSON mapping
случайных ключей (минимум 16 символов) на `{"name":"operator","role":"proposer"}`.
Допустимые роли: reader, proposer, reviewer, owner. Не помещайте ключи в Git,
URL или shared terminal transcript. По умолчанию accounts пусты: доступ к данным
и изменения запрещены. В форме ключ хранится только в памяти страницы, не в
localStorage. Авторизация — server-side Bearer; роль из запроса не принимается.
Сервис по умолчанию слушает loopback; это локальная консоль, не публичный IdP.

1. Proposer выбирает canonical value/поле, новое написание, provenance и полный
   scope. Draft не меняет опубликованный профиль. Unknown canonical сохраняется
   предложением и требует отдельного согласования vocabulary владельцем схемы.
2. Impact сравнивает старый/предложенный профиль на frozen development inputs.
   Допустимы только явно помеченные synthetic/development/validation_feedback;
   closed/test flags запрещены. Raw source не переписывается. Report содержит
   diff, изменённые пары, source/config hashes и conflicts/decisions.
3. При `--reference` рассчитываются before/after reviewed-development metrics
   и delta TP/FP/FN. Reference обязан быть manual/reviewed и совпадать с теми же
   development source/SKU. Без reference метрики null, не «0 ошибок».
4. Другой reviewer подтверждает текущий impact. Автор не review/publish своей
   правки. Schema owner публикует reviewed proposal явным действием.
5. Version conflict возвращает HTTP 409: чужая публикация не затирается.
   Versions immutable, содержат parent/config hash/author/reviewer/publisher/date.
6. Скачать опубликованный профиль и явно выбрать его в **новом** запуске:
   `python -m goodsai.cli --config outputs/approved-profile.json predict ...`.
   Старые predictions сохраняют исходные dictionary/config versions; действующие
   процессы не меняют configuration snapshot автоматически.
7. Owner выбирает прежний version ID для rollback. Создаётся новая immutable
   версия, история не удаляется и прошлый version ID не перемещается.

Aliases проверяются на existing ownership/collisions/canonical cycles, scope и
тип. По умолчанию разрешена literal/transliteration эквивалентность, а не вывод
о производителе по модели: `iPhone→Apple` отклоняется. Другая семантика требует
явного trusted semantic policy через backend adapter и schema owner; кнопка
предложения не является таким согласием. Model output как provenance запрещён.

SQLite с proposal/impact содержит рабочие тексты и сохраняется вне Git.
Недоверенные значения в HTML выводятся через textContent; server CSP разрешает
только точные hashes встроенных script/style. POST ограничен 16 KiB, endpoint
не принимает file paths, роли и raw cards. Данные для impact задаются сервером.

Проверены 20 вымышленных proposals, полный API lifecycle/RBAC, HTML escaping,
CAS гонка двух публикаций, stale rollback, source/test guards и immutable versions.
Скорость работы реального оператора против ручного JSON не измерялась; UX keep
#60 и подключение к PRODUCT-002/CONF-003 остаются отдельной приёмкой.
