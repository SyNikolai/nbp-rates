-- Flatten raw NBP tables into one typed row per currency per day,
-- written as Parquet partitioned by year and month.
COPY (
    SELECT
        rate.code AS currency_code,
        rate.currency AS currency_name,
        CAST(t.effectiveDate AS DATE) AS effective_date,
        CAST(rate.mid AS DECIMAL(18, 8)) AS mid_rate,
        t.no AS table_no,
        CAST(regexp_extract(t.filename, 'ingest_date=([0-9-]+)', 1) AS DATE) AS ingest_date,
        t.filename AS source_file,
        year(CAST(t.effectiveDate AS DATE)) AS year,
        month(CAST(t.effectiveDate AS DATE)) AS month
    FROM read_json(
        '${raw_glob}',
        format = 'array',
        filename = true,
        columns = {
            'table': 'VARCHAR',
            'no': 'VARCHAR',
            'effectiveDate': 'VARCHAR',
            'rates': 'STRUCT(currency VARCHAR, code VARCHAR, mid VARCHAR)[]'
        }
    ) AS t,
    unnest(t.rates) AS u(rate)
) TO '${staging_dir}' (FORMAT parquet, PARTITION_BY (year, month));
