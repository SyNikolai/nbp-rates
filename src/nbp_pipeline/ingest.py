from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.nbp.pl/api/exchangerates/tables/A"
MAX_DAYS_PER_REQUEST = 93  # maximum time chunk - NBP rejects ranges longer than this
RAW_DIR = Path("data/raw")


def chunk_range(
    start: date, end: date, max_days: int = MAX_DAYS_PER_REQUEST
) -> list[tuple[date, date]]:
    """Function to split the inclusive range [start, end] into chunks of at most max_days."""
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=max_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def fetch_table(
    client: httpx.Client,
    start: date,
    end: date,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Function to fetch the rate tables NBP published between the incluse range of dates: start and end.

    NBP answers 404 when nothing was published in the range (weekends,
    holidays) and returns an empty list.
    Timeouts and 5xx errors are retried with exponential backoff; any other
    4xx means our request is wrong, so it fails immediately.
    """
    url = f"{BASE_URL}/{start.isoformat()}/{end.isoformat()}/"
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, params={"format": "json"})
            if response.status_code == 404:
                log.info("No tables published %s..%s", start, end)
                return []
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                exc.response.status_code >= 500
            )
            if not retryable or attempt == attempts:
                raise
            delay = 2 ** (attempt - 1)
            log.warning(
                "Attempt %d/%d failed (%s), retrying in %ds",
                attempt,
                attempts,
                exc,
                delay,
            )
            sleep(delay)
    raise RuntimeError("unreachable")


def raw_path(start: date, end: date, ingest_date: date, raw_dir: Path) -> Path:
    """Function to figure the location/path  the raw file for one chunk."""
    folder = raw_dir / f"ingest_date={ingest_date.isoformat()}"
    return folder / f"{start.isoformat()}_{end.isoformat()}.json"


def land_raw(tables: list[dict], path: Path) -> None:
    """Function to write tables to path. Mode "x" makes the OS refuse to overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(tables, f, ensure_ascii=False, indent=2)


def ingest_range(
    client: httpx.Client,
    start: date,
    end: date,
    raw_dir: Path = RAW_DIR,
    ingest_date: date | None = None,
) -> date | None:
    """Function to fetch chunks sequential in chronological order and land each chunk as raw JSON.

    Chunks already landed today are skipped, so an interrupted backfill can
    simply be rerun. Returns the latest effective date landed, or None.
    """
    ingest_date = ingest_date or date.today()
    latest: date | None = None
    for chunk_start, chunk_end in chunk_range(start, end):
        path = raw_path(chunk_start, chunk_end, ingest_date, raw_dir)
        if path.exists():
            log.info("Already landed %s, skipping", path)
            continue
        tables = fetch_table(client, chunk_start, chunk_end)
        if not tables:
            continue
        land_raw(tables, path)
        log.info("Landed %d tables to %s", len(tables), path)
        newest = max(date.fromisoformat(t["effectiveDate"]) for t in tables)
        latest = max(latest, newest) if latest else newest
    return latest
