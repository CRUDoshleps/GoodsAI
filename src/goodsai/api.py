"""Provisional HTTP transport for the unchanged E1 contract, pending organizer API."""
import argparse
import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from goodsai.contracts import Product, load_config
from goodsai.verify import Extractor

MAX_BODY_BYTES = 128 * 1024
LOGGER = logging.getLogger(__name__)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app() -> FastAPI:
    # Fail before listening if the packaged configuration cannot be loaded.
    config = load_config()
    extractor = Extractor(config)
    app = FastAPI(title="GoodsAI provisional API", version="0.1.0",
                  description="Temporary weekend API. Organizer endpoints are pending.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(exc.status_code, "http_error", "Request cannot be handled")

    @app.get("/")
    def index():
        return {"service": "goodsai", "api_status": "provisional",
                "health": "/health", "predict": "/predict", "docs": "/docs"}

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "goodsai", "schema_version": "0.1",
                "api_status": "provisional", "categories": sorted(config["categories"])}

    @app.post("/predict", openapi_extra={"requestBody": {
        "required": True, "content": {"application/json": {"schema": {
            "type": "object", "additionalProperties": False,
            "required": ["schema_version", "sku_id", "title"],
            "properties": {
                "schema_version": {"type": "string", "enum": ["0.1"]},
                "sku_id": {"type": "string", "minLength": 1},
                "category_id": {"type": ["string", "null"]},
                "title": {"type": "string", "minLength": 1},
                "description": {"type": ["string", "null"]},
                "seller_attributes": {"type": "array", "maxItems": 0},
                "source_flags": {"type": "array", "items": {"type": "string"}}
            }}}}}})
    async def predict(request: Request):
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return error(415, "unsupported_media_type", "Use application/json")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                return error(413, "request_too_large", "Maximum request body is 128 KiB")
            body.extend(chunk)
        try:
            # Strict UTF-8 JSON; reject NaN/Infinity rather than accepting non-JSON values.
            def invalid_constant(value):
                raise ValueError("Non-JSON number")
            row = json.loads(body.decode("utf-8"), parse_constant=invalid_constant)
        except (ValueError, RecursionError):
            return error(400, "invalid_json", "Body must be a UTF-8 JSON object")
        try:
            product = Product.from_dict(row)
        except ValueError as exc:
            # Contract errors are fixed strings and never include submitted values.
            return error(422, "invalid_product", str(exc))
        try:
            return await run_in_threadpool(extractor.predict, product, run_id="http-rules-v0")
        except Exception:
            # No request text, SKU or exception details in responses or application logs.
            LOGGER.error("GoodsAI extraction failed")
            return error(500, "prediction_failed", "Extraction failed")

    return app


def main():
    parser = argparse.ArgumentParser(description="Run the provisional GoodsAI HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False,
                limit_concurrency=32, timeout_keep_alive=5)


if __name__ == "__main__":
    main()
