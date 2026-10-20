"""Synthetic source preparation, transaction and immutable split-handoff tests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from goodsai.contracts import Product, load_config
from goodsai.data import digest, inventory_sources, prepare, read_jsonl, verify_sources, write_line
from goodsai.storage import OutputBusyError, output_lock
from scripts.research import audit_splits, prepare_dataset
from test_split_audit import fixture as split_fixture


def sources(root, *, catalog_rows=None, description_rows=None):
    raw = root / "raw"
    raw.mkdir()
    (raw / "skus.pkl").write_bytes(b"opaque synthetic file; never unpickle")
    catalog_rows = catalog_rows if catalog_rows is not None else [
        {"sku_id": "1", "category_ids": '["761"]', "title": "Телефон Ёж <b>Q77</b> 🐟",
         "vendor": "TARGET_BRAND", "model": "TARGET_MODEL", "seller": "PRIVATE_SELLER", "params_json": "TARGET_PARAMS"},
        {"sku_id": "2", "category_ids": '["482"]', "title": "Synthetic kettle K44",
         "vendor": None, "model": None, "seller": None, "params_json": None},
        {"sku_id": "3", "category_ids": '["999"]', "title": None,
         "vendor": None, "model": None, "seller": None, "params_json": None}]
    description_rows = description_rows if description_rows is not None else [
        {"sku_id": 1, "title": "Other title", "description": "<p>Экран 6,5″ &amp; 😀</p>"},
        {"sku_id": 2, "title": None, "description": "  \t"},
        {"sku_id": 77, "title": None, "description": None}]
    catalog, desc = root / "catalog.parquet", raw / "sku_desc.parquet"
    pq.write_table(pa.Table.from_pylist(catalog_rows), catalog)
    pq.write_table(pa.Table.from_pylist(description_rows), desc)
    inventory = root / "inventory.json"
    inventory_sources(raw, inventory)
    return raw, catalog, desc, inventory


class PreparationTests(unittest.TestCase):
    def test_profiles_optional_clicks_and_legacy_reference_are_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, _, _, inv = sources(root)
            report = json.loads(inv.read_text(encoding="utf-8"))
            self.assertEqual([r["file"] for r in report["files"]], ["skus.pkl", "sku_desc.parquet"])
            self.assertEqual(report["optional_files"], [{"file": "query_clicks.parquet", "present": False, "used": False}])
            with self.assertRaises(FileNotFoundError):
                inventory_sources(raw, root / "analytics.json", "analytics")
            (raw / "query_clicks.parquet").write_bytes(b"synthetic clicks")
            analytics = inventory_sources(raw, root / "analytics.json", "analytics")
            self.assertEqual(len(analytics["files"]), 3)
            # Legacy inventories lack the version/profile fields, but retain exact hashes.
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"files": analytics["files"]}), encoding="utf-8")
            second = inventory_sources(raw, root / "second.json", reference=legacy)
            self.assertEqual(second["verified_reference_sha256"], digest(legacy))
            (raw / "query_clicks.parquet").write_bytes(b"changed")
            verify_sources(raw, inv)  # optional file is not an inference input
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_sources(raw, legacy, "analytics")
            (raw / "skus.pkl").write_bytes(b"changed catalog")
            with self.assertRaisesRegex(ValueError, "differs"):
                inventory_sources(raw, root / "bad.json", reference=legacy)
            self.assertFalse((root / "bad.json").exists())

    def test_inventory_rejects_duplicates_traversal_missing_entries_and_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, _, _, inv = sources(root)
            original = inv.read_bytes()
            entries = json.loads(original)["files"]
            for rows in [entries + [entries[0]], entries[:1], [entries[0] | {"file": "../skus.pkl"}],
                         [entries[0] | {"bytes": True}, entries[1]]]:
                bad = root / "bad.json"
                bad.write_text(json.dumps({"files": rows}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    verify_sources(raw, bad)
            with self.assertRaisesRegex(ValueError, "new inventory"):
                inventory_sources(raw, inv)
            self.assertEqual(inv.read_bytes(), original)
            with self.assertRaises(ValueError):
                inventory_sources(raw, raw / "inventory.json")

    def test_prepare_is_repeatable_preserves_raw_text_and_accounts_for_every_row(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, catalog, desc, inv = sources(root)
            one = prepare(catalog, desc, inv, root / "one", load_config())
            two = prepare(catalog, desc, inv, root / "two", load_config())
            self.assertEqual(one, two)
            for name in ["pilot.jsonl", "provenance.jsonl", "prepare_manifest.json"]:
                self.assertEqual((root / "one" / name).read_bytes(), (root / "two" / name).read_bytes())
            products = list(read_jsonl(root / "one/pilot.jsonl"))
            self.assertEqual(products[0]["title"], "Телефон Ёж <b>Q77</b> 🐟")
            self.assertEqual(products[0]["description"], "<p>Экран 6,5″ &amp; 😀</p>")
            self.assertIsNone(products[1]["description"])
            for row in products:
                Product.from_dict(row)
            self.assertNotIn("TARGET_", (root / "one/pilot.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("PRIVATE_SELLER", (root / "one/pilot.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(one["accounting"], {
                "catalog_rows": 3, "selected_rows": 2, "filtered_category_rows": 1, "filtered_categories": {"999": 1},
                "description_rows": 3, "matched_description_rows": 2, "unmatched_description_rows": 1,
                "selected_without_description_row": 0, "matched_blank_description_rows": 1, "dropped_selected_rows": 0})
            before = (root / "one/prepare_manifest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "new output"):
                prepare(catalog, desc, inv, root / "one", load_config())
            self.assertEqual((root / "one/prepare_manifest.json").read_bytes(), before)

    def test_invalid_schema_null_title_skus_and_joins_leave_no_partial_bundle(self):
        for problem in ["catalog_type", "missing_column", "null_title", "duplicate_catalog",
                        "null_description_sku", "duplicate_description", "wrong_description_type", "bad_categories"]:
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                raw, catalog, desc, inv = sources(root)
                table = pq.read_table(catalog)
                rows = table.to_pylist()
                if problem == "catalog_type":
                    pq.write_table(table.set_column(0, "sku_id", pa.array([1, 2, 3])), catalog)
                elif problem == "missing_column":
                    pq.write_table(table.drop(["title"]), catalog)
                elif problem in {"null_title", "bad_categories", "duplicate_catalog"}:
                    if problem == "null_title": rows[0]["title"] = None
                    elif problem == "bad_categories": rows[0]["category_ids"] = '[761]'
                    else: rows.append(rows[0])
                    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), catalog)
                else:
                    rows = pq.read_table(desc).to_pylist()
                    if problem == "null_description_sku": rows[0]["sku_id"] = None
                    elif problem == "duplicate_description": rows.append(rows[0])
                    else:
                        for row in rows: row["description"] = 17
                    pq.write_table(pa.Table.from_pylist(rows), desc)
                    inv = root / "updated-inventory.json"
                    inventory_sources(raw, inv)
                with self.assertRaises(ValueError):
                    prepare(catalog, desc, inv, root / "out", load_config())
                self.assertFalse((root / "out").exists())

    def test_same_size_source_change_is_rejected_by_sha_before_publication(self):
        for name in ["skus.pkl", "sku_desc.parquet"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                raw, catalog, desc, inv = sources(root)
                path = raw / name
                original = path.read_bytes()
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                self.assertEqual(path.stat().st_size, len(original))
                with self.assertRaisesRegex(ValueError, "differs"):
                    prepare(catalog, desc, inv, root / "out", load_config())
                self.assertFalse((root / "out").exists())

    def test_busy_destination_is_rejected_without_partial_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, catalog, desc, inv = sources(root)
            with output_lock(root / "out"):
                with self.assertRaises(OutputBusyError):
                    prepare(catalog, desc, inv, root / "out", load_config())
            self.assertFalse((root / "out").exists())

    def test_changed_sources_and_write_failure_do_not_publish_or_destroy_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, catalog, desc, inv = sources(root)
            before = digest(catalog)
            original_bytes = catalog.read_bytes()
            from goodsai import data
            original_write = data.write_line
            changed = False
            def mutate(stream, row):
                nonlocal changed
                original_write(stream, row)
                if not changed:
                    changed = True
                    with catalog.open("ab") as target: target.write(b"mutation")
            with patch.object(data, "write_line", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    prepare(catalog, desc, inv, root / "out", load_config())
            self.assertFalse((root / "out").exists())
            self.assertNotEqual(digest(catalog), before)
            catalog.write_bytes(original_bytes)
            with patch.object(data, "write_line", side_effect=OSError("synthetic disk failure")):
                with self.assertRaises(OSError):
                    prepare(catalog, desc, inv, root / "disk-error", load_config())
            self.assertFalse((root / "disk-error").exists())
            with self.assertRaises(ValueError):
                prepare(catalog, desc, inv, raw / "out", load_config())

    def test_cli_profile_prepare_and_missing_analytics_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, catalog, desc, inv = sources(root)
            def cli(*args):
                return subprocess.run([sys.executable, "-m", "goodsai.cli", *map(str, args)],
                                      capture_output=True, encoding="utf-8")
            result = cli("inventory", "--raw-dir", raw, "--profile", "text-only", "--output", root / "cli.json",
                         "--verify-against", inv)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = cli("prepare", "--catalog", catalog, "--descriptions", desc, "--inventory", root / "cli.json",
                         "--output-dir", root / "prepared")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = cli("inventory", "--raw-dir", raw, "--profile", "analytics", "--output", root / "analytics.json")
            self.assertEqual(result.returncode, 2)


class SplitHandoffTests(unittest.TestCase):
    def fixture(self, root):
        raw, catalog, desc, inv = sources(root)
        prepared = root / "frozen"
        prepare(catalog, desc, inv, prepared, load_config())
        # Existing EVAL-002 fixture, frozen on the exact prepared input bytes.
        products = list(read_jsonl(prepared / "pilot.jsonl"))
        products[0]["sku_id"], products[1]["sku_id"] = "a", "d"
        audit_root = root / "audit-inputs"
        audit_root.mkdir()
        args = split_fixture(audit_root, products)
        frozen_input = args[0].with_name("pilot.jsonl")
        args[0].rename(frozen_input)
        args = (frozen_input, *args[1:])
        # Use actual projection IDs a/d, so the handoff cannot pass through a SKU lookup.
        catrows = pq.read_table(catalog).to_pylist()[:2]
        catrows[0]["sku_id"], catrows[1]["sku_id"] = "a", "d"
        pq.write_table(pa.Table.from_pylist(catrows), catalog)
        descrows = pq.read_table(desc).to_pylist()[:2]
        descrows[0]["sku_id"], descrows[1]["sku_id"] = "a", "d"
        pq.write_table(pa.Table.from_pylist(descrows), desc)
        inv = root / "frozen-inventory.json"
        inventory_sources(raw, inv)
        new = prepare(catalog, desc, inv, root / "frozen2", load_config())
        args[0].write_bytes((root / "frozen2/pilot.jsonl").read_bytes())
        summary = json.loads(args[3].read_text(encoding="utf-8"))
        summary["protected_sources"] = {str(args[0]): new["input_sha256"], str(args[1]): digest(args[1])}
        args[3].write_text(json.dumps(summary), encoding="utf-8")
        args[5][0].write_text('{"sku_id":"a"}\n', encoding="utf-8")
        audit_splits.audit(*args, root / "audit")
        return catalog, desc, inv, root / "audit"

    def test_handoff_reuses_verified_groups_and_rejects_wrong_input_or_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog, desc, inv, audit = self.fixture(root)
            original_raw_files = set(desc.parent.iterdir())
            with self.assertRaisesRegex(ValueError, "outside_raw"):
                prepare_dataset.build(catalog, desc, inv, audit, desc.parent / "out", load_config())
            self.assertEqual(set(desc.parent.iterdir()), original_raw_files)
            report = prepare_dataset.build(catalog, desc, inv, audit, root / "out", load_config())
            self.assertFalse(report["split_audit"]["reserve_text_exported"])
            self.assertEqual(prepare_dataset.verify(root / "out", catalog, desc, inv, audit)["status"], "verified")
            repeat = prepare_dataset.build(catalog, desc, inv, audit, root / "repeat", load_config())
            self.assertEqual(repeat, report)
            result = subprocess.run([sys.executable, "scripts/research/prepare_dataset.py", "--verify", str(root / "out"),
                                     "--catalog", str(catalog), "--descriptions", str(desc), "--inventory", str(inv),
                                     "--split-audit", str(audit)], capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("TARGET_", result.stdout + result.stderr)
            with self.assertRaisesRegex(ValueError, "new output"):
                prepare_dataset.build(catalog, desc, inv, audit, root / "out", load_config())
            with self.assertRaisesRegex(ValueError, "differs_from_frozen"):
                prepare_dataset.bind_audit(audit, "0" * 64)
            config = load_config()
            config["categories"].pop("482")
            with self.assertRaisesRegex(ValueError, "differs_from_frozen"):
                prepare_dataset.build(catalog, desc, inv, audit, root / "wrong-input", config)
            self.assertFalse((root / "wrong-input").exists())
            with (root / "out/prepared/pilot.jsonl").open("a") as stream: stream.write("\n")
            with self.assertRaisesRegex(ValueError, "artifact_hash"):
                prepare_dataset.verify(root / "out", catalog, desc, inv, audit)
