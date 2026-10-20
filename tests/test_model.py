"""Invented fixtures for model extraction and its trust boundary."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.rules import Candidate
from goodsai.verify import Extractor, validate_candidate


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.extractor = Extractor(self.config)

    def product(self, title, description=None, category="761"):
        return Product.from_dict({"schema_version": "0.1", "sku_id": "invented",
                                  "title": title, "description": description, "category_id": category})

    def model(self, title, description=None, category="761"):
        p = self.product(title, description, category)
        result = self.extractor.predict(p)
        validate_prediction(result, self.config, p)
        m = next(a for a in result["attributes"] if a["attribute"] == "model")
        if m["value"] is not None:
            self.assertEqual(m["decision"], "review")
            self.assertEqual(m["method"], "rule")
            self.assertIsNone(m["unit"])
            e = m["evidence"]
            self.assertEqual(getattr(p, e["field"])[e["start"]:e["end"]], e["text"])
        return m

    def test_phone_name_and_significant_suffixes(self):
        for name in ["Orbit X82 Ultra", "Orbit X82 Pro 5G", "A81 LTE", "iPhone 31 Pro Max", "Series 42 Mini"]:
            with self.subTest(name=name):
                m = self.model("Восстановленный смартфон Samsung " + name + " 8/256GB черный")
                self.assertEqual(m["value"], name)
                self.assertEqual(m["evidence"]["text"], name)

    def test_explicit_quantity_and_feature_boundaries_without_memory_inference(self):
        for title, category, expected in [
            ('Чайник Bosch PX-7142 1200 мл 2400 Вт', '482', 'PX-7142'),
            ('Чайник Bosch ZX-838, 1900ml', '482', 'ZX-838'),
            ('Смартфон HONOR 7D 64GB Gold', '761', '7D'),
            ('Смартфон Apple iPhone 38 Dual SIM+eSim, 256GB', '761', 'iPhone 38'),
            ('Чайник Redmond LX721 Black Matte', '482', 'LX721'),
            ('Чайник Clatronic WKS 4928 нержавеющая сталь', '482', 'WKS 4928'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(self.model(title, category=category)['value'], expected)

    def test_full_commercial_names_and_split_alphanumeric_indices(self):
        for title, expected in [
            ('Чайник Tefal Aurora KO991188 белый', 'Aurora KO991188'),
            ('Чайник Polaris PWK 2829CA', 'PWK 2829CA'),
            ('Чайник QVC JK-HQ7291', 'JK-HQ7291'),
            ('Чайник Weissgauff WK 2728 Db Touch CoolShell', 'WK 2728 Db Touch CoolShell'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(self.model(title, category='482')['value'], expected)
        title = 'Чайник Tefal <b>Aurora</b>&nbsp;KO991188 1900 мл'
        m = self.model(title, category='482')
        self.assertEqual(m['value'], 'Aurora KO991188')
        self.assertEqual(m['evidence']['text'], 'Aurora</b>&nbsp;KO991188')

    def test_new_boundaries_do_not_admit_ambiguous_codes_or_standalone_features(self):
        for title, category in [
            ('Смартфон Samsung 5G', '761'),
            ('Смартфон Samsung 32GB', '761'),
            ('Смартфон Samsung Sample ROM 256GB', '761'),
            ('Чайник Bosch 1900ml', '482'),
            ('Чайник Bosch PX-7142 XQ-88 1900 мл', '482'),
            ('Чайник Tefal Bright Home KX-91', '482'),
            ('Чайник Unknown Maker KX-91', '482'),
            ('Чайник Bosch WK 2728 RU', '482'),
            ('Чайник Bosch WK 2728 Type', '482'),
            ('Чайник Invented KX-82 FancyLine', '482'),
            ('Смартфон Samsung Orbit X82 8/256', '761'),
        ]:
            with self.subTest(title=title):
                self.assertIsNone(self.model(title, category=category)['value'])

    def test_unknown_maker_still_requires_label_and_conflicts_still_abstain(self):
        self.assertEqual(self.model('Товар', 'Модель: QX 9827CB', '482')['value'], 'QX 9827CB')
        m = self.model('Чайник Bosch PX-7142 1200 мл', 'Модель: PX-7143;', '482')
        self.assertIsNone(m['value'])
        self.assertEqual(m['reason_codes'], ['conflicting_evidence'])

    def test_whitespace_and_html_keep_exact_raw_evidence(self):
        title = "Смартфон Samsung <b>Orbit</b>&nbsp;X82  Pro  5G 8/256GB"
        m = self.model(title)
        self.assertEqual(m["value"], "Orbit X82 Pro 5G")
        self.assertEqual(m["evidence"]["text"], "Orbit</b>&nbsp;X82  Pro  5G")
        self.assertEqual(self.model("Товар", "Модель: Nova\u00a0\u00a0Z-82; Цвет: белый")["value"], "Nova Z-82")

    def test_network_support_does_not_change_model(self):
        self.assertEqual(self.model("Смартфон Samsung Orbit X82 128GB", "Поддержка 5G.")["value"], "Orbit X82")

    def test_kettle_indices_without_vendor_lookup(self):
        for maker, name in [("Polaris", "AB-9876"), ("Invented", "KQ 8421"),
                            ("Name & Co", "PK-WH82"), ("Kitfort", "КТ-9898")]:
            with self.subTest(name=name):
                self.assertEqual(self.model("Электрочайник " + maker + " " + name, category="482")["value"], name)
        # The suffix BLK is part of the index, never evidence of the color.
        p = self.product("Электрочайник Invented PK-BLK82", category="482")
        color = next(a for a in self.extractor.predict(p)["attributes"] if a["attribute"] == "color")
        self.assertIsNone(color["value"])

    def test_adjacent_explicit_brands_are_not_part_of_phone_model(self):
        for title in ["Смартфон Xiaomi POCO Orbit X91 Pro 256GB", "Xiaomi Redmi Nova R83 5G"]:
            with self.subTest(title=title):
                m = self.model(title)
                self.assertEqual(m["value"], "Orbit X91 Pro" if "POCO" in title else "Nova R83 5G")
                self.assertNotIn("Xiaomi", m["evidence"]["text"])
        self.assertEqual(self.model("Товар", "Модель: Xiaomi POCO Orbit X91 Pro")["value"], "Orbit X91 Pro")
        self.assertEqual(self.model("Samsung Galaxy Q83 128GB")["value"], "Galaxy Q83")

    def test_kettle_series_requires_an_unambiguous_boundary(self):
        for title in ["Чайник Tefal Bright Home KX-91", "Чайник Unknown Maker KX-91"]:
            with self.subTest(title=title):
                self.assertIsNone(self.model(title, category="482")["value"])
        # An explicit label can establish that words belong to the model.
        self.assertEqual(self.model("Товар", "Модель: Bright Home KX-91", "482")["value"], "Bright Home KX-91")
        # The already approved compound brand is only a boundary, not a target.
        self.assertEqual(self.model("Чайник Galaxy LINE HX 849", category="482")["value"], "HX 849")

    def test_labelled_model_does_not_require_a_known_brand_or_index(self):
        for desc, expected in [("Модель: Aurora", "Aurora"),
                               ("Model: Samsung Orbit X82", "Orbit X82"),
                               ("Модель: XY-82; Мощность: 2000 Вт", "XY-82")]:
            with self.subTest(desc=desc):
                self.assertEqual(self.model("Товар", desc, "482")["value"], expected)

    def test_conflict_is_not_solved_by_title_priority(self):
        m = self.model("Смартфон Samsung Orbit X82", "Модель: Orbit X83")
        self.assertEqual(m["reason_codes"], ["conflicting_evidence"])
        m = self.model("Смартфон Samsung Orbit X82", "Модель: Orbit  X82")
        self.assertEqual(m["value"], "Orbit X82")
        self.assertEqual(self.model("Товар", "Модель: X82; Модель: X83")["decision"], "abstain")

    def test_unknown_boundaries_and_technical_codes_abstain(self):
        for title in ["Смартфон Samsung Orbit X82 Mysteryshade", "Смартфон Samsung Orbit X82 (TYPE-X)",
                      "Смартфон Samsung Orbit X82 / Orbit X83", "Смартфон Galaxy A81",
                      "Смартфон Samsung Orbit X82 8/256", "Смартфон Samsung 256GB",
                      "Смартфон Samsung Demo", "Смартфон Unknown Orbit X82"]:
            with self.subTest(title=title):
                self.assertIsNone(self.model(title)["value"])
        for title in ["Чайник Invented KX-82 TX-83", "Чайник Invented KX-82 FancyLine", "Чайник Invented 1.7 л"]:
            with self.subTest(title=title):
                self.assertIsNone(self.model(title, category="482")["value"])

    def test_references_negations_and_non_model_labels_abstain(self):
        for title, desc in [("Чехол для Samsung Orbit X82", None),
                            ("Смартфон Samsung Orbit X82 совместим с Orbit X83", None),
                            ("Товар", "Для устройства модель: X82"),
                            ("Товар", "Модель: X82 / X83"), ("Товар", "Модель: не X82"),
                            ("Товар", "Модель: Orbit X82 и Orbit X83"),
                            ("Товар", "Модель: KX-82 TY-83"),
                            ("Товар", "Модель: 256GB"), ("Товар", "Модель: белый"),
                            ("Товар", "Модель: восстановленный"), ("Товар", "Модель: 5G"),
                            ("Товар", "Модель: неизвестна"), ("Товар", "Модель: X82 тип TY83")]:
            with self.subTest(title=title, desc=desc):
                self.assertIsNone(self.model(title, desc)["value"])

    def test_hidden_text_cannot_supply_model(self):
        desc = '<a href="Модель: X82">Ссылка</a><script>Модель: Z99</script><p>Модель: A78</p>'
        self.assertEqual(self.model("Товар", desc)["value"], "A78")
        self.assertIsNone(self.model("Товар", '<script>Модель: X82</script>')["value"])

    def test_candidate_validation_precedes_merging(self):
        p = self.product("Смартфон Samsung Orbit X82")
        start = p.title.index("Orbit")
        good = Candidate("model", "Orbit X82", None, "title", start, len(p.title), "Orbit X82", 0.8, "test.v1")
        validate_candidate(good, p, self.config["categories"]["761"])
        bad = [replace(good, attribute="other"), replace(good, attribute=[]),
               replace(good, field="sku_id"), replace(good, field=[]),
               replace(good, start=True), replace(good, end=999), replace(good, start=-1),
               replace(good, value="Invented"), replace(good, score=True), replace(good, score=float("nan")),
               replace(good, score=float("inf")), replace(good, unit="GB"), replace(good, rule_id=""),
               replace(good, text="wrong")]
        for c in bad:
            with self.subTest(candidate=c), patch.object(self.extractor.rules, "candidates", return_value=[c]):
                with self.assertRaises(ValueError):
                    self.extractor.predict(p)

    def test_output_validator_rejects_real_span_with_another_value(self):
        p = self.product("Смартфон Samsung Orbit X82")
        result = self.extractor.predict(p)
        m = next(a for a in result["attributes"] if a["attribute"] == "model")
        m["value"] = "Orbit X83"
        with self.assertRaises(ValueError):
            validate_prediction(result, self.config, p)
        m["value"] = "Orbit X82"
        m["confidence"] = True
        with self.assertRaises(ValueError):
            validate_prediction(result, self.config, p)

    def test_raw_span_may_not_escape_its_original_html_context(self):
        for source, visible in [('<script>Orbit X82</script>', 'Orbit X82'),
                                ('Orbit<script>hidden</script> X82', 'Orbit X82')]:
            p = self.product("Товар", source)
            start = source.index("Orbit")
            end = source.index("X82") + 3
            c = Candidate("model", visible, None, "description", start, end, source[start:end], 0.8, "test.v1")
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_candidate(c, p, self.config["categories"]["761"])


if __name__ == "__main__":
    unittest.main()
