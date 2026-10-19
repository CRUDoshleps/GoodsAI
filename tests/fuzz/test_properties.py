"""QA-003: bounded synthetic properties. Run explicitly; Hypothesis is an optional test dependency."""
import copy
from decimal import Decimal
from html import unescape
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from hypothesis import given, seed, settings, strategies as st

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_jsonl, write_line
from goodsai.normalize import BOUNDS, UNITS, model_name, numeric
from goodsai.text import visible_span, visible_view
from goodsai.verify import Extractor

PROFILE = os.environ.get("GOODSAI_FUZZ_PROFILE", "quick")
SEED = int(os.environ.get("GOODSAI_FUZZ_SEED", "20261019"))
settings.register_profile("quick", max_examples=300, deadline=500, database=None, print_blob=True)
settings.register_profile("nightly", max_examples=2000, deadline=1000, database=None, print_blob=True)
settings.load_profile(PROFILE)
print(f"GoodsAI fuzz: profile={PROFILE} seed={SEED} max_examples={settings.default.max_examples}", flush=True)

TEXT = st.text(max_size=160)
JSON = st.recursive(st.none() | st.booleans() | st.integers(-10**12, 10**12) | TEXT,
                    lambda child: st.lists(child, max_size=4) | st.dictionaries(TEXT, child, max_size=4), max_leaves=12)
VALID_PRODUCT = st.fixed_dictionaries({
    "schema_version": st.just("0.1"), "sku_id": TEXT.filter(lambda text: bool(text.strip())),
    "category_id": st.sampled_from(["761", "482", "unknown", None]),
    "title": TEXT.filter(lambda text: bool(text.strip())), "description": st.none() | TEXT,
    "seller_attributes": st.just([]), "source_flags": st.lists(TEXT, max_size=4),
})
CHUNKS = st.sampled_from(["Samsung", "Bosch", " ", "\n", "<b>", "</b>", "<br>", "<p>", "</p>",
                         "<script>8/256GB</script>", "<style>2200 Вт</style>", "<!--black-->", "<template>1.7л</template>",
                         "&amp;", "&nbsp;", "&#x1F600;", "&NotEqualTilde;", "&unknown;", "&lt;", "<![", "<![x]>",
                         "<![CDATA[x]]>", "<!DOCTYPE html>", "<!--", "8/256GB", "1,7 л", "2200 Вт", "черный", "\u0301", "\u202e"])
HTML = st.lists(CHUNKS | st.text(max_size=12), max_size=24).map("".join)


class FuzzProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.extractor = Extractor(cls.config)

    @seed(SEED)
    @given(JSON | VALID_PRODUCT)
    def test_product_boundary_accepts_only_roundtrippable_text_contract(self, value):
        try:
            product = Product.from_dict(value)
        except ValueError:
            return
        self.assertEqual(Product.from_dict(product.as_dict()), product)
        self.assertIsInstance(product.title, str)

    @seed(SEED)
    @given(st.sampled_from(["vendor", "model", "gold", "params", "clicks", "target"]), JSON)
    def test_target_like_fields_never_enter_product(self, key, value):
        row = {"schema_version": "0.1", "sku_id": "synthetic", "title": "Phone", key: value}
        with self.assertRaises(ValueError):
            Product.from_dict(row)

    @seed(SEED)
    @given(st.lists(st.dictionaries(TEXT, JSON, max_size=4), min_size=1, max_size=4))
    def test_jsonl_unicode_roundtrip(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.jsonl"
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    write_line(stream, row)
            self.assertEqual(list(read_jsonl(path)), rows)

    @seed(SEED)
    @given(st.text(max_size=512))
    def test_malformed_jsonl_rejects_cleanly(self, text):
        try:
            expected = [json.loads(line) for line in io.StringIO(text + "\n", newline=None)]
            valid = bool(expected) and all(isinstance(row, dict) for row in expected)
        except ValueError:
            valid = False
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.jsonl"
            path.write_text(text + "\n", encoding="utf-8")
            if valid:
                self.assertEqual(list(read_jsonl(path)), expected)
            else:
                with self.assertRaises(ValueError):
                    list(read_jsonl(path))

    @seed(SEED)
    @given(HTML)
    def test_visible_unicode_html_positions_are_original_and_monotone(self, source):
        visible, positions = visible_view(source)
        self.assertEqual(len(visible), len(positions))
        previous = (0, 0)
        for char, pos in zip(visible, positions):
            if pos is None:
                self.assertEqual(char, "\n")
                continue
            start, end = pos
            self.assertTrue(0 <= start < end <= len(source), (source, pos))
            self.assertGreaterEqual(pos, previous)
            self.assertIn(char, unescape(source[start:end]))
            previous = pos

    @seed(SEED)
    @given(HTML.filter(lambda text: bool(text.strip())), st.one_of(st.none(), HTML), st.sampled_from(["761", "482", "unknown", None]))
    def test_extraction_is_total_and_all_values_have_exact_raw_evidence(self, title, description, category):
        product = Product("synthetic-fuzz", category, title, description)
        self.assertEqual(Product.from_dict(product.as_dict()), product)
        result = self.extractor.predict(product)
        validate_prediction(result, self.config, product)
        self.assertEqual(result, self.extractor.predict(product))
        for attr in result["attributes"]:
            if attr["value"] is None:
                self.assertEqual(attr["decision"], "abstain")
                self.assertIsNone(attr["evidence"])
                self.assertTrue(attr["reason_codes"])
            else:
                e = attr["evidence"]
                self.assertEqual(getattr(product, e["field"])[e["start"]:e["end"]], e["text"])
                self.assertEqual(attr["decision"], "review")
                if attr["attribute"] == "model":
                    self.assertEqual(model_name(visible_span(getattr(product, e["field"]), e["start"], e["end"])), attr["value"])

    @seed(SEED)
    @given(st.integers(0, 20000), st.sampled_from(["ml", "мл"]), st.sampled_from([" ", "\u00a0", "\u202f"]))
    def test_capacity_conversion_bounds_and_canonical_idempotence(self, millilitres, unit, separator):
        raw = f"{millilitres:,}".replace(",", separator)
        if 100 <= millilitres <= 10000:
            result = numeric("capacity_l", raw, unit)
            self.assertEqual(Decimal(result), Decimal(millilitres) / 1000)
            self.assertEqual(numeric("capacity_l", result, "L"), result)
        else:
            with self.assertRaises(ValueError):
                numeric("capacity_l", raw, unit)

    @seed(SEED)
    @given(st.sampled_from(list(BOUNDS)), st.one_of(st.text(max_size=40), st.sampled_from(["NaN", "sNaN", "Infinity", "-Infinity", "1e999999999999999999999", "1e999999", "-1e999999", "0e99999999"])), st.booleans())
    def test_numeric_input_is_bounded_finite_or_value_error(self, attribute, raw, converted):
        unit = {"power_w": "kW", "capacity_l": "ml"}.get(attribute, UNITS[attribute]) if converted else UNITS[attribute]
        try:
            result = numeric(attribute, raw, unit)
        except ValueError:
            return
        value = Decimal(result)
        low, high = BOUNDS[attribute]
        self.assertTrue(value.is_finite())
        self.assertTrue(Decimal(str(low)) <= value <= Decimal(str(high)))
        self.assertEqual(numeric(attribute, result, UNITS[attribute]), result)

    @seed(SEED)
    @given(st.sampled_from(["schema_version", "sku_id", "category_id", "status", "attributes"]), JSON)
    def test_prediction_shape_is_valid_or_value_error(self, field, value):
        product = Product("synthetic-schema", "761", "Samsung Orbit X82 8/256GB")
        result = self.extractor.predict(product)
        result[field] = value
        try:
            validate_prediction(result, self.config, product)
        except ValueError:
            return
        self.assertEqual(result["sku_id"], product.sku_id)
        self.assertEqual(result["category_id"], product.category_id)

    @seed(SEED)
    @given(st.sampled_from(["script", "style", "template", "noscript"]), st.text(alphabet="xyz😀\u0301", max_size=32))
    def test_hidden_facts_never_supply_candidate(self, tag, prefix):
        product = Product("synthetic-hidden", "482", prefix + " Чайник", f"<{tag}>Объем 1.7 л, мощность 2200 Вт</{tag}>")
        result = self.extractor.predict(product)
        self.assertTrue(all(a["value"] is None for a in result["attributes"]))

    @seed(SEED)
    @given(st.sampled_from([None, {}, {"field": "title"}, {"field": "gold", "start": 0, "end": 1, "text": "S"},
                           {"field": "title", "start": True, "end": 2, "text": "Sa"},
                           {"field": "title", "start": -1, "end": 9999, "text": "wrong"}, [], "wrong"]),
           st.text(alphabet="😀\u0301xyz ", max_size=12))
    def test_missing_or_corrupt_evidence_never_validates(self, evidence, suffix):
        product = Product("synthetic-tamper", "761", "Samsung Orbit X82 8/256GB " + suffix)
        result = copy.deepcopy(self.extractor.predict(product))
        self.assertEqual(result["attributes"][0]["decision"], "review")
        result["attributes"][0]["evidence"] = evidence
        with self.assertRaises(ValueError):
            validate_prediction(result, self.config, product)
