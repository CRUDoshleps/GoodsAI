"""Minimal synthetic regressions from QA-003, independent of Hypothesis availability."""
import copy
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_jsonl
from goodsai.normalize import numeric
from goodsai.text import VisibleText, visible_view
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

    def test_unknown_marked_sections_keep_facts_hidden_nodes_and_raw_offsets(self):
        for declaration in ('<![x]>', '<![x Мощность 9999 Вт]>', '<![0]>'):
            with self.subTest(declaration=declaration):
                description = ('😀\n<template>Мощность 9999 Вт</template>'
                               + declaration + '<b>Мощность&nbsp;2200 Вт</b>')
                product = Product('synthetic-marked', '482', 'Чайник Bosch KX-82', description)
                result = Extractor(self.config).predict(product)
                validate_prediction(result, self.config, product)
                power = next(a for a in result['attributes'] if a['attribute'] == 'power_w')
                self.assertEqual(power['value'], '2200')
                evidence = power['evidence']
                self.assertEqual(description[evidence['start']:evidence['end']], evidence['text'])
                self.assertNotIn('9999', visible_view(description)[0])
        result = Extractor(self.config).predict(Product('synthetic-marked-only', '761', '<![x]>'))
        self.assertTrue(all(a['decision'] == 'abstain' for a in result['attributes']))

    def test_legacy_marked_section_assertion_is_local_and_interrupts_propagate(self):
        parser = VisibleText('<![x]>')
        parser.rawdata = parser.source
        def legacy_assertion(*args):
            parser.updatepos(0, 3)
            raise AssertionError("unknown status keyword 'x' in marked section")
        with patch.object(HTMLParser, 'parse_marked_section',
                          side_effect=legacy_assertion):
            self.assertEqual(parser.parse_marked_section(0), len(parser.source))
        self.assertEqual(parser.parts, [])
        self.assertEqual(parser.getpos(), (1, 0))
        for interruption in (KeyboardInterrupt, SystemExit):
            with patch.object(HTMLParser, 'parse_marked_section', side_effect=interruption), \
                    self.assertRaises(interruption):
                parser.parse_marked_section(0)

    def test_malformed_unclosed_declarations_preserve_position_map(self):
        for source in ('<![0', '<![<script>8/256GB</script>', '😀\n&nbsp;<![0'):
            with self.subTest(source=source):
                text, positions = visible_view(source)
                self.assertEqual(len(text), len(positions))
                previous = (0, 0)
                for char, position in zip(text, positions):
                    if position is not None:
                        start, end = position
                        self.assertTrue(0 <= start < end <= len(source))
                        self.assertGreaterEqual(position, previous)
                        self.assertIn(char, unescape(source[start:end]))
                        previous = position

    def test_malformed_html_cli_batch_retains_rows_and_exact_evidence(self):
        rows = [self.product.as_dict(), Product('synthetic-marked-only', '761', '<![x]>').as_dict(),
                Product('synthetic-marked-fact', '482', 'Чайник', '<![x]>Мощность 2200 Вт').as_dict()]
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'input.jsonl', Path(folder) / 'predictions.jsonl'
            source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
            completed = subprocess.run([sys.executable, '-m', 'goodsai.cli', 'predict', '--input', str(source),
                                        '--output', str(output)], capture_output=True, timeout=20)
            self.assertEqual(completed.returncode, 0)
            predictions = list(read_jsonl(output))
            self.assertEqual(len(predictions), len(rows))
            for row, prediction in zip(rows, predictions):
                validate_prediction(prediction, self.config, Product.from_dict(row))
            power = next(a for a in predictions[-1]['attributes'] if a['attribute'] == 'power_w')
            self.assertEqual(power['value'], '2200')

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
