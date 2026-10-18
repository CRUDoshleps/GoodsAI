"""Agreed M2 policies on invented cards; no catalogue rows or SKU lookup."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from goodsai.cli import predict
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_predictions
from goodsai.verify import Extractor


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.extractor = Extractor(self.config)

    def product(self, title="Samsung Nebula Q88", description=None, category="761"):
        return Product.from_dict({"schema_version": "0.1", "sku_id": "invented-policy",
                                  "category_id": category, "title": title, "description": description})

    def attributes(self, product):
        row = self.extractor.predict(product)
        validate_prediction(row, self.config, product)
        for attr in row["attributes"]:
            self.assertIn(attr["decision"], {"review", "abstain"})
            self.assertEqual(attr["confidence_kind"], "heuristic")
            if attr["evidence"]:
                e = attr["evidence"]
                self.assertEqual(getattr(product, e["field"])[e["start"]:e["end"]], e["text"])
        return {a["attribute"]: a for a in row["attributes"]}

    def test_single_capacity_does_not_imply_a_role(self):
        for capacity in ["8Gb", "32GB", "128 ГБ", "256GB", "512GB"]:
            for field in ["title", "description"]:
                with self.subTest(capacity=capacity, field=field):
                    p = self.product(**{field: "Samsung Nebula Q88 " + capacity})
                    a = self.attributes(p)
                    self.assertIsNone(a["storage_gb"]["value"])
                    self.assertIsNone(a["ram_gb"]["value"])

    def test_only_the_explicit_role_supplies_memory(self):
        a = self.attributes(self.product("Samsung Nebula Q88 512GB", "Встроенная память 128 ГБ."))
        self.assertEqual(a["storage_gb"]["value"], "128")
        self.assertEqual(a["storage_gb"]["evidence"]["field"], "description")
        for title in ["Samsung Nebula Q88 8/256GB", "Samsung Nebula Q88 8+256Gb",
                      "Samsung Nebula Q88 8GB/256GB", "Samsung Nebula Q88 8 Гб + 256 ГБ"]:
            a = self.attributes(self.product(title))
            self.assertEqual((a["ram_gb"]["value"], a["storage_gb"]["value"]), ("8", "256"))
        a = self.attributes(self.product("Samsung Nebula Q88 8+256"))
        self.assertIsNone(a["storage_gb"]["value"])
        self.assertIsNone(a["ram_gb"]["value"])

    def test_adjacent_approved_subbrand_is_separate_from_model(self):
        p = self.product("Смартфон Xiaomi Redmi Nebula Q88 5G 8/256GB")
        a = self.attributes(p)
        self.assertEqual(a["brand"]["value"], "Redmi")
        self.assertEqual(a["brand"]["evidence"]["text"], "Redmi")
        self.assertEqual(a["model"]["value"], "Nebula Q88 5G")

    def test_subbrand_is_not_inferred_or_selected_from_other_mentions(self):
        cases = [("Xiaomi Nebula Q88", "Модель похожа на Redmi", "Xiaomi"),
                 ("Xiaomi Nebula Q88 для Redmi", None, "Xiaomi"),
                 ("Xiaomi Nebula Q88; сравнение Redmi", None, "Xiaomi"),
                 ("Samsung Nebula Q88 Redmi", None, "Samsung"),
                 ("Redmi Nebula Q88", None, "Redmi"),
                 ("iPhone Nebula Q88", None, None)]
        for title, desc, brand in cases:
            with self.subTest(title=title):
                self.assertEqual(self.attributes(self.product(title, desc))["brand"]["value"], brand)

    def test_full_brand_match_and_visible_html_evidence(self):
        for title, brand in [("Чайник Galaxy Line ZX-918 белый", "Galaxy Line"),
                             ("Чайник Galaxy ZX-918 белый", "GALAXY"),
                             ("Чайник <b>Galaxy</b>&nbsp;LINE ZX-918 белый", "Galaxy Line")]:
            with self.subTest(title=title):
                a = self.attributes(self.product(title, category="482"))
                self.assertEqual(a["brand"]["value"], brand)
                self.assertEqual(a["model"]["value"], "ZX-918")
        self.assertIsNone(self.attributes(self.product("Galaxy Line Nebula Q88"))["brand"]["value"])
        a = self.attributes(self.product("Xiaomi <b>Redmi</b> Nebula Q88"))
        self.assertEqual(a["brand"]["value"], "Redmi")

    def test_added_brand_spellings_require_explicit_text(self):
        for brand in ["Sonnen", "Weissgauff", "Аксинья"]:
            with self.subTest(brand=brand):
                a = self.attributes(self.product("Чайник " + brand + " ZX-918 белый", category="482"))
                self.assertEqual(a["brand"]["value"], brand)
        self.assertIsNone(self.attributes(self.product("Чайник InventedMaker ZX-918", category="482"))["brand"]["value"])

    def test_known_shades_and_compounds_keep_their_precision(self):
        for source, value in [("глубокий синий", "глубокий синий"), ("Deep Blue", "глубокий синий"),
                              ("Ultramarine", "ультрамарин"), ("Lavender", "лавандовый"),
                              ("серо-зелёный", "серо-зеленый"), ("серебристо-голубой", "серебристо-голубой"),
                              ("Titanium Silverblue", "серебристо-голубой"),
                              ("Silver-Black", "серебристо-черный")]:
            with self.subTest(source=source):
                a = self.attributes(self.product("Samsung Nebula Q88 " + source))
                self.assertEqual(a["color"]["value"], value)
                self.assertEqual(a["color"]["evidence"]["text"], source)
        a = self.attributes(self.product(description="Корпус бронзового цвета."))
        self.assertEqual(a["color"]["value"], "бронзовый")

    def test_marketing_words_remain_in_evidence(self):
        for source, value in [("Prestige Gold", "золотой"), ("Misty Green", "зеленый"),
                              ("Black Matte", "черный")]:
            with self.subTest(source=source):
                a = self.attributes(self.product("Samsung Nebula Q88 " + source))
                self.assertEqual(a["color"]["value"], value)
                self.assertEqual(a["color"]["evidence"]["text"], source)

    def test_generic_color_does_not_resolve_two_concrete_colors(self):
        for source in ["Titanium многоцветный", "многоцветный Titanium"]:
            with self.subTest(source=source):
                a = self.attributes(self.product("Samsung Nebula Q88 " + source))
                self.assertEqual(a["color"]["value"], "титановый")
                self.assertEqual(a["color"]["evidence"]["text"], source)
        for title, desc in [("Samsung Nebula Q88 Black White многоцветный", None),
                            ("Samsung Nebula Q88 Titanium Black", None),
                            ("Samsung Nebula Q88 Black", "Цвет корпуса белый, многоцветный.")]:
            a = self.attributes(self.product(title, desc))
            self.assertEqual(a["color"]["reason_codes"], ["conflicting_evidence"])
        self.assertIsNone(self.attributes(self.product("Samsung Nebula Q88 многоцветный"))["color"]["value"])

    def test_material_unknown_shades_and_hidden_text_do_not_supply_color(self):
        for title, desc in [("Samsung Nebula Q88", "Материал корпуса Titanium."),
                            ("Samsung Nebula Q88 Titanium корпус", None),
                            ("Samsung Nebula Q88 корпус Titanium", None),
                            ("Samsung Nebula Q88", "Титановый корпус."),
                            ("Samsung Nebula Q88 Deep Green", None),
                            ("Samsung Nebula Q88 Titanium UnknownShade", None),
                            ("Samsung Nebula Q88", '<script>Цвет Ultramarine</script><b data-color="Lavender">Дисплей</b>')]:
            with self.subTest(title=title, desc=desc):
                self.assertIsNone(self.attributes(self.product(title, desc))["color"]["value"])
        a = self.attributes(self.product(description="Цвет корпуса: Titanium."))
        self.assertEqual(a["color"]["value"], "титановый")
        a = self.attributes(self.product(description="Цвет <b>глубокий</b>&nbsp;синий."))
        self.assertEqual(a["color"]["value"], "глубокий синий")
        self.assertEqual(a["color"]["evidence"]["text"], "глубокий</b>&nbsp;синий")

    def test_cli_uses_the_same_policy_as_core(self):
        products = [self.product("Xiaomi Redmi Nebula Q88 256GB Ultramarine"),
                    replace(self.product("Чайник Galaxy Line ZX-918 Deep Blue", category="482"), sku_id="invented-kettle")]
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "input.jsonl", Path(folder) / "predictions.jsonl"
            source.write_text("".join(json.dumps(p.as_dict(), ensure_ascii=False) + "\n" for p in products), encoding="utf-8")
            predict(source, target, self.config)
            for p, row in zip(products, read_predictions(target)):
                self.assertEqual(row["attributes"], self.extractor.predict(p)["attributes"])


if __name__ == "__main__":
    unittest.main()
