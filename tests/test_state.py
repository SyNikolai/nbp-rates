from datetime import date

from nbp_pipeline.state import advance_watermark, read_watermark


def test_no_watermark_before_first_load(tmp_path):
    assert read_watermark(tmp_path / "state.json") is None


def test_watermark_moves_forward(tmp_path):
    path = tmp_path / "state.json"
    advance_watermark(date(2026, 1, 1), path)
    advance_watermark(date(2026, 2, 1), path)
    assert read_watermark(path) == date(2026, 2, 1)


def test_watermark_never_moves_backwards(tmp_path):
    path = tmp_path / "state.json"
    advance_watermark(date(2026, 10, 1), path)
    advance_watermark(date(2024, 1, 1), path)  # e.g. backfilling old history
    assert read_watermark(path) == date(2026, 10, 1)
