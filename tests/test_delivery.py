"""Delivery selection must protect whole families and never export EDA examples."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.release import prepare_delivery as delivery
from goodsai.contracts import Product


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "input.jsonl"
        self.splits = self.root / "split.jsonl"
        self.families = self.root / "family.jsonl"
        self.output = self.root / "selected.jsonl"
        self.products = [{"schema_version": "0.1", "sku_id": sku, "category_id": "761",
                          "title": "Invented synthetic device"} for sku in ["keep", "dev-test-family", "reserved", "validation", "dev-validation-family"]]
        assignments = [("keep", "development", "single"), ("dev-test-family", "development", "mixed-test"),
                       ("reserved", "test_reserved", "mixed-test"), ("validation", "validation", "mixed-val"),
                       ("dev-validation-family", "development", "mixed-val")]
        self.metadata = [{"sku_id": sku, "category_id": "761", "group_id": "group-" + sku,
                          "split": split} for sku, split, family in assignments]
        self.family_metadata = [row | {"family_id": family, "mixed_split_family": False}
                                for row, (_, _, family) in zip(self.metadata, assignments)]
        self.refresh()

    @staticmethod
    def write(path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def refresh(self):
        self.write(self.input, self.products)
        self.write(self.splits, self.metadata)
        self.write(self.families, self.family_metadata)

    def select(self):
        return delivery.select_development(self.input, self.splits, self.families, self.output)

    def test_whole_test_and_validation_families_are_excluded_even_if_flag_is_wrong(self):
        report = self.select()
        rows = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["sku_id"] for row in rows], ["keep"])
        self.assertEqual(report["selected_rows"], 1)
        self.assertEqual(report["excluded_rows"], 4)
        self.assertEqual(report["test_reserved_rows_excluded"], 1)
        self.assertFalse(report["test_predictions_generated"])

    def test_protected_text_is_never_passed_to_product_and_metadata_is_not_forwarded(self):
        self.products[2] = {"sku_id": "reserved", "vendor": "DO-NOT-READ-TARGET", "title": None}
        self.refresh()
        real = Product.from_dict
        calls = []

        def inspect(row):
            calls.append(row["sku_id"])
            self.assertNotIn("family_id", row)
            self.assertNotIn("group_id", row)
            self.assertNotIn("split", row)
            return real(row)

        with patch.object(delivery.Product, "from_dict", side_effect=inspect):
            self.select()
        self.assertEqual(calls, ["keep"])
        self.assertNotIn("DO-NOT-READ-TARGET", self.output.read_text(encoding="utf-8"))

    def test_unknown_or_duplicate_sku_fails_instead_of_being_silently_predicted(self):
        self.products.append({"schema_version": "0.1", "sku_id": "unknown", "category_id": "761", "title": "Invented"})
        self.refresh()
        with self.assertRaisesRegex(ValueError, "absent from metadata"):
            self.select()

    def test_split_disagreement_fails_before_selection(self):
        self.family_metadata[0]["split"] = "test_reserved"
        self.refresh()
        with self.assertRaisesRegex(ValueError, "assignments differ"):
            self.select()
        self.assertFalse(self.output.exists())

    def test_new_output_never_overwrites_previous_selection(self):
        self.select()
        old = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.select()
        self.assertEqual(old, self.output.read_bytes())

    @staticmethod
    def eda_fixture():
        catalog = {name: 3 for name in ["n_rows", "unique_ids", "vendors", "models", "sellers", "primary_categories",
                   "min_param_count", "max_param_count", "missing_vendor", "missing_model", "missing_title"]}
        catalog["param_count_quantiles"] = [1, 2, 3]
        profile = {"rows": 3, "issues": {"duplicate_param_names_rows": 1},
                   "attribute_examples_local_only": {"private": "DO-NOT-EXPORT-EXAMPLES"},
                   "seller_counts": {"PRIVATE-SELLER-ID": 3}}
        joins = {"catalog": [catalog], "catalog_description_join": [{key: 3 for key in
                  ["catalog_rows", "matched_catalog_rows", "equal_titles", "differing_titles"]}]}
        parquet = {"descriptions": [{key: 3 for key in ["n_rows", "unique_ids", "null_descriptions", "blank_descriptions",
                   "html_rows", "min_desc_length", "max_desc_length"]}]}
        preparation = {"rows": 3, "counts": {cat: {key: 1 for key in ["rows", "with_description", "title_only", "title_mismatch"]}
                       for cat in ["761", "482"]}}
        return profile, joins, parquet, preparation

    def test_eda_export_is_numeric_allowlist_without_examples_or_seller_ids(self):
        profile, joins, parquet, prep = self.eda_fixture()
        result = delivery.safe_eda(profile, joins, parquet, prep)
        text = json.dumps(result)
        self.assertNotIn("DO-NOT-EXPORT", text)
        self.assertNotIn("PRIVATE-SELLER", text)
        self.assertEqual(result["catalog"]["n_rows"], 3)
        md = delivery.render_eda(result, {"source_rows": 3, "selected_rows": 1, "excluded_rows": 2,
                                         "excluded_reasons": {"non_development_split": 2}}, {}, "2026-10-19")
        self.assertNotIn("546069", md)
        self.assertNotIn("DO-NOT-EXPORT", md)

    def test_invalid_eda_counter_and_row_disagreement_are_rejected(self):
        args = list(self.eda_fixture())
        args[1]["catalog"][0]["n_rows"] = "three"
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            delivery.safe_eda(*args)
        args = list(self.eda_fixture())
        args[0]["rows"] = 4
        with self.assertRaisesRegex(ValueError, "row counts differ"):
            delivery.safe_eda(*args)

    def test_metadata_missing_family_is_rejected(self):
        del self.family_metadata[0]["family_id"]
        self.refresh()
        with self.assertRaisesRegex(ValueError, "family identity"):
            self.select()


if __name__ == "__main__":
    unittest.main()
