"""Synthetic cases only: never copy organizer datasets into Git fixtures."""
import json
from pathlib import Path
import tempfile
import unittest

from goodsai.cli import predict
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_jsonl, write_line
from goodsai.evaluate import evaluate
from goodsai.normalize import numeric
from goodsai.verify import Extractor


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.extractor = Extractor(cls.config)

    def product(self, title="Смартфон Samsung Example", description=None, category="761", sku="test"):
        return Product.from_dict({"schema_version": "0.1", "sku_id": sku, "category_id": category,
                                  "title": title, "description": description, "seller_attributes": []})

    def attributes(self, product):
        result = self.extractor.predict(product)
        validate_prediction(result, self.config, product)
        return {a["attribute"]: a for a in result["attributes"]}

    def test_explicit_memory(self):
        for text, ram, rom in [
            ("Смартфон Samsung Test 8/256GB", "8", "256"),
            ("Смартфон Xiaomi Test 6+128GB", "6", "128"),
            ("Оперативная память 6 Гб; встроенная память 128 ГБ", "6", "128"),
            ("6 GB оперативной памяти; 128 GB встроенной памяти", "6", "128")]:
            with self.subTest(text=text):
                a = self.attributes(self.product(description=text)) if "памяти" in text or "память" in text else self.attributes(self.product(title=text))
                self.assertEqual(a["ram_gb"]["value"], ram)
                self.assertEqual(a["storage_gb"]["value"], rom)

    def test_no_model_lookup_and_no_card_memory(self):
        a = self.attributes(self.product(description="Поддержка карты памяти microSD до 512 ГБ. Частота экрана 120 Гц."))
        self.assertIsNone(a["storage_gb"]["value"])
        self.assertIsNone(a["screen_inches"]["value"])
        self.assertEqual(a["model"]["reason_codes"], ["rule_not_implemented"])

    def test_conflicting_memory_abstains(self):
        a = self.attributes(self.product(title="Смартфон Samsung Test 256GB", description="Встроенная память 128 ГБ."))
        self.assertEqual(a["storage_gb"]["decision"], "abstain")
        self.assertEqual(a["storage_gb"]["reason_codes"], ["conflicting_evidence"])

    def test_kettle_units_and_nbsp(self):
        for desc in ["Объём 1,7 л. Мощность 2 400 Вт.", "Объем 1700 мл. Мощность 2,4 кВт.",
                     "Объем 1.7 L; мощность 2\u00a0400 W."]:
            with self.subTest(desc=desc):
                a = self.attributes(self.product("Электрочайник Tefal Test", desc, "482"))
                self.assertEqual((a["capacity_l"]["value"], a["capacity_l"]["unit"]), ("1.7", "L"))
                self.assertEqual((a["power_w"]["value"], a["power_w"]["unit"]), ("2400", "W"))

    def test_negations_ranges_and_standby(self):
        for desc in ["Объем от 1.6 до 1.8 л.", "Объём 1.6–1.8 л.", "Объем не 1.7 л.",
                     "Объем заварочного чайника 0.5 л.", "Мощность в режиме ожидания 150 Вт."]:
            with self.subTest(desc=desc):
                a = self.attributes(self.product("Электрочайник Tefal Test", desc, "482"))
                self.assertIsNone(a["capacity_l"]["value"])
                self.assertIsNone(a["power_w"]["value"])

    def test_html_visible_only_and_raw_coordinates(self):
        desc = '<a href="2200W">Подробнее</a><script>Объем 2 л</script><style>.x{}</style><p>Объём <b>1,7 л</b>.</p>'
        p = self.product("Электрочайник Tefal Test", desc, "482")
        a = self.attributes(p)
        self.assertEqual(a["capacity_l"]["value"], "1.7")
        e = a["capacity_l"]["evidence"]
        self.assertEqual(desc[e["start"]:e["end"]], "1,7 л")
        self.assertIsNone(a["power_w"]["value"])

    def test_html_entities_and_split_units(self):
        p = self.product("Электрочайник Tefal Test", "Объем <b>1</b>&nbsp;700 мл. Мощность 2&#160;400 Вт.", "482")
        a = self.attributes(p)
        self.assertEqual(a["capacity_l"]["value"], "1.7")
        self.assertEqual(a["power_w"]["value"], "2400")
        for attr in ["capacity_l", "power_w"]:
            e = a[attr]["evidence"]
            self.assertEqual(p.description[e["start"]:e["end"]], e["text"])

    def test_color_scope_conflicts_and_shades(self):
        a = self.attributes(self.product("Смартфон Samsung Test Dark Blue"))
        self.assertEqual(a["color"]["value"], "темно-синий")
        a = self.attributes(self.product("Смартфон Samsung Test Blue Black"))
        self.assertEqual(a["color"]["decision"], "abstain")
        a = self.attributes(self.product(description="Кнопка красная, подсветка синяя."))
        self.assertIsNone(a["color"]["value"])
        for shade in ["темно-зеленый", "светло серый", "черно-белый"]:
            with self.subTest(shade=shade):
                self.assertIsNone(self.attributes(self.product("Смартфон Samsung Test " + shade))["color"]["value"])

    def test_brand_not_inferred_from_model(self):
        a = self.attributes(self.product("Смартфон Samsung Galaxy Example"))
        self.assertEqual(a["brand"]["value"], "Samsung")
        a = self.attributes(self.product("Смартфон iPhone Example"))
        self.assertIsNone(a["brand"]["value"])
        self.assertIsNone(self.attributes(self.product("Смартфон Galaxy Example"))["brand"]["value"])

    def test_screen_and_battery(self):
        p = self.product(description="Диагональ экрана 6,5 дюйма; аккумулятор 5 000 мАч.")
        a = self.attributes(p)
        self.assertEqual(a["screen_inches"]["value"], "6.5")
        self.assertEqual(a["battery_mah"]["value"], "5000")

    def test_forbidden_inputs_and_unknown_category(self):
        row = self.product().as_dict()
        for key in ["vendor", "model", "param", "gold", "clicks"]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                Product.from_dict(row | {key: "hidden answer"})
        with self.assertRaises(ValueError):
            Product.from_dict(row | {"seller_attributes": [{"name": "Color", "value": "red"}]})
        self.assertEqual(self.extractor.predict(self.product(category="999"))["status"], "unsupported_category")

    def test_verifier_rejects_fake_evidence(self):
        p = self.product()
        row = self.extractor.predict(p)
        row["attributes"][0]["evidence"]["start"] = 0
        with self.assertRaises(ValueError):
            validate_prediction(row, self.config, p)

    def test_numeric_bounds(self):
        self.assertEqual(numeric("capacity_l", "1,700", "L"), "1.7")
        with self.assertRaises(ValueError):
            numeric("ram_gb", "512", "GB")

    def test_cli_determinism_and_invalid_record(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "input.jsonl"
            with source.open("w", encoding="utf-8") as f:
                write_line(f, self.product().as_dict())
                write_line(f, {"sku_id": "bad", "title": 42})
            first, second = folder / "one.jsonl", folder / "two.jsonl"
            report = predict(source, first, self.config)
            predict(source, second, self.config)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(report["invalid_input_rows"], 1)
            self.assertEqual(list(read_jsonl(first))[1]["status"], "invalid_input")

    def test_manual_metrics_wrong_value_and_abstain(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            p = self.product("Электрочайник Tefal Test белый", "Объем 1.7 л. Мощность 2200 Вт.", "482")
            pred = self.extractor.predict(p)
            pred["attributes"][2]["value"] = "2"  # Simulate a wrong normalized result.
            gold = p.as_dict() | {"annotation_status": "reviewed", "label_source": "manual", "annotator": "synthetic-test",
                                  "attributes": [{"attribute": a, "status": "present", "value": value, "unit": unit}
                                                 for a, value, unit in [("brand", "Tefal", None), ("model", "Test", None),
                                                                       ("capacity_l", "1.7", "L"), ("power_w", "2200", "W"),
                                                                       ("color", "белый", None)]]}
            for a in gold["attributes"]:
                field = "title" if a["attribute"] in {"brand", "model", "color"} else "description"
                source = getattr(p, field)
                text = a["value"]
                start = source.index(text)
                a["evidence"] = {"field": field, "start": start, "end": start + len(text), "text": text}
            pp, gp = folder / "pred.jsonl", folder / "gold.jsonl"
            pp.write_text(json.dumps(pred, ensure_ascii=False) + "\n", encoding="utf-8")
            gp.write_text(json.dumps(gold, ensure_ascii=False) + "\n", encoding="utf-8")
            m = evaluate(pp, gp, self.config)["metrics"]["micro"]
            self.assertEqual((m["tp"], m["fp"], m["fn"]), (3, 1, 2))
            self.assertEqual(evaluate(pp, None, self.config)["evaluation_status"], "unavailable")
            gold["annotation_status"] = "unreviewed"
            gp.write_text(json.dumps(gold) + "\n", encoding="utf-8")
            self.assertIsNone(evaluate(pp, gp, self.config)["f1"])

    def test_evaluation_ambiguous_absent_missing_and_weak_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            p = self.product("Электрочайник Tefal Test белый", "Объем 1.7 л.", "482")
            prediction = self.extractor.predict(p)
            gold = p.as_dict() | {"annotation_status": "reviewed", "label_source": "manual", "annotator": "synthetic-test",
                                  "attributes": [{"attribute": a, "status": "absent", "value": None, "unit": None}
                                                 for a in self.config["categories"]["482"]]}
            gold["attributes"][0].update(status="present", value="Tefal")
            start = p.title.index("Tefal")
            gold["attributes"][0]["evidence"] = {"field": "title", "start": start, "end": start + 5, "text": "Tefal"}
            gold["attributes"][2].update(status="ambiguous")
            pp, gp = folder / "p.jsonl", folder / "g.jsonl"
            pp.write_text(json.dumps(prediction) + "\n", encoding="utf-8")
            gp.write_text(json.dumps(gold) + "\n", encoding="utf-8")
            r = evaluate(pp, gp, self.config)
            self.assertEqual(r["excluded_pairs"], 1)
            self.assertEqual((r["metrics"]["micro"]["tp"], r["metrics"]["micro"]["fp"]), (1, 1))
            pp.write_text("", encoding="utf-8")
            r = evaluate(pp, gp, self.config)
            self.assertEqual(r["missing_prediction_cards"], 1)
            self.assertEqual(r["metrics"]["micro"]["fn"], 1)
            gold["label_source"] = "catalog_weak_label"
            gp.write_text(json.dumps(gold) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manual"):
                evaluate(pp, gp, self.config)


if __name__ == "__main__":
    unittest.main()
