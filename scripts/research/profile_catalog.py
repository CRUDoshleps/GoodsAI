"""Bounded-memory reader for this verified plain-container protocol-4 catalog.

Requires inspect_pickle.py output and explicit --trusted-pickle. Uses CPython's
private pure-Python unpickler; validated on Python 3.12, not a general pickle API.
Referenced memo objects must be immutable. Completed offers are consumed then
discarded, while the small category tree remains intact. No source is modified.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import pickle
from pathlib import Path
import time

import pyarrow as pa
import pyarrow.parquet as pq

SENTINEL = object()
ALLOWED = {"PROTO", "FRAME", "EMPTY_DICT", "MEMOIZE", "SHORT_BINUNICODE",
           "BINUNICODE", "BINUNICODE8", "MARK", "EMPTY_LIST", "SETITEMS",
           "SETITEM", "APPENDS", "APPEND", "BINGET", "LONG_BINGET", "NONE",
           "NEWTRUE", "NEWFALSE", "BININT", "BININT1", "BININT2", "LONG1",
           "BINFLOAT", "STOP"}


class CatalogReader(pickle._Unpickler):
    dispatch = pickle._Unpickler.dispatch.copy()

    def __init__(self, stream, references, on_offer):
        super().__init__(stream)
        self.references = references
        self.on_offer = on_offer
        self.memo_index = 0
        self.offers = 0

    def find_class(self, module, name):
        raise ValueError("Object construction is forbidden")

    def load_memoize(self):
        if self.memo_index in self.references:
            value = self.stack[-1]
            if not isinstance(value, (str, bytes, int, float, bool, type(None))):
                raise ValueError("Referenced mutable container: reader not applicable")
            self.memo[self.memo_index] = value
        self.memo_index += 1

    def load_setitems(self):
        super().load_setitems()
        value = self.stack[-1]
        if isinstance(value, dict) and "@id" in value and "categories" in value:
            self.on_offer(value)
            self.offers += 1
            self.stack[-1] = SENTINEL

    def load_appends(self):
        items = self.pop_mark()
        if any(item is SENTINEL for item in items):
            if not all(item is SENTINEL for item in items):
                raise ValueError("Mixed offer and non-offer list")
        else:
            self.stack[-1].extend(items)

    def load_append(self):
        value = self.stack.pop()
        if value is not SENTINEL:
            self.stack[-1].append(value)

    dispatch[pickle.MEMOIZE[0]] = load_memoize
    dispatch[pickle.SETITEMS[0]] = load_setitems
    dispatch[pickle.APPENDS[0]] = load_appends
    dispatch[pickle.APPEND[0]] = load_append


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trusted-pickle", action="store_true", required=True)
    args = parser.parse_args()
    out = Path("outputs/eda")
    scan = json.loads((out / "pickle_opcodes.json").read_text())
    with open("data/raw/skus.pkl", "rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != scan["source_sha256"]:
            raise ValueError("Pickle changed since opcode inspection")
    unexpected = set(scan["opcodes"]) - ALLOWED
    if unexpected:
        raise ValueError(f"Unsupported pickle opcodes: {unexpected}")
    fields, types, missing, category_counts, attr_counts = (Counter() for _ in range(5))
    seller_counts, category_attrs, param_types, issues = Counter(), defaultdict(Counter), Counter(), Counter()
    sample_params = defaultdict(list)
    # Initial candidate categories, verified from the category tree; not an extractor scope.
    candidates = {"761", "987", "1682", "1263", "482"}
    buffer = []
    schema = pa.schema([(k, pa.string()) for k in
                        ["sku_id", "vendor", "model", "title", "category_ids", "seller", "params_json"]]
                       + [("param_count", pa.int32())])
    writer = pq.ParquetWriter(out / "catalog_skus.parquet", schema, compression="zstd")
    n = 0
    start = time.monotonic()

    def flush():
        if buffer:
            writer.write_table(pa.Table.from_pylist(buffer, schema=schema))
            buffer.clear()

    def offer(row):
        nonlocal n
        n += 1
        fields.update(row.keys())
        types.update(f"{k}:{type(v).__name__}" for k, v in row.items())
        for k in ["@id", "vendor", "model", "name", "categories", "param"]:
            if not row.get(k):
                missing[k] += 1
        cat = row.get("categories", {}).get("categoryId", [])
        cats = cat if isinstance(cat, list) else [cat]
        if not all(isinstance(c, str) for c in cats):
            raise ValueError("Unexpected category type")
        category_counts.update(cats)
        if len(cats) != 1:
            issues["not_single_category"] += 1
        params = row.get("param", [])
        param_types[type(params).__name__] += 1
        params = [params] if isinstance(params, dict) else (params or [])
        if not isinstance(params, list):
            raise ValueError("Unexpected param container")
        names = [p.get("@name", "") for p in params]
        attr_counts.update(set(names))
        if len(names) != len(set(names)):
            issues["duplicate_param_names_rows"] += 1
        for c in cats:
            category_attrs[c].update(set(names))
        sellers = [p.get("#text") for p in params if p.get("@name") == "Продавец"]
        seller = str(sellers[0]) if sellers else None
        if seller is not None:
            seller_counts[seller] += 1
        else:
            issues["missing_seller"] += 1
        for p in params:
            if not p.get("#text"):
                issues["empty_param_value"] += 1
            name = p.get("@name", "")
            if len(sample_params[name]) < 3:
                sample_params[name].append({"value": p.get("#text"), "unit": p.get("@unit")})
        for key in ["vendor", "model", "name"]:
            if isinstance(row.get(key), str) and row[key].strip() in {"", "-", "—"}:
                issues[f"placeholder_{key}"] += 1
        buffer.append({"sku_id": str(row.get("@id")), "vendor": row.get("vendor"),
                       "model": row.get("model"), "title": row.get("name"),
                       "category_ids": json.dumps(cats), "seller": seller,
                       "params_json": json.dumps(params, ensure_ascii=False) if candidates.intersection(cats) else None,
                       "param_count": len(params)})
        if len(buffer) >= 4096:
            flush()
        if n % 100000 == 0:
            print(f"Profiled {n:,} offers in {time.monotonic()-start:.1f}s", flush=True)

    try:
        with open("data/raw/skus.pkl", "rb") as stream:
            reader = CatalogReader(stream, set(scan["referenced_indices"]), offer)
            root = reader.load()
            assert stream.read(1) == b"", "Trailing data after pickle STOP"
        assert reader.memo_index == scan["memo_entries"]
        assert reader.offers == n
        flush()
    finally:
        writer.close()
    catalog = root["yml_catalog"]
    categories = catalog["shop"]["categories"]["category"]
    names = {c["@id"]: c.get("#text") for c in categories}
    result = {
        "rows": n, "catalog_date": catalog.get("@date"),
        "root_keys": list(root), "shop_keys": list(catalog["shop"]),
        "category_definitions": categories, "category_definition_count": len(categories),
        "fields": dict(fields), "types": dict(types), "missing": dict(missing),
        "param_container_types": dict(param_types), "issues": dict(issues),
        "category_counts": [{"id": c, "name": names.get(c), "rows": count}
                            for c, count in category_counts.most_common()],
        "attributes": dict(attr_counts.most_common()),
        "category_attributes": dict(category_attrs), "attribute_examples_local_only": dict(sample_params),
        "seller_counts": dict(seller_counts.most_common()),
        "retained_params_categories": sorted(candidates),
        "memo_entries_retained": len(reader.memo), "seconds": time.monotonic()-start,
    }
    (out / "catalog_profile.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completed catalog: {n:,} offers; {len(categories):,} category definitions", flush=True)


if __name__ == "__main__":
    main()
