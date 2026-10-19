# EDA: сохранённые результаты и состав development delivery

Сводка на 2026-10-19.
Использованы прежние EDA caches и Parquet footer; полный EDA и pickle loading не повторялись.

## Каталог

| Показатель | Значение |
| --- | ---: |
| Карточки / уникальные SKU | 546069 / 546069 |
| Наблюдаемые категории / продавцы | 3599 / 2048 |
| Различные vendor / model (исходные поля) | 6765 / 420491 |
| Пустой vendor / model / title | 11 / 5 / 0 |
| Параметров на SKU: min / max | 1 / 301 |
| Параметров: p50 / p90 / p99 | 27 / 71 / 169 |
| SKU с повторяющимися названиями параметров | 148871 |

Число карточек каталога — 546069, а 148871 относится к повторяющимся названиям параметров.
Эта ошибка была в сокращённом DATASET.md. Vendor/model/params не являются gold и не передаются extractor.

## Описания и join

| Показатель | Значение |
| --- | ---: |
| Строки / уникальные SKU таблицы описаний | 1177200 / 1177200 |
| Null / пустое описание | 0 / 0 |
| Описания с HTML | 580505 |
| Длина описания min / max, символов | 3 / 27525 |
| Каталог с сопоставленным SKU описания | 241355 |
| Совпавшие / различающиеся titles при join | 197253 / 44102 |

Число строк таблицы описаний не равно числу карточек каталога. HTML требует сохранения raw offsets;
title mismatch требует provenance, а повтор параметра не доказывает правильность значения.

## Подготовленный E1

| Категория | SKU | С description | Title-only | Title mismatch |
| --- | ---: | ---: | ---: | ---: |
| Смартфоны (761) | 7988 | 3056 | 4932 | 269 |
| Чайники (482) | 2336 | 1188 | 1148 | 74 |

## Новый прогноз

Из 10324 E1 SKU выбрано 2198 development SKU.
Исключено 8126: {"non_development_split": 4783, "protected_or_mixed_development_family": 3343}.
Политика: `development-only-unmixed-families-v1`. Закрытые и смешанные семейства не предсказываются.
Это ограниченный batch, не predictions по всему каталогу. Near-duplicate grouping — существующая
лексическая эвристика, не доказательство отсутствия всех семантических дублей.

## Происхождение

| Локальный источник | SHA-256 |
| --- | --- |
| input | `68875ae2ef66c3527915be0e2cca29639c4a1c792e359973ae8623a404b70fe3` |
| prepare_manifest | `1e4256f628f9dec82836655d7852b6ea74ce10e5cf68fa367c2d2f844c70eba4` |
| annotation_manifest | `945f1900787e56ce734ba8f3c5a92c8a94bcc6958a1fce0b798a1c69d990c77a` |
| splits | `ad7e8b96ed436c304788021740c65fc545e5a188e8f05fef647dd27092331de2` |
| families | `61f3d35b4d2b7dd46b313d62e1adb73b545f9e87e337cc2dff665817792f7de7` |
| selection_summary | `be0f7972e25b75208bb6576b2ce0b2c60789a6cdb2f5e4d01ba1e317f9287dea` |
| reference | `2fda7384f77c83d9d39690d6cbb0f6bd2d4a3f448340fb61b704635d8d7e0337` |
| catalog_profile | `a18cf37589f01ceb58fc972cd2c920effc75a6edbda11c1528a9c08ad27ac33a` |
| joins_profile | `c53d74b11d3e41105e26a8b09af24c6c04bb4f452e5baffb95230b941cdee0c1` |
| parquet_profile | `e00101491686fd92b2e03bba91a60da727360c033e7acb51035b1680e9222e42` |
| opcode_scan | `8485f7c5fbd9e4797986ca5692b1ec1fca00eb0c88b1a68853e45a03cbe3de77` |
| projection | `2a80d0f0c55a37458faed6638bebc3af417c35e2d8de0265cbd5c023bdf6c250` |

Оригинальные raw-файлы не изменялись. Их происхождение унаследовано от прежней проверки;
raw pickle не перечитывался. Примеры карточек, SKU, seller IDs и target params в эту сводку не включены.
