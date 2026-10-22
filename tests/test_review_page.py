"""Operator review screen: served by the API, self-contained, prediction path untouched."""
import importlib.util
import re
import unittest
from pathlib import Path

SERVICE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "uvicorn"))
if SERVICE_DEPS:
    from httpx import ASGITransport, AsyncClient
    from goodsai import review_page
    from goodsai.api import create_app
    from goodsai.contracts import Product, load_config
    from goodsai.verify import Extractor

SOURCE = Path(__file__).resolve().parents[1] / "src" / "goodsai"
CODE = re.compile(r'"((?:relation|llm|verifier)_[a-z_]+|conflicting_[a-z_]+|not_found_by_rules|invalid_text_only_input)"')
NOT_REASONS = {"llm_enabled", "llm_calls", "llm_changes", "llm_cache_write_failed",
               "conflicting_reference_units"}  # report keys and evaluation errors, not reason_codes


@unittest.skipUnless(SERVICE_DEPS, "HTTP tests require pip install -e .[serve,test]")
class ReviewPageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_page_is_served_as_html_with_restrictive_headers(self):
        response = await self.client.get("/review")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        csp = response.headers["content-security-policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_page_is_self_contained_and_calls_the_same_predict(self):
        page = (await self.client.get("/review")).text
        self.assertNotIn("__REASONS", page)
        self.assertIn('fetch("predict"', page)
        self.assertIsNone(re.search(r"""(?:src|href)\s*=\s*["']https?:""", page))
        self.assertIsNone(re.search(r"https?://", page))
        for element in ('id="title"', 'id="description"', 'id="check"', 'id="rows"', 'id="download"'):
            self.assertIn(element, page)
        for action in ("accepted", "corrected", "rejected", "filled", "confirmed_empty"):
            self.assertIn(action, page)

    async def test_user_text_is_never_inserted_as_html(self):
        page = (await self.client.get("/review")).text
        script = page.split("<script>", 1)[1]
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertNotIn("document.write", script)

    async def test_every_runtime_reason_code_has_operator_text(self):
        codes = set()
        for path in SOURCE.glob("*.py"):
            codes.update(CODE.findall(path.read_text(encoding="utf-8")))
        codes -= NOT_REASONS
        self.assertIn("conflicting_evidence", codes)
        for code in sorted(codes):
            with self.subTest(code=code):
                explained = code in review_page.REASONS or any(
                    code.startswith(prefix) for prefix in review_page.REASON_PREFIXES)
                self.assertTrue(explained, code)
        page = (await self.client.get("/review")).text
        self.assertIn(review_page.REASONS["conflicting_evidence"], page)

    async def test_predict_root_and_openapi_are_unchanged(self):
        product = {"schema_version": "0.1", "sku_id": "review-check", "category_id": "761",
                   "title": "Смартфон Samsung Nova X86 12/512GB белый"}
        response = await self.client.post("/predict", json=product)
        expected = Extractor(load_config()).predict(Product.from_dict(product), run_id="http-rules-v0")
        self.assertEqual(response.json(), expected)
        self.assertEqual((await self.client.get("/")).json()["api_status"], "provisional")
        paths = (await self.client.get("/openapi.json")).json()["paths"]
        self.assertIn("/review", paths)
        self.assertIn("/predict", paths)
