# OPS-001: диагностика, временные файлы и research pickle

[DONE — feature candidate] Ветка `ops/ops-001-safe-io`, владелец `timur0o31`,
claim `7d38377`. Изменения не являются обновлением VM или принятым release.
Проверки: [операционные тесты](../tests/test_operations.py),
[граница research reader](../scripts/research/test_catalog_boundary.py).

## Ошибки и логи

[DONE — feature candidate] CLI/demo и research entrypoints не печатают исходный
текст исключения или traceback в обработанных ошибках. Они возвращают ненулевой
exit code и фиксированное сообщение. CLI сохраняет безопасный номер строки для
четырёх известных JSONL-диагностик. Ключи и пути из произвольного исключения
не выводятся. Неожиданная внутренняя ошибка даёт exit code 1; ошибка входа/I/O —
2; отмена Ctrl+C — 130. Внутренняя ошибка не становится успешным пустым ответом.
Реализация: [diagnostics.py](../src/goodsai/diagnostics.py),
[cli.py](../src/goodsai/cli.py), [demo.py](../src/goodsai/demo.py).

| Код | Действие оператора |
| --- | --- |
| `file_missing` | Проверить локальные пути и наличие утверждённых входов |
| `permission_denied` | Проверить владельца каталога и права доступа |
| `output_exists` | Выбрать новый каталог, не затирать старый результат |
| `output_busy` | Проверить активного writer и дождаться завершения |
| `invalid_input` / `invalid_metadata` | Проверить schema/config и формат локального файла |
| `io_error` / `internal_error` | Сохранить приватные артефакты; воспроизвести на синтетике |
| `interrupted` | Убедиться, что процесс завершён; проверить журнал и согласованность пары |

[DONE — feature candidate] HTTP validation отвечает фиксированным сообщением
без значений входа. Неожиданные ошибки обработчика до отправки ответа дают 500
и фиксированную запись application logger без exception payload. Access log
остаётся выключенным в штатной команде запуска. [HTTP boundary](../src/goodsai/api.py).
Это не аудит всех версий ASGI-сервера, proxy, system journal или сторонних handlers.
Не включать логирование request body, authorization, environment или `exc_info`
для запросов с реальными карточками. Response predictions содержат evidence
для пользователя; они не являются operational log.

## Выходные файлы и отмена

[DONE — feature candidate] На POSIX новые конечные файлы atomic writer и locks
имеют mode `0600`, новый непосредственный output-каталог — `0700` даже при
permissive umask. Transaction directories создаёт `mkdtemp` в output-каталоге.
Staging остаётся на той же файловой системе, что и результат. Существующие
пользовательские каталоги/старые outputs автоматически не chmod-ятся; их права
проверяет владелец. Private mode не заменяет защиту учётной записи/диска.
[Storage implementation](../src/goodsai/storage.py).

Locks не удаляются при освобождении: удаление inode могло бы разрешить двух
writers. Симлинк, hardlink, не regular file или чужой POSIX-владелец lock дают
отказ. Симлинк журнала восстановления также отклоняется. Каталог outputs должен
контролироваться владельцем сервиса: это не защита от другого процесса того же
пользователя, который намеренно меняет каталог во время операций.

[DONE — feature candidate] Recovery в `_publish` сохраняет `except BaseException`
с последующим `raise`: это нужно для KeyboardInterrupt/SystemExit после замены
первого файла. Тесты проверяют восстановление прежней пары и повторный выброс
отмены. Прежние crash/concurrency tests остаются regression gate. Если recovery
не может завершиться, журнал и backups сохраняются для диагностики; их нельзя
удалять ради зелёного запуска.

[PLAN / ENV-001, QA-004] Поддерживаемое хранилище — локальный диск с рабочими
OS locks и atomic replace. NFS/SMB/FUSE и распределённые writers не поддержаны
этой проверкой; автоматического надёжного определения всех network mounts нет.
Перед VM release оператор подтверждает тип mount. Windows ACLs и Windows lock
behavior в OPS-001 не проверялись; POSIX modes не являются гарантией Windows ACL.

## Изолированная подготовка pickle

[DONE — feature candidate] Production package/HTTP не импортирует pickle или
research reader; это проверяет AST regression test. `inspect_pickle.py`
сканирует инструкции без исполнения, отклоняет trailing bytes, не перезаписывает
источник или прежний отчёт. Opcode report публикуется atomic writer с private mode.

[DONE — feature candidate] `profile_catalog.py` требует `--trusted-pickle`,
проверяет metadata report и digest. Он хеширует, декодирует и повторно проверяет
один открытый descriptor; замена пути или изменение файла отменяют публикацию.
Allowlist ограничивает непосредственно dispatch декодера, включая запрет
EXT/REDUCE; один лишь изменённый opcode report не разрешает запрещённую инструкцию.
Projection/profile сначала создаются в private staging. Ошибка decode/hash
удаляет staging без публикации projection. Прежние результаты не перезаписываются.

После проверок два готовых файла публикуются отдельными atomic replace; это не
двухфайловая транзакция research outputs. Сбой во время публикации может оставить
неполный комплект. Не использовать его как готовый EDA; сохранить для диагностики
и повторить в новом каталоге. Парная транзакция predictions/manifest не менялась.

SHA фиксирует соответствие локальной копии, не удостоверяет отправителя. Reader
использует private CPython API, не ограничивает все виды CPU/RAM exhaustion и
не является sandbox для недоверенного файла. Использовать только утверждённый
неизменяемый источник в отдельном процессе/окружении с лимитами ресурсов.
Не загружать неизвестный pickle, не применять fallback на `pickle.load`.

Параметры исследовательского запуска (только если готовая проекция отсутствует):

```bash
.venv/bin/python scripts/research/inspect_pickle.py SOURCE.pkl outputs/eda-next/scan.json
.venv/bin/python scripts/research/profile_catalog.py --trusted-pickle \
  --input SOURCE.pkl --scan outputs/eda-next/scan.json --output-dir outputs/eda-next
```

## Проверка candidate

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
.venv/bin/python -m pip check
.venv/bin/python -m goodsai.demo --output-dir outputs/ops-smoke-next
```

[DONE — feature candidate] Новые tests используют только вымышленные карточки
и маленькие primitive pickle. Реальные исходники, закрытый test, EDA caches,
секреты, VM и внешние model calls не используются. Финальные команды и результаты
сохраняются в PR/статусе задачи. После restart сервиса отдельно проверить health
и release identity; наличие кода в ветке не подтверждает deployment.
