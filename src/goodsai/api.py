"""HTTP transport for the unchanged E1 contract (schema 0.1)."""
import argparse
import json
import logging

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from goodsai import api_examples
from goodsai.contracts import Product, load_config
from goodsai.config import default_api_limits
from goodsai.composition import Components, build_runtime
from goodsai.policy import resolve_runtime_policy
from goodsai.review_page import register as register_review_page

MAX_BODY_BYTES = default_api_limits()["max_body_bytes"]  # Backward-compatible default export.
LOGGER = logging.getLogger(__name__)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(config_path: str | None = None, *, components: Components | None = None) -> FastAPI:
    # Fail before listening if the packaged configuration cannot be loaded.
    config = load_config(config_path)
    policy = resolve_runtime_policy(config)
    runtime = build_runtime(config, policy, components=components)
    config, metadata = runtime.config, runtime.metadata
    api_limits = config["runtime"]["api"]
    extractor, llm = runtime.predictor, runtime.llm
    run_id = "http-rules-llm-v0" if llm is not None else "http-rules-v0"
    app = FastAPI(title=api_examples.TITLE, version="0.1.0", description=api_examples.DESCRIPTION)
    app.state.goodsai_config = config
    app.state.goodsai_runtime = metadata

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(exc.status_code, "http_error", "Request cannot be handled")

    register_review_page(app)  # operator screen: calls the same /predict, stores nothing

    @app.get("/")
    def index():
        return {"service": "goodsai", "api_status": "provisional",
                "health": "/health", "predict": "/predict", "docs": "/docs"}

    @app.get("/health", summary=api_examples.HEALTH_SUMMARY)
    def health():
        body = {"status": "ok", "service": "goodsai", "schema_version": "0.1",
                "api_status": "provisional", "categories": sorted(config["categories"]),
                "runtime_policy_sha256": metadata["runtime_policy_sha256"],
                "effective_config_sha256": metadata["effective_config_sha256"]}
        body["auto_accept_policies"] = policy["decisions"]["auto_accept_policies"]
        acceptance = policy["decisions"].get("auto_accept")
        if acceptance is not None:
            body["auto_accept"] = acceptance
        from goodsai.learned_confidence import metadata as confidence_metadata
        confidence = confidence_metadata(config)
        if confidence is not None:
            body['confidence'] = confidence
        if llm is not None:
            report = llm.report()
            body["llm"] = {key: report[key] for key in ("enabled", "model", "prompt_version", "calls",
                                                         "max_calls", "cache_hits", "disabled_reason")}
        return body

    @app.post("/predict", summary=api_examples.PREDICT_SUMMARY, description=api_examples.PREDICT_DESCRIPTION,
              openapi_extra={"requestBody": {
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
            if len(body) + len(chunk) > api_limits["max_body_bytes"]:
                limit = api_limits["max_body_bytes"]
                label = f"{limit // 1024} KiB" if limit % 1024 == 0 else f"{limit} bytes"
                return error(413, "request_too_large", f"Maximum request body is {label}")
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
            return await run_in_threadpool(extractor.predict, product, run_id=run_id)
        except Exception:
            # No request text, SKU or exception details in responses or application logs.
            LOGGER.error("GoodsAI extraction failed")
            return error(500, "prediction_failed", "Extraction failed")

    def openapi_with_examples():
        # Examples are attached after generation: FastAPI drops null values inside
        # examples, and documented responses must keep every field of schema 0.1.
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version,
                                 description=app.description, routes=app.routes)
            app.openapi_schema = api_examples.attach(schema)
        return app.openapi_schema

    app.openapi = openapi_with_examples
    return app


def main():
    parser = argparse.ArgumentParser(description="Run the provisional GoodsAI HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", help="Versioned JSON configuration; same format as CLI --config")
    args = parser.parse_args()
    # Validate before starting the server; never start with a partial/bad profile.
    try:
        app = create_app(args.config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    api_limits = app.state.goodsai_config["runtime"]["api"]
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, access_log=False,
                limit_concurrency=api_limits["limit_concurrency"],
                timeout_keep_alive=api_limits["timeout_keep_alive_seconds"])


if __name__ == "__main__":
    main()
