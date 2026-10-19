"""Runtime config tests use invented text and temporary files; no gold/provider calls."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.cli import main, predict
from goodsai.config import POLICY_KEYS, load_config, validate_config
from goodsai.contracts import Product, validate_prediction
from goodsai.normalize import numeric
from goodsai.rules import Candidate
from goodsai.runtime import identity
from goodsai.verify import Extractor, validate_candidate

SERVICE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "uvicorn"))
if SERVICE_DEPS:
    from goodsai.api import create_app
    from httpx import ASGITransport, AsyncClient


def product(category="761", title="Смартфон Samsung Orbit X82 8/256GB черный", description=None):
    return {"schema_version": "0.1", "sku_id": "config-synthetic", "category_id": category,
            "title": title, "description": description}


def attributes(config, source=None):
    row = Extractor(config).predict(Product.from_dict(source or product()))
    return {attribute["attribute"]: attribute for attribute in row["attributes"]}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def write_config(self, root, config):
        path = root / "config.json"
        path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        return path

    def test_default_and_explicit_profile_are_independent_and_equivalent(self):
        with tempfile.TemporaryDirectory() as folder:
            explicit = load_config(self.write_config(Path(folder), self.config))
        self.assertEqual(self.config, explicit)
        self.assertEqual(attributes(self.config), attributes(explicit))
        explicit["numeric_bounds"]["storage_gb"][1] = 128
        self.assertEqual(load_config()["numeric_bounds"]["storage_gb"], [1, 4096])
        self.assertIs(self.config["runtime"]["llm_enabled"], False)
        self.assertIs(self.config["runtime"]["auto_accept_enabled"], False)

    def test_legacy_config_has_explicit_deterministic_migration(self):
        legacy = {key: value for key, value in self.config.items() if key not in POLICY_KEYS}
        with tempfile.TemporaryDirectory() as folder:
            effective = load_config(self.write_config(Path(folder), legacy))
        self.assertEqual(effective, self.config)
        self.assertEqual(attributes(effective), attributes(self.config))
        legacy["numeric_bounds"] = self.config["numeric_bounds"]
        with self.assertRaises(ValueError):
            validate_config(legacy)  # A partial v1 file is not silently migrated.

    def test_malformed_duplicate_and_non_json_numbers_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            for text in ["{", "[]", "null", '{"schema_version":"0.1","schema_version":"0.1"}',
                         '{"value":NaN}', '{"value":Infinity}', '{"value":1e999}']:
                with self.subTest(text=text), self.assertRaises(ValueError):
                    path.write_text(text, encoding="utf-8")
                    load_config(path)

    def test_unknown_missing_and_bad_nested_fields_fail(self):
        cases = []
        for section in ("numeric_bounds", "rule_scores", "rule_limits", "runtime", "category_profiles"):
            missing = deepcopy(self.config)
            del missing[section]
            cases.append(missing)
            unknown = deepcopy(self.config)
            unknown[section]["typo"] = 1
            cases.append(unknown)
        unknown = deepcopy(self.config)
        unknown["api_key"] = "must-not-be-accepted"
        cases += [unknown, self.config | {"config_version": "2"}, self.config | {"schema_version": "2"}]
        for config in cases:
            with self.subTest(config_keys=list(config)), self.assertRaises(ValueError):
                validate_config(config)

    def test_scores_bounds_and_limits_reject_wrong_types(self):
        changes = [
            ("rule_scores", "brand", True), ("rule_scores", "color", float("nan")),
            ("rule_scores", "model", float("inf")), ("rule_scores", "quantity", 1.1),
            ("rule_scores", "quantity", -0.1),
            ("numeric_bounds", "power_w", [5000, 100]),
            ("numeric_bounds", "ram_gb", [1, 1.5]),
            ("numeric_bounds", "ram_gb", [True, 128]),
            ("numeric_bounds", "power_w", [1, float("inf")]),
            ("rule_limits", "memory_role_distance_chars", 0),
            ("rule_limits", "brand_prefix_chars", True),
            ("rule_limits", "memory_pair_ram_bounds", [64, 1]),
        ]
        for section, key, value in changes:
            config = deepcopy(self.config)
            config[section][key] = value
            with self.subTest(section=section, key=key, value=value), self.assertRaises(ValueError):
                validate_config(config)
        for key in self.config["runtime"]["api"]:
            for value in (0, -1, True, "32", 1.5):
                config = deepcopy(self.config)
                config["runtime"]["api"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_config(config)

    def test_unsupported_policy_cannot_enable_llm_or_auto_accept(self):
        for flag in ("llm_enabled", "auto_accept_enabled"):
            for value in (True, 0, None, "false"):
                config = deepcopy(self.config)
                config["runtime"][flag] = value
                with self.subTest(flag=flag, value=value), self.assertRaises(ValueError):
                    Extractor(config)

    def test_category_schema_and_aliases_fail_fast(self):
        for section, value in [
            ("categories", {"761": ["brand", "brand"]}),
            ("categories", {"761": ["invented"]}),
            ("categories", {"761": []}),
            ("category_profiles", {"761": "unknown", "482": "kettle"}),
            ("brands", {"Samsung": ["Samsung"], "Other": ["samsung"]}),
            ("colors", {"черный": []}),
            ("model_brand_aliases", [1]),
            ("brand_subbrands", {"Samsung": ["unknown"]}),
            ("color_modifiers", {"typo": []}),
        ]:
            with self.subTest(section=section), self.assertRaises(ValueError):
                validate_config(self.config | {section: value})

    def test_scores_are_applied_per_rule_without_changing_values(self):
        changed = deepcopy(self.config)
        changed["rule_scores"] = {key: 0.42 for key in changed["rule_scores"]}
        before, after = attributes(self.config), attributes(changed)
        for name, previous in before.items():
            self.assertEqual(previous["value"], after[name]["value"])
            self.assertEqual(previous["evidence"], after[name]["evidence"])
            if after[name]["value"] is not None:
                self.assertEqual(after[name]["confidence"], 0.42)
                self.assertEqual(after[name]["decision"], "review")
        kettle = attributes(changed, product("482", "Чайник Bosch KX-82 1,7 л 2200 Вт"))
        self.assertEqual(kettle["power_w"]["confidence"], 0.42)
        contextual = attributes(changed, product(title="Смартфон", description="Оперативная память 8 ГБ"))
        self.assertEqual(contextual["ram_gb"]["confidence"], 0.42)

    def test_numeric_bounds_apply_to_rules_verifier_and_output(self):
        changed = deepcopy(self.config)
        changed["numeric_bounds"]["storage_gb"] = [1, 128]
        after = attributes(changed)
        self.assertIsNone(after["storage_gb"]["value"])
        self.assertEqual(after["ram_gb"]["value"], "8")
        text = "Встроенная память 256 GB"
        source = Product.from_dict(product(title=text))
        candidate = Candidate("storage_gb", "256", "GB", "title", 0, len(text), text, 0.8, "synthetic")
        with self.assertRaises(ValueError):
            validate_candidate(candidate, source, changed["categories"]["761"], changed)
        original = Extractor(self.config).predict(source)
        with self.assertRaises(ValueError):
            validate_prediction(original, changed, source)
        with self.assertRaises(ValueError):
            numeric("storage_gb", "256", "GB", changed["numeric_bounds"])
        self.assertIsNone(attributes(changed, product(title=text))["storage_gb"]["value"])

    def test_memory_pair_and_context_windows_are_effective(self):
        changed = deepcopy(self.config)
        changed["rule_limits"]["memory_pair_ram_bounds"] = [1, 4]
        self.assertIsNone(attributes(changed)["ram_gb"]["value"])
        self.assertIsNone(attributes(changed)["storage_gb"]["value"])
        changed = deepcopy(self.config)
        changed["rule_limits"]["memory_role_distance_chars"] = 1
        source = product(title="Смартфон", description="Оперативная память составляет 8 ГБ")
        self.assertEqual(attributes(self.config, source)["ram_gb"]["value"], "8")
        self.assertIsNone(attributes(changed, source)["ram_gb"]["value"])
        changed["rule_limits"]["brand_prefix_chars"] = 1
        self.assertIsNone(attributes(changed)["brand"]["value"])

    def test_existing_rule_family_can_be_reused_by_a_new_category(self):
        changed = deepcopy(self.config)
        changed["categories"]["synthetic-phone"] = ["model", "ram_gb", "storage_gb"]
        changed["category_profiles"]["synthetic-phone"] = "smartphone"
        attrs = attributes(changed, product("synthetic-phone"))
        self.assertEqual(list(attrs), ["model", "ram_gb", "storage_gb"])
        self.assertEqual(attrs["model"]["value"], "Orbit X82")
        self.assertEqual(attrs["storage_gb"]["value"], "256")
        changed["categories"]["synthetic-kettle"] = ["power_w"]
        changed["category_profiles"]["synthetic-kettle"] = "kettle"
        self.assertEqual(attributes(changed, product("synthetic-kettle", "Чайник Bosch KX-82 2200 Вт"))["power_w"]["value"], "2200")

    def test_direct_config_is_validated_and_copied(self):
        extractor = Extractor(self.config)
        self.config["rule_scores"]["brand"] = 0.1
        self.assertEqual(extractor.config["rule_scores"]["brand"], 0.85)
        with self.assertRaises(ValueError):
            Extractor(self.config | {"unknown": 1})

    def test_effective_config_hash_and_failed_cli_do_not_publish_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.jsonl"
            source.write_text(json.dumps(product()) + "\n", encoding="utf-8")
            changed = deepcopy(self.config)
            changed["rule_scores"]["brand"] = 0.5
            path = self.write_config(root, changed)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--config", str(path), "predict", "--input", str(source), "--output", str(root / "output.jsonl")]), 0)
            manifest = json.loads((root / "output.manifest.json").read_text())
            self.assertEqual(manifest["config_sha256"], identity(changed)["config_sha256"])
            self.assertNotEqual(manifest["config_sha256"], identity(self.config)["config_sha256"])
            path.write_text('{"config_version":"unsupported"}', encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--config", str(path), "predict", "--input", str(source), "--output", str(root / "bad.jsonl")]), 2)
            self.assertFalse((root / "bad.jsonl").exists())
            self.assertFalse((root / "bad.manifest.json").exists())


@unittest.skipUnless(SERVICE_DEPS, "HTTP tests require .[serve,test]")
class ConfigApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_config_matches_cli_and_overrides_body_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = load_config()
            config["rule_scores"]["brand"] = 0.51
            config["numeric_bounds"]["storage_gb"] = [1, 128]
            config["runtime"]["api"]["max_body_bytes"] = 1024
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            app = create_app(str(path))
            source = root / "input.jsonl"
            source.write_text(json.dumps(product()) + "\n", encoding="utf-8")
            predict(source, root / "prediction.jsonl", load_config(path))
            expected = json.loads((root / "prediction.jsonl").read_text())
            expected["run_id"] = "http-rules-v0"
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/predict", json=product())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), expected)
                response = await client.post("/predict", json=product(title="x" * 1100))
                self.assertEqual(response.status_code, 413)
            self.assertEqual(app.state.goodsai_config, config)

    async def test_invalid_config_fails_before_uvicorn_and_limits_are_forwarded(self):
        from goodsai.api import main as serve
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            config = load_config()
            config["runtime"]["api"].update(limit_concurrency=7, timeout_keep_alive_seconds=11)
            path.write_text(json.dumps(config), encoding="utf-8")
            with patch("sys.argv", ["goodsai.api", "--config", str(path)]), patch("uvicorn.run") as run:
                serve()
            self.assertEqual(run.call_args.kwargs["limit_concurrency"], 7)
            self.assertEqual(run.call_args.kwargs["timeout_keep_alive"], 11)
            path.write_text('{"config_version":"2"}', encoding="utf-8")
            with patch("sys.argv", ["goodsai.api", "--config", str(path)]), patch("uvicorn.run") as run, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    serve()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()
