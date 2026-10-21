"""Turn raw JSON into typed Parquet, then load the DuckDB warehouse."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from string import Template

import duckdb

from nbp_pipeline.ingest import RAW_DIR

log = logging.getLogger(__name__)

SQL_DIR = Path("sql")
STAGING_DIR = Path("data/staging")
WAREHOUSE_PATH = Path("data/warehouse.duckdb")


def render(name: str, **params: str) -> str:
    """Read sql/<name> and fill in its ${placeholders}."""
    return Template((SQL_DIR / name).read_text()).substitute(params)


def build_staging(
    con: duckdb.DuckDBPyConnection, raw_dir: Path, staging_dir: Path
) -> None:
    """Rebuild staging from scratch. It is derived data, so raw is the truth."""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    con.execute(
        render(
            "staging.sql", raw_glob=f"{raw_dir}/*/*.json", staging_dir=str(staging_dir)
        )
    )


def load_warehouse(con: duckdb.DuckDBPyConnection, staging_dir: Path) -> None:
    """Upsert into the fact table and rebuild the marts in one transaction."""
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(render("warehouse.sql", staging_glob=f"{staging_dir}/**/*.parquet"))
        con.execute(render("marts.sql"))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def run_transform(
    raw_dir: Path = RAW_DIR,
    staging_dir: Path = STAGING_DIR,
    warehouse_path: Path = WAREHOUSE_PATH,
) -> dict[str, int]:
    """Run staging and warehouse loads. Returns the row count of each table."""
    if not any(raw_dir.glob("*/*.json")):
        raise FileNotFoundError(f"No raw files in {raw_dir}. Run ingest first.")
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(warehouse_path)) as con:
        build_staging(con, raw_dir, staging_dir)
        load_warehouse(con, staging_dir)
        counts = {
            table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("stg_rates", "fct_daily_rates", "mart_monthly_volatility")
        }
    for table, count in counts.items():
        log.info("%-24s %d rows", table, count)
    return counts
