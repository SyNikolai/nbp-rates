"""Shared helpers: fake raw NBP files that look like the real API output."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def business_days(start: date, end: date) -> list[date]:
    days = (start + timedelta(n) for n in range((end - start).days + 1))
    return [d for d in days if d.weekday() < 5]


def make_tables(start: date, end: date, eur: float = 4.25) -> list[dict]:
    """NBP-shaped tables for every business day in [start, end]."""
    return [
        {
            "table": "A",
            "no": f"{d:%j}/A/NBP/{d.year}",
            "effectiveDate": d.isoformat(),
            "rates": [
                {"currency": "euro", "code": "EUR", "mid": eur},
                {
                    "currency": "dolar amerykański",
                    "code": "USD",
                    "mid": 3.9 + d.day / 100,
                },
            ],
        }
        for d in business_days(start, end)
    ]


def write_raw(raw_dir: Path, ingest_date: date, tables: list[dict]) -> None:
    folder = raw_dir / f"ingest_date={ingest_date.isoformat()}"
    folder.mkdir(parents=True, exist_ok=True)
    start, end = tables[0]["effectiveDate"], tables[-1]["effectiveDate"]
    (folder / f"{start}_{end}.json").write_text(json.dumps(tables))
