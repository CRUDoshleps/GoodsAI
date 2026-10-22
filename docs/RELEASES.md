# Разработка в GitHub и сдача в Gitea

## Назначение репозиториев

| Remote | Сервис | Назначение |
| --- | --- | --- |
| `work` | GitHub | разработка, задачи, feature-ветки, PR, исследования и основной `main` |
| `release` | Gitea организаторов | код, проверки, инструкции и материалы сдачи |

С 20 октября Gitea публикует отфильтрованный состав сдачи, а не полное зеркало.
GitHub SHA и Gitea SHA различаются. Связь между ними записывается в корневой
`submission-manifest.json` Gitea и в Actions artifact `gitea-publication`.
Секреты хранятся только в GitHub Secrets, не в remote URL и логах.

## Разработка

Ветка от свежего `work/main`, опубликованный claim в TASKS, реализация, PR,
review и merge. Интегратор ждёт успешного workflow публикации перед `DONE`.
Напрямую в `main` обоих репозиториев рабочие commits не отправляются.

## Состав сдачи

Workflow `.github/workflows/mirror-main-to-gitea.yml` вызывает
[`publish_gitea.py`](../scripts/release/publish_gitea.py) после push в GitHub
`main` или ручного `workflow_dispatch`.

- Исполняемый Python-код `src/`, `scripts/`, `tests/`, package fixtures,
  зависимости, production-конфиг и systemd unit сохраняются.
- Документы, JSON/PDF/PPTX и прочие материалы включаются только по явному
  списку `PUBLIC_FILES`. Новый Markdown-документ сам по себе не публикуется.
- Корневой README берётся из
  [`submission_readme.md`](../scripts/release/submission_readme.md).
- AGENTS, CONTRIBUTING, TASKS, RESEARCH, PROJECT_STATUS, внутренние планы,
  `docs/research/`, `docs/reviews/` и GitHub workflow/templates не включаются.
- `scripts/research/*.py` — исполняемые инструменты оценки, подготовки и
  сравнения, нужные тестам и воспроизведению. Они сохраняются вместе с HTML
  human-review формой; исследовательские Markdown-записки не включаются.
- Архивные слайды продуктового этапа (`docs/product-stage/presentation/`),
  их `SOURCE_MANIFEST.json` и индекс архива остаются в GitHub для истории,
  но исключены из сдачи. Исходное задание в `context/case/` сохраняется.
  Технический комплект `docs/delivery/2026-10-19/` сохраняется целиком:
  это зафиксированный snapshot с manifest, а не обновляемые финальные слайды.
- Ссылки технических документов на исключённые файлы ведут в GitHub на точный
  source SHA. Материалы не копируются ради сохранения ссылки.

Фильтр читает только Git objects выбранного source commit. Dirty/untracked
файлы и локальные данные не берутся. Source archive из `build_release.py`,
собранный в Gitea, использует только отслеживаемые там файлы.

Добавление документа в сдачу требует изменения `PUBLIC_FILES` и review.
Удаление файла из списка удалит его из текущего дерева Gitea при следующей
публикации. Runtime-код не редактируется при экспорте.

## История и защита от перезаписи

Первая публикация создаёт дочерний commit прежнего Gitea `main` с очищенным
деревом. Предыдущее зеркало остаётся в истории; старые файлы доступны через
старые commits. Это очистка текущей сдачи, не удаление истории.

Последующие commits имеют единственного родителя — предыдущий Gitea commit.
Новые GitHub commits не добавляются родителями, поэтому их внутренние файлы
не приезжают в Gitea через новую историю. Source SHA хранится как provenance.

Перед push проверяются origin marker, hashes файлов предыдущей публикации и
то, что новый GitHub source не старее предыдущего. Неизвестная история или
посторонняя правка Gitea останавливают job. Обычный push дополнительно защищает
от гонки после fetch. Force push и автоматическое затирание расхождений запрещены.
Повторная публикация того же source не создаёт нового commit.

## Проверка публикации

Actions summary и artifact содержат `source_sha`, `gitea_sha`,
`previous_gitea_sha`, `tree_sha` и число файлов. В Gitea:

```bash
git fetch release main
git show release/main:submission-manifest.json
```

1. `source_sha` совпадает с ожидаемым GitHub candidate.
2. Gitea `main` совпадает с `gitea_sha` успешного workflow.
3. SHA-256 каждого текущего файла совпадает с `files_sha256` manifest
   (сам manifest не включает свой hash).
4. На чистом Gitea checkout выполняются tests, внешний JSONL, API и smoke/verify.
5. VM обновляется на **Gitea SHA** и проверяется отдельно по RUNBOOK.

Публикация кода не означает deployment, независимую оценку качества или
официальную готовность полного комплекта. Данные и predictions не публикуются
автоматически. [ARTIFACT_BUNDLE](ARTIFACT_BUNDLE.md) описывает шесть артефактов.

## Release manifest и tags

Release manifest хранит разные `work_source_sha`, `gitea_merge_sha`,
`previous_gitea_sha`, hashes конфигурации/input/predictions/metrics, test report,
результат VM smoke и время. Predictions создаются на том checkout, чей SHA
записан в их manifest; нельзя заменять его SHA другого репозитория.

Source tag в GitHub и submission tag в Gitea указывают на соответствующие
commits. Не отправляйте GitHub tag в Gitea: он снова перенесёт development
историю. Release engineer сверяет оба SHA и provenance перед тегированием.

## Hotfix, divergence и rollback

Hotfix: Issue/claim → минимальный PR в GitHub → tests/review/merge → успешная
публикация → VM smoke. VM не становится единственным местом правки.

Если Gitea изменён вручную, release engineer сначала получает и проверяет diff,
переносит полезные изменения в GitHub через PR и отдельно восстанавливает
согласованную цепочку публикаций. Workflow не обходит эту защиту автоматически.

Rollback VM запускает предыдущий известный Gitea SHA. Для постоянного rollback
создаётся обычный revert в GitHub; новый source публикуется следующим Gitea
commit. Release tags не перемещаются, история не переписывается.

## Историческая синхронизация

19 октября актуальная история Gitea `48b45dc` стала GitHub `main`; прежний GitHub
сохранён в `legacy/github-main-before-gitea-sync-2026-10-19`. До REL-005 workflow
публиковал один и тот же commit в оба `main`. Упоминания равенства SHA в старых
протоколах относятся к тому периоду.
