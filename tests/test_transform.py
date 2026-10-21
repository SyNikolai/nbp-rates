from __future__ import annotations

from datetime import date

import duckdb
import pytest

from nbp_pipeline.quality import run_checks
from nbp_pipeline.transform import run_transform
from tests.helpers import make_tables, write_raw


@pytest.fixture
def paths(tmp_path):
    return {
        "raw_dir": tmp_path / "raw",
        "staging_dir": tmp_path / "staging",
        "warehouse_path": tmp_path / "warehouse.duckdb",
    }


def eur_rate(warehouse_path, day: date):
    with duckdb.connect(str(warehouse_path), read_only=True) as con:
        return con.execute(
            "SELECT mid_rate FROM fct_daily_rates "
            "WHERE currency_code = 'EUR' AND effective_date = ?",
            [day],
        ).fetchall()


def test_transform_is_idempotent(paths):
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 1, 1), date(2026, 3, 31)),
    )
    first = run_transform(**paths)
    second = run_transform(**paths)
    assert first == second
    assert first["fct_daily_rates"] == first["stg_rates"]  # no duplicates in input


def test_rebuild_from_raw_gives_same_result(paths):
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 1, 1), date(2026, 3, 31)),
    )
    before = run_transform(**paths)
    paths["warehouse_path"].unlink()
    assert run_transform(**paths) == before


def test_latest_ingest_wins_for_republished_rates(paths):
    day = date(2026, 3, 2)
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 3, 2), date(2026, 3, 6), eur=4.25),
    )
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 21),
        make_tables(date(2026, 3, 2), date(2026, 3, 3), eur=4.30),
    )
    counts = run_transform(**paths)
    assert counts["stg_rates"] == 14  # 5 days + 2 refetched days, 2 currencies
    assert counts["fct_daily_rates"] == 10  # duplicates collapsed
    assert [float(r[0]) for r in eur_rate(paths["warehouse_path"], day)] == [4.30]


def test_checks_pass_on_good_data(paths):
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 9, 1), date(2026, 10, 20)),
    )
    run_transform(**paths)
    results = run_checks(paths["warehouse_path"], today=date(2026, 10, 21))
    assert all(violations == 0 for violations in results.values())


def test_checks_catch_stale_data_and_gaps(paths):
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 1, 1), date(2026, 1, 9)),
    )
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 2, 2), date(2026, 2, 6)),
    )
    run_transform(**paths)
    results = run_checks(paths["warehouse_path"], today=date(2026, 10, 21))
    failed = {name for name, violations in results.items() if violations}
    assert failed == {
        "latest table is at most 7 days old",
        "no gap longer than 7 days between tables",
    }


def test_checks_catch_non_positive_rates(paths):
    write_raw(
        paths["raw_dir"],
        date(2026, 10, 20),
        make_tables(date(2026, 10, 12), date(2026, 10, 16), eur=0),
    )
    run_transform(**paths)
    results = run_checks(paths["warehouse_path"], today=date(2026, 10, 19))
    assert results["all rates are positive"] == 5  # EUR on 5 business days
