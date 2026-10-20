"""ARCH-001: real transports over replaceable stages, synthetic inputs, no network."""
import ast
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goodsai.candidate_verifier import VerifierFactory
from goodsai.category_registry import Registry
from goodsai.cli import predict
from goodsai.composition import Components, build_runtime
from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.experimental_gliner import HybridExtractor
from goodsai.llm import LLMExtractor, LLMSettings, ProviderError, ProviderResponse
from goodsai.policy import policy_for_settings, resolve_runtime_policy
from goodsai.stages import Candidate, ProviderResponse as StageResponse, STAGE_CONTRACT_VERSION
from goodsai.storage import FilePredictionSink
from goodsai.verify import Extractor

SERVICE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))
if SERVICE_DEPS:
    from fastapi.testclient import TestClient
    from goodsai.api import create_app


PRODUCT = {"schema_version": "0.1", "sku_id": "invented", "category_id": "761",
           "title": "Смартфон Zorion QX-900", "description": "Батарея 5000 мАч"}


def attributes(row):
    return {a["attribute"]: a for a in row["attributes"]}


class ModelSource:
    """A model-shaped source with no Rules, config or registry attributes."""
    def candidates(self, product):
        start = product.title.index("Zorion")
        yield Candidate("brand", "Zorion", None, "title", start, start + 6,
                        "Zorion", .6, "synthetic.model.v1")


class EmptySource:
    def candidates(self, product):
        return ()


class OfflineProvider:
    model = "synthetic-provider"
    def __init__(self, failure=False):
        self.calls = 0
        self.failure = failure

    def complete(self, messages, max_tokens, *, deadline=None, reserve_attempt=None):
        self.calls += 1
        if reserve_attempt is not None:
            reason = reserve_attempt()
            if reason:
                raise ProviderError(reason)
        if self.failure:
            raise ProviderError("llm_timeout")
        return ProviderResponse(json.dumps({"attributes": [
            {"attribute": "brand", "value": "Zorion", "quote": "Zorion"}]}), 10, 10)


class BrandRouter:
    def __init__(self):
        self.calls = 0

    def select(self, product, eligible):
        self.calls += 1
        return tuple(a for a in eligible if a == "brand")


