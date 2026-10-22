"""OpenAPI documentation for the HTTP API: service description and real examples.

Every response example below is the actual output of the default profile for the
paired request example; ``tests/test_api_examples.py`` replays each request and
fails if the documented answer drifts from runtime. Nothing here affects predictions.
"""

TITLE = "GoodsAI — извлечение характеристик товара"

DESCRIPTION = """\
Извлекает характеристики товара из текста карточки (`title` и `description`).
Поддерживаемые категории: **761** — смартфоны, **482** — электрочайники.

Каждый атрибут в ответе — либо нормализованное значение с цитатой-доказательством,
либо явный отказ с кодом причины:

- `evidence` — поле, позиции `start`/`end` в исходной строке и точный текст цитаты;
- `decision`: `review` — значение найдено, его подтверждает оператор; `abstain` —
  значения нет, причина в `reason_codes`; `auto_accept` — только если профиль сервиса
  включает проверенный человеком пилот (накопитель смартфонов, см. `/health`);
- `confidence` — эвристический score источника, **не вероятность** правильности.

Примеры ниже — настоящие ответы штатного профиля, их можно отправить кнопкой
**Try it out**. Готовые поля каталога (`vendor`, `model`, `params`) во входе запрещены:
сервис работает только по тексту.

| Метод | Назначение |
| --- | --- |
| `POST /predict` | одна карточка → ответ schema 0.1 |
| `GET /health` | состояние, категории, hashes конфигурации, активные политики |

Ошибки всегда имеют вид `{"error": {"code": "...", "message": "..."}}`; текст карточки
в ошибки и логи не попадает. Пакетная обработка с выгрузкой JSONL и manifest —
`python -m goodsai.cli predict`. Подробно о полях, причинах отказа и действиях
оператора — `docs/RESPONSES.md`, запуск с нуля — `docs/QUICKSTART.md`.
"""

PREDICT_SUMMARY = "Извлечь характеристики из одной карточки"
PREDICT_DESCRIPTION = (
    "Принимает одну карточку в формате schema 0.1 и возвращает все атрибуты схемы её категории "
    "в порядке схемы. Неподдерживаемая категория — HTTP 200 со `status: unsupported_category`. "
    "Невалидный вход — HTTP 422, ответ строки не создаётся.")
HEALTH_SUMMARY = "Состояние сервиса и активный профиль"


def _attribute(name, value=None, unit=None, confidence=None, rule_id=None, evidence=None, reasons=()):
    found = value is not None
    return {"attribute": name, "value": value, "unit": unit, "confidence": confidence,
            "confidence_kind": "heuristic", "decision": "review" if found else "abstain",
            "method": "rule", "rule_id": rule_id,
            "evidence": dict(zip(("field", "start", "end", "text"), evidence)) if evidence else None,
            "reason_codes": list(reasons)}


def _response(sku_id, category_id, attributes, status="processed"):
    return {"schema_version": "0.1", "run_id": "http-rules-v0", "sku_id": sku_id,
            "category_id": category_id, "status": status, "attributes": attributes}


SMARTPHONE = {"schema_version": "0.1", "sku_id": "demo-phone", "category_id": "761",
              "title": "Смартфон Samsung Nova X86 12/512GB белый",
              "description": "Экран 6,4 дюйма. Аккумулятор 4600 мАч."}
CONFLICT = {"schema_version": "0.1", "sku_id": "demo-conflict", "category_id": "761",
            "title": "Смартфон Samsung Nova X86 8/256GB черный",
            "description": "<p>Встроенная память 128 ГБ.</p><p>Экран&nbsp;6,1 дюйма.</p>"}
KETTLE = {"schema_version": "0.1", "sku_id": "demo-kettle", "category_id": "482",
          "title": "Электрочайник Vexa KT-17 1,7 л 2200 Вт серебристый"}
UNSUPPORTED = {"schema_version": "0.1", "sku_id": "demo-vacuum", "category_id": "999",
               "title": "Пылесос Vexa VC-10"}
FORBIDDEN_FIELD = {"schema_version": "0.1", "sku_id": "demo-invalid", "category_id": "761",
                   "title": "Смартфон Samsung Nova X86", "vendor": "Samsung"}

