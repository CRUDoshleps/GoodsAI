"""Invented train/test projections only; no real catalog, gold or remote APIs."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from goodsai.category_registry import Registry
from goodsai.cli import predict
from goodsai.stages import Candidate
from goodsai.config import load_config, validate_config
from goodsai.contracts import Product, validate_prediction
from goodsai.data import digest
from goodsai.learn_categories import attribute_id, build, main, publish
from goodsai.verify import Extractor


def fixtures(root, count=1):
    train = root / "train.jsonl"
    records = []
    for category in range(count):
        for index, (ram, storage) in enumerate(((4, 64), (8, 128), (12, 256), (16, 512))):
            records.append({"sku_id": f"invented-{category}-{index}", "category_id": f"invented-category-{category}",
                "title": f"Демонстрационный прибор {ram}/{storage}GB 10x20x30см",
                "description": "Материал: металл;",
                "params": [{"name": "Оперативная память", "value": str(ram), "unit": "GB"},
                           {"name": "Накопитель", "value": str(storage), "unit": "GB"},
                           {"name": "Ширина", "value": "10", "unit": "см"},
                           {"name": "Высота", "value": "20", "unit": "см"},
                           {"name": "Глубина", "value": "30", "unit": "см"},
                           {"name": "Материал", "value": "металл", "unit": None}]
                           + ([{"name": "Редкое поле", "value": "редкое", "unit": None}] if index == 0 else [])})
    train.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    split = root / "split.json"
    traffic = root / "traffic.json"
    split.write_text(json.dumps({"schema_version": "goodsai-train-split-1", "train_sha256": digest(train),
        "train_sku_ids": [r["sku_id"] for r in records], "validation_sku_ids": ["invented-validation"],
        "test_sku_ids": ["invented-unopened-test"]}))
    traffic.write_text(json.dumps({"schema_version": "goodsai-category-traffic-1", "scope": "train", "train_sha256": digest(train),
        "category_traffic": {f"invented-category-{i}": (count-i)*10 for i in range(count)}}))
    return train, split, traffic


def card(title="Материал: металл;", description=None, category="invented-category-0"):
    return Product("invented-inference", category, title, description)


def attrs(config, product):
    return {a["attribute"]: a for a in Extractor(config).predict(product)["attributes"]}


class CategoryRegistryTests(unittest.TestCase):
    def test_30_categories_train_schema_roles_and_text_only_predictions(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = fixtures(Path(folder), 30)
            config, report = build(*paths)
            self.assertEqual(report["learned_categories"], 30)
            self.assertTrue(report["top_k_complete"])
            self.assertEqual(report["templates"], 60)
            for i in range(30):
                result = attrs(config, card("Прибор 8/128GB 10×20×30см", "Материал: металл;", f"invented-category-{i}"))
                for name, value in (("Оперативная память", "8"), ("Накопитель", "128"), ("Ширина", "10"),
                                    ("Высота", "20"), ("Глубина", "30"), ("Материал", "металл")):
                    self.assertEqual(result[attribute_id(name)]["value"], value)
                    self.assertEqual(result[attribute_id(name)]["decision"], "review")
                self.assertNotIn(attribute_id("Редкое поле"), result)
            second, second_report = build(*paths)
            self.assertEqual(validate_config(json.loads(json.dumps(config, sort_keys=True))), config)
            self.assertEqual(config, second)
            self.assertEqual(report, second_report)
            self.assertEqual(load_config()["config_version"], "1")
            self.assertEqual(set(load_config()["categories"]), {"761", "482"})

    def test_new_category_needs_config_only_and_keeps_exact_html_offsets(self):
        with tempfile.TemporaryDirectory() as folder:
            config, _ = build(*fixtures(Path(folder)))
            registry = config["category_registry"]["categories"]
            registry["invented-added"] = deepcopy(registry["invented-category-0"])
            config["category_registry"]["provenance"]["top_k"] = 30
            config["categories"]["invented-added"] = list(registry["invented-added"]["attributes"])
            config["category_profiles"]["invented-added"] = "learned"
            config = validate_config(config)
            product = card("<p>Материал: <b>металл</b>;</p>", category="invented-added")
            row = Extractor(config).predict(product)
            material = next(a for a in row["attributes"] if a["attribute"] == attribute_id("Материал"))
            self.assertEqual(material["value"], "металл")
            evidence = material["evidence"]
            self.assertEqual(product.title[evidence["start"]:evidence["end"]], evidence["text"])
            validate_prediction(row, config, product)

    def test_absence_conflict_unknown_value_and_negative_context_abstain(self):
        with tempfile.TemporaryDirectory() as folder:
            config, _ = build(*fixtures(Path(folder)))
            for title in ("металл", "Материал: стекло;", "не Материал: металл;", "для другой модели Материал: металл;",
                          "Материал: металл с покрытием;", "<script>Материал: металл;</script>Прибор"):
                with self.subTest(title=title):
                    self.assertEqual(attrs(config, card(title))[attribute_id("Материал")]["decision"], "abstain")
            conflict = attrs(config, card("Оперативная память: 8GB;", "Оперативная память: 16GB;"))
            self.assertEqual(conflict[attribute_id("Оперативная память")]["reason_codes"], ["conflicting_evidence"])
            for title in ("-8/128GB", "около 8/128GB", "8/128MB", "16/8/128GB"):
                with self.subTest(title=title):
                    self.assertEqual(attrs(config, card(title))[attribute_id("Оперативная память")]["decision"], "abstain")

    def test_injected_source_cannot_invent_generic_value(self):
        with tempfile.TemporaryDirectory() as folder:
            config, _ = build(*fixtures(Path(folder)))
            product = card("Оперативная память: 8GB;")
            class InventingSource:
                def candidates(self, product):
                    yield Candidate(attribute_id("Оперативная память"), "16", "GB", "title", 0, len(product.title)-1,
                                    product.title[:-1], 0.8, "synthetic.invalid")
            with self.assertRaises(ValueError):
                Extractor(config, source=InventingSource()).predict(product)

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("fastapi", "httpx", "uvicorn")), "Optional service dependencies absent")
    def test_http_and_cli_use_identical_registry(self):
        import asyncio
        from goodsai.api import create_app
        from httpx import ASGITransport, AsyncClient
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config, _ = build(*fixtures(root))
            path = root / "config.json"
            path.write_text(json.dumps(config, ensure_ascii=False))
            app = create_app(str(path))
            async def request():
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    return await client.post("/predict", json=card().as_dict())
            response = asyncio.run(request())
            self.assertEqual(response.status_code, 200)
            expected = Extractor(config).predict(card())
            self.assertEqual(response.json()["attributes"], expected["attributes"])

    def test_split_overlap_wrong_hash_and_heldout_membership_rejected(self):
        for error in ("overlap", "hash", "membership", "missing"):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as folder:
                train, split, traffic = fixtures(Path(folder))
                doc = json.loads(split.read_text())
                if error == "overlap":
                    doc["test_sku_ids"].append(doc["train_sku_ids"][0])
                elif error == "hash":
                    doc["train_sha256"] = "0"*64
                elif error == "membership":
                    doc["train_sku_ids"].pop()
                else:
                    doc["train_sku_ids"].append("invented-missing")
                split.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):
                    build(train, split, traffic)

    def test_fill_threshold_train_traffic_ranking_and_insufficient_categories(self):
        with tempfile.TemporaryDirectory() as folder:
            train, split, traffic = fixtures(Path(folder), 3)
            config, report = build(train, split, traffic, top_k=2)
            self.assertEqual(set(config["category_registry"]["categories"]), {"invented-category-0", "invented-category-1"})
            self.assertNotIn(attribute_id("Редкое поле"), config["categories"]["invented-category-0"])
            _, short = build(train, split, traffic, top_k=30)
            self.assertFalse(short["top_k_complete"])
            doc = json.loads(traffic.read_text())
            doc["scope"] = "test"
            traffic.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                build(train, split, traffic)

    def test_inconsistent_positional_roles_do_not_become_a_template(self):
        with tempfile.TemporaryDirectory() as folder:
            train, split, traffic = fixtures(Path(folder))
            records = [json.loads(line) for line in train.read_text().splitlines()]
            for row in records[2:]:
                row["params"][0]["value"], row["params"][1]["value"] = row["params"][1]["value"], row["params"][0]["value"]
            train.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in records))
            for path in (split, traffic):
                doc = json.loads(path.read_text())
                doc["train_sha256"] = digest(train)
                path.write_text(json.dumps(doc))
            config, report = build(train, split, traffic)
            self.assertEqual(report["templates"], 1)  # Only dimensions, no memory pair.
            result = attrs(config, card("Прибор 8/128GB"))
            self.assertEqual(result[attribute_id("Оперативная память")]["decision"], "abstain")

    def test_strict_registry_fails_before_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            config, _ = build(*fixtures(Path(folder)))
            cases = []
            invalid = deepcopy(config)
            invalid["category_registry"]["regex"] = ".*"
            cases.append(invalid)
            invalid = deepcopy(config)
            invalid["category_profiles"]["invented-category-0"] = "kettle"
            cases.append(invalid)
            invalid = deepcopy(config)
            invalid["category_registry"]["categories"]["invented-category-0"]["templates"][0]["support"] = 1
            cases.append(invalid)
            invalid = deepcopy(config)
            invalid["categories"]["invented-category-0"].append("unknown")
            cases.append(invalid)
            for invalid in cases:
                with self.assertRaises(ValueError):
                    validate_config(invalid)

    def test_predict_publish_private_config_and_failure_does_not_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = fixtures(root)
            output = root / "candidate"
            report = publish(*paths, output)
            self.assertEqual(report["learned_categories"], 1)
            if os.name != "nt":
                self.assertEqual((output / "config.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                publish(*paths, output)
            config = load_config(output / "config.json")
            input_path = root / "text-only.jsonl"
            input_path.write_text(json.dumps(card().as_dict(), ensure_ascii=False)+"\n")
            result = predict(input_path, root / "predictions.jsonl", config)
            self.assertEqual(result["rows"], 1)
            invalid_output = root / "bad"
            paths[1].write_text("{}")
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                exit_code = main(["--train", str(paths[0]), "--split", str(paths[1]), "--traffic", str(paths[2]), "--output-dir", str(invalid_output)])
            self.assertEqual(exit_code, 2)
            self.assertFalse(invalid_output.exists())


if __name__ == "__main__":
    unittest.main()