class RecordingSink:
    def __init__(self):
        self.published = False
        self.paths = None

    @contextmanager
    def stage(self, output):
        with FilePredictionSink().stage(output) as paths:
            self.paths = paths
            yield paths
        self.published = True


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = Product.from_dict(PRODUCT)

    def enabled_policy(self):
        return resolve_runtime_policy(self.config, enabled=True, environ={}, overrides={
            "model": "synthetic-provider", "budget_ledger": str(self.root / "budget.json")})

    def batch(self, components, policy=None):
        source = self.root / "input.jsonl"
        source.write_text(json.dumps(PRODUCT, ensure_ascii=False) + "\n", encoding="utf-8")
        output = self.root / "predictions.jsonl"
        report = predict(source, output, self.config, components=components, runtime_policy=policy)
        return json.loads(output.read_text(encoding="utf-8")), report

    @unittest.skipUnless(SERVICE_DEPS, "HTTP test extras are optional")
    def test_model_source_replacement_cli_api_and_sink_without_orchestration_edits(self):
        sink = RecordingSink()
        parts = Components(source=ModelSource(), sink=sink)
        batch, report = self.batch(parts)
        with patch.dict(os.environ, {"GOODSAI_LLM_ENABLED": "0"}), TestClient(create_app(components=parts)) as client:
            response = client.post("/predict", json=PRODUCT)
            self.assertEqual(response.status_code, 200)
            http = response.json()
            health = client.get("/health").json()
        self.assertEqual(batch["attributes"], http["attributes"])
        self.assertEqual(attributes(batch)["brand"]["value"], "Zorion")
        self.assertEqual(attributes(batch)["brand"]["decision"], "review")
        self.assertEqual(attributes(batch)["model"]["decision"], "abstain")
        self.assertEqual(report["effective_config_sha256"], health["effective_config_sha256"])
        self.assertTrue(sink.published)
        self.assertIsNotNone(sink.paths)

    def test_injected_source_cannot_bypass_raw_evidence(self):
        class Broken(ModelSource):
            def candidates(self, product):
                return [replace(next(super().candidates(product)), text="invented")]
        with self.assertRaises(ValueError):
            self.batch(Components(source=Broken()))
        self.assertFalse((self.root / "predictions.jsonl").exists())

    def test_sink_failure_preserves_previous_pair(self):
        self.batch(Components())
        output = self.root / "predictions.jsonl"
        manifest = output.with_suffix(".manifest.json")
        previous = (output.read_bytes(), manifest.read_bytes())
        class FailingSink:
            @contextmanager
            def stage(self, output):
                with FilePredictionSink().stage(output) as paths:
                    yield paths
                    raise OSError("synthetic sink failure")
        with self.assertRaises(OSError):
            self.batch(Components(source=ModelSource(), sink=FailingSink()))
        self.assertEqual(previous, (output.read_bytes(), manifest.read_bytes()))

    @unittest.skipUnless(SERVICE_DEPS, "HTTP test extras are optional")
    def test_cli_and_api_use_same_router_provider_and_policy(self):
        policy = self.enabled_policy()
        first = OfflineProvider()
        second = OfflineProvider()
        config_path = self.root / "profile.json"
        config = deepcopy(self.config)
        config["runtime"]["llm"] = policy["llm"]
        config_path.write_text(json.dumps(config), encoding="utf-8")
        # Same explicit profile on both transports; process env only opts HTTP in.
        source = self.root / "input.jsonl"
        source.write_text(json.dumps(PRODUCT, ensure_ascii=False) + "\n", encoding="utf-8")
        batch_output = self.root / "profile-predictions.jsonl"
        report = predict(source, batch_output, config, runtime_policy=policy,
                         components=Components(router=BrandRouter(), provider=first))
        batch = json.loads(batch_output.read_text(encoding="utf-8"))
        with patch.dict(os.environ, {"GOODSAI_LLM_ENABLED": "1"}), TestClient(create_app(
                str(config_path), components=Components(router=BrandRouter(), provider=second))) as client:
            http = client.post("/predict", json=PRODUCT).json()
            health = client.get("/health").json()
        self.assertEqual(batch["attributes"], http["attributes"])
        self.assertEqual(report["effective_config_sha256"], health["effective_config_sha256"])
        self.assertEqual(second.calls, 1)
        self.assertEqual(report["llm"]["calls"], 1)

    def test_injected_numeric_normalizer_receives_explicit_category_and_raw_unit(self):
        calls = []
        registry = Registry(self.config)
        class Normalizer:
            def normalize(self, category_id, attribute, value, unit):
                calls.append((category_id, attribute, value, unit))
                return registry.normalize(category_id, attribute, value, unit)
        runtime = build_runtime(self.config, components=Components(normalizer=Normalizer()))
        self.assertEqual(attributes(runtime.predictor.predict(self.product))["battery_mah"]["value"], "5000")
        self.assertIn(("761", "battery_mah", "5000", "мАч"), calls)

    def test_gate_factory_shared_by_rules_and_fresh_provider(self):
        calls = []
        default = VerifierFactory(self.config)
        class Factory:
            def create(self, product):
                calls.append(product.sku_id)
                return default.create(product)
        provider = OfflineProvider()
        router = BrandRouter()
        runtime = build_runtime(self.config, self.enabled_policy(), components=Components(
            source=EmptySource(), gate_factory=Factory(), router=router, provider=provider))
        row = runtime.predictor.predict(self.product)
        self.assertEqual(attributes(row)["brand"]["value"], "Zorion")
        self.assertEqual(calls, ["invented", "invented"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(router.calls, 1)
        self.assertEqual(runtime.llm.report()["attributes_requested"], 1)

    def test_provider_offline_failure_keeps_rules_and_fixed_diagnostic(self):
        runtime = build_runtime(self.config, self.enabled_policy(), components=Components(
            router=BrandRouter(), provider=OfflineProvider(failure=True)))
        row = runtime.predictor.predict(self.product)
        self.assertEqual(attributes(row)["battery_mah"]["value"], "5000")
        self.assertIn("llm_timeout", attributes(row)["brand"]["reason_codes"])
        self.assertEqual(runtime.llm.report()["calls"], 1)

    def test_router_cannot_send_reserved_data_even_with_explicit_provider(self):
        provider, router = OfflineProvider(), BrandRouter()
        runtime = build_runtime(self.config, self.enabled_policy(), components=Components(
            router=router, provider=provider))
        row = runtime.predictor.predict(replace(self.product, source_flags=("test_reserved",)))
        self.assertEqual(provider.calls, 0)
        self.assertEqual(router.calls, 0)
        self.assertIn("llm_blocked_by_data_policy", attributes(row)["brand"]["reason_codes"])

    def test_bad_router_cannot_overwrite_rules_or_duplicate_requests(self):
        for selected in (("battery_mah",), ("brand", "brand"), ("unknown",), ["brand"], ([],), (None,)):
            class BadRouter:
                def select(self, product, eligible):
                    return selected
            provider = OfflineProvider()
            runtime = build_runtime(self.config, self.enabled_policy(), components=Components(
                router=BadRouter(), provider=provider))
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                runtime.predictor.predict(self.product)
            self.assertEqual(provider.calls, 0)

    def test_disabled_composition_never_creates_live_provider(self):
        with patch("goodsai.llm.provider_from_env", side_effect=AssertionError("live factory")):
            runtime = build_runtime(self.config)
            self.assertIsNone(runtime.llm)
            runtime.predictor.predict(self.product)
        with self.assertRaises(ValueError):
            build_runtime(self.config, components=Components(provider=OfflineProvider()))

    def test_policy_snapshot_and_configuration_are_copied_not_read_from_env(self):
        policy = policy_for_settings(self.config)
        with patch.dict(os.environ, {"GOODSAI_LLM_ENABLED": "1", "GOODSAI_LLM_MODEL": "do-not-read"}):
            runtime = build_runtime(self.config, policy)
        self.config["numeric_bounds"]["battery_mah"][1] = 10
        policy["decisions"]["auto_accept_enabled"] = True
        self.assertEqual(attributes(runtime.predictor.predict(self.product))["battery_mah"]["value"], "5000")
        self.assertFalse(runtime.policy["decisions"]["auto_accept_enabled"])

    def test_wrong_policy_version_or_decisions_fail_before_sink_or_provider(self):
        for change in ({"policy_version": "99"}, {"llm_enabled": 1},
                       {"decisions": {"auto_accept_enabled": True}}, {"unexpected": True}):
            policy = policy_for_settings(self.config) | change
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_runtime(self.config, policy)

    def test_legacy_llm_keeps_instance_stats_and_rejects_mismatched_profile(self):
        legacy = LLMExtractor(self.config, OfflineProvider(), LLMSettings(model="synthetic-provider"))
        runtime = build_runtime(self.config, legacy_llm=legacy)
        self.assertIs(runtime.predictor, legacy)
        self.assertIs(runtime.llm, legacy)
        changed = deepcopy(self.config)
        changed["numeric_bounds"]["battery_mah"][1] -= 1
        with self.assertRaises(ValueError):
            build_runtime(changed, legacy_llm=legacy)

    def test_model_adapter_accepts_predictor_without_rules_internals(self):
        config = self.config
        class PredictorOnly:
            def predict(self, product, run_id="rules-v0"):
                return Extractor(config, source=EmptySource()).predict(product, run_id)
        class Backend:
            def predict(self, text):
                return [{"label": "brand", "text": "Zorion", "start": 9, "end": 15, "score": .9}]
        hybrid = HybridExtractor(config, Backend(), rules=PredictorOnly())
        self.assertEqual(attributes(hybrid.predict(self.product))["brand"]["value"], "Zorion")

    def test_stage_version_and_provider_response_import_compatibility(self):
        self.assertEqual(STAGE_CONTRACT_VERSION, "1")
        self.assertIs(StageResponse, ProviderResponse)

    def test_runtime_import_graph_is_acyclic_without_optional_ml_imports(self):
        root = Path(importlib.import_module("goodsai").__file__).parent
        graph = {}
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            # Top-level imports only. TYPE_CHECKING and lazy provider/model imports
            # are not eager dependency edges.
            graph[path.stem] = {node.module.split(".")[1] for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("goodsai.")}
        visited, active = set(), set()
        def visit(name):
            self.assertNotIn(name, active, "eager import cycle")
            if name in visited:
                return
            active.add(name)
            for other in graph.get(name, ()):
                visit(other)
            active.remove(name)
            visited.add(name)
        for name in graph:
            visit(name)
        imports = "import goodsai.composition, goodsai.cli" + (", goodsai.api" if SERVICE_DEPS else "")
        result = subprocess.run([sys.executable, "-c", imports + "; "
            "import sys; assert 'torch' not in sys.modules; assert 'gliner' not in sys.modules"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
