"""Synthetic only: noisy-reference denominators, isolation and offline gates."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from goodsai.contracts import Product, load_config
from goodsai.silver_calibration import calibrate, reliability
from goodsai.silver_evaluate import bootstrap, evaluate_rows
from goodsai.silver_prepare import assemble, labels, role, verify_bundle
from goodsai.silver_prepare import dump, write_rows
from goodsai.silver_prepare import VERSION
from goodsai.data import digest
from goodsai.silver_support import canonical, support
from goodsai.verify import Extractor


def fixture(count=1):
    config = load_config()
    products, catalog, members = [], {}, {}
    for i in range(count):
        sku = "synthetic-" + str(i)
        products.append(Product(sku, "761", "Смартфон Samsung Demo X82 черный", "Встроенная память: 256 GB. RAM: 8 GB.").as_dict())
        catalog[sku] = {"category_id": "761", "vendor": "Samsung", "model": "Demo X82", "seller": "invented-seller",
            "params": [{"@name": "Встроенная память (ROM)_search", "#text": "256", "@unit": "GB"}]}
        members[sku] = {"sku_id": sku, "category_id": "761", "family_id": "family-"+str(i), "split": "development", "quarantine_reasons": [], "family_exposed": False}
    return config, products, catalog, members


class SupportTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_numeric_units_are_explicit_and_decimal_tb(self):
        self.assertEqual(canonical("storage_gb", "1 TB", None, self.config), ("1000", "GB"))
        self.assertEqual(canonical("capacity_l", "1700", "мл", self.config), ("1.7", "L"))
        for raw, unit in [("256", None), ("256 G", None), ("256 GB", "TB")]:
            with self.assertRaises(ValueError):
                canonical("storage_gb", raw, unit, self.config)

    def test_role_is_not_guessed_from_one_gb_value(self):
        p = Product("s", "761", "Устройство 256 GB")
        self.assertEqual(support(p, "storage_gb", "256", "GB", self.config)["state"], "unknown")
        p = Product("s", "761", "RAM: 8 GB, встроенная память: 256 GB")
        self.assertEqual(support(p, "storage_gb", "256", "GB", self.config)["state"], "supported")
        self.assertEqual(support(p, "ram_gb", "8", "GB", self.config)["state"], "supported")
        self.assertNotEqual(support(p, "ram_gb", "256", "GB", self.config)["state"], "supported")

    def test_hidden_text_and_token_boundaries(self):
        p = Product("s", "761", "<script>Samsung</script> Samsungish")
        self.assertEqual(support(p, "brand", "Samsung", None, self.config)["state"], "unsupported")
        p = Product("s", "761", "<b>Samsung</b>")
        span = support(p, "brand", "Samsung", None, self.config)["evidence"]
        self.assertEqual(p.title[span["start"]:span["end"]], span["text"])

    def test_negation_and_foreign_brand_are_unknown(self):
        for text in ["для Samsung", "не Samsung", "совместим с Samsung"]:
            state = support(Product("s", "761", text), "brand", "Samsung", None, self.config)["state"]
            self.assertNotEqual(state, "supported")


class PreparationTests(unittest.TestCase):
    def test_conflicting_and_missing_labels_not_filled(self):
        config, _, catalog, _ = fixture()
        row = catalog["synthetic-0"]
        row["params"].append({"@name": "Встроенная память", "#text": "128 GB"})
        attrs = {x["attribute"]: x for x in labels(row, config)}
        self.assertEqual(attrs["storage_gb"]["status"], "conflict")
        self.assertIsNone(attrs["storage_gb"]["value"])
        self.assertEqual(attrs["ram_gb"]["status"], "unknown")

    def test_shuffle_determinism_text_only_and_unknown_input_metadata(self):
        config, products, catalog, members = fixture(8)
        a = assemble(products, catalog, members, config)
        b = assemble(reversed(products), catalog, dict(reversed(list(members.items()))), config)
        self.assertEqual(a, b)
        for row in a[0]:
            Product.from_dict(row)
            self.assertFalse(set(row) & {"vendor", "model", "seller", "params", "traffic"})
        products[0]["model"] = "target"
        with self.assertRaises(ValueError):
            assemble(products, catalog, members, config)

    def test_protected_family_and_exposed_validation_are_excluded(self):
        config, products, catalog, members = fixture(5)
        members["synthetic-0"]["split"] = "test_reserved"
        members["synthetic-1"]["family_id"] = members["synthetic-0"]["family_id"]
        members["synthetic-1"]["split"] = "test_reserved"
        members["synthetic-2"]["split"] = "validation"
        inputs, _, _, counts = assemble(products, catalog, members, config,
            protected_ids=["synthetic-0"], exposed_ids=["synthetic-2"])
        self.assertEqual({r["sku_id"] for r in inputs}, {"synthetic-3", "synthetic-4"})
        self.assertEqual(counts["excluded_new_exposure_feedback_family"], 1)

    def test_crossing_duplicates_unknown_group_and_duplicate_sku_fail(self):
        config, products, catalog, members = fixture(2)
        members["synthetic-0"]["family_id"] = members["synthetic-1"]["family_id"]
        members["synthetic-1"]["split"] = "validation"
        with self.assertRaisesRegex(ValueError, "cross_split"):
            assemble(products, catalog, members, config)
        with self.assertRaises(ValueError):
            assemble(products, catalog, members, config, exposed_ids=["missing"])
        with self.assertRaises(ValueError):
            assemble(products + products, catalog, members, config)

    def test_bundle_checksums_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/"manifest.json").write_text(json.dumps({"version":VERSION, "reference_kind":"catalog_silver", "artifacts":{"../foreign":"bad"}}))
            with self.assertRaises(ValueError):
                verify_bundle(p)

    def test_filter_buckets_only_constrain_exact_values(self):
        config, _, catalog, _ = fixture()
        row = catalog["synthetic-0"]
        row["params"] = [{"@name":"Емкость аккумулятора", "#text":"3000-5000 мАч"},
            {"@name":"Емкость аккумулятора_search", "#text":"4000", "@unit":"мАч"}]
        label = next(a for a in labels(row, config) if a["attribute"] == "battery_mah")
        self.assertEqual((label["status"],label["value"]), ("known","4000"))
        row["params"][1]["#text"] = "6000"
        self.assertEqual(next(a for a in labels(row, config) if a["attribute"] == "battery_mah")["status"], "conflict")
        row["params"].pop()
        self.assertEqual(next(a for a in labels(row, config) if a["attribute"] == "battery_mah")["status"], "unknown")


class EvaluationTests(unittest.TestCase):
    def prepared(self, count=1):
        config, products, catalog, members = fixture(count)
        inputs, refs, metas, _ = assemble(products, catalog, members, config)
        predictions = [Extractor(config).predict(Product.from_dict(p), "test") for p in inputs]
        return config, inputs, refs, metas, predictions

    def test_wrong_known_value_is_fp_and_fn_unknown_candidate_not_fp(self):
        config, inputs, refs, metas, predictions = self.prepared()
        known = {x["attribute"]: x for x in refs[0]["attributes"]}
        known["model"]["value"] = "Other model"
        report, _, _ = evaluate_rows(inputs, refs, metas, predictions, config, 100)
        count = report["agreement"]
        self.assertEqual((count["tp"], count["fp"], count["fn"]), (2, 1, 1))
        self.assertGreater(count["unassessed_candidates"], 0)
        self.assertLess(count["assessed_candidate_fraction"], 1)
        self.assertIsNone(report["traffic_agreement"])

    def test_missing_prediction_keeps_recall_denominator(self):
        config, inputs, refs, metas, _ = self.prepared()
        report, _, _ = evaluate_rows(inputs, refs, metas, [], config, 100)
        self.assertEqual(report["agreement"]["fn"], 3)
        self.assertEqual(report["missing_prediction_cards"], 1)
        self.assertEqual(report["agreement"]["requested"], 7)

    def test_evidence_and_duplicate_identity_are_verified(self):
        config, inputs, refs, metas, predictions = self.prepared()
        with self.assertRaises(ValueError):
            evaluate_rows(inputs, refs, metas, predictions + predictions, config, 100)
        predictions[0]["attributes"][0]["evidence"]["text"] = "forged"
        with self.assertRaisesRegex(ValueError, "Evidence"):
            evaluate_rows(inputs, refs, metas, predictions, config, 100)

    def test_zero_traffic_and_nonfinite_weights(self):
        config, inputs, refs, metas, predictions = self.prepared()
        metas[0]["traffic"] = 0
        report, _, _ = evaluate_rows(inputs, refs, metas, predictions, config, 100)
        self.assertIsNone(report["traffic_agreement"]["f1"])
        metas[0]["traffic"] = float("nan")
        with self.assertRaises(ValueError):
            evaluate_rows(inputs, refs, metas, predictions, config, 100)

    def test_bootstrap_is_grouped_paired_and_deterministic(self):
        groups = {str(i): Counter(tp=i%3, fp=1, fn=2) for i in range(25)}
        a = bootstrap(groups, 100)
        self.assertEqual(a, bootstrap(dict(reversed(list(groups.items()))), 100))
        delta = bootstrap(groups, 100, other=groups)
        self.assertEqual(delta["intervals"]["f1"]["lower"], 0)
        self.assertEqual(delta["intervals"]["f1"]["upper"], 0)
        self.assertEqual(bootstrap({"x":Counter(tp=1)}, 100)["status"], "insufficient_groups")


class CalibrationTests(unittest.TestCase):
    def test_no_fake_model_when_data_is_insufficient(self):
        report, model = calibrate([])
        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(model)
        self.assertEqual(report["auto_accept"], "forbidden")

    def test_reliability_matches_hand_computed_values(self):
        result = reliability([.5, .5], [0, 1])
        self.assertEqual(result["brier"], .25)
        self.assertEqual(result["ece"], 0)

    def test_group_overlap_fails_before_fit(self):
        rows=[{"family_id":"a", "role": role, "correct": True} for role in ["fit", "diagnostic"]]
        with self.assertRaisesRegex(ValueError, "family_leakage"):
            calibrate(rows)

    def test_positive_offline_fit_never_changes_runtime_or_uses_target_features(self):
        rows = []
        for role_name, count in [("fit", 240), ("calibration", 40), ("diagnostic", 40)]:
            for i in range(count):
                rows.append({"sku_id": role_name + str(i), "family_id": role_name+str(i),
                    "role": role_name, "correct": bool(i%2), "heuristic_score": .8,
                    "reason_count": 0, "attribute": "brand", "method": "rule", "evidence_field": "title"})
        report, model = calibrate(rows)
        self.assertEqual(report["status"], "offline_fitted")
        self.assertFalse(report["runtime_changed"])
        self.assertIsNone(report["threshold"])
        self.assertAlmostEqual(report["diagnostic_calibrated"]["brier"], .25, places=3)
        self.assertFalse(any(name.startswith("sku") for name in model["weights"]))


class CommandTests(unittest.TestCase):
    def test_end_to_end_repeat_candidate_and_public_privacy(self):
        from scripts.research.run_silver_evaluation import ROOT, run
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            bundle.mkdir()
            config, products, catalog, members = fixture(24)
            inputs, refs, metas, counts = assemble(products, catalog, members, config)
            write_rows(bundle / "input.jsonl", inputs)
            write_rows(bundle / "llm_screening.input.jsonl", inputs[:10])
            write_rows(bundle / "reference.jsonl", refs)
            write_rows(bundle / "metadata.jsonl", metas)
            write_rows(bundle / "train.jsonl", [])
            dump(bundle / "train.split.json", {})
            write_rows(bundle / "support_review.blank.jsonl", [])
            dump(bundle / "policy.json", {"config":config,"baseline_sha":"977c5ed"})
            manifest = {"version":VERSION, "reference_kind":"catalog_silver", "counts":counts,
                "family_groups":24, "protected_reserve_rows":0, "universe_rows":24,
                "universe_categories":1, "universe_configured_rows":24, "top30":[],
                "seller_role_crossings":1, "brand_role_crossings":1, "exposure_history":"synthetic",
                "support_review_status":"pending", "source_sha256":{},
                "artifacts":{p.name:digest(p) for p in bundle.iterdir()}}
            dump(bundle / "manifest.json", manifest)
            args = argparse.Namespace(bundle=bundle, output_dir=root/"run", repeats=100, candidate=[], candidate_config=[])
            result = run(args)
            self.assertEqual(result["cards"], 24)
            public = (args.output_dir/"run_stats.json").read_text(encoding="utf-8")
            self.assertNotIn("invented-seller", public)
            self.assertNotIn("synthetic-0", public)
            self.assertNotIn("Demo X82", public)
            with self.assertRaisesRegex(ValueError, "new_private"):
                run(args)
            # Same frozen values are a legitimate zero-delta paired comparison.
            args.candidate = ["control=" + str(args.output_dir/"predictions.jsonl")]
            args.output_dir = root/"paired"
            run(args)
            paired = json.loads((args.output_dir/"run_stats.json").read_text(encoding="utf-8"))
            self.assertEqual(paired["variants"]["control"]["paired_delta_vs_rules"]["intervals"]["f1"]["upper"], 0)
            # Changing a frozen dataset must be rejected before inference.
            (bundle/"input.jsonl").write_text("{}\n")
            args.output_dir = root/"corrupt"
            with self.assertRaisesRegex(ValueError, "artifact_hash"):
                run(args)

if __name__ == "__main__":
    unittest.main()
