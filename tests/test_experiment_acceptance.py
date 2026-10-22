"""Unaudited all-fields auto_accept experiment: explicit opt-in only, values unchanged."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from goodsai.composition import build_runtime
from goodsai.config import load_config, validate_config
from goodsai.contracts import Product, validate_prediction
from goodsai.experiment_acceptance import EXPERIMENT_POLICY, apply_policy, metadata
from goodsai.policy import policy_for_settings
from goodsai.verify import Extractor

ROOT = Path(__file__).resolve().parents[1]
PHONE = Product("exp-phone", "761", 'Смартфон Samsung Galaxy A55 8/256GB 6.6" черный', "Аккумулятор 5000 мАч")
KETTLE = Product("exp-kettle", "482", "Чайник электрический Bosch TWK 1.7 л 2200 Вт белый")
CONFLICT = Product("exp-conflict", "761", "Смартфон Demo 8/256GB", "Встроенная память 128 GB.")


def experiment_config():
    config = load_config()
    for category, attributes in config["categories"].items():
        for attribute in attributes:
            config["runtime"]["auto_accept_policies"][category][attribute] = EXPERIMENT_POLICY
    config["runtime"].update(auto_accept_enabled=True, auto_accept_experiment={
        "policy_version": EXPERIMENT_POLICY, "acknowledge_unaudited": True})
    return validate_config(config)


def strip(row):
    row = deepcopy(row)
    for a in row["attributes"]:
        a.pop("decision")
    return row


class ExperimentAcceptanceTests(unittest.TestCase):
    def test_default_profile_has_no_experiment(self):
        config = load_config()
        self.assertIsNone(metadata(config))
        self.assertNotIn("auto_accept_experiment", policy_for_settings(config)["decisions"])

    def test_every_configured_field_is_active_and_only_decisions_change(self):
        config = experiment_config()
        cells = {(c, a) for c, row in metadata(config)["cells"].items() for a, v in row.items() if v["active"]}
        self.assertEqual(cells, {(c, a) for c, attrs in config["categories"].items() for a in attrs})
        self.assertEqual(len(cells), 12)
        for product in (PHONE, KETTLE):
            row = Extractor(config).predict(product)
            validate_prediction(row, config, product)
            baseline = Extractor(load_config()).predict(product)
            self.assertEqual(strip(row), strip(baseline))
            for got, base in zip(row["attributes"], baseline["attributes"]):
                expected = "auto_accept" if base["decision"] == "review" else base["decision"]
                self.assertEqual(got["decision"], expected)
        decisions = {a["attribute"]: a["decision"] for a in Extractor(config).predict(PHONE)["attributes"]}
        self.assertEqual(decisions["model"], "auto_accept")

    def test_abstain_and_conflicts_are_never_accepted(self):
        row = Extractor(experiment_config()).predict(CONFLICT)
        storage = next(a for a in row["attributes"] if a["attribute"] == "storage_gb")
        self.assertEqual((storage["decision"], storage["value"]), ("abstain", None))

    def test_requires_explicit_acknowledgement(self):
        for change in [lambda r: r.pop("auto_accept_experiment"),
                       lambda r: r["auto_accept_experiment"].update(acknowledge_unaudited=False),
                       lambda r: r["auto_accept_experiment"].update(acknowledge_unaudited="true"),
                       lambda r: r["auto_accept_experiment"].update(policy_version="all-fields-v2"),
                       lambda r: r["auto_accept_experiment"].update(extra=1)]:
            config = experiment_config()
            change(config["runtime"])
            with self.assertRaises(ValueError):
                validate_config(config)
        config = load_config()
        config["runtime"]["auto_accept_policies"]["761"]["model"] = EXPERIMENT_POLICY
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_switch_off_restores_review_and_modified_rules_are_rejected(self):
        config = experiment_config()
        config["runtime"]["auto_accept_enabled"] = False
        config = validate_config(config)
        self.assertEqual(Extractor(config).predict(PHONE), Extractor(load_config()).predict(PHONE))
        config = experiment_config()
        config["rule_scores"]["model"] = .99
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_forged_values_and_llm_candidates_are_rejected(self):
        config = experiment_config()
        row = Extractor(config).predict(PHONE)
        with self.assertRaises(ValueError):
            validate_prediction(row, load_config(), PHONE)
        for change in [{"value": "Galaxy S99"}, {"rule_id": "model.invented"}, {"method": "llm"},
                       {"reason_codes": ["conflicting_evidence"]}]:
            bad = deepcopy(row)
            next(a for a in bad["attributes"] if a["attribute"] == "model").update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_prediction(bad, config, PHONE)
        row = Extractor(load_config()).predict(PHONE)
        model = next(a for a in row["attributes"] if a["attribute"] == "model")
        model.update(method="llm", rule_id="llm.fake")
        apply_policy(row, PHONE, config)
        self.assertEqual(model["decision"], "review")

    def test_policy_snapshot_marks_experiment_unaudited(self):
        config = experiment_config()
        state = policy_for_settings(config)["decisions"]["auto_accept_experiment"]
        self.assertFalse(state["audited"])
        self.assertFalse(state["production_safe"])
        self.assertIsNone(state["evidence_threshold"])
        self.assertEqual(state["cells"]["482"]["capacity_l"]["silver_tp"], 0)
        self.assertLess(state["cells"]["761"]["model"]["silver_one_sided_lower_95"], .5)
        runtime = build_runtime(config, policy_for_settings(config))
        self.assertEqual(next(a for a in runtime.predictor.predict(KETTLE)["attributes"]
                              if a["attribute"] == "power_w")["decision"], "auto_accept")
        self.assertEqual(validate_config(config), config)

    def test_profile_command_writes_valid_profile_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "all.json"
            command = [sys.executable, "-m", "goodsai.experiment_acceptance", "--output", str(path)]
            env = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}
            result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(load_config(path), experiment_config())
            again = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=env)
            self.assertNotEqual(again.returncode, 0)


if __name__ == "__main__":
    unittest.main()
