"""Adversarial synthetic examples only; no organizer cards or model calls."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.cli import predict
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.relation import RelationVerifier
from goodsai.rules import Candidate
from goodsai.verify import Extractor
from relation_fixtures import probes


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.extractor = Extractor(self.config)

    def product(self, description=None, title="Смартфон Samsung Orbit Z83", category="761"):
        return Product("synthetic-relation", category, title, description)

    def attrs(self, product):
        row = self.extractor.predict(product)
        validate_prediction(row, self.config, product)
        return {a["attribute"]: a for a in row["attributes"]}

    def candidate(self, product, quote, attribute="screen_inches", value="6.3", field="description", occurrence=0):
        source = getattr(product, field)
        start = -1
        for _ in range(occurrence + 1):
            start = source.index(quote, start + 1)
        return Candidate(attribute, value, {"screen_inches": "inch", "power_w": "W"}.get(attribute),
                         field, start, start + len(quote), quote, .8, "synthetic.provider")

    def test_compatibility_comparison_and_bundle_candidates_rejected(self):
        for text, reason in [
            ("Совместим с телефоном: экран 6,3 дюйма", "relation_foreign_entity"),
            ("Подходит для смартфона с экраном 6,3 дюйма", "relation_foreign_entity"),
            ("В отличие от другого телефона, экран 6,3 дюйма", "relation_foreign_entity"),
            ("По сравнению с другой моделью: экран 6,3 дюйма", "relation_foreign_entity"),
            ("Compatible with phone, display 6.3 inches", "relation_foreign_entity"),
            ("В комплекте второй телефон: экран 6,3 дюйма", "relation_bundle_item"),
            ("Комплектация: телефон с экраном 6,3 дюйма", "relation_bundle_item"),
            ("Другой телефон: экран 6,3 дюйма", "relation_other_object"),
        ]:
            with self.subTest(text=text):
                p = self.product(text)
                quote = "6.3 inches" if "inches" in text else "6,3 дюйма"
                self.assertEqual(RelationVerifier(p).reason(self.candidate(p, quote)), reason)
                self.assertIsNone(self.attrs(p)["screen_inches"]["value"])

    def test_accessory_title_rejects_all_candidates_including_description(self):
        for title in ["Чехол Samsung черный 8/256GB", "Кабель Samsung черный",
                      "Защитное стекло для смартфона Samsung 6,3 дюйма", "Case Samsung Black",
                      "Черный чехол Samsung", "Transparent case Samsung"]:
            with self.subTest(title=title):
                p = self.product("Экран 6,3 дюйма, аккумулятор 4300 мАч", title)
                attrs = self.attrs(p)
                self.assertTrue(all(a["value"] is None for a in attrs.values()))
                self.assertEqual(attrs["screen_inches"]["reason_codes"], ["relation_accessory_product"])

    def test_accessory_and_external_battery_are_not_main_product(self):
        for desc, attr in [
            ("Чехол имеет цвет корпуса черный", "color"),
            ("Цвет черный у чехла", "color"),
            ("Внешний аккумулятор имеет емкость 4300 мАч", "battery_mah"),
            ("Подставка имеет мощность 2100 Вт", "power_w"),
            ("Упаковка имеет объем 2 л", "capacity_l"),
        ]:
            with self.subTest(desc=desc):
                p = self.product(desc, category="482" if attr in {"power_w", "capacity_l"} else "761")
                self.assertIsNone(self.attrs(p)[attr]["value"])

    def test_negation_shared_interface_even_if_generator_does_not_filter(self):
        for desc in ["Нет экрана диагональю 6,3 дюйма", "Без экрана размером 6,3 дюйма",
                     "Экран 6,3 дюйма не предусмотрен", "Not screen size 6,3 дюйма"]:
            with self.subTest(desc=desc):
                p = self.product(desc)
                c = self.candidate(p, "6,3 дюйма")
                with patch.object(self.extractor.rules, "candidates", return_value=[c]):
                    a = self.attrs(p)["screen_inches"]
                self.assertIsNone(a["value"])
                self.assertEqual(a["reason_codes"], ["relation_negated"])

    def test_true_main_facts_survive_scope_boundaries_and_unrelated_negation(self):
        for desc in [
            "Чехол красный. Экран 6,3 дюйма.",
            "В комплекте кабель; экран 6,3 дюйма.",
            "Совместим с зарядкой, но экран 6,3 дюйма.",
            "Чехол черный, этот смартфон имеет экран 6,3 дюйма.",
            "Без кабеля, экран 6,3 дюйма.",
            "Без подзарядки работает долго, экран 6,3 дюйма.",
            "Не только экран 6,3 дюйма, но и хороший звук.",
            "Цвет не указан. Экран 6,3 дюйма.",
        ]:
            with self.subTest(desc=desc):
                p = self.product(desc)
                c = self.candidate(p, "6,3 дюйма")
                self.assertIsNone(RelationVerifier(p).reason(c))

    def test_repeated_quote_and_positive_candidate_after_rejection(self):
        p = self.product("Другой телефон: экран 6,3 дюйма. Экран 6,3 дюйма.")
        a = self.attrs(p)["screen_inches"]
        self.assertEqual(a["value"], "6.3")
        self.assertEqual(a["evidence"]["start"], p.description.rindex("6,3 дюйма"))

    def test_foreign_value_does_not_create_false_conflict(self):
        p = self.product("Экран 6,3 дюйма. Совместим с телефоном: экран 5,1 дюйма.")
        self.assertEqual(self.attrs(p)["screen_inches"]["value"], "6.3")

    def test_two_primary_values_still_conflict_across_title_and_description(self):
        p = self.product("Экран 5,1 дюйма.", title="Samsung Orbit 6,3 дюйма")
        a = self.attrs(p)["screen_inches"]
        self.assertEqual(a["reason_codes"], ["conflicting_evidence"])
        self.assertIsNone(a["value"])

    def test_raw_unicode_html_entities_and_hidden_text(self):
        p = self.product('😀 <p>Совместим с телефоном: экран <b>6,3</b>&nbsp;дюйма</p>'
                         '<p>Экран <b>5,1</b>&nbsp;дюйма</p><script>Экран 9 дюймов</script>')
        a = self.attrs(p)["screen_inches"]
        self.assertEqual(a["value"], "5.1")
        e = a["evidence"]
        self.assertEqual(p.description[e["start"]:e["end"]], e["text"])
        hidden = self.candidate(p, "9 дюймов", value="9")
        self.assertEqual(RelationVerifier(p).reason(hidden), "relation_nonvisible_evidence")

    def test_structural_error_still_fails_before_relation_filter(self):
        p = self.product("Совместим с телефоном: экран 6,3 дюйма")
        bad = replace(self.candidate(p, "6,3 дюйма"), text="fabricated")
        with patch.object(self.extractor.rules, "candidates", return_value=[bad]):
            with self.assertRaisesRegex(ValueError, "evidence"):
                self.extractor.predict(p)

    def test_limits_do_not_scan_entire_document_per_candidate(self):
        p = self.product("Совместим с телефоном " + "текст " * 10000 + "экран 6,3 дюйма")
        self.assertIsNone(RelationVerifier(p).reason(self.candidate(p, "6,3 дюйма")))

    def test_cli_uses_same_guard(self):
        p = self.product("В комплекте телефон: экран 6,3 дюйма")
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.jsonl", Path(directory) / "output.jsonl"
            source.write_text(json.dumps(p.as_dict()) + "\n", encoding="utf-8")
            predict(source, output, self.config)
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["attributes"], self.extractor.predict(p)["attributes"])

    def test_targeted_false_accepts_and_true_facts_before_after(self):
        scores = {}
        for variant in ("before", "after"):
            false_accepts = true_facts = 0
            for p, expected in probes():
                if variant == "before":
                    with patch.object(RelationVerifier, "reason", return_value=None):
                        got = self.attrs(p)["screen_inches"]["value"]
                else:
                    got = self.attrs(p)["screen_inches"]["value"]
                false_accepts += expected is None and got is not None
                true_facts += expected is not None and got == expected
            scores[variant] = (false_accepts, true_facts)
        # Two negatives were already handled by the original numeric rules.
        self.assertEqual(scores, {"before": (8, 10), "after": (0, 10)})
