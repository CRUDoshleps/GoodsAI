"""Regression checks for the research-only sparse pickle reader, synthetic data."""
import io
import pickle
import pickletools
import unittest

from profile_catalog import CatalogReader


def reader_for(value, callback):
    data = pickle.dumps(value, protocol=4)
    refs = {arg for op, arg, _ in pickletools.genops(data)
            if op.name in {"GET", "BINGET", "LONG_BINGET"}}
    return CatalogReader(io.BytesIO(data), refs, callback)


class CatalogReaderTests(unittest.TestCase):
    def test_matches_standard_pickle_across_list_batches(self):
        offers = [{"@id": str(i), "categories": {"categoryId": "761"},
                   "name": f"Synthetic item {i}",
                   "param": [{"@name": "Color", "#text": "Black"}]}
                  for i in range(2001)]
        categories = [{"@id": "761", "#text": "Synthetic category"}]
        source = {"categories": categories, "offers": offers}
        received = []
        remainder = reader_for(source, received.append).load()
        self.assertEqual(received, offers)
        self.assertEqual(remainder, {"categories": categories, "offers": []})

    def test_rejects_shared_mutable_objects(self):
        shared = []
        with self.assertRaisesRegex(ValueError, "mutable"):
            reader_for([shared, shared], lambda _: None).load()

    def test_rejects_global_object_construction(self):
        with self.assertRaisesRegex(ValueError, "forbidden"):
            reader_for(ValueError("synthetic"), lambda _: None).load()


if __name__ == "__main__":
    unittest.main()
