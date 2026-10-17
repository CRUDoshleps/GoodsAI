import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from goodsai.annotation import annotation_tasks
from goodsai.contracts import Product, load_config
from goodsai.data import prepare, read_jsonl, write_line


class DataTests(unittest.TestCase):
    def test_prepare_uses_text_only_and_preserves_missing_description(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            raw = folder / "raw"
            raw.mkdir()
            (raw / "skus.pkl").write_bytes(b"synthetic opaque source, must never be deserialized")
            desc = raw / "sku_desc.parquet"
            pq.write_table(pa.Table.from_pylist([{"sku_id": 1, "title": "Other title", "description": "Description"}]), desc)
            inventory = raw / ".local_inventory.json"
            inventory.write_text(json.dumps({"files": [{"file": p.name, "bytes": p.stat().st_size,
                                                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                                      for p in [raw / "skus.pkl", desc]]}), encoding="utf-8")
            catalog = folder / "projection.parquet"
            pq.write_table(pa.Table.from_pylist([
                {"sku_id": str(i), "category_ids": '["761"]' if i < 3 else '["999"]',
                 "title": f"Title {i}", "vendor": "Hidden brand", "model": "Hidden model",
                 "seller": "Synthetic seller", "params_json": "hidden targets"} for i in range(1, 4)]), catalog)
            output = folder / "processed"
            report = prepare(catalog, desc, inventory, output, load_config())
            self.assertEqual(report["rows"], 2)
            rows = list(read_jsonl(output / "pilot.jsonl"))
            self.assertEqual(rows[0]["source_flags"], ["title_mismatch"])
            self.assertIsNone(rows[1]["description"])
            self.assertEqual(rows[1]["source_flags"], ["missing_description"])
            self.assertTrue(all(not set(row).intersection({"vendor", "model", "param", "params_json"}) for row in rows))
            for row in rows:
                Product.from_dict(row)
            with self.assertRaises(ValueError):
                prepare(catalog, desc, inventory, raw / "bad-output", load_config())
            (raw / "skus.pkl").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "differs"):
                prepare(catalog, desc, inventory, output, load_config())

    def test_annotation_connected_components_and_eda_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, meta, sample = folder / "input.jsonl", folder / "meta.jsonl", folder / "eda.json"
            with source.open("w", encoding="utf-8") as inputs, meta.open("w", encoding="utf-8") as metadata:
                for i in range(200):
                    title = "Same title" if i in {0, 1} else f"Unique title {i}"
                    desc = "Same description" if i in {1, 2} else (f"Unique description {i}" if i % 2 else None)
                    p = Product(str(i), "761" if i < 100 else "482", title, desc)
                    write_line(inputs, p.as_dict())
                    write_line(metadata, {"sku_id": str(i), "vendor": "Vendor", "model": f"Model {i}"})
            sample.write_text('[{"sku_id":"0"}]', encoding="utf-8")
            report = annotation_tasks(source, meta, sample, folder / "annotation", load_config(), 4)
            splits = {r["sku_id"]: r for r in read_jsonl(folder / "annotation/split_manifest.jsonl")}
            self.assertEqual({splits[str(i)]["group_id"] for i in [0, 1, 2]}, {splits["0"]["group_id"]})
            self.assertEqual({splits[str(i)]["split"] for i in [0, 1, 2]}, {"development"})
            by_group = {}
            for row in splits.values():
                by_group.setdefault(row["group_id"], set()).add(row["split"])
            self.assertTrue(all(len(s) == 1 for s in by_group.values()))
            tasks = list(read_jsonl(folder / "annotation/tasks.jsonl"))
            self.assertEqual(report["tasks"], 16)
            self.assertTrue(all(r["annotation_status"] == "unreviewed" for r in tasks))
            self.assertTrue(all(a["status"] == "unreviewed" for r in tasks for a in r["attributes"]))


if __name__ == "__main__":
    unittest.main()
