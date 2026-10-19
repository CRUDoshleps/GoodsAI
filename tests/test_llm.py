"""LLM-003 fallback: fake providers only, no network, no real card text."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from goodsai import cli
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.llm import (LLMExtractor, LLMSettings, OpenAICompatibleProvider, ProviderError, ProviderResponse,
                         cache_key, parse_proposals)
from goodsai.verify import Extractor


def answer(*items):
    return json.dumps({"attributes": [dict(zip(("attribute", "value", "quote"), item)) for item in items]},
                      ensure_ascii=False)


class FakeProvider:
    model = "fake-model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0
        self.messages = []

    def complete(self, messages, max_tokens):
        self.calls += 1
        self.messages.append(messages)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return ProviderResponse(item, prompt_tokens=120, completion_tokens=30)


PHONE = Product("sku-1", "761", "Смартфон Zorion QX-900 8/256GB черный",
                "Аккумулятор 5000 мА*ч. Экран 6,7 дюйма.")


def attrs(row):
    return {a["attribute"]: a for a in row["attributes"]}


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.settings = LLMSettings(model="fake-model")

    def run_one(self, product, *responses, settings=None):
        provider = FakeProvider(*responses)
        extractor = LLMExtractor(self.config, provider, settings or self.settings)
        row = extractor.predict(product, "same")
        validate_prediction(row, self.config, product)
        return row, extractor, provider

    def test_only_rule_gaps_are_requested_and_rule_decisions_are_preserved(self):
        row, extractor, provider = self.run_one(PHONE, answer(("brand", "Zorion", "Смартфон Zorion")))
        sent = json.loads(provider.messages[0][1]["content"])
        rules = attrs(Extractor(self.config).predict(PHONE, "same"))
        gaps = [name for name, a in rules.items() if a["reason_codes"] == ["not_found_by_rules"]]
        self.assertEqual([item["attribute"] for item in sent["requested_attributes"]], gaps)
        for name, a in attrs(row).items():
            if name not in gaps:
                self.assertEqual(a, rules[name])

    def test_grounded_values_get_exact_raw_evidence_and_stay_review(self):
        row, extractor, _ = self.run_one(PHONE, answer(
            ("brand", "Zorion", "Смартфон Zorion"), ("battery_mah", "5000 мАч", "Аккумулятор 5000 мА*ч")))
        brand, battery = attrs(row)["brand"], attrs(row)["battery_mah"]
        self.assertEqual((brand["value"], brand["method"], brand["decision"], brand["confidence_kind"]),
                         ("Zorion", "llm", "review", "heuristic"))
        self.assertEqual(battery["value"], "5000")
        self.assertEqual(PHONE.description[battery["evidence"]["start"]:battery["evidence"]["end"]], "5000 мА*ч")
        self.assertEqual(extractor.report()["accepted"], 2)

    def test_html_description_offsets_point_into_untouched_source(self):
        product = Product("sku-2", "482", "Электрочайник Vexa KT-1", "<p>&laquo;Vexa&raquo; вмещает <b>1,7 л</b> воды.</p>")
        row, _, _ = self.run_one(product, answer(("capacity_l", "1.7", "1,7 л")))
        cap = attrs(row)["capacity_l"]
        self.assertEqual((cap["value"], cap["method"]), ("1.7", "llm"))
        self.assertEqual(product.description[cap["evidence"]["start"]:cap["evidence"]["end"]], "1,7 л")

    def test_rejections_keep_abstain_with_reason(self):
        cases = {
            "llm_quote_not_found": ("battery_mah", "5000", "батарея на 5000 мА·ч"),
            "llm_value_not_in_quote": ("battery_mah", "4500", "Аккумулятор 5000 мА*ч"),
            "llm_value_not_in_schema": ("brand", "смартфон", "Смартфон"),
            "llm_bad_types": ("brand", True, "Смартфон Zorion"),
        }
        for reason, item in cases.items():
            with self.subTest(reason):
                row, extractor, _ = self.run_one(PHONE, answer(item))
                a = attrs(row)[item[0]]
                self.assertEqual((a["value"], a["decision"]), (None, "abstain"))
                self.assertEqual(a["reason_codes"], ["not_found_by_rules", reason])
                self.assertEqual(extractor.report()["rejected"], {reason: 1})

    def test_unknown_attribute_extra_keys_and_resolved_fields_are_ignored(self):
        payload = json.dumps({"attributes": [
            {"attribute": "weight_g", "value": "200", "quote": "Смартфон"},
            {"attribute": "brand", "value": "Zorion", "quote": "Zorion", "source": "web"},
            {"attribute": "color", "value": "белый", "quote": "черный"}]}, ensure_ascii=False)
        row, extractor, _ = self.run_one(PHONE, payload)
        self.assertEqual(attrs(row)["color"]["value"], "черный")
        self.assertIsNone(attrs(row)["brand"]["value"])
        self.assertEqual(extractor.report()["rejected"], {"llm_unknown_attribute": 2, "llm_unknown_field": 1})

    def test_uncertain_or_negated_context_is_rejected(self):
        product = Product("sku-3", "761", "Смартфон Zorion QX-900", "Аккумулятор до 5000 мА·ч.")
        row, _, _ = self.run_one(product, answer(("battery_mah", "5000", "до 5000 мА·ч")))
        self.assertIn("llm_uncertain_context", attrs(row)["battery_mah"]["reason_codes"])

    def test_color_outside_dictionary_and_conflicting_values(self):
        product = Product("sku-4", "761", "Смартфон Zorion QX-900", "Цвет корпуса: бирюзово-мятный.")
        row, _, _ = self.run_one(product, answer(("color", "бирюзово-мятный", "бирюзово-мятный")))
        self.assertIn("llm_value_not_in_schema", attrs(row)["color"]["reason_codes"])
        row, _, _ = self.run_one(Product("sku-5", "482", "Чайник Vexa", "Потребляет 2200 Вт, в турборежиме 2400 Вт."),
                                 answer(("power_w", "2200", "Потребляет 2200 Вт"), ("power_w", "2400", "2400 Вт")))
        self.assertIn("conflicting_llm_evidence", attrs(row)["power_w"]["reason_codes"])

    def test_foreign_brand_after_compatibility_phrase_is_rejected(self):
        product = Product("sku-6", "761", "Смартфон для Zorion QX-900")
        row, _, _ = self.run_one(product, answer(("brand", "Zorion", "для Zorion")))
        self.assertIn("llm_foreign_entity", attrs(row)["brand"]["reason_codes"])

    def test_no_gap_and_unsupported_category_never_call_provider(self):
        provider = FakeProvider(AssertionError("must not be called"))
        extractor = LLMExtractor(self.config, provider, self.settings)
        extractor.predict(Product("x", "unknown", "Что-то"))
        self.assertEqual(provider.calls, 0)
        self.assertEqual(extractor.report()["cards_routed"], 0)

    def test_malformed_json_and_fenced_json(self):
        self.assertEqual(parse_proposals('```json\n{"attributes": []}\n```'), [])
        for bad in ["not json", '{"attributes": {}}', '{"attributes": [], "x": 1}', '{"attributes": [NaN]}']:
            with self.assertRaises(ProviderError):
                parse_proposals(bad)
        row, extractor, _ = self.run_one(PHONE, "Вот ответ: бренд Zorion")
        self.assertIn("llm_malformed_json", attrs(row)["brand"]["reason_codes"])
        self.assertEqual(extractor.report()["calls"], 1)


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_provider_failure_keeps_rule_output_and_adds_reason(self):
        baseline = Extractor(self.config).predict(PHONE, "same")
        extractor = LLMExtractor(self.config, FakeProvider(ProviderError("llm_timeout")), LLMSettings(model="m"))
        row = extractor.predict(PHONE, "same")
        for got, base in zip(row["attributes"], baseline["attributes"]):
            if base["reason_codes"] == ["not_found_by_rules"]:
                self.assertEqual(got["reason_codes"], ["not_found_by_rules", "llm_timeout"])
            else:
                self.assertEqual(got, base)
        self.assertEqual(extractor.report()["failures"], {"llm_timeout": 1})

    def test_missing_key_is_fatal_once(self):
        settings = LLMSettings(model="m")
        provider = OpenAICompatibleProvider(None, None, settings, opener=self.fail_opener)
        extractor = LLMExtractor(self.config, provider, settings)
        for _ in range(3):
            row = extractor.predict(PHONE)
        self.assertIn("llm_missing_key", attrs(row)["brand"]["reason_codes"])
        report = extractor.report()
        self.assertEqual((report["disabled_reason"], report["calls"]), ("llm_missing_key", 1))

    @staticmethod
    def fail_opener(*_args, **_kwargs):
        raise AssertionError("network must not be used")

    def test_budget_exhausted_and_circuit_breaker(self):
        extractor = LLMExtractor(self.config, FakeProvider(answer()), LLMSettings(model="m", max_calls=1))
        extractor.predict(PHONE)
        row = extractor.predict(Product("sku-9", "761", "Смартфон Zorion QX-901"))
        self.assertIn("llm_budget_exhausted", attrs(row)["brand"]["reason_codes"])
        self.assertEqual(extractor.report()["calls"], 1)
        provider = FakeProvider(ProviderError("llm_server_error"))
        extractor = LLMExtractor(self.config, provider, LLMSettings(model="m", circuit_breaker=2))
        for i in range(4):
            row = extractor.predict(Product(f"s{i}", "761", f"Смартфон Zorion QX-90{i}"))
        self.assertEqual(provider.calls, 2)
        self.assertEqual(extractor.report()["disabled_reason"], "llm_circuit_open")
        self.assertIn("llm_circuit_open", attrs(row)["brand"]["reason_codes"])


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://gateway.invalid", code, "error", headers, None)


class ProviderTests(unittest.TestCase):
    def provider(self, *events, attempts=3):
        sleeps = []
        events = list(events)

        def opener(request, timeout):
            self.assertEqual(timeout, 60.0)
            self.requests.append(json.loads(request.data))
            event = events.pop(0)
            if isinstance(event, BaseException):
                raise event
            return Response(json.dumps(event).encode())
        self.requests = []
        settings = LLMSettings(model="gw-model", max_attempts=attempts)
        return OpenAICompatibleProvider("https://gateway.invalid/v1/", "secret", settings,
                                        sleep=sleeps.append, opener=opener), sleeps

    def ok(self, content='{"attributes": []}'):
        return {"model": "gw-model", "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3}}

    def test_retries_429_and_502_with_retry_after_then_succeeds(self):
        provider, sleeps = self.provider(http_error(429, "7"), http_error(502), self.ok())
        response = provider.complete([{"role": "user", "content": "x"}], 256)
        self.assertEqual((response.attempts, response.prompt_tokens, response.completion_tokens), (3, 11, 3))
        self.assertEqual(sleeps, [7.0, 2])
        self.assertEqual(self.requests[0]["temperature"], 0)
        self.assertNotIn("response_format", self.requests[0])

    def test_timeout_exhausts_bounded_attempts(self):
        provider, sleeps = self.provider(TimeoutError(), TimeoutError(), attempts=2)
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 256)
        self.assertEqual((caught.exception.code, caught.exception.attempts), ("llm_timeout", 2))
        self.assertEqual(len(sleeps), 1)

    def test_auth_and_client_errors_are_not_retried(self):
        for code, reason, fatal in [(401, "llm_auth_failed", True), (400, "llm_http_error", False)]:
            provider, sleeps = self.provider(http_error(code), self.ok())
            with self.assertRaises(ProviderError) as caught:
                provider.complete([], 256)
            self.assertEqual((caught.exception.code, caught.exception.fatal, sleeps), (reason, fatal, []))

    def test_malformed_gateway_payload(self):
        provider, _ = self.provider({"choices": []})
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 256)
        self.assertEqual(caught.exception.code, "llm_malformed_response")

    def test_error_messages_never_contain_key_or_url(self):
        provider, _ = self.provider(http_error(500), http_error(500), http_error(500))
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 256)
        text = str(caught.exception) + repr(caught.exception)
        self.assertNotIn("secret", text)
        self.assertNotIn("gateway.invalid", text)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = LLMSettings(model="m", cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_warm_hit_skips_provider_and_is_reverified(self):
        provider = FakeProvider(answer(("brand", "Zorion", "Смартфон Zorion")))
        first = LLMExtractor(self.config, provider, self.settings).predict(PHONE, "same")
        warm = LLMExtractor(self.config, provider, self.settings)
        second = warm.predict(PHONE, "same")
        self.assertEqual(first, second)
        self.assertEqual((provider.calls, warm.report()["calls"], warm.report()["cache_hits"]), (1, 0, 1))

    def test_changed_text_misses_and_tampered_entry_is_still_verified(self):
        provider = FakeProvider(answer(("brand", "Zorion", "Смартфон Zorion")))
        extractor = LLMExtractor(self.config, provider, self.settings)
        extractor.predict(PHONE)
        changed = Product(PHONE.sku_id, "761", PHONE.title.replace("QX-900", "QX-901"), PHONE.description)
        self.assertNotEqual(cache_key(PHONE, ["brand", "model"], self.config, self.settings),
                            cache_key(changed, ["brand", "model"], self.config, self.settings))
        for path in Path(self.tmp.name).rglob("*.json"):
            entry = json.loads(path.read_text(encoding="utf-8"))
            entry["proposals"] = [{"attribute": "brand", "value": "Vexa", "quote": "Смартфон Vexa"}]
            path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        row = LLMExtractor(self.config, provider, self.settings).predict(PHONE)
        self.assertIn("llm_quote_not_found", attrs(row)["brand"]["reason_codes"])
        self.assertEqual(provider.calls, 1)

    def test_corrupted_entry_is_a_miss(self):
        provider = FakeProvider(answer())
        LLMExtractor(self.config, provider, self.settings).predict(PHONE)
        for path in Path(self.tmp.name).rglob("*.json"):
            path.write_text("{broken", encoding="utf-8")
        LLMExtractor(self.config, provider, self.settings).predict(PHONE)
        self.assertEqual(provider.calls, 2)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input = self.root / "input.jsonl"
        self.input.write_text(json.dumps(PHONE.as_dict(), ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, env=None):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env or {}, clear=False), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_llm_run_records_counts_without_text_or_secrets(self):
        provider = FakeProvider(answer(("brand", "Zorion", "Смартфон Zorion")))
        with patch("goodsai.llm.provider_from_env", return_value=provider):
            code, _, _ = self.run_cli("predict", "--input", str(self.input), "--output", str(self.root / "llm.jsonl"),
                                      "--llm", "--llm-model", "fake-model",
                                      env={"GOODSAI_LLM_API_KEY": "secret-key", "GOODSAI_LLM_BASE_URL": "https://gw.invalid"})
        self.assertEqual(code, 0)
        manifest_text = (self.root / "llm.manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual((manifest["llm_calls"], manifest["llm"]["accepted"]), (1, 1))
        self.assertEqual(manifest["method_counts"]["llm"], 1)
        for secret in ["secret-key", "gw.invalid", "Zorion", "Аккумулятор"]:
            self.assertNotIn(secret, manifest_text)
        code, _, _ = self.run_cli("predict", "--input", str(self.input), "--output", str(self.root / "rules.jsonl"))
        rules = json.loads((self.root / "rules.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((rules["llm_calls"], "llm" in rules), (0, False))
        self.assertNotEqual(rules["run_id"], manifest["run_id"])

    def test_llm_requires_model_name(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOODSAI_LLM_MODEL", None)
            code, _, err = self.run_cli("predict", "--input", str(self.input), "--output", str(self.root / "x.jsonl"),
                                        "--llm")
        self.assertEqual(code, 2)
        self.assertIn("--llm-model", err)

    def test_missing_key_warns_and_rules_still_written(self):
        env = {"GOODSAI_LLM_API_KEY": "", "GOODSAI_LLM_BASE_URL": ""}
        code, _, err = self.run_cli("predict", "--input", str(self.input), "--output", str(self.root / "k.jsonl"),
                                    "--llm", "--llm-model", "m", env=env)
        self.assertEqual(code, 0)
        self.assertIn("llm_missing_key", err)
        row = json.loads((self.root / "k.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(attrs(row)["storage_gb"]["value"], "256")


class ApiTests(unittest.TestCase):
    def test_api_llm_mode_is_opt_in_and_health_has_no_secrets(self):
        try:
            from fastapi.testclient import TestClient
            from goodsai.api import create_app
        except ImportError:
            self.skipTest("serve extras are not installed")
        provider = FakeProvider(answer(("brand", "Zorion", "Смартфон Zorion")))
        env = {"GOODSAI_LLM_ENABLED": "1", "GOODSAI_LLM_MODEL": "fake-model",
               "GOODSAI_LLM_API_KEY": "secret-key", "GOODSAI_LLM_BASE_URL": "https://gw.invalid"}
        with patch.dict(os.environ, env), patch("goodsai.llm.provider_from_env", return_value=provider):
            client = TestClient(create_app())
            body = PHONE.as_dict()
            row = client.post("/predict", json=body).json()
            health = client.get("/health").text
        self.assertEqual(attrs(row)["brand"]["method"], "llm")
        self.assertEqual(row["run_id"], "http-rules-llm-v0")
        self.assertNotIn("secret-key", health)
        self.assertNotIn("gw.invalid", health)
        self.assertEqual(json.loads(health)["llm"]["calls"], 1)


class SettingsTests(unittest.TestCase):
    def test_invalid_settings_are_rejected(self):
        for kwargs in [{"model": ""}, {"model": "m", "max_calls": -1}, {"model": "m", "max_attempts": 0},
                       {"model": "m", "concurrency": 0}, {"model": "m", "price_input_per_1k": float("nan")}]:
            with self.assertRaises(ValueError):
                LLMSettings(**kwargs)

    def test_cost_is_reported_only_with_prices(self):
        config = load_config()
        settings = LLMSettings(model="m", price_input_per_1k=0.5, price_output_per_1k=1.5)
        extractor = LLMExtractor(config, FakeProvider(answer()), settings)
        extractor.predict(PHONE)
        report = extractor.report()
        self.assertEqual(report["cost_status"], "priced")
        self.assertAlmostEqual(report["cost"], 120 / 1000 * 0.5 + 30 / 1000 * 1.5)


if __name__ == "__main__":
    unittest.main()