SMARTPHONE_RESPONSE = _response("demo-phone", "761", [
    _attribute("brand", "Samsung", None, 0.85, "brand.explicit-title.v1", ("title", 9, 16, "Samsung")),
    _attribute("model", "Nova X86", None, 0.8, "model.phone-title.v2", ("title", 17, 25, "Nova X86")),
    _attribute("storage_gb", "512", "GB", 0.8, "memory.title-pair.v1", ("title", 26, 34, "12/512GB")),
    _attribute("ram_gb", "12", "GB", 0.8, "memory.title-pair.v1", ("title", 26, 34, "12/512GB")),
    _attribute("screen_inches", "6.4", "inch", 0.8, "screen_inches.explicit.v1",
               ("description", 6, 15, "6,4 дюйма")),
    _attribute("battery_mah", "4600", "mAh", 0.8, "battery_mah.explicit.v1",
               ("description", 29, 37, "4600 мАч")),
    _attribute("color", "белый", None, 0.75, "color.explicit.v2", ("title", 35, 40, "белый")),
])
CONFLICT_RESPONSE = _response("demo-conflict", "761", [
    _attribute("brand", "Samsung", None, 0.85, "brand.explicit-title.v1", ("title", 9, 16, "Samsung")),
    _attribute("model", "Nova X86", None, 0.8, "model.phone-title.v2", ("title", 17, 25, "Nova X86")),
    _attribute("storage_gb", reasons=["conflicting_evidence"]),
    _attribute("ram_gb", "8", "GB", 0.8, "memory.title-pair.v1", ("title", 26, 33, "8/256GB")),
    _attribute("screen_inches", "6.1", "inch", 0.8, "screen_inches.explicit.v1",
               ("description", 46, 55, "6,1 дюйма")),
    _attribute("battery_mah", reasons=["not_found_by_rules"]),
    _attribute("color", "черный", None, 0.75, "color.explicit.v2", ("title", 34, 40, "черный")),
])
KETTLE_RESPONSE = _response("demo-kettle", "482", [
    _attribute("brand", reasons=["not_found_by_rules"]),
    _attribute("model", "KT-17", None, 0.8, "model.kettle-title.v2", ("title", 19, 24, "KT-17")),
    _attribute("capacity_l", "1.7", "L", 0.8, "capacity_l.explicit.v1", ("title", 25, 30, "1,7 л")),
    _attribute("power_w", "2200", "W", 0.8, "power_w.explicit.v1", ("title", 31, 38, "2200 Вт")),
    _attribute("color", "серебристый", None, 0.75, "color.explicit.v2", ("title", 39, 50, "серебристый")),
])
UNSUPPORTED_RESPONSE = _response("demo-vacuum", "999", [], status="unsupported_category")

# name -> (summary, request, response); the same names are used in requestBody and 200 examples.
PREDICT_EXAMPLES = {
    "smartphone": ("Смартфон: все 7 полей найдены, у каждого цитата", SMARTPHONE, SMARTPHONE_RESPONSE),
    "conflict": ("Конфликт: 256 GB в title и 128 ГБ в описании → накопитель abstain",
                 CONFLICT, CONFLICT_RESPONSE),
    "kettle": ("Чайник: бренда нет в словаре → abstain, остальное найдено", KETTLE, KETTLE_RESPONSE),
    "unsupported_category": ("Категория вне схемы → HTTP 200, status unsupported_category",
                             UNSUPPORTED, UNSUPPORTED_RESPONSE),
}


def _error(code, message):
    return {"error": {"code": code, "message": message}}


ERROR_EXAMPLES = {
    400: ("Тело не является JSON-объектом в UTF-8", _error("invalid_json", "Body must be a UTF-8 JSON object")),
    413: ("Тело больше лимита профиля (по умолчанию 128 KiB)",
          _error("request_too_large", "Maximum request body is 128 KiB")),
    415: ("Заголовок Content-Type не application/json", _error("unsupported_media_type", "Use application/json")),
    422: ("Во входе есть поле каталога (например vendor) или нарушена schema 0.1",
          _error("invalid_product", "Unknown input fields: text-only input must not contain targets or metadata")),
    500: ("Внутренняя ошибка извлечения; детали в ответ и логи не попадают",
          _error("prediction_failed", "Extraction failed")),
}


def request_examples() -> dict:
    examples = {name: {"summary": summary, "value": request}
                for name, (summary, request, _) in PREDICT_EXAMPLES.items()}
    examples["forbidden_field"] = {"summary": "Запрещённое поле vendor → HTTP 422", "value": FORBIDDEN_FIELD}
    return examples


def predict_responses() -> dict:
    ok = {name: {"summary": summary, "value": response}
          for name, (summary, _, response) in PREDICT_EXAMPLES.items()}
    responses = {200: {"description": "Карточка обработана: атрибуты схемы или unsupported_category",
                       "content": {"application/json": {"examples": ok}}}}
    for status, (summary, body) in ERROR_EXAMPLES.items():
        responses[status] = {"description": summary,
                             "content": {"application/json": {"example": body}}}
    return responses


def attach(schema: dict) -> dict:
    """Add request and response examples to a generated OpenAPI schema, keeping nulls."""
    operation = schema["paths"]["/predict"]["post"]
    operation["requestBody"]["content"]["application/json"]["examples"] = request_examples()
    responses = operation.setdefault("responses", {})
    responses.pop("422", None)
    for status, body in predict_responses().items():
        responses[str(status)] = body
    return schema
