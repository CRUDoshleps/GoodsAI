"""CONF-008 trial: opt-in catalog-silver auto_accept for all 12 fields, gated by evidence; not a quality claim."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from goodsai.composition import build_runtime
from goodsai.config import load_config, validate_config
from goodsai.contracts import Product, validate_prediction
from goodsai.policy import policy_for_settings
from goodsai.storage_acceptance import AUDIT_LOWER, POLICY_VERSION
from goodsai.trial_acceptance import (DEFAULT_TARGETS, EVIDENCE, LOWER, MIN_TARGET, SOURCE, TRIAL_POLICY, apply_policy,
                                      lower_bound, metadata)
from goodsai.verify import Extractor

ROOT = Path(__file__).resolve().parents[1]
PHONE = Product("trial-phone", "761", "Смартфон Samsung Galaxy A55 8/256GB черный", "Аккумулятор 5000 мАч")
KETTLE = Product("trial-kettle", "482", "Чайник электрический Bosch TWK 1.7 л 2200 Вт белый")
TRIAL_CELLS = {(c, a) for c, row in DEFAULT_TARGETS.items() for a in row}
ACTIVE_CELLS = {("761", "ram_gb"), ("761", "battery_mah"), ("761", "color"), ("761", "brand"),
                ("482", "brand"), ("482", "color"), ("482", "power_w")}


def trial_config(targets=None, storage=True):
    config = load_config()
    targets = deepcopy(DEFAULT_TARGETS if targets is None else targets)
    for category, cells in targets.items():
        for attribute in cells:
            config["runtime"]["auto_accept_policies"][category][attribute] = TRIAL_POLICY
    config["runtime"].update(auto_accept_enabled=True,
                             auto_accept_trial={"policy_version": TRIAL_POLICY, "targets": targets})
    if storage:
        config["runtime"]["auto_accept"] = {"policy_version": POLICY_VERSION, "target_precision": .97}
    else:
        config["runtime"]["auto_accept_policies"]["761"]["storage_gb"] = "review"
    return validate_config(config)


def decisions(row):
    return {a["attribute"]: a["decision"] for a in row["attributes"]}


def without_decisions(row):
    row = deepcopy(row)
    for a in row["attributes"]:
        a.pop("decision")
    return row


class TrialAcceptanceTests(unittest.TestCase):
    def test_default_profile_has_no_trial_and_stays_review(self):
        config = load_config()
        self.assertIsNone(metadata(config))
        self.assertNotIn("auto_accept_trial", policy_for_settings(config)["decisions"])
        for product in (PHONE, KETTLE):
            self.assertNotIn("auto_accept", decisions(Extractor(config).predict(product)).values())

    def test_evidence_matches_frozen_report_and_targets_sit_below_bounds(self):
        report = json.loads((ROOT / "reports/run_stats.json").read_text(encoding="utf-8"))
        cells = report["slices"]["category_attribute"]
        config = load_config()
        all_cells = {(c, a) for c, attrs in config["categories"].items() for a in attrs}
        self.assertEqual(len(all_cells), 12)
        self.assertEqual(TRIAL_CELLS, set(EVIDENCE))
        self.assertEqual(TRIAL_CELLS | {("761", "storage_gb")}, all_cells)
        for (category, attribute), evidence in EVIDENCE.items():
            measured = cells[f"{category}:{attribute}"]
            self.assertEqual((evidence["tp"], evidence["fp"]), (measured["tp"], measured["fp"]))
            strong = LOWER[(category, attribute)] >= DEFAULT_TARGETS[category][attribute]
            self.assertEqual(strong, (category, attribute) in ACTIVE_CELLS)
            self.assertGreaterEqual(DEFAULT_TARGETS[category][attribute], MIN_TARGET)
        self.assertEqual(report["cards"], SOURCE["cards"])
        self.assertIn(SOURCE["producer"], json.dumps(report))

    def test_lower_bound_matches_exact_binomial_cases(self):
        self.assertAlmostEqual(lower_bound(145, 145), AUDIT_LOWER, places=12)
        self.assertEqual(lower_bound(0, 10), 0.)
        self.assertLess(lower_bound(90, 100), .9)
        self.assertGreater(lower_bound(1714, 1870), .9)  # large n must not overflow

    def test_all_twelve_cells_bound_but_only_strong_evidence_auto_accepts(self):
        config = trial_config()
        baseline = load_config()
        for product in (PHONE, KETTLE):
            row = Extractor(config).predict(product)
            accepted = {(product.category_id, k) for k, v in decisions(row).items() if v == "auto_accept"}
            expected = {cell for cell in ACTIVE_CELLS if cell[0] == product.category_id}
            if product is PHONE:
                expected.add(("761", "storage_gb"))
            self.assertEqual(accepted, expected)
            self.assertEqual(without_decisions(row), without_decisions(Extractor(baseline).predict(product)))
        state = metadata(config)
        reasons = {(c, a): v["reason"] for c, row in state["cells"].items() for a, v in row.items()}
        self.assertEqual({cell for cell, r in reasons.items() if r == "trial_active"}, ACTIVE_CELLS)
        self.assertEqual(reasons[("482", "capacity_l")], "no_evidence")
        for cell in [("761", "model"), ("761", "screen_inches"), ("482", "model")]:
            self.assertEqual(reasons[cell], "evidence_below_target")
        self.assertFalse(state["human_audit"])
        self.assertFalse(state["independent_reference"])
        self.assertTrue(state["target_chosen_after_results"])

    def test_trial_without_storage_pilot_and_switch_off(self):
        config = trial_config(storage=False)
        self.assertEqual(decisions(Extractor(config).predict(PHONE))["storage_gb"], "review")
        self.assertEqual(decisions(Extractor(config).predict(PHONE))["ram_gb"], "auto_accept")
        config["runtime"]["auto_accept_enabled"] = False
        config = validate_config(config)
        self.assertEqual(Extractor(config).predict(PHONE), Extractor(load_config()).predict(PHONE))
        self.assertEqual(metadata(config)["cells"]["761"]["ram_gb"]["reason"], "disabled")

    def test_target_above_evidence_keeps_review(self):
        targets = deepcopy(DEFAULT_TARGETS)
        targets["761"]["color"] = .95
        config = trial_config(targets)
        self.assertEqual(metadata(config)["cells"]["761"]["color"]["reason"], "evidence_below_target")
        row = decisions(Extractor(config).predict(PHONE))
        self.assertEqual((row["color"], row["ram_gb"]), ("review", "auto_accept"))

    def test_invalid_trial_configuration_is_rejected(self):
        bad_targets = [.84, 1.01, True, None, "0.9", float("nan")]
        for target in bad_targets:
            targets = deepcopy(DEFAULT_TARGETS)
            targets["761"]["ram_gb"] = target
            with self.subTest(target=target), self.assertRaises(ValueError):
                trial_config(targets)
        for cell in [("761", "storage_gb"), ("761", "invented"), ("9999", "brand")]:
            config = load_config()
            config["runtime"]["auto_accept_policies"].setdefault(cell[0], {})[cell[1]] = TRIAL_POLICY
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                validate_config(config)
        targets = deepcopy(DEFAULT_TARGETS)
        targets["761"]["storage_gb"] = .99  # storage belongs to the human-audited pilot only
        with self.assertRaises(ValueError):
            trial_config(targets)
        config = trial_config()
        changes = [lambda r: r["auto_accept_trial"].update(policy_version="silver-trial-v2"),
                   lambda r: r["auto_accept_trial"].update(extra=True),
                   lambda r: r["auto_accept_trial"]["targets"]["761"].pop("ram_gb"),
                   lambda r: r["auto_accept_policies"]["761"].update(ram_gb="review"),
                   lambda r: r["auto_accept_trial"]["targets"]["761"].update(storage_gb=.99),
                   lambda r: r.pop("auto_accept")]
        for index, change in enumerate(changes):
            profile = deepcopy(config)
            change(profile["runtime"])
            with self.subTest(change=index), self.assertRaises(ValueError):
                validate_config(profile)

    def test_modified_extraction_profile_cannot_reuse_evidence(self):
        config = trial_config()
        config["rule_scores"]["brand"] = .99
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_forged_or_unapproved_auto_accept_is_rejected(self):
        config = trial_config()
        row = Extractor(config).predict(PHONE)
        validate_prediction(row, config, PHONE)
        with self.assertRaises(ValueError):
            validate_prediction(row, load_config(), PHONE)
        changes = [{"value": "12"}, {"rule_id": "memory.invented"}, {"method": "llm"},
                   {"reason_codes": ["conflicting_evidence"]},
                   {"evidence": {"field": "title", "start": 0, "end": 3, "text": "Смa"}}]
        for change in changes:
            bad = deepcopy(row)
            next(a for a in bad["attributes"] if a["attribute"] == "ram_gb").update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_prediction(bad, config, PHONE)
        bad = deepcopy(row)
        next(a for a in bad["attributes"] if a["attribute"] == "model")["decision"] = "auto_accept"
        with self.assertRaises(ValueError):
            validate_prediction(bad, config, PHONE)

    def test_llm_candidate_never_auto_accepts(self):
        row = Extractor(load_config()).predict(PHONE)
        ram = next(a for a in row["attributes"] if a["attribute"] == "ram_gb")
        ram.update(method="llm", rule_id="llm.fake")
        apply_policy(row, PHONE, trial_config())
        self.assertEqual(ram["decision"], "review")

    def test_policy_snapshot_and_runtime_assembly(self):
        config = trial_config()
        policy = policy_for_settings(config)
        self.assertEqual(policy["decisions"]["auto_accept_trial"], metadata(config))
        cells = policy["decisions"]["auto_accept_policies"]
        self.assertEqual({(c, a) for c, row in cells.items() for a, p in row.items() if p == TRIAL_POLICY}, TRIAL_CELLS)
        runtime = build_runtime(config, policy)
        self.assertEqual(decisions(runtime.predictor.predict(KETTLE))["brand"], "auto_accept")
        self.assertEqual(validate_config(config), config)

    def test_profile_command_writes_valid_profile_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            for flags, storage in [([], True), (["--without-storage-pilot"], False)]:
                path = Path(folder) / f"trial-{storage}.json"
                command = [sys.executable, "-m", "goodsai.trial_acceptance", "--output", str(path), *flags]
                env = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}
                result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                profile = load_config(path)
                self.assertEqual(profile, trial_config(storage=storage))
                again = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=env)
                self.assertNotEqual(again.returncode, 0)


if __name__ == "__main__":
    unittest.main()
