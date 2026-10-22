"""Scoped runtime pilot, not a claim of independent real-data precision."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goodsai.config import load_config, validate_config
from goodsai.contracts import Product, validate_prediction
from goodsai.composition import build_runtime
from goodsai.data import read_predictions
from goodsai.policy import policy_for_settings
from goodsai.storage_acceptance import (metadata, apply_policy, AUDIT_LOWER, AUDITED_POLICIES, POLICY_VERSION,
                                        effective_cell_policies)
from goodsai.verify import Extractor
from scripts.research.storage_pilot import pilot_config, compare, reassess
from scripts.research.storage_shadow import select_reason


def attributes(row):
    return {a["attribute"]: a for a in row["attributes"]}


PHONE = Product("invented", "761", "Смартфон Samsung Demo X82 8/256GB черный")
ROOT = Path(__file__).resolve().parents[1]


class StorageAcceptanceTests(unittest.TestCase):
    def test_default_97_and_99_change_only_scoped_decision(self):
        baseline = Extractor(load_config()).predict(PHONE)
        pilot = Extractor(pilot_config()).predict(PHONE)
        strict = Extractor(pilot_config(.99)).predict(PHONE)
        self.assertEqual(baseline, strict)
        a = attributes(pilot)["storage_gb"]
        self.assertEqual((a["decision"], a["confidence"], a["confidence_kind"]), ("auto_accept", .8, "heuristic"))
        a["decision"] = "review"
        self.assertEqual(baseline, pilot)

    def test_both_previously_audited_forms_and_exact_raw_html_evidence(self):
        for p in [PHONE, Product("context", "761", "Смартфон Demo", "Встроенная память 256 GB."),
                  Product("html", "761", "Смартфон Demo", "<p>Встроенная память <b>256 GB</b>.</p>")]:
            before = Extractor(load_config()).predict(p)
            self.assertIsNone(select_reason(p, before, load_config()))
            after = Extractor(pilot_config()).predict(p)
            a = attributes(after)["storage_gb"]
            self.assertEqual(a["decision"], "auto_accept")
            e = a["evidence"]
            self.assertEqual(getattr(p, e["field"])[e["start"]:e["end"]], e["text"])
            self.assertEqual(a["evidence"], attributes(before)["storage_gb"]["evidence"])

    def test_accessories_wrong_category_missing_role_bad_units_negations_and_conflicts(self):
        products = [
            Product("case", "761", "Чехол для смартфона Demo 8/256GB"),
            Product("watch", "761", "Смартфон часы Demo 8/256GB"),
            Product("kettle", "482", "Чайник Demo 8/256GB"),
            Product("unknown", "9999", "Смартфон Demo 8/256GB"),
            Product("missing", "761", "Смартфон Demo 256 GB"),
            Product("units", "761", "Смартфон Demo 8/256G"),
            Product("negation", "761", "Смартфон Demo", "Встроенная память не 256 GB."),
            Product("storage-conflict", "761", "Смартфон Demo 8/256GB", "Встроенная память 128 GB."),
            Product("ram-conflict", "761", "Смартфон Demo 8/256GB", "Оперативная память 12 GB."),
            Product("no-marker", "761", "Samsung Demo 8/256GB"),
        ]
        for p in products:
            with self.subTest(case=p.sku_id):
                row = Extractor(pilot_config()).predict(p)
                self.assertNotIn("auto_accept", [a["decision"] for a in row["attributes"]])

    def test_bare_flag_and_invalid_policy_are_rejected(self):
        c = load_config()
        c["runtime"]["auto_accept_enabled"] = True
        with self.assertRaises(ValueError):
            validate_config(c)
        for target in [.96, True, None, "0.97", float("nan"), float("inf"), 1.01]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                pilot_config(target)
        for change in [{"policy_version": "unknown"}, {"extra": True}, {"target_precision": .9}]:
            c = pilot_config()
            c["runtime"]["auto_accept"].update(change)
            with self.assertRaises(ValueError):
                validate_config(c)

    def test_modified_rules_dictionary_or_category_cannot_reuse_audit(self):
        for key, change in [("rule_scores", {"memory_pair": .99}), ("numeric_bounds", {"storage_gb": [1, 1024]}),
                            ("brands", {"Invented": ["Invented"]}), ("category_profiles", {"761": "kettle"})]:
            c = pilot_config()
            c[key].update(change)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(c)

    def test_switch_off_restores_review_and_policy_snapshot_is_defensive(self):
        c = pilot_config()
        c["runtime"]["auto_accept_enabled"] = False
        self.assertEqual(Extractor(c).predict(PHONE), Extractor(load_config()).predict(PHONE))
        self.assertFalse(metadata(c)["active"])
        policy = policy_for_settings(pilot_config())
        runtime = build_runtime(pilot_config(), policy)
        policy["decisions"]["auto_accept"]["target_precision"] = .99
        self.assertEqual(attributes(runtime.predictor.predict(PHONE))["storage_gb"]["decision"], "auto_accept")

    def test_unauthorized_auto_accept_and_forged_value_or_evidence_are_rejected(self):
        row = Extractor(pilot_config()).predict(PHONE)
        with self.assertRaises(ValueError):
            validate_prediction(row, load_config(), PHONE)
        with self.assertRaises(ValueError):
            validate_prediction(row, pilot_config(.99), PHONE)
        changes = [{"value": "128"}, {"unit": "TB"}, {"rule_id": "memory.invented"},
                   {"method": "llm"}, {"reason_codes": ["conflicting_evidence"]},
                   {"evidence": {"field": "title", "start": 0, "end": 3, "text": "bad"}}]
        for change in changes:
            bad = deepcopy(row)
            attributes(bad)["storage_gb"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_prediction(bad, pilot_config(), PHONE)
        bad = deepcopy(row)
        attributes(bad)["ram_gb"]["decision"] = "auto_accept"
        with self.assertRaises(ValueError):
            validate_prediction(bad, pilot_config(), PHONE)

    def test_llm_candidate_never_auto_accepts(self):
        row = Extractor(load_config()).predict(PHONE)
        a = attributes(row)["storage_gb"]
        a.update(method="llm", rule_id="llm.fake")
        apply_policy(row, PHONE, pilot_config())
        self.assertEqual(a["decision"], "review")

    def test_runtime_audit_constants_match_immutable_report(self):
        report = json.loads((ROOT / "reports/storage_shadow_20261022.json").read_text(encoding="utf-8"))
        state = metadata(pilot_config())
        self.assertEqual(AUDIT_LOWER, report["human_audit"]["exploratory_one_sided_95_lower"])
        self.assertEqual(state["answers_sha256"], report["verification"]["answers_sha256"])
        self.assertEqual(state["audit_total"], report["human_audit"]["sample_size"])
        self.assertTrue(state["target_chosen_after_audit"])
        self.assertFalse(state["independent_reference"])

    def test_cli_comparison_preserves_values_and_repeats_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "input.jsonl"
            path.write_text(json.dumps(PHONE.as_dict()) + "\n", encoding="utf-8")
            result = compare(path, root / "comparison")
            self.assertEqual(result["accepted_pairs"], 1)
            self.assertTrue(result["repeat_predictions_identical"])
            self.assertEqual(result["decision_counts"]["pilot"]["auto_accept"], 1)
            with self.assertRaises(ValueError):
                compare(path, root / "comparison")

    def test_profile_command_generates_complete_config_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            cmd = [sys.executable, "-m", "goodsai.storage_acceptance", "--output", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(load_config(path), pilot_config())
            previous = path.read_bytes()
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(path.read_bytes(), previous)

    def test_reassessment_rejects_unconfirmed_or_other_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audit = root / "audit"
            audit.mkdir()
            # A sealed package is mandatory even if somebody writes plausible metrics.
            (audit / "human.metrics.json").write_text('{}', encoding="utf-8")
            with self.assertRaises((ValueError, FileNotFoundError)):
                reassess(audit, root / "out")

    def test_silver_metrics_keep_auto_accept_separate_from_review(self):
        from test_storage_shadow import fixture
        from goodsai.data import read_jsonl
        from goodsai.silver_evaluate import evaluate_rows
        with tempfile.TemporaryDirectory() as folder:
            bundle = fixture(Path(folder))
            inputs, refs, metas = [list(read_jsonl(bundle / name)) for name in
                                   ("input.jsonl", "reference.jsonl", "metadata.jsonl")]
            config = pilot_config()
            predictions = [Extractor(config).predict(Product.from_dict(r)) for r in inputs]
            report, _, _ = evaluate_rows(inputs, refs, metas, predictions, config, repeats=100)
            storage = report["per_attribute"]["storage_gb"]
            self.assertEqual(storage["auto_accept"], 3)
            self.assertEqual(storage.get("review", 0), 0)
            self.assertEqual(storage["fp"], 1)  # A catalog mismatch remains visible.
            self.assertIsNone(report["independent_precision"])


SERVICE_DEPS = all(importlib.util.find_spec(n) for n in ("fastapi", "httpx", "uvicorn"))
if SERVICE_DEPS:
    from goodsai.api import create_app
    from httpx import ASGITransport, AsyncClient


KETTLE = Product("kettle-ok", "482", "Чайник Demo 1.7 л 2200 Вт белый")


class CategoryPolicyMatrixTests(unittest.TestCase):
    """CONF-007: every configured category x attribute has a policy; default off."""

    def test_default_matrix_covers_every_category_attribute_and_is_off(self):
        config = load_config()
        self.assertIs(config["runtime"]["auto_accept_enabled"], False)
        cells = config["runtime"]["auto_accept_policies"]
        self.assertEqual({k: list(v) for k, v in cells.items()}, config["categories"])
        bound = {(c, a) for c, row in cells.items() for a, p in row.items() if p != "review"}
        self.assertEqual(bound, set(AUDITED_POLICIES))
        self.assertEqual(policy_for_settings(config)["decisions"]["auto_accept_policies"], cells)
        for product in (PHONE, KETTLE):
            row = Extractor(config).predict(product)
            self.assertNotIn("auto_accept", [a["decision"] for a in row["attributes"]])

    def test_unaudited_cells_and_malformed_matrix_cannot_be_enabled(self):
        config = load_config()
        for category, attributes in config["categories"].items():
            for attribute in attributes:
                if (category, attribute) in AUDITED_POLICIES:
                    continue
                for profile in (load_config(), pilot_config()):
                    profile["runtime"]["auto_accept_policies"][category][attribute] = POLICY_VERSION
                    with self.subTest(cell=(category, attribute)), self.assertRaises(ValueError):
                        validate_config(profile)
        for bad in [None, [], {"761": None}, {"761": ["storage_gb"]}, {"761": {"storage_gb": "storage-pilot-99"}},
                    {"761": {"storage_gb": True}}, {"761": {"storage_gb": None}}, {"9999": {"storage_gb": POLICY_VERSION}},
                    {"761": {"storge_gb": POLICY_VERSION}}, {"482": {"storage_gb": POLICY_VERSION}}]:
            profile = pilot_config()
            profile["runtime"]["auto_accept_policies"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_config(profile)

    def test_flag_without_bound_cell_fails_and_review_cell_disables_scope(self):
        profile = pilot_config()
        profile["runtime"]["auto_accept_policies"]["761"]["storage_gb"] = "review"
        with self.assertRaises(ValueError):
            validate_config(profile)
        profile["runtime"]["auto_accept_enabled"] = False
        profile = validate_config(profile)
        self.assertEqual(metadata(profile)["reason"], "disabled")
        self.assertEqual(Extractor(profile).predict(PHONE), Extractor(load_config()).predict(PHONE))

    def test_old_profile_without_section_and_explicit_matrix_behave_identically(self):
        old = pilot_config()
        del old["runtime"]["auto_accept_policies"]
        old = validate_config(old)
        self.assertNotIn("auto_accept_policies", old["runtime"])
        self.assertEqual(effective_cell_policies(old), effective_cell_policies(pilot_config()))
        for product in (PHONE, KETTLE):
            self.assertEqual(Extractor(old).predict(product), Extractor(pilot_config()).predict(product))
        row = Extractor(pilot_config()).predict(PHONE)
        decisions = {a["attribute"]: a["decision"] for a in row["attributes"]}
        self.assertEqual([k for k, v in decisions.items() if v == "auto_accept"], ["storage_gb"])
        self.assertEqual(validate_config(pilot_config()), pilot_config())

    def test_added_category_is_review_in_effective_view(self):
        profile = load_config()
        profile["categories"]["invented"] = ["brand", "color"]
        profile["category_profiles"]["invented"] = "kettle"
        profile = validate_config(profile)
        self.assertEqual(effective_cell_policies(profile)["invented"], {"brand": "review", "color": "review"})
        self.assertEqual(validate_config(profile), profile)


@unittest.skipUnless(SERVICE_DEPS, "serve/test extras are required")
class StorageAcceptanceAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_api_and_cli_share_values_decisions_and_visible_policy(self):
        for target, decision in [(.97, "auto_accept"), (.99, "review")]:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "config.json"
                path.write_text(json.dumps(pilot_config(target)), encoding="utf-8")
                with patch.dict("os.environ", {}, clear=True):
                    app = create_app(str(path))
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post("/predict", json=PHONE.as_dict())
                    self.assertEqual(response.status_code, 200, response.text)
                    body = response.json()
                    self.assertEqual(attributes(body)["storage_gb"]["decision"], decision)
                    expected = Extractor(pilot_config(target)).predict(PHONE, body["run_id"])
                    self.assertEqual(body, expected)
                    state = (await client.get("/health")).json()["auto_accept"]
                    self.assertEqual(state["target_precision"], target)
                    self.assertEqual(state["active"], target == .97)
                    self.assertFalse(state["independent_reference"])
