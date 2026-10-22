"""Documented OpenAPI examples must be the real answers of the default profile."""
import importlib.util
import json
import unittest

SERVICE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "uvicorn"))
if SERVICE_DEPS:
    from httpx import ASGITransport, AsyncClient
    from goodsai import api_examples
    from goodsai.api import create_app
    from goodsai.contracts import Product, load_config, validate_prediction


@unittest.skipUnless(SERVICE_DEPS, "HTTP tests require pip install -e .[serve,test]")
class ApiExamplesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.schema = (await self.client.get("/openapi.json")).json()
        self.operation = self.schema["paths"]["/predict"]["post"]

    async def test_service_description_replaces_temporary_text(self):
        info = self.schema["info"]
        self.assertEqual(info["title"], api_examples.TITLE)
        self.assertNotIn("Temporary", info["description"])
        for fragment in ("761", "482", "evidence", "abstain", "не вероятность"):
            self.assertIn(fragment, info["description"])

    async def test_every_success_example_is_replayed_exactly(self):
        requests = self.operation["requestBody"]["content"]["application/json"]["examples"]
        responses = self.operation["responses"]["200"]["content"]["application/json"]["examples"]
        self.assertEqual(set(api_examples.PREDICT_EXAMPLES), set(responses))
        config = load_config()
        for name, documented in responses.items():
            with self.subTest(example=name):
                request = requests[name]["value"]
                actual = await self.client.post("/predict", json=request)
                self.assertEqual(actual.status_code, 200)
                self.assertEqual(actual.json(), documented["value"])
                validate_prediction(documented["value"], config, Product.from_dict(request))

    async def test_examples_cover_review_conflict_and_unsupported(self):
        responses = api_examples.PREDICT_EXAMPLES
        decisions = {a["decision"] for _, _, row in responses.values() for a in row["attributes"]}
        reasons = {code for _, _, row in responses.values() for a in row["attributes"] for code in a["reason_codes"]}
        statuses = {row["status"] for _, _, row in responses.values()}
        self.assertEqual(decisions, {"review", "abstain"})
        self.assertLessEqual({"conflicting_evidence", "not_found_by_rules"}, reasons)
        self.assertEqual(statuses, {"processed", "unsupported_category"})

    async def test_error_examples_match_runtime(self):
        documented = {int(code): body["content"]["application/json"]["example"]
                      for code, body in self.operation["responses"].items() if code != "200"}
        self.assertEqual(set(documented), {400, 413, 415, 422, 500})
        forbidden = self.operation["requestBody"]["content"]["application/json"]["examples"]["forbidden_field"]
        limit = load_config()["runtime"]["api"]["max_body_bytes"]
        cases = {
            400: dict(content=b"{", headers={"Content-Type": "application/json"}),
            413: dict(content=b" " * (limit + 1), headers={"Content-Type": "application/json"}),
            415: dict(content=b"{}", headers={"Content-Type": "text/plain"}),
            422: dict(content=json.dumps(forbidden["value"]).encode(), headers={"Content-Type": "application/json"}),
        }
        for status, kwargs in cases.items():
            with self.subTest(status=status):
                response = await self.client.post("/predict", **kwargs)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), documented[status])
        self.assertEqual(documented[500], {"error": {"code": "prediction_failed", "message": "Extraction failed"}})

    async def test_existing_routes_and_health_unchanged(self):
        self.assertEqual((await self.client.get("/")).json()["api_status"], "provisional")
        health = (await self.client.get("/health")).json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["categories"], ["482", "761"])
