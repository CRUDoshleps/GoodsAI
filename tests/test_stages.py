"""All sources cross structural, relation and conflict checks; invented inputs only."""
from dataclasses import replace
import unittest

from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.rules import Candidate as RulesCandidate
from goodsai.stages import Candidate
from goodsai.verify import Extractor


class Source:
    def __init__(self, *candidates):
        self.items = candidates

    def candidates(self, product):
        yield from self.items


class StageTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.product = Product("invented", "761", "цвет: черный")
        self.candidate = Candidate("color", "черный", None, "title", 6, 12,
                                   "черный", 0.75, "synthetic.source.v1")

    def result(self, source, product=None):
        row = Extractor(self.config, source=source).predict(product or self.product)
        return next(a for a in row["attributes"] if a["attribute"] == "color")

    def test_legacy_candidate_import_is_the_same_contract(self):
        self.assertIs(RulesCandidate, Candidate)

    def test_source_is_verified_and_absent_attributes_abstain(self):
        self.assertEqual(self.result(Source(self.candidate))["value"], "черный")
        self.assertEqual(self.result(Source())["decision"], "abstain")

    def test_invalid_source_evidence_and_unit_fail(self):
        for change in ({"text": "другой"}, {"unit": "W"}, {"attribute": "unknown"},
                       {"score": float("nan")}, {"start": -1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.result(Source(replace(self.candidate, **change)))

    def test_source_cannot_skip_relation_guard(self):
        product = Product("invented", "761", "цвет: не черный")
        candidate = replace(self.candidate, start=9, end=15)
        result = self.result(Source(candidate), product)
        self.assertEqual(result["decision"], "abstain")
        self.assertIn("relation_negated", result["reason_codes"])

    def test_two_source_values_conflict(self):
        product = Product("invented", "761", "цвет: черный; цвет: белый")
        other = replace(self.candidate, value="белый", start=20, end=25, text="белый")
        result = self.result(Source(self.candidate, other), product)
        self.assertEqual(result["reason_codes"], ["conflicting_evidence"])


if __name__ == "__main__":
    unittest.main()
