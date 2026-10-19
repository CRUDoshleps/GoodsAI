"""BASE-002: original offsets, identity, unknown names and explicit bounded truncation."""
from dataclasses import asdict, replace
import unittest

from goodsai.contracts import Product, load_config
from goodsai.span_index import SpanConfig, build_span_index
from goodsai.verify import Extractor


class SpanIndexTests(unittest.TestCase):
    def product(self, title="Неизвестный Zorion QX-900", description=None):
        return Product("synthetic-span", "761", title, description)

    def test_unknown_name_is_available_without_dictionary(self):
        product = self.product()
        index = build_span_index(product)
        self.assertEqual(index.status, "available")
        self.assertIn("Zorion QX-900", {e.surface for e in index.entries})
        self.assertEqual(index, build_span_index(product))
        for entry in index.entries:
            self.assertEqual(index.resolve(entry.span_id, product), entry)
            self.assertEqual(getattr(product, entry.field)[entry.start:entry.end], entry.surface)

    def test_duplicate_quotes_have_distinct_offsets_and_ids(self):
        product = self.product("Zorion Zorion", "Zorion")
        index = build_span_index(product)
        entries = [e for e in index.entries if e.surface == "Zorion"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(len({e.span_id for e in entries}), 3)
        self.assertEqual([(e.field, e.start, e.end) for e in entries], [("title", 0, 6), ("title", 7, 13), ("description", 0, 6)])

    def test_unicode_inline_html_and_entities_keep_exact_raw_spans(self):
        product = self.product("😀 Смартфон <b>Zorion</b> QX&#45;900 e\u0301", "Ёмкость <b>5&#49;00</b> мА·ч")
        index = build_span_index(product)
        surfaces = {e.surface for e in index.entries}
        self.assertIn("Zorion</b> QX&#45;900", surfaces)
        self.assertIn("5&#49;00</b> мА·ч", surfaces)
        self.assertIn("e\u0301", surfaces)
        for entry in index.entries:
            source = getattr(product, entry.field)
            self.assertTrue(0 <= entry.start < entry.end <= len(source))
            self.assertEqual(source[entry.start:entry.end], entry.surface)

    def test_entities_are_never_partially_selected(self):
        product = self.product("&fjlig; &#x1F600; &NotEqualTilde;")
        index = build_span_index(product)
        self.assertIn("&fjlig;", {e.surface for e in index.entries})
        self.assertEqual(len([e for e in index.entries if e.surface == "&fjlig;"]), 1)

    def test_hidden_and_block_boundaries_are_not_joined(self):
        product = self.product("Zorion<script>Secret</script>QX<br>900", "<p>не 5100 mAh</p><p>2200 W</p>")
        index = build_span_index(product)
        self.assertFalse(any("Secret" in e.surface or "<br>" in e.surface or "</p><p>" in e.surface for e in index.entries))
        self.assertIn("не 5100 mAh", {e.surface for e in index.entries})
        # Negation is retained as a selectable source fragment, not interpreted as a decision.

    def test_source_config_and_null_description_change_identity(self):
        product = self.product()
        index = build_span_index(product)
        self.assertEqual(index.index_id, build_span_index(replace(product, sku_id="different", category_id="482")).index_id)
        for changed in [replace(product, title=product.title + "!"), replace(product, description="")]:
            self.assertNotEqual(index.index_id, build_span_index(changed).index_id)
            with self.assertRaises(ValueError):
                index.resolve(index.entries[0].span_id, changed)
        config = SpanConfig(max_window_tokens=2)
        other = build_span_index(product, config)
        self.assertNotEqual(index.index_id, other.index_id)
        with self.assertRaises(ValueError):
            other.resolve(other.entries[0].span_id, product)
        self.assertEqual(other.resolve(other.entries[0].span_id, product, config), other.entries[0])
        with self.assertRaises(ValueError):
            index.resolve("unknown", product)

    def test_size_count_window_and_length_limits_are_explicit(self):
        product = self.product("one two three four")
        for config, reason in [(SpanConfig(max_source_chars=3), "source_length_limit"),
                               (SpanConfig(max_spans=2), "span_count_limit"),
                               (SpanConfig(max_window_tokens=1), "window_token_limit"),
                               (SpanConfig(max_span_chars=4), "span_length_limit")]:
            with self.subTest(config=config):
                index = build_span_index(product, config)
                self.assertIn(reason, index.reason_codes)
                self.assertIn(index.status, {"truncated", "unavailable"})
                self.assertLessEqual(len(index.entries), config.max_spans)
                self.assertTrue(all(len(e.surface) <= config.max_span_chars for e in index.entries))
        self.assertEqual(build_span_index(self.product("<script>hidden</script>" )).status, "unavailable")

    def test_invalid_configuration_rejected(self):
        for key in asdict(SpanConfig()):
            for value in [0, -1, True, 1.5, "2", 10**9]:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    SpanConfig(**{key: value})

    def test_runtime_predictions_unchanged_by_index_construction(self):
        product = self.product("Samsung Orbit X82 8/256GB", "Экран 6.7 дюймов")
        extractor = Extractor(load_config())
        before = extractor.predict(product)
        build_span_index(product)
        self.assertEqual(before, extractor.predict(product))

    def test_long_input_returns_bounded_result(self):
        product = self.product("token " * 10000)
        index = build_span_index(product, SpanConfig(max_spans=50))
        self.assertEqual(len(index.entries), 50)
        self.assertIn("span_count_limit", index.reason_codes)
        unavailable = build_span_index(self.product("token " * 20000))
        self.assertEqual(unavailable.reason_codes, ("source_length_limit",))
        self.assertFalse(unavailable.entries)
