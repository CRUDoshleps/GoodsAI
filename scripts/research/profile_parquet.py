"""Read-only source EDA; aggregates and scratch database stay under outputs/."""
import json
import time
from pathlib import Path

import duckdb
import pyarrow.parquet as pq


def main():
    out = Path("outputs/eda")
    out.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect(str(out / "profile.duckdb"))
    db.execute("SET memory_limit='768MB'")
    db.execute("SET threads=2")
    db.execute("SET preserve_insertion_order=false")
    db.execute("SET temp_directory='outputs/eda/duckdb_tmp'")
    result = {}

    def query(name, sql):
        start = time.monotonic()
        cur = db.execute(sql)
        names = [col[0] for col in cur.description]
        result[name] = [dict(zip(names, row)) for row in cur.fetchall()]
        (out / "parquet_profile.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"Completed {name} in {time.monotonic()-start:.1f}s", flush=True)

    for name in ["sku_desc", "query_clicks"]:
        p = pq.ParquetFile(f"data/raw/{name}.parquet")
        result[name + "_metadata"] = {
            "rows": p.metadata.num_rows, "row_groups": p.metadata.num_row_groups,
            "schema": str(p.schema_arrow),
            "row_group_stats": [
                {"rows": p.metadata.row_group(i).num_rows,
                 "uncompressed_bytes": p.metadata.row_group(i).total_byte_size,
                 "columns": [{"name": p.metadata.row_group(i).column(j).path_in_schema,
                              "statistics": str(p.metadata.row_group(i).column(j).statistics)}
                             for j in range(p.metadata.num_columns)]}
                for i in range(p.metadata.num_row_groups)]}
    db.execute("CREATE OR REPLACE VIEW d AS SELECT * FROM read_parquet('data/raw/sku_desc.parquet')")
    db.execute("CREATE OR REPLACE VIEW q AS SELECT * FROM read_parquet('data/raw/query_clicks.parquet')")
    query("descriptions", """SELECT count(*) n_rows, count(DISTINCT sku_id) unique_ids,
        count(*)-count(sku_id) null_ids,
        count(*) FILTER (WHERE title IS NULL) null_titles,
        count(*) FILTER (WHERE trim(title)='') blank_titles,
        count(*) FILTER (WHERE description IS NULL) null_descriptions,
        count(*) FILTER (WHERE trim(description)='') blank_descriptions,
        min(length(title)) min_title_length, max(length(title)) max_title_length,
        quantile_disc(length(title),[0.5,0.9,0.99]) title_length_quantiles,
        min(length(description)) min_desc_length, max(length(description)) max_desc_length,
        quantile_disc(length(description),[0.5,0.9,0.99]) desc_length_quantiles,
        count(*) FILTER (WHERE regexp_matches(description,'<[^>]+>')) html_rows,
        count(*) FILTER (WHERE contains(description,chr(65533))) replacement_char_rows,
        count(*) FILTER (WHERE contains(description,chr(10))) newline_rows
        FROM d""")
    query("description_duplicates", """SELECT count(*) duplicate_id_groups, coalesce(sum(n-1),0) excess_rows
        FROM (SELECT sku_id,count(*) n FROM d GROUP BY sku_id HAVING count(*)>1)""")
    query("text_duplicates", """SELECT
        count(*)-count(DISTINCT title) repeated_title_rows,
        count(*) FILTER (WHERE length(trim(description))>0)-count(DISTINCT md5(description))
          FILTER (WHERE length(trim(description))>0) repeated_nonempty_desc_md5_rows,
        count(*)-count(DISTINCT (sku_id,md5(title),md5(description))) duplicate_row_fingerprints FROM d""")
    query("clicks", """SELECT count(*) n_rows, count(DISTINCT sku_id) unique_ids,
        min(sku_id) min_id, max(sku_id) max_id,
        min(sku_price) min_price, max(sku_price) max_price,
        count(*) FILTER (WHERE sku_price<=0) nonpositive_price,
        count(*) FILTER (WHERE NOT isfinite(sku_price)) nonfinite_price,
        min(sku_position) min_position, max(sku_position) max_position,
        count(*) FILTER (WHERE sku_position=0) position_zero,
        count(DISTINCT sku_subject_id) subject_ids, count(DISTINCT sku_seo_id) seo_ids
        FROM q""")
    columns = db.execute("DESCRIBE q").fetchall()
    for col, typ, *_ in columns:
        quoted = '"' + col.replace('"', '""') + '"'
        extra = f", count(*) FILTER (WHERE trim({quoted})='') blank" if "VARCHAR" in typ else ""
        query("click_column_" + col, f"SELECT count(*) FILTER (WHERE {quoted} IS NULL) null_count {extra} FROM q")
    query("query_texts", '''SELECT count(DISTINCT "toValidUTF8(query_text)") unique_queries,
        quantile_disc(length("toValidUTF8(query_text)"),[0.5,0.9,0.99]) length_quantiles,
        max(length("toValidUTF8(query_text)")) max_length FROM q''')
    db.execute("""CREATE OR REPLACE TABLE click_skus AS
        SELECT sku_id,count(*) event_rows,count(DISTINCT sku_subject_id) subject_count,
        min(sku_subject_id) subject_id,count(DISTINCT sku_seo_id) seo_count,min(sku_seo_id) seo_id
        FROM q GROUP BY sku_id""")
    query("click_description_join", """SELECT count(*) click_unique_ids,
        count(*) FILTER (WHERE d.sku_id IS NOT NULL) matched_description_ids,
        sum(event_rows) total_events,
        sum(event_rows) FILTER (WHERE d.sku_id IS NOT NULL) matched_description_events,
        count(*) FILTER (WHERE subject_count>1) mult_subject_skus,
        count(*) FILTER (WHERE seo_count>1) mult_seo_skus
        FROM click_skus c LEFT JOIN d ON c.sku_id=d.sku_id""")
    query("click_duplicates_first_100k", """SELECT count(*) n_rows,
        count(*)-count(DISTINCT (sku_id,"toValidUTF8(sku_name)","toValidUTF8(sku_brand_name)",
          sku_price,sku_subject_id,sku_seo_id,"toValidUTF8(query_text)",sku_position)) duplicate_rows
        FROM (SELECT * FROM q LIMIT 100000)""")
    db.close()


if __name__ == "__main__":
    main()
