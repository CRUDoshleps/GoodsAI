# Временный HTTP-сервис GoodsAI

Основание: переданное пользователем 17 октября сообщение администраторов —
на выходные поднять решение на порту **8000** и опубликовать код в **main**
одного выданного репозитория. Ручки/транзакции обещаны в понедельник вечером.
Ниже внутренняя реализация транспорта; официальный API ещё не получен.

## Установка и запуск

Используется существующий Python 3.12+, без БД и изменения правил baseline.
В актуальной рабочей копии на ВМ:

```bash
cd ~/project
git status --short --branch
git fetch origin
git merge --ff-only origin/main
.venv/bin/python -m pip install -e '.[serve,test]'
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s scripts/research -p 'test_*.py' -v
.venv/bin/python -m goodsai.api --host 0.0.0.0 --port 8000
```

Перед merge проверить свою ветку main и отсутствие незакоммиченных изменений;
не перезаписывать локальные файлы при конфликте. Существующую `.venv` не удалять.
`serve` включает FastAPI/Uvicorn, `test` — HTTPX для HTTP-тестов; без extras
обычный CLI работает, HTTP-тесты явно пропускаются. Для сервиса пропуски этих
тестов не считаются проверкой. Прямые зависимости зафиксированы в pyproject;
транзитивные разрешаются pip при установке, полного lock-файла пока нет.

Запуск в foreground годится для smoke, но завершается вместе с сессией.
Способ постоянного запуска выбирается по диагностике ниже. Не запускать второй
процесс на занятом порту и не завершать чужие процессы.

## Проверка и управление процессом

До выбора менеджера выполнить read-only команды в SSH:

```bash
ps -p 1 -o comm=
systemctl --user is-system-running
loginctl show-user "$(id -u)" -p Linger
ss -ltn
```

Пользователь передал результат: PID 1 — systemd, user manager — running,
Linger=no, TCP 8000 свободен. Поэтому выбран пользовательский systemd unit
[deploy/systemd/goodsai.service](../../deploy/systemd/goodsai.service).
Он запускает существующую `.venv` из `~/project`, перезапускает процесс при
сбое и включается в default.target. Изменение пути checkout требует правки unit.

Сначала обновить чистую ветку main, установить `.[serve,test]` и выполнить
обе тестовые команды из раздела выше. Foreground-команду после тестов для
этого способа запускать не нужно. Затем в SSH:

```bash
cd ~/project &&
loginctl enable-linger "$(id -un)" &&
test "$(loginctl show-user "$(id -u)" -p Linger --value)" = yes &&
mkdir -p "$HOME/.config/systemd/user" &&
test ! -e "$HOME/.config/systemd/user/goodsai.service" &&
test ! -L "$HOME/.config/systemd/user/goodsai.service" &&
install -m 0644 deploy/systemd/goodsai.service "$HOME/.config/systemd/user/goodsai.service" &&
systemctl --user daemon-reload &&
systemctl --user enable --now goodsai.service &&
systemctl --user status goodsai.service --no-pager --full &&
curl --fail-with-body --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
```

`enable-linger` оставляет менеджер этого пользователя работающим после logout
и запускает его при загрузке ВМ. Поведение описано в
[официальной документации loginctl](https://github.com/systemd/systemd/blob/main/man/loginctl.xml).
Если команда требует недоступных прав/возвращает Access denied, остановиться
и передать вывод: нужен администратор для включения linger; sudo автоматически
не добавлять. Одна опция `enable` без linger не доказывает работу после выхода.
Если unit-файл уже существует, цепочка тоже остановится: сначала сравнить
его с версией из Git, не перезаписывать неизвестную конфигурацию.

Нужны `active (running)`, `enabled` и `Linger=yes`; health проверяется отдельно,
поскольку Type=simple может стать active до готовности HTTP. При ошибке:

```bash
systemctl --user status goodsai.service --no-pager --full
journalctl --user -u goodsai.service -n 50 --no-pager
```

Управление только GoodsAI: `systemctl --user restart goodsai.service` после
обновления кода/окружения; `systemctl --user disable --now goodsai.service`
останавливает процесс и отключает автозапуск. Linger не отключать автоматически:
он относится ко всем службам пользователя. Установка unit на ВМ подтверждена
пользователем: enabled/active и health.
Историческую последовательность первой установки выше повторять не нужно;
для установленной службы — [обновление main и restart](update_vm.md).

После запуска проверить с ВМ:

```bash
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  --data '{"schema_version":"0.1","sku_id":"demo","category_id":"482","title":"Чайник Bosch Example 1,7 л 2200 Вт"}'
ss -ltn
```

Ожидаются HTTP 200, status=ok для health; status=processed для predict,
capacity_l=1.7 L, power_w=2200 W, кандидаты review и model=null.
После настройки менеджера выйти из SSH, войти снова и повторить health.
Ответ с localhost не подтверждает доступность со стороны проверяющей платформы:
для этого нужен проверенный путь доступа организаторов. Firewall, proxy,
публичную публикацию и системный Python этот этап не меняет.

## Временный контракт

| Метод/путь | Результат |
| --- | --- |
| GET / | Название, provisional-статус, ссылки на health/predict/docs |
| GET /health | Успешная загрузка конфигурации/экстрактора, категории |
| POST /predict | Один объект Product v0.1 → один prediction v0.1 |
| GET /docs, /openapi.json | Описание временных маршрутов и формы входа |

Вход и семантика из [контракта E1](../research/architecture_and_contract.md).
Content-Type application/json, UTF-8, максимум **128 KiB** включая весь JSON.
seller_attributes только пустой список; готовые target/vendor/model/gold
отклоняются. sku_id используется только как идентификатор, не как подсказка.
Новые категории возвращают HTTP 200 с status=unsupported_category и attributes=[].
Это явный результат ядра, а не извлечение по всем категориям.

Ошибки: 400 — некорректный JSON; 413 — превышен размер; 415 — неверный
Content-Type; 422 — нарушен Product-контракт; 500 — сбой экстрактора.
Форма: `{"error":{"code":"...","message":"..."}}`. Текст карточки и детали
внутреннего исключения в ошибку не включаются. Неверный запрос не выдаётся
за успешное пустое предсказание. Данные и результаты не сохраняются сервером.
Access log штатной команды выключен; не включать body logging.

Сервис не добавляет авторизацию, TLS, batch, транзакции или вызовы LLM:
требования к ним неизвестны. Доступ определяется сетью ВМ; bind 0.0.0.0
должен использоваться в предусмотренной организаторами среде.
run_id HTTP фиксирован как http-rules-v0 и не является manifest CLI/метрик.
Добавление api.py меняет вычисляемый CLI code hash; старые benchmark-файлы
не пересчитываются и не перезаписываются этим релизом.

При получении официальной спецификации проверить методы, схемы, auth,
транзакции, ошибки и ограничения; менять транспорт отдельно от качества правил.
