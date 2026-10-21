# QA-002: общий приёмочный прогон

Протокол [#29](https://github.com/CRUDoshleps/GoodsAI/issues/29) объединяет
существующие regression suites, clean-run и scenario matrix. Отдельного runner
или второго evaluator нет. [Фактический отчёт 21.10.2026](../reports/qa002_20261021.md)
и [JSON](../reports/qa002_20261021.json) описывают конкретный source SHA,
окружение, команды, counts и hashes; это snapshot, не гарантия любой будущей версии.

## Повторить проверки

Нужен полный чистый Git checkout и Python 3.12 с установленным проектом по README.
Для всей QA suite установите также optional extra `fuzz`; обычной установке API
он не требуется. Все команды выполняются из корня checkout.

```bash
python -m pip install -e '.[serve,test,fuzz]'
python -m pip check
python -m unittest discover -s tests -v
python -m unittest discover -s scripts/research -p 'test_*.py' -v
```

Property suite с зафиксированными profile/seed:

```bash
GOODSAI_FUZZ_PROFILE=quick GOODSAI_FUZZ_SEED=20261021 python -m unittest discover -s tests/fuzz -v
```

PowerShell:

```powershell
$env:GOODSAI_FUZZ_PROFILE = "quick"
$env:GOODSAI_FUZZ_SEED = "20261021"
.\.venv\Scripts\python.exe -m unittest discover -s tests/fuzz -v
```

Остальные `python` команды в PowerShell можно запускать через
`.\.venv\Scripts\python.exe`. Каждый шаг должен завершиться с exit 0;
при ошибке сохранить исходный лог и разобрать причину. Нельзя выдавать
неустановленный optional dependency или skipped suite за пройденную проверку.

```bash
python scripts/release/clean_run.py --output-dir outputs/qa-clean-next
python scripts/release/clean_run.py --output-dir outputs/qa-clean-next
python scripts/release/scenario_matrix.py --seed 20261021 --output-dir outputs/qa-matrix-next
python scripts/release/scenario_matrix.py --verify outputs/qa-matrix-next
```

Первый clean-run создаёт собственное окружение по hash-locked dependencies,
проверяет rules batch, API contract, packaged demo и synthetic artifact bundle.
Второй проверяет сохранённые hashes и версии без нового prediction.
После изменения source/environment/input нужен новый output-dir.
Matrix проверяет внешний CLI и настоящий loopback HTTP из изолированной копии
runtime без packaged examples, затем offline verifier/config/LLM и отдельное demo.
Результаты сохраняются внутри ignored `outputs/`; старые прогоны не перезаписываются.

## Проверяемые области

| Критерий QA-002 | Существующее исполняемое доказательство |
| --- | --- |
| Config и rules-only | `test_config.py`, external oracle, clean-run batch/manifest |
| LLM success и точное evidence | `test_llm.GroundingTests`, SCN-016 |
| Provider failure, timeout, retry и бюджеты | `test_llm.FailureTests`, `test_llm_bounds.LocalGateway`, SCN-016 |
| Evidence reject, конфликт и safe abstain | `test_candidate_verifier.py`, `test_llm_validation.py`, SCN-015/016 |
| Cache и отсутствие утечки в диагностике | `test_llm.CacheTests`, `ProviderTests`, `CliTests`, `test_api.ApiTests.test_failure_does_not_leak_input_or_exception` |
| CLI/API parity и ошибки входа | External CLI/listening HTTP, `test_api.py`, malformed JSONL recovery |
| Demo и артефакты | `test_demo.py`, packaged 6-case smoke, clean-run artifact verification/replay |
| Ошибочный HTML | `test_fuzz_regressions.py`, `test_api.py`, исходная property suite; #158 |

`scenario_catalog.EVIDENCE_TESTS` закрепляет конкретные acceptance test IDs.
QA-002 добавил 12 обязательных LLM-контролей к прежним verifier/config:
зелёный suite с посторонними тестами больше не скрывает их отсутствие.
`required_tests_missing` должен быть пуст; zero tests и skips не дают PASS.
CI уже исполняет эти инструменты: `External input acceptance`, `Clean run`,
`Span index` и `Synthetic property tests`. Обязательные проверки не обходятся.

## Границы вывода

Это synthetic correctness/reproducibility acceptance. Счётчики suites и matrix
перекрываются и не складываются в число уникальных сценариев. Property profile
задаёт максимум примеров на свойство, а не измеренный объём реального каталога.
Fake/loopback LLM проверяет интеграцию и отказы; реальный gateway, live model
quality, invoice, final VM deployment и независимый human test здесь не проверены.
Полный финальный комплект на реальных данных не заменяется synthetic smoke.
Gaps матрицы остаются видимыми даже при успешном executable gate.

[Quality report](../reports/quality_20261021.md) относится к своему frozen runtime
`9ebba1d`. Новый QA parser fix не сопровождается новым замером catalog P/R/F1;
исторические числа и provenance не переписываются. [RESULTS](RESULTS.md) хранит
границы каждого измерения, [RELEASES](RELEASES.md) — связь GitHub/Gitea, а приёмка
целевой ВМ остаётся отдельной #82. QA-002 сам по себе не обновляет сервис.
