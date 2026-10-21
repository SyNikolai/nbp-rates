from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise

import httpx
import pytest

from nbp_pipeline.ingest import chunk_range, fetch_table, ingest_range
from tests.helpers import make_tables


@pytest.mark.parametrize(
    ("start", "end", "expected_windows"),
    [
        (date(2026, 1, 1), date(2026, 1, 1), 1),  # single day
        (date(2026, 1, 1), date(2026, 2, 1), 1),  # shorter than one window
        (date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=185), 2),  # exactly 2
        (date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=186), 3),  # one day over
    ],
)
def test_chunk_range_window_count(start, end, expected_windows):
    assert len(chunk_range(start, end)) == expected_windows


def test_chunk_range_covers_range_without_gaps_or_overlaps():
    windows = chunk_range(date(2020, 1, 1), date(2026, 10, 21))
    assert windows[0][0] == date(2020, 1, 1)
    assert windows[-1][1] == date(2026, 10, 21)
    for (_, prev_end), (next_start, _) in pairwise(windows):
        assert next_start == prev_end + timedelta(days=1)
    assert all((end - start).days + 1 <= 93 for start, end in windows)


def test_chunk_range_empty_when_start_after_end():
    assert chunk_range(date(2026, 1, 2), date(2026, 1, 1)) == []


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_table_treats_404_as_no_data():
    client = mock_client(lambda request: httpx.Response(404))
    assert fetch_table(client, date(2026, 1, 3), date(2026, 1, 4)) == []


def test_fetch_table_retries_server_errors_with_backoff():
    responses = iter(
        [httpx.Response(503), httpx.Response(502), httpx.Response(200, json=[])]
    )
    sleeps: list[float] = []
    client = mock_client(lambda request: next(responses))
    assert (
        fetch_table(client, date(2026, 1, 5), date(2026, 1, 5), sleep=sleeps.append)
        == []
    )
    assert sleeps == [1, 2]


def test_fetch_table_fails_fast_on_client_errors():
    sleeps: list[float] = []
    client = mock_client(lambda request: httpx.Response(400))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_table(client, date(2026, 1, 5), date(2026, 1, 5), sleep=sleeps.append)
    assert sleeps == []


def test_fetch_table_gives_up_after_all_attempts():
    client = mock_client(lambda request: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_table(client, date(2026, 1, 5), date(2026, 1, 5), sleep=lambda s: None)


def test_ingest_range_is_idempotent(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        *_, start, end = request.url.path.strip("/").split("/")
        tables = make_tables(date.fromisoformat(start), date.fromisoformat(end))
        return httpx.Response(200, json=tables) if tables else httpx.Response(404)

    client = mock_client(handler)
    first = ingest_range(client, date(2026, 1, 1), date(2026, 4, 30), raw_dir=tmp_path)
    assert first == date(2026, 4, 30)
    assert len(calls) == 2

    second = ingest_range(client, date(2026, 1, 1), date(2026, 4, 30), raw_dir=tmp_path)
    assert second is None
    assert len(calls) == 2  # nothing fetched again
