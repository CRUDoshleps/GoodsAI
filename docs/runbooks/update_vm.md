# Повторное обновление GoodsAI на ВМ

Для уже установленного goodsai.service, checkout `~/project`, main и Python
3.12 в `.venv`. Первичная настройка — [HTTP runbook](http_service.md).
Опубликованный M2 добавил исследовательские инструменты, тесты и отчёты.
В этой версии policy fixes (rules-0.3.0-m2-policy): исправлены роль памяти,
brand/color по согласованной разметке. Перед этими командами убедиться,
что PR этой версии merged в main. LLM не добавлен. [Результаты](../research/m2_policy_fixes_results.md).

Сначала убедиться, что текущий PR уже merged в Gitea main. В SSH:

```bash
cd ~/project
git status --short --branch
```

Нужна ветка main без списка изменённых/неотслеживаемых файлов. Игнорируемые
data, outputs и .venv обновлению не мешают. При локальных изменениях сначала
разобраться с ними; команды ниже не выполняют reset/clean/stash.

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

Каждый следующий шаг выполняется только при успехе предыдущего. Ожидаются SHA
последнего main из Gitea, Python 3.12+, после публикации policy fixes — 82 tests без пропусков HTTP-тестов,
`active` и JSON health со status=ok. Единичный Connection refused при запуске
может исчезнуть на следующей повторной попытке; итоговая команда должна завершиться успешно.
Это инструкция, не утверждение, что Linux-проверки M2 уже выполнены.

Проверить синтетическую карточку:

```bash
curl --fail-with-body http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  --data '{"schema_version":"0.1","sku_id":"vm-smoke","category_id":"761","title":"Samsung Demo X82 8/256GB black"}'
```

Ожидаются status=processed, brand=Samsung, model=Demo X82, storage_gb=256,
ram_gb=8 и color=черный. Экран/батарея не написаны — abstain. Все найденные
значения review, уверенность heuristic. Корень демо остаётся служебным JSON;
интерактивная форма доступна по `/docs` в адресе демо команды.

Unit-файл M2 не менялся: повторно копировать его, включать linger или запускать
второй foreground-сервер на 8000 не требуется. Если restart/health не прошёл:

```bash
systemctl --user status goodsai.service --no-pager --full
journalctl --user -u goodsai.service -n 50 --no-pager
```

Для подтверждения обновления достаточно передать SHA из git log, итог тестов,
active/health и синтетический predict. Агент без такого вывода не объявляет
новую версию проверенной на ВМ. Реальные данные/gold/predictions в Gitea не
передаются; тесты и HTTP smoke используют вымышленные примеры.
