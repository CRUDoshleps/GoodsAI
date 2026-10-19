"""Synthetic candidate-set evaluation counts misses under truncation, never independent model quality."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.research.check_span_index import measure
from goodsai.span_index import SpanConfig

FIXTURES = Path(__file__).parent / "fixtures/span_index"


class SpanMeasurementTests(unittest.TestCase):
    def test_frozen_synthetic_offsets_resources_and_safe_aggregate_report(self):
        report = measure(FIXTURES / "products.jsonl", FIXTURES / "reference.json")
        self.assertEqual((report["rows"], report["reference_spans"], report["matched_spans"]), (3, 6, 6))
        self.assertEqual(report["candidate_set_recall"], 1)
        self.assertFalse(report["independent_quality"])
        self.assertGreater(report["peak_traced_python_bytes"], 0)
        self.assertGreater(report["build_seconds_with_tracemalloc"], 0)
        self.assertNotIn("Zorion", json.dumps(report))
        self.assertNotIn("span-unknown", json.dumps(report))

    def test_truncation_and_unavailable_spans_stay_in_denominator(self):
        report = measure(FIXTURES / "products.jsonl", FIXTURES / "reference.json", SpanConfig(max_spans=1))
        self.assertEqual(report["reference_spans"], 6)
        self.assertLess(report["matched_spans"], 6)
        report = measure(FIXTURES / "products.jsonl", FIXTURES / "reference.json", SpanConfig(max_source_chars=1))
        self.assertEqual(report["candidate_set_recall"], 0)
        self.assertEqual(report["status_counts"], {"unavailable": 3})

    def test_no_reference_means_null_recall(self):
        report = measure(FIXTURES / "products.jsonl")
        self.assertIsNone(report["candidate_set_recall"])
        self.assertIsNone(report["reference_kind"])

    def test_invalid_or_blind_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic-reference.json"
            for payload in [{"reference_kind": "blind_test", "records": []},
                            {"reference_kind": "synthetic", "records": [{"sku_id": "missing", "spans": []}]},
                            {"reference_kind": "synthetic", "records": [{"sku_id": "span-html", "spans": [{"field": "title", "start": 0, "end": 9999}]}]}]:
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    measure(FIXTURES / "products.jsonl", path)
