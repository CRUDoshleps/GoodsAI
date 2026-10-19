"""Invented 30-category demonstration; not real catalog coverage or quality."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from goodsai.cli import predict
from goodsai.config import load_config
from goodsai.data import digest
from goodsai.learn_categories import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    train = root / "train.jsonl"
    records, products = [], []
    for category in range(30):
        category_id = f"invented-category-{category:02d}"
        for index, (ram, storage) in enumerate(((4, 64), (8, 128), (12, 256), (16, 512))):
            records.append({"sku_id": f"invented-train-{category}-{index}", "category_id": category_id,
                "title": f"Пример {ram}/{storage}GB 10×20×30см", "description": "Материал: металл;",
                "params": [{"name": "Оперативная память", "value": str(ram), "unit": "GB"},
                           {"name": "Накопитель", "value": str(storage), "unit": "GB"},
                           {"name": "Ширина", "value": "10", "unit": "см"},
                           {"name": "Высота", "value": "20", "unit": "см"},
                           {"name": "Глубина", "value": "30", "unit": "см"},
                           {"name": "Материал", "value": "металл", "unit": None}]})
        products.append({"schema_version": "0.1", "sku_id": f"invented-inference-{category}", "category_id": category_id,
                         "title": "Пример 8/128GB 10х20х30см", "description": "Материал: металл;"})
    split, traffic, source = [root / name for name in ("split.json", "traffic.json", "text-only.jsonl")]
    train.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    split.write_text(json.dumps({"schema_version": "goodsai-train-split-1", "train_sha256": digest(train),
        "train_sku_ids": [r["sku_id"] for r in records], "validation_sku_ids": [], "test_sku_ids": []}), encoding="utf-8")
    traffic.write_text(json.dumps({"schema_version": "goodsai-category-traffic-1", "scope": "train", "train_sha256": digest(train),
        "category_traffic": {r["category_id"]: 1000-i for i, r in enumerate(products)}}), encoding="utf-8")
    source.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in products), encoding="utf-8")
    for path in (train, split, traffic, source):
        path.chmod(0o600)
    report = publish(train, split, traffic, root / "registry")
    config = load_config(root / "registry" / "config.json")
    run = predict(source, root / "predictions.jsonl", config)
    print(json.dumps({"synthetic_only": True, "real_category_coverage": "not_measured", "learning": report,
                      "prediction_rows": run["rows"], "candidate_pairs": sum(c["predicted"] for c in run["attribute_counts"].values()),
                      "note": "Synthetic extraction counts are not a quality metric"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
