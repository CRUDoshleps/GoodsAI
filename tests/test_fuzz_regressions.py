"""Minimal synthetic regressions from QA-003, independent of Hypothesis availability."""
import copy
from pathlib import Path
import tempfile
import unittest

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_jsonl
from goodsai.normalize import numeric
from goodsai.text import visible_view
from goodsai.verify import Extractor


class FuzzRegressions(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.product = Product("synthetic-regression", "761", "Samsung Orbit X82 8/256GB")
        self.prediction = Extractor(self.config).predict(self.product)

    def test_missing_or_nonobject_evidence_is_value_error(self):
        # Hypothesis 6.170.1, seed 20261019, shrunk example: evidence=None, suffix=''.
        for evidence in [None, [], "wrong", 0, {"field": []}]:
            result = copy.deepcopy(self.prediction)
            result["attributes"][0]["evidence"] = evidence
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                validate_prediction(result, self.config, self.product)

    def test_malformed_prediction_shapes_fail_as_contract_errors(self):
        for field, value in [("category_id", []), ("status", {}), ("attributes", [None]), ("attributes", ["brand"])]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_prediction(self.prediction | {field: value}, self.config, self.product)
        for row in [None, [], "wrong"]:
            with self.assertRaises(ValueError):
                validate_prediction(row, self.config, self.product)

    def test_unit_conversion_overflow_is_value_error(self):
        for raw in ["1e999999", "-1e999999"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                numeric("power_w", raw, "kW")

    def test_unicode_entities_keep_raw_coordinates(self):
        source = "😀e\u0301 <b>&NotEqualTilde;</b> &#x1F600; &nbsp;"
        visible, positions = visible_view(source)
        self.assertEqual(len(visible), len(positions))
        start = source.index("&NotEqualTilde;")
        self.assertEqual([positions[i] for i, c in enumerate(visible) if c in "≂̸"],
                         [(start, start + len("&NotEqualTilde;"))] * 2)

    def test_bounded_long_html_input_does_not_break_offsets(self):
        product = Product("synthetic-long", "482", "Чайник Bosch KX-82 1.7 л 2200 Вт",
                          "<p>" + "😀e\u0301&nbsp;" * 2000 + "</p><script>9999 Вт</script>")
        result = Extractor(self.config).predict(product)
        validate_prediction(result, self.config, product)
        power = next(a for a in result["attributes"] if a["attribute"] == "power_w")
        self.assertEqual(power["value"], "2200")

    def test_jsonl_nonobjects_empty_lines_and_broken_json_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.jsonl"
            for value in ["\n", "[]\n", "null\n", "{\n", '{}\n\n']:
                path.write_text(value, encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(ValueError):
                    list(read_jsonl(path))
