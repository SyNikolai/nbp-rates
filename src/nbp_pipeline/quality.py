"""Data quality checks on the warehouse. Each check counts violations."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import duckdb

from nbp_pipeline.transform import WAREHOUSE_PATH

log = logging.getLogger(__name__)

MAX_GAP_DAYS = 7  # longest normal break: Christmas holidays plus a weekend

# (name, SQL returning the number of violations). 0 means the check passed.
CHECKS: list[tuple[str, str]] = [
    (
        "fact table is not empty",
        "SELECT CASE WHEN count(*) = 0 THEN 1 ELSE 0 END FROM fct_daily_rates",
    ),
    (
        "one row per currency per day",
        """
        SELECT count(*) FROM (
            SELECT currency_code, effective_date
            FROM fct_daily_rates
            GROUP BY ALL
            HAVING count(*) > 1
        )
        """,
    ),
    (
        "all rates are positive",
        "SELECT count(*) FROM fct_daily_rates WHERE mid_rate <= 0",
    ),
    (
        f"latest table is at most {MAX_GAP_DAYS} days old",
        f"""
        SELECT CASE
            WHEN max(effective_date) < CAST($today AS DATE) - {MAX_GAP_DAYS}
            THEN 1 ELSE 0 END
        FROM fct_daily_rates
        """,
    ),
    (
        f"no gap longer than {MAX_GAP_DAYS} days between tables",
        f"""
        SELECT count(*) FROM (
            SELECT effective_date - lag(effective_date) OVER (ORDER BY effective_date)
                AS gap_days
            FROM (SELECT DISTINCT effective_date FROM fct_daily_rates)
        )
        WHERE gap_days > {MAX_GAP_DAYS}
        """,
    ),
]


def run_checks(
    warehouse_path: Path = WAREHOUSE_PATH, today: date | None = None
) -> dict[str, int]:
    """Run every check and return {check name: number of violations}."""
    today = today or date.today()
    results = {}
    with duckdb.connect(str(warehouse_path), read_only=True) as con:
        for name, sql in CHECKS:
            params = {"today": today} if "$today" in sql else {}
            results[name] = con.execute(sql, params).fetchone()[0]
    for name, violations in results.items():
        status = "PASS" if violations == 0 else f"FAIL ({violations})"
        log.info("%-12s %s", status, name)
    return results
