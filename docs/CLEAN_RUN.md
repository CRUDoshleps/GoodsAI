# Воспроизводимый чистый запуск

ENV-002 / [#41](https://github.com/CRUDoshleps/GoodsAI/issues/41). Из полного,
чистого Git checkout с установленным **CPython 3.12**:

```bash
python3.12 scripts/release/clean_run.py --output-dir outputs/clean-first
```

Windows PowerShell: `py -3.12 scripts/release/clean_run.py --output-dir outputs/clean-first`.
Подготовка venv и установка зависимостей входят в команду. Нужны Git, сеть до
индекса пакетов и минимум 512 MiB свободного диска; для большого внешнего batch
нужен дополнительный запас. Поддерживаемая матрица: CPython 3.12, macOS arm64,
Linux x86_64 и Windows AMD64. Linux/Windows проверяются workflow `Clean run`,
локальный протокол ниже. Другие Python/architecture отклоняются до установки.

Внешний JSONL обрабатывается тем же predictor целиком:

```bash
python3.12 scripts/release/clean_run.py --input /path/to/products.jsonl --output-dir outputs/clean-external
```

По умолчанию используется публичный synthetic JSONL. Независимо от входа runner
также выполняет отдельное demo с 6/6 проверками, `pip check`, API contract tests,
оценку без gold, проверку каждой строки/evidence/manifest внешнего batch,
сборку и verification synthetic artifact bundle. Нет provider calls, ключей,
скачивания датасетов, загрузки pickle или обращения к gold. Доступность модели
проверяется как `provider=disabled_rules_only`, а `llm_calls` обязано равняться 0.
API проверяется внутри процесса через ASGI; listening socket и VM deployment
этой проверкой не подтверждаются.

`report.json` содержит source SHA, input/config/lock/runner hashes, Python/OS,
точные установленные версии, имя и exit code каждого этапа, время и hashes
выходов. `report.md` — краткая таблица этапов. Runtime manifest сохраняет
canonical config hash. Predictions детерминированы для одинаковых bytes и
версий; timing, RSS, environment и manifest bytes могут отличаться между OS.
Без reviewed reference P/R/F1 равны `null`/`N/A`; bundle имеет статус
`synthetic_smoke`, а не готовой сдачи шести артефактов.

Внешний input и predictions остаются в ignored `outputs/`. Они могут быть
закрытыми. В stdout/отчёт этапов не копируется содержимое subprocess stdout/
stderr; отчёт содержит только allowlisted агрегаты. CI публикует только два
отчёта собственного synthetic run, не каталог batch. Reports с hashes локальных
данных всё равно требуют решения владельца перед публикацией.

Повтор той же команды проверяет hashes сохранённых артефактов и возвращает тот
же успешный report без переустановки и повторного prediction. Изменённые
input/source/lock/Python требуют нового output-dir. Изменённые успешные
артефакты отклоняются. При сбое сохраняются `status=failed`, имя этапа, exit code
(при timeout — null) и recovery. После исправления причины повтор команды
использует venv, но создаёт новый `attempt-NNNN`, сохраняя прошлые файлы.
Каждый subprocess ограничен 180 секундами; установка lock — 600 секундами.

Preflight сообщает причину: неверный Python/platform, dirty или shallow Git,
небезопасный путь, отсутствующий input или недостаток места. Сбой preflight
не создаёт ложного runtime report. `.runner-lock` исключает второй процесс.
После process kill lock не ломается автоматически: убедиться, что записанный
PID не работает, сохранить старый каталог и выбрать новый output-dir.
Это локальный runner, NFS/SMB locking не заявляется.

## Lock и аудит зависимостей

`requirements/clean-run.in` фиксирует direct runtime/test/build pins;
`clean-run.lock` — 23 distributions и SHA-256 разрешённых wheel-файлов.
Установка использует `--require-hashes --only-binary=:all:`; проект ставится
из проверенного checkout с `--no-deps --no-build-isolation`. Build tooling
также зафиксирован. Colorama включена явно для Windows marker у Click.
Lock не является утверждением безопасности всех будущих релизов.

Прямые зависимости проверены по version-specific PyPI JSON 19.10.2026.
Для перечисленных версий `vulnerabilities=[]` в PyPI; это снимок advisory feed,
не гарантия отсутствия неизвестных уязвимостей. Все 23 записи проверяются при
обновлении lock; несовместимости выявляют `pip check` и regression suite.

| Пакет | Pin | Дата wheel | Причина и план |
| --- | --- | --- | --- |
| [pyarrow](https://pypi.org/pypi/pyarrow/26.0.0/json) | 26.0.0 | 2026-10-09 | Совместимость Parquet/prepare; обновлять отдельно с data tests |
| [fastapi](https://pypi.org/pypi/fastapi/0.143.3/json) | 0.143.3 | 2026-10-16 | Текущий API contract; обновлять с API negative tests |
| [uvicorn](https://pypi.org/pypi/uvicorn/0.54.0/json) | 0.54.0 | 2026-09-25 | Текущий server; обновлять с listening smoke на VM |
| [httpx](https://pypi.org/pypi/httpx/0.28.1/json) | 0.28.1 | 2024-12-06 | Старый pin сохранён для ASGITransport; API tests проходят, блокирующих advisories в снимке PyPI нет; пересматривать перед релизом |
| [setuptools](https://pypi.org/pypi/setuptools/84.0.0/json) | 84.0.0 | 2026-08-08 | Editable build без плавающего build isolation |
| [wheel](https://pypi.org/pypi/wheel/0.48.0/json) | 0.48.0 | 2026-08-11 | Локальная сборка проекта |
| [pip](https://pypi.org/pypi/pip/26.2.1/json) | 26.2.1 | 2026-08-04 | Воспроизводимый installer после venv bootstrap |
| [colorama](https://pypi.org/pypi/colorama/0.4.6/json) | 0.4.6 | 2022-10-25 | Windows Click dependency; старый совместимый pin без PyPI advisories в снимке; пересматривать с Click |

Обновление выполняется отдельным PR на CPython 3.12:

```bash
python -m pip install pip-tools==7.6.2
pip-compile --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host --output-file requirements/clean-run.lock requirements/clean-run.in
```

При первоначальном создании pins разрешены pip-tools, hashes взяты из
version-specific PyPI JSON для всех non-yanked wheels (без загрузки всех wheels).
При regeneration pip-tools может добавить hashes sdists; runner всё равно
принимает только wheels. Проверить diff, advisory feeds, `pip check`, suite и
clean-run на матрице OS до принятия обновления. Основание выбора hash-checking:
[pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/).

## Протокол проверки

Фактический локальный clean-clone прогон и CI результаты записываются в PR.
Тесты runner проверяют повреждённые artifacts/evidence, невалидные пути,
конкурирующий процесс, timeout, dirty source, свободное место и безопасный
failure report. Проверка на VM организаторов остаётся частью ENV-001; её
нельзя объявлять пройденной по результату на ноутбуке или hosted CI VM.
