"""CONF-003 acceptance over actual entrypoints; invented data, no real pilot."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goodsai.config import load_config
from goodsai.learn_categories import build
from goodsai.policy import policy_for_settings, policy_hash, runtime_metadata
from test_category_registry import fixtures

SERVICE_DEPS = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx"))


class RegistryAcceptanceTests(unittest.TestCase):
    def test_registry_identity_is_content_bound_and_does_not_publish_dictionary(self):
        with tempfile.TemporaryDirectory() as folder:
            config, _ = build(*fixtures(Path(folder), 3))
            meta = runtime_metadata(config, policy_for_settings(config))
            expected = {"registry_version": "1", "registry_sha256": policy_hash(config["category_registry"])}
            self.assertEqual(meta["category_registry"], expected)
            changed = deepcopy(config)
            spec = next(iter(changed["category_registry"]["categories"].values()))["attributes"]
            next(s for s in spec.values() if s["kind"] == "enum")["values"].append("стекло")
            new = runtime_metadata(changed, policy_for_settings(changed))
            self.assertNotEqual(meta["category_registry"], new["category_registry"])
            self.assertNotEqual(meta["effective_config_sha256"], new["effective_config_sha256"])
            self.assertNotIn("стекло", json.dumps(new["category_registry"]))
            reordered = json.loads(json.dumps(config, sort_keys=True))
            self.assertEqual(meta["category_registry"], runtime_metadata(reordered, policy_for_settings(reordered))["category_registry"])

    def test_default_profile_keeps_existing_metadata_and_two_categories(self):
        config = load_config()
        self.assertEqual(set(config["categories"]), {"761", "482"})
        self.assertNotIn("category_registry", runtime_metadata(config, policy_for_settings(config)))

    @unittest.skipUnless(SERVICE_DEPS, "Optional HTTP dependencies absent")
    def test_external_cli_and_api_share_three_category_profile_and_registry_identity(self):
        from fastapi.testclient import TestClient
        from goodsai.api import create_app
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config, _ = build(*fixtures(root, 3))
            profile = root / "profile.json"
            profile.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            products = [{"schema_version": "0.1", "sku_id": f"external-{i}",
                         "category_id": f"invented-category-{i}",
                         "title": "Прибор 8/128GB 10×20×30см", "description": "Материал: металл;"} for i in range(3)]
            source, target = root / "external.jsonl", root / "predictions.jsonl"
            source.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in products), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("GOODSAI_LLM_")}
            result = subprocess.run([sys.executable, "-m", "goodsai.cli", "--config", str(profile), "predict",
                                     "--input", str(source), "--output", str(target)], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            predictions = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            manifest = json.loads(target.with_suffix(".manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["category_registry"]["registry_sha256"], policy_hash(config["category_registry"]))
            self.assertEqual(manifest["llm_calls"], 0)
            with patch.dict(os.environ, env, clear=True), TestClient(create_app(str(profile))) as client:
                health = client.get("/health").json()
                self.assertEqual(health["category_registry"], manifest["category_registry"])
                self.assertEqual(health["effective_config_sha256"], manifest["effective_config_sha256"])
                self.assertNotIn("values", json.dumps(health))
                for product, expected in zip(products, predictions):
                    response = client.post("/predict", json=product)
                    self.assertEqual(response.status_code, 200)
                    actual = response.json()
                    self.assertEqual(actual["attributes"], expected["attributes"])
                    self.assertEqual(expected["run_id"], manifest["run_id"])
                    self.assertEqual(actual["schema_version"], "0.1")
                    self.assertEqual(len(actual["attributes"]), 6)
                    for attr in actual["attributes"]:
                        self.assertEqual(attr["decision"], "review")
                        evidence = attr["evidence"]
                        self.assertEqual(product[evidence["field"]][evidence["start"]:evidence["end"]], evidence["text"])
                forbidden = products[0] | {"params": [{"name": "Материал", "value": "металл"}]}
                self.assertEqual(client.post("/predict", json=forbidden).status_code, 422)
                unknown = products[0] | {"category_id": "unconfigured"}
                self.assertEqual(client.post("/predict", json=unknown).json()["status"], "unsupported_category")
                legacy = {"schema_version": "0.1", "sku_id": "legacy", "category_id": "482", "title": "Чайник Bosch 1,7 л 2200 Вт"}
                with TestClient(create_app()) as baseline:
                    self.assertEqual(client.post("/predict", json=legacy).json()["attributes"],
                                     baseline.post("/predict", json=legacy).json()["attributes"])
