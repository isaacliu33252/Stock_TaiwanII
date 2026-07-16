from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from group_a_plus.integrations.ncf_signal_archive import (
    append_archive_rows,
    build_archive_row,
    evaluate_archive_against_realized,
    load_archive,
)


def _ncf_signal(ticker: str, date: str, *, prob_1: float, prob_5: float, prob_20: float) -> dict:
    return {
        "ticker": ticker,
        "date": date,
        "calibrated_prob_up": prob_20,
        "confidence": 0.8,
        "horizon_prob_up": {"1": prob_1, "5": prob_5, "20": prob_20},
        "horizon_val_auc": {"1": 0.55, "5": 0.62, "20": 0.68},
    }


def test_build_archive_row_includes_all_blend_variants():
    signal = _ncf_signal("00631L.TW", "2026-06-23", prob_1=0.55, prob_5=0.60, prob_20=0.65)
    row = build_archive_row(signal, blend_variants=(0.0, 0.35, 1.0))
    assert row["ticker"] == "00631L.TW"
    assert row["date"] == "2026-06-23"
    assert "blend_0.00_probability_up" in row
    assert "blend_0.35_probability_up" in row
    assert "blend_1.00_probability_up" in row


def test_build_archive_row_returns_none_without_horizon_data():
    signal = {"ticker": "00631L.TW", "date": "2026-06-23", "calibrated_prob_up": 0.5, "confidence": 0.5}
    assert build_archive_row(signal) is None


def test_append_archive_rows_deduplicates_by_ticker_and_date(tmp_path: Path):
    archive_path = tmp_path / "archive.jsonl"
    row1 = build_archive_row(_ncf_signal("00631L.TW", "2026-06-23", prob_1=0.55, prob_5=0.6, prob_20=0.65))
    row2 = build_archive_row(_ncf_signal("00631L.TW", "2026-06-24", prob_1=0.5, prob_5=0.5, prob_20=0.5))

    appended_first = append_archive_rows([row1, row2], archive_path)
    appended_second = append_archive_rows([row1, row2], archive_path)  # same rows again

    assert appended_first == 2
    assert appended_second == 0
    frame = load_archive(archive_path)
    assert len(frame) == 2


def test_append_archive_rows_deduplicates_within_same_batch(tmp_path: Path):
    """Two source files can carry the same (ticker, date) in a single append call
    (e.g. a stale snapshot re-reporting yesterday's last_close_date) -- both must
    collapse to one persisted row, not just dedupe against already-written rows."""
    archive_path = tmp_path / "archive.jsonl"
    row_a = build_archive_row(_ncf_signal("00631L.TW", "2026-07-02", prob_1=0.55, prob_5=0.6, prob_20=0.65))
    row_b = build_archive_row(_ncf_signal("00631L.TW", "2026-07-02", prob_1=0.55, prob_5=0.6, prob_20=0.65))

    appended = append_archive_rows([row_a, row_b], archive_path)

    assert appended == 1
    assert len(load_archive(archive_path)) == 1


def test_append_archive_rows_skips_none_entries(tmp_path: Path):
    archive_path = tmp_path / "archive.jsonl"
    appended = append_archive_rows([None, None], archive_path)
    assert appended == 0
    assert not archive_path.exists() or load_archive(archive_path).empty


def test_load_archive_empty_when_missing(tmp_path: Path):
    frame = load_archive(tmp_path / "missing.jsonl")
    assert frame.empty


def test_evaluate_archive_against_realized_reports_insufficient_data(tmp_path: Path):
    archive_path = tmp_path / "archive.jsonl"
    row = build_archive_row(_ncf_signal("00631L.TW", "2026-06-23", prob_1=0.6, prob_5=0.6, prob_20=0.6))
    append_archive_rows([row], archive_path)
    archive = load_archive(archive_path)

    dates = pd.bdate_range("2026-06-01", periods=60)
    close = pd.Series(100.0 + pd.Series(range(60), index=dates).astype(float), index=dates)

    result = evaluate_archive_against_realized(archive, {"00631L.TW": close}, horizons=(1, 5, 20), min_samples=30)

    for horizon in ("1", "5", "20"):
        assert result[horizon]["status"] == "insufficient_data"
        assert result[horizon]["n"] == 1


def test_evaluate_archive_against_realized_computes_hit_rate_with_enough_samples(tmp_path: Path):
    archive_path = tmp_path / "archive.jsonl"
    dates = pd.bdate_range("2026-01-05", periods=80)
    # Monotonically rising close: every UP prediction at h=1 is always correct.
    close = pd.Series(100.0 + pd.Series(range(len(dates)), index=dates).astype(float), index=dates)

    rows = []
    for dt in dates[:40]:
        signal = _ncf_signal("00631L.TW", dt.strftime("%Y-%m-%d"), prob_1=0.9, prob_5=0.9, prob_20=0.9)
        rows.append(build_archive_row(signal, blend_variants=(0.0, 0.35, 1.0)))
    append_archive_rows(rows, archive_path)
    archive = load_archive(archive_path)

    result = evaluate_archive_against_realized(
        archive, {"00631L.TW": close}, horizons=(1,), blend_variants=(0.0, 0.35, 1.0), min_samples=30
    )

    assert result["1"]["status"] == "ok"
    for blend_key in ("0.00", "0.35", "1.00"):
        assert result["1"]["blend_hit_rates"][blend_key]["hit_rate"] == pytest.approx(1.0)


def test_evaluate_archive_against_realized_empty_archive():
    result = evaluate_archive_against_realized(pd.DataFrame(), {})
    assert result["status"] == "empty_archive"
