# Запуск и диагностика

Команды не содержат адресов, токенов и паролей. Доступы берутся только со
страницы команды и вводятся локально.

## Чистая установка

```bash
git status --short --branch
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[serve,test]'
python -m pip check
```

## Быстрая проверка

```bash
python -m goodsai.demo --output-dir outputs/demo
python -m unittest discover -s tests -v
python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Сохранить Git SHA, Python/OS, команды, exit codes и число tests. Не копировать
в отчёт переменные окружения и тексты реальных карточек.

## HTTP service

Разовый запуск:

```bash
goodsai-serve --host 0.0.0.0 --port 8000
```

Локальная проверка:

```bash
curl --fail http://127.0.0.1:8000/health
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

```bash
goodsai predict --input INPUT.jsonl --output outputs/predictions.jsonl
goodsai evaluate \
  --predictions outputs/predictions.jsonl \
  --gold GOLD.jsonl \
  --output outputs/metrics.json
```

После запуска сверить количество строк, `input_sha256`, `output_sha256`,
`git_commit`, `git_dirty=false`, status counts и `quality_status` в manifest.

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
