"""HTTP boundary checks using synthetic text only; install .[serve,test] to run."""
import importlib.util
import json
import unittest
from unittest.mock import patch

SERVICE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "uvicorn"))
if SERVICE_DEPS:
    from httpx import ASGITransport, AsyncClient
    from goodsai.api import MAX_BODY_BYTES, create_app
    from goodsai.contracts import Product, load_config
    from goodsai.verify import Extractor


@unittest.skipUnless(SERVICE_DEPS, "HTTP tests require pip install -e .[serve,test]")
class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.product = {"schema_version": "0.1", "sku_id": "synthetic",
                        "category_id": "761", "title": "Samsung Example 8/256GB"}

    async def test_health_root_and_openapi(self):
        self.assertEqual((await self.client.get("/health")).json()["status"], "ok")
        self.assertEqual((await self.client.get("/")).json()["api_status"], "provisional")
        schema = (await self.client.get("/openapi.json")).json()
        self.assertIn("requestBody", schema["paths"]["/predict"]["post"])

    async def test_same_predictions_as_cli_core(self):
        for category, title in [("761", "Samsung Example 8/256GB"),
                                ("482", "Чайник Bosch Example 1,7 л 2200 Вт")]:
            with self.subTest(category=category):
                self.product.update(category_id=category, title=title)
                response = await self.client.post("/predict", json=self.product)
                self.assertEqual(response.status_code, 200)
                expected = Extractor(load_config()).predict(Product.from_dict(self.product),
                                                           run_id="http-rules-v0")
                self.assertEqual(response.json(), expected)

    async def test_unknown_category_is_domain_response(self):
        self.product["category_id"] = "unknown"
        response = await self.client.post("/predict", json=self.product)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unsupported_category")
        self.assertEqual(response.json()["attributes"], [])

    async def test_targets_and_invalid_products_rejected(self):
        for invalid in [dict(self.product, vendor="secret"),
                        dict(self.product, seller_attributes=[{"brand": "secret"}]),
                        dict(self.product, title=" "), dict(self.product, schema_version="2"),
                        dict(self.product, category_id=761), [], None]:
            with self.subTest(invalid=invalid):
                response = await self.client.post("/predict", content=json.dumps(invalid),
                                            headers={"content-type": "application/json"})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("secret", response.text)

    async def test_bad_json_and_content_type(self):
        for content in [b"{", b"\xff", b'{"title": NaN}']:
            response = await self.client.post("/predict", content=content,
                                        headers={"content-type": "application/json"})
            self.assertEqual(response.status_code, 400)
        self.assertEqual((await self.client.post("/predict", content="text")).status_code, 415)

    async def test_request_size_limit_without_content_length(self):
        async def chunks():
            for _ in range(3):
                yield b"x" * 65536
        response = await self.client.post("/predict", content=chunks(),
                                    headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertGreater(3 * 65536, MAX_BODY_BYTES)

    async def test_failure_does_not_leak_input_or_exception(self):
        with patch.object(Extractor, "predict", side_effect=RuntimeError("secret body")):
            with self.assertLogs("goodsai.api", level="ERROR") as logs:
                response = await self.client.post("/predict", json=self.product)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.text + str(logs.output))
        self.assertNotIn(self.product["title"], response.text + str(logs.output))


if __name__ == "__main__":
    unittest.main()
