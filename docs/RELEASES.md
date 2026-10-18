# Разработка в GitHub и релизы в Gitea

## Назначение репозиториев

| Remote | Сервис | Назначение |
| --- | --- | --- |
| `work` | GitHub | задачи, feature-ветки, review и интеграция |
| `release` | Gitea организаторов | проверяемый `main` и release tags |

Секреты не встраиваются в remote URL. HTTPS credential вводится интерактивно
или через разрешённый credential manager; предпочтительный GitHub transport — SSH.

## Начальная синхронизация 19 октября

GitHub и Gitea имели несвязанные истории. Актуальным техническим источником
выбран Gitea `main` `48b45dc`, потому что только там есть runtime, tests и свежий
`PROJECT_STATUS`. Эта история опубликована в новой GitHub-ветке
`docs/gov-001-team-workflow`; существующие GitHub `main` и `dev` не
переписывались.

После review этой ветки интегратор создаёт в GitHub постоянную базу
`integration/current` на проверенном commit. Новые задачи до этого момента
ответвляются от commit, указанного в `TASKS.md`. Замена старой `dev` требует
отдельного согласования, потому что это изменение истории.

## Обычная разработка

```bash
git fetch work --prune
git switch -c <type>/<task-id>-<slug> work/integration/current
# claim в TASKS.md, отдельный commit и push
git push -u work HEAD
```

PR направляется в `integration/current`. После review интегратор сливает его и
ставит задачу в `DONE`. Gitea на этом этапе не меняется.

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

## Публикация в Gitea

Публикация выполняется из отдельной release-ветки, созданной от проверенного
GitHub commit. Release engineer сначала обновляет удалённое состояние и
убеждается, что Gitea `main` не изменился после начала подготовки.

Безопасная последовательность:

```text
fetch work + release
verify expected GitHub SHA
verify expected Gitea main SHA
create rel/<date>-<n> from source SHA
run preflight again
push release branch to Gitea
open Gitea PR into main
review diff and manifests
merge without force
tag release-YYYYMMDD-N
update VM to merged SHA
run smoke and save release report
```

Точные push/merge команды выполняет release engineer после проверки удалённого
состояния. Документ специально не предлагает force push или переписывание main.

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
2. ветка от текущего Gitea `main`;
3. минимальная правка и regression test;
4. PR в Gitea;
5. немедленный backport того же commit/diff в GitHub;
6. новый release manifest.

VM никогда не становится единственным местом правки.

## Rollback

Rollback возвращает предыдущий известный Gitea release SHA, перезапускает
service и проверяет health/predict. Причина и время фиксируются в release report.
После восстановления создаётся отдельная задача на исправление; повреждённый
release tag не перемещается.
