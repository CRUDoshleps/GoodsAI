# Запуск и диагностика

Команды не содержат адресов, токенов и паролей. Доступы берутся только со
страницы команды и вводятся локально.

Первый запуск на своих карточках с ожидаемыми выводами — [QUICKSTART](QUICKSTART.md);
расшифровка ответов, reason codes и ошибок API — [RESPONSES](RESPONSES.md).

## Чистая установка

```bash
git status --short --branch
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m pip check
```

Требуется Python >=3.12 и полный Git clone, включая `5f77d81` и `5adab92`
(их используют comparison tests/experiments). Не устанавливать поверх
существующей `.venv`: сначала `.venv/bin/python --version`. Для shallow clone
получить полную историю (`git fetch --unshallow <имя-remote>`), только если
`git rev-parse --is-shallow-repository` вернул `true`. ZIP без `.git` позволяет
запустить demo, но не воспроизвести историческое A/B/C.

На VM системный `python3` ранее был 3.10. Если Python 3.12 установлен через uv,
новое окружение создаётся так (только когда `.venv` ещё нет):

```bash
"$HOME/.local/bin/uv" python find 3.12
goodsai_python="$("$HOME/.local/bin/uv" python find 3.12)" && "$goodsai_python" -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip install -e '.[serve,test]'
```

Это альтернатива `python3.12 -m venv`, а не обязательная переустановка.
Для Windows команды установки приведены в [README](../README.md#быстрый-запуск);
далее заменить `.venv/bin/python` на `.\.venv\Scripts\python.exe`.

## Быстрая проверка

```bash
.venv/bin/python -m goodsai.demo --output-dir outputs/demo-next
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Demo требует **новый** каталог, создаёт input/predictions/manifest/summary.
Ожидается 6/6, rows=6, llm_calls=0. Это synthetic smoke; метрики каталога N/A.
В manifest проверить `git_commit`, `git_dirty`, code/config/input/output SHA.
Dirty tree допустим для локальной проверки правок, но не является clean release.

Сохранить Git SHA, Python/OS, команды, exit codes и число tests. Не копировать
в отчёт переменные окружения и тексты реальных карточек.

## HTTP service

Разовый запуск:

```bash
.venv/bin/python -m goodsai.api --host 0.0.0.0 --port 8000
```

Локальная проверка:

```bash
curl --fail-with-body http://127.0.0.1:8000/health
```

API docs доступны на `/docs`. В operational logs не должны попадать body,
authorization headers, ключи и текст карточек.

## Systemd user service

Unit находится в `deploy/systemd/goodsai.service`. Перед установкой проверить
его `WorkingDirectory`, Python path и пользователя. После изменения release:

```bash
systemctl --user daemon-reload
systemctl --user restart goodsai.service
systemctl --user status goodsai.service --no-pager
journalctl --user -u goodsai.service -n 100 --no-pager
```

В командный отчёт переносится только безопасный фрагмент статуса. Полный journal
остаётся на VM.

## Batch

Команды ниже — шаблон: `INPUT.jsonl` должен содержать ровно карточки,
размеченные в `GOLD.jsonl`; файлы должны существовать локально. Для точного
M2 A/B/C использовать [RESULTS](RESULTS.md#воспроизведение-m2): runner сам
создаёт совпадающий text-only input. Synthetic demo не сравнивать с real gold.

```bash
.venv/bin/python -m goodsai.cli predict --input INPUT.jsonl --output outputs/batch-next/predictions.jsonl
.venv/bin/python -m goodsai.cli evaluate \
  --predictions outputs/batch-next/predictions.jsonl \
  --gold GOLD.jsonl \
  --output outputs/batch-next/metrics.json
```

После запуска сверить количество строк, `input_sha256`, `output_sha256`,
`git_commit`, `git_dirty=false`, status counts и `quality_status` в manifest.
Evaluator оценивает reviewed gold-пары; лишние prediction SKU не гарантированно
сделают evaluate ошибкой. Наборы SKU и категории нужно сверить отдельно либо
использовать comparative runner. `manual_reference` описывает формат, а не
независимость разметки. Без `--gold` возвращается unavailable/N/A, не нулевой F1.

## Обновление существующего сервиса VM

Выполняется release engineer после проверки GitHub/Gitea SHA и разрешения
релиза. Здесь приведена инструкция, в DOCS-001 VM не изменялась.
В существующем clone VM `origin` может оставаться Gitea — переименовывать его
для запуска сервиса не требуется. Перед командами проверить `git remote -v`.

```bash
cd ~/project &&
test "$(git branch --show-current)" = main &&
test -z "$(git status --porcelain)" &&
git fetch origin &&
git merge --ff-only origin/main &&
git log -1 --oneline &&
.venv/bin/python --version &&
.venv/bin/python -m pip install -e '.[serve,test]' &&
.venv/bin/python -m pip check &&
.venv/bin/python -m unittest discover -s tests -v &&
systemctl --user restart goodsai.service &&
systemctl --user is-active goodsai.service &&
curl --fail-with-body --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
```

Если git checks не прошли, не обходить их reset/clean. Сразу после restart
первый curl может получить connection refused, затем повторить запрос;
успех — только финальный JSON health с exit code 0. `active` сам по себе
не доказывает готовность API.

## Атомарные outputs

Predictions и manifest публикуются парой. Если процесс прерван:

1. убедиться, что writer больше не работает;
2. не удалять lock во время активного процесса;
3. проверить transaction marker и временный каталог;
4. сохранить повреждённые файлы отдельно для диагностики;
5. повторить run в новый output path;
6. сравнить hashes, прежде чем заменять release artifact.

Два процесса не должны писать в один output path.

## Типовые сбои

| Симптом | Проверка | Действие |
| --- | --- | --- |
| service не стартует | Python path, install, journal | исправить окружение, не скрывать restart loop |
| порт 8000 занят | владелец процесса | остановить старую версию или согласовать порт |
| health старой версии | commit в manifest/checkout | обновить только по release plan |
| 422 | schema version и неизвестные поля | исправить клиентский JSON |
| unsupported category | `category_id` | добавить категорию отдельной задачей |
| много abstain | reason counts и data slice | error analysis, не снижать порог вслепую |
| LLM недоступна | timeout/budget/provider health | сохранить rules path и abstain |
| output lock | активный writer/старый marker | следовать recovery, не делать `rm -rf` |

## Проверка VM перед релизом

- checkout указывает на ожидаемый release SHA;
- working tree чистый;
- данные и секреты вне Git;
- свободны диск и RAM;
- tests и demo прошли на этом SHA;
- service active и health отвечает;
- один sample predict прошёл без реального текста в отчёте;
- rollback SHA известен;
- release manifest сохранён.

## Запрещённые действия

- `git reset --hard`/`git clean` на VM без инвентаризации локальных данных;
- вывод `.env` и `/opt/.../ai.env`;
- ключи в curl history, notebook output или URL remote;
- ручная правка runtime на VM без обратного commit в GitHub;
- публикация метрик с другого SHA;
- замена Gitea `main` непроверенной рабочей веткой.
