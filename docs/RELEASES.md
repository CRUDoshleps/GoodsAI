# Разработка в GitHub и релизы в Gitea

## Назначение репозиториев

| Remote | Сервис | Назначение |
| --- | --- | --- |
| `work` | GitHub | задачи, feature-ветки, PR и основной `main` |
| `release` | Gitea организаторов | автоматическое зеркало GitHub `main` и release tags |

Секреты не встраиваются в remote URL. HTTPS credential вводится интерактивно
или через разрешённый credential manager; предпочтительный GitHub transport — SSH.

## Начальная синхронизация 19 октября

GitHub и Gitea имели несвязанные истории. Актуальным техническим источником
выбран Gitea `main` `48b45dc`, потому что только там есть runtime, tests и свежий
`PROJECT_STATUS`. Прежний GitHub `main` сохранён в резервной ветке
`legacy/github-main-before-gitea-sync-2026-10-19`. После этого актуальная
история стала новым GitHub `main`. Старая `dev` сохранена без изменений.

## Обычная разработка

```bash
git fetch work --prune
git switch -c <type>/<task-id>-<slug> work/main
# claim в TASKS.md, отдельный commit и push
git push -u work HEAD
```

PR направляется в GitHub `main`. После review интегратор сливает его, ждёт
успешного mirror workflow и только затем ставит задачу в `DONE`.

## Автоматическое зеркало GitHub main → Gitea main

Workflow `.github/workflows/mirror-main-to-gitea.yml` запускается после каждого
push в GitHub `main` и при ручном `workflow_dispatch`. Он читает
`GITEA_USERNAME` и `GITEA_PASSWORD` из GitHub Secrets, получает Gitea `main`,
проверяет fast-forward и только после этого выполняет push.

Workflow никогда не делает force push. Если в Gitea появился отдельный commit,
job завершается ошибкой. Такой commit сначала нужно получить локально, проверить
и включить в GitHub `main`, после чего перезапустить workflow.

Смена или ротация Gitea credentials требует обновления GitHub Secrets. Значения
нельзя записывать в YAML, remote URL, Actions logs и repository variables.

## Состав release candidate

Release candidate — конкретный GitHub commit. Для него создаются:

- source SHA и clean-tree proof;
- test report с Python/OS и exit codes;
- demo report;
- predictions-файл или утверждённая ссылка на него;
- predictions manifest и SHA-256;
- metrics report с split/provenance;
- конфиг и versions без секретов;
- список известных ограничений;
- предыдущий Gitea SHA для rollback.

## Preflight

1. Все release-задачи имеют `DONE` или записанный waiver.
2. `git status` чистый, source commit существует в GitHub.
3. Tests и demo проходят в чистом окружении.
4. Batch run создаёт согласованную пару predictions/manifest.
5. Количество строк и hashes сверены.
6. Metrics принадлежат тому же commit/config/input.
7. LLM budget, timeouts и fallback проверены, если route включён.
8. Секреты, данные и реальные тексты отсутствуют в diff.
9. VM проверена по `RUNBOOK.md`.
10. Назначены release engineer и reviewer.

## Фиксация релиза

GitHub `main` уже публикуется в Gitea автоматически. Release engineer сначала
убеждается, что оба `main` указывают на один commit, затем выполняет preflight,
обновляет VM и фиксирует release manifest. Release tag можно отдельно отправить
в оба репозитория после успешного smoke.

Безопасная последовательность:

```text
fetch work + release
verify expected GitHub SHA
verify Gitea main equals GitHub main
run preflight again
tag release-YYYYMMDD-N
push the same tag to work and release
update VM to main SHA
run smoke and save release report
```

Точные tag/deploy команды выполняет release engineer после проверки удалённого
состояния. Force push и переписывание Gitea `main` запрещены.

## Release manifest

Минимальные поля:

```json
{
  "release_id": "release-YYYYMMDD-N",
  "work_source_sha": "<github-sha>",
  "gitea_merge_sha": "<gitea-sha>",
  "previous_gitea_sha": "<rollback-sha>",
  "config_sha256": "<sha256>",
  "input_sha256": "<sha256>",
  "predictions_sha256": "<sha256>",
  "metrics_sha256": "<sha256>",
  "tests": {"passed": 0, "failed": 0},
  "vm_smoke": "passed",
  "released_at": "<ISO-8601>"
}
```

Manifest не содержит токены, пароли, URL с credentials и реальные строки
карточек.

## Hotfix

Hotfix допускается только при поломке проверяемого сервиса:

1. задача `REL/BUG` в `TASKS.md`;
2. ветка от текущего GitHub `main`;
3. минимальная правка и regression test;
4. PR в GitHub `main`;
5. успешный автоматический mirror в Gitea;
6. новый release manifest.

VM никогда не становится единственным местом правки.

## Rollback

Для быстрого восстановления VM временно запускается на предыдущем известном
release SHA. В GitHub `main` создаётся обычный revert commit; workflow
fast-forward переносит его в Gitea. После этого VM обновляется на новый main и
проверяет health/predict. Release tag не перемещается, force push не применяется.
