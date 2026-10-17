"""Join coverage, category aggregates and bounded label inspection; no extraction model."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import duckdb
import pyarrow.parquet as pq


def main():
    out = Path("outputs/eda")
    catalog = json.loads((out / "catalog_profile.json").read_text(encoding="utf-8"))
    names = {c["@id"]: c["#text"] for c in catalog["category_definitions"]}
    db = duckdb.connect(str(out / "profile.duckdb"))
    db.execute("SET memory_limit='768MB'")
    db.execute("SET threads=2")
    db.execute("SET preserve_insertion_order=false")
    db.execute("CREATE OR REPLACE VIEW c AS SELECT *, json_extract_string(category_ids,'$[0]') category_id FROM read_parquet('outputs/eda/catalog_skus.parquet')")
    result = {}

    def query(name, sql):
        cur = db.execute(sql)
        result[name] = [dict(zip([col[0] for col in cur.description], row)) for row in cur.fetchall()]

    query("catalog", """SELECT count(*) n_rows, count(DISTINCT sku_id) unique_ids,
        count(DISTINCT vendor) vendors, count(DISTINCT model) models,
        count(DISTINCT seller) sellers, count(DISTINCT category_id) primary_categories,
        min(param_count) min_param_count, max(param_count) max_param_count,
        quantile_disc(param_count,[0.5,0.9,0.99]) param_count_quantiles,
        count(*) FILTER (WHERE vendor IS NULL OR trim(vendor)='') missing_vendor,
        count(*) FILTER (WHERE model IS NULL OR trim(model)='') missing_model,
        count(*) FILTER (WHERE title IS NULL OR trim(title)='') missing_title FROM c""")
    query("catalog_description_join", """SELECT count(*) catalog_rows,
        count(*) FILTER (WHERE d.sku_id IS NOT NULL) matched_catalog_rows,
        count(*) FILTER (WHERE d.sku_id IS NOT NULL AND c.title=d.title) equal_titles,
        count(*) FILTER (WHERE d.sku_id IS NOT NULL AND c.title<>d.title) differing_titles
        FROM c LEFT JOIN d ON try_cast(c.sku_id AS BIGINT)=d.sku_id""")
    query("three_way_join", """SELECT count(*) joined_skus FROM c
        JOIN d ON try_cast(c.sku_id AS BIGINT)=d.sku_id
        JOIN click_skus q ON try_cast(c.sku_id AS UBIGINT)=q.sku_id""")
    query("category_join", """SELECT c.category_id, count(*) catalog_rows,
        count(d.sku_id) description_rows,
        count(*) FILTER (WHERE d.sku_id IS NOT NULL AND c.title<>d.title) differing_titles,
        count(*) FILTER (WHERE cl.sku_id IS NOT NULL) with_clicks,
        coalesce(sum(cl.event_rows),0) event_rows
        FROM c LEFT JOIN d ON try_cast(c.sku_id AS BIGINT)=d.sku_id
        LEFT JOIN click_skus cl ON try_cast(c.sku_id AS UBIGINT)=cl.sku_id
        GROUP BY c.category_id ORDER BY catalog_rows DESC""")
    for row in result["category_join"]:
        row["name"] = names.get(row["category_id"])
    query("catalog_clicks_join", """SELECT count(*) click_unique_ids,
        count(c.sku_id) matched_catalog_ids,
        sum(event_rows) FILTER (WHERE c.sku_id IS NOT NULL) matched_catalog_events,
        count(*) FILTER (WHERE c.sku_id IS NOT NULL AND subject_count=1 AND
          list_contains(json_extract_string(c.category_ids,'$[*]'),cast(subject_id AS VARCHAR))) subject_matches,
        count(*) FILTER (WHERE c.sku_id IS NOT NULL AND seo_count=1 AND
          list_contains(json_extract_string(c.category_ids,'$[*]'),cast(seo_id AS VARCHAR))) seo_matches
        FROM click_skus cl LEFT JOIN c ON cl.sku_id=try_cast(c.sku_id AS UBIGINT)""")
    query("model_groups", """SELECT count(*) repeated_vendor_model_groups, sum(n-1) excess_rows
        FROM (SELECT vendor,model,count(*) n FROM c
        WHERE model IS NOT NULL AND trim(model) NOT IN ('','-','—')
        GROUP BY vendor,model HAVING count(*)>1)""")
    attr_occurrences, attr_skus = Counter(), Counter()
    attr_values, attr_units = defaultdict(set), defaultdict(set)
    for batch in pq.ParquetFile(out / "catalog_skus.parquet").iter_batches(
            batch_size=1024, columns=["category_ids", "params_json"]):
        for row in batch.to_pylist():
            if row["params_json"] is None:
                continue
            cat = json.loads(row["category_ids"])[0]
            present = set()
            for p in json.loads(row["params_json"]):
                key = (cat, p.get("@name", ""))
                attr_occurrences[key] += 1
                present.add(key)
                attr_values[key].add(json.dumps(p.get("#text"), ensure_ascii=False))
                attr_units[key].add(p.get("@unit"))
            attr_skus.update(present)
    result["candidate_params"] = [
        {"category_id": cat, "attr_name": name, "occurrences": count,
         "skus": attr_skus[(cat, name)], "distinct_values": len(attr_values[(cat, name)]),
         "units": sorted(attr_units[(cat, name)], key=str)}
        for (cat, name), count in attr_occurrences.items()]
    # Stable sample of up to 200 joined cards per candidate category for manual label inspection.
    db.execute("""CREATE OR REPLACE TEMP TABLE sample_ids AS
        SELECT c.sku_id,c.category_id FROM c JOIN d ON try_cast(c.sku_id AS BIGINT)=d.sku_id
        WHERE c.params_json IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY c.category_id ORDER BY md5(c.sku_id||':goodsai-eda-v1'))<=200""")
    sample = db.execute("""SELECT c.sku_id,c.category_id,c.vendor,c.model,c.title,d.description,c.params_json
        FROM sample_ids s JOIN c ON c.sku_id=s.sku_id
        JOIN d ON try_cast(c.sku_id AS BIGINT)=d.sku_id
        ORDER BY c.category_id,c.sku_id""").fetchall()
    local_samples, support = [], defaultdict(Counter)
    for sku, cat, vendor, model, title, description, params in sample:
        ps = json.loads(params)
        text = (title + "\n" + description).casefold()
        support[cat]["sample_rows"] += 1
        if vendor and vendor.casefold() in text:
            support[cat]["vendor_literal_in_text"] += 1
        if model and model not in {"-", "—"} and model.casefold() in text:
            support[cat]["model_literal_in_text"] += 1
        for p in ps:
            name, val = p.get("@name", ""), p.get("#text", "")
            if any(w in name.casefold() for w in ["памят", "диагонал", "цвет", "объем", "объём", "мощност"]):
                support[cat]["label_present:" + name] += 1
                if isinstance(val, str) and val.casefold() in text:
                    support[cat]["label_literal_support:" + name] += 1
        local_samples.append({"sku_id":sku,"category_id":cat,"vendor":vendor,"model":model,
                              "title":title,"description":description,"params":ps})
    (out / "inspection_sample.json").write_text(json.dumps(local_samples,ensure_ascii=False,indent=2),encoding="utf-8")
    result["sample_literal_support"] = dict(support)
    result["sample_method"] = "Up to 200 joined cards/category, ascending md5(sku_id + ':goodsai-eda-v1'); literal substring diagnostics, not accuracy."
    (out / "joins_profile.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print("Join profiles and bounded inspection sample saved under outputs/eda/.")
    db.close()


if __name__ == "__main__":
    main()
