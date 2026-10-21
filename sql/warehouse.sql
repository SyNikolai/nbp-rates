-- Staging view over the Parquet files; the year/month folders become columns.
CREATE OR REPLACE VIEW stg_rates AS
SELECT * FROM read_parquet('${staging_glob}', hive_partitioning = true);

-- One row per currency per day. The primary key makes duplicates impossible.
CREATE TABLE IF NOT EXISTS fct_daily_rates (
    currency_code VARCHAR NOT NULL,
    currency_name VARCHAR NOT NULL,
    effective_date DATE NOT NULL,
    mid_rate DECIMAL(18, 8) NOT NULL,
    table_no VARCHAR NOT NULL,
    ingest_date DATE NOT NULL,
    PRIMARY KEY (currency_code, effective_date)
);

-- Upsert: if the same day was fetched more than once, the latest ingest wins,
-- so a republished rate overwrites the old one instead of duplicating it.
INSERT INTO fct_daily_rates
SELECT currency_code, currency_name, effective_date, mid_rate, table_no, ingest_date
FROM stg_rates
QUALIFY row_number() OVER (
    PARTITION BY currency_code, effective_date
    ORDER BY ingest_date DESC, source_file DESC
) = 1
ON CONFLICT (currency_code, effective_date) DO UPDATE SET
    currency_name = excluded.currency_name,
    mid_rate = excluded.mid_rate,
    table_no = excluded.table_no,
    ingest_date = excluded.ingest_date;
