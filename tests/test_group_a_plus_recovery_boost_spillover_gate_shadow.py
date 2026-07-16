from __future__ import annotations

import json

import numpy as np
import pandas as pd

from group_a_plus.integrations.recovery_boost_spillover_gate_shadow import (
    RECOVERY_REGIME_NAME,
    _recovery_age,
    append_shadow_log_row,
    build_shadow_log_row,
)


def _quiet_ohlcv(periods: int = 360) -> pd.DataFrame:
    """Low, non-crisis realized-variance OHLCV for all DEFAULT_TICKERS."""
    idx = pd.date_range("2025-01-01", periods=periods, freq="B")
    tickers = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00646.TW", "00713.TW", "00878.TW")
    rows = []
    for ticker in tickers:
        for i, dt in enumerate(idx):
            close = 100 + 0.01 * i
            rows.append(
                {
                    "dt": dt,
                    "ticker": ticker,
                    "open": close * 0.999,
                    "high": close * 1.002,
                    "low": close * 0.998,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)


def test_recovery_age_counts_trailing_recovery_days_only() -> None:
    regime = pd.Series(["golden1", RECOVERY_REGIME_NAME, RECOVERY_REGIME_NAME, RECOVERY_REGIME_NAME])
    assert _recovery_age(regime) == 3

    regime_broken = pd.Series([RECOVERY_REGIME_NAME, RECOVERY_REGIME_NAME, "golden1", RECOVERY_REGIME_NAME])
    assert _recovery_age(regime_broken) == 1

    assert _recovery_age(pd.Series(["golden1", "cash"])) == 0


def test_build_shadow_log_row_not_in_recovery_short_circuits() -> None:
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    regime = pd.Series(["golden1"] * 4 + ["cash"], index=idx)

    row = build_shadow_log_row(execution_regime=regime, ohlcv=_quiet_ohlcv())

    assert row["status"] == "available"
    assert row["research_only"] is True
    assert row["production_effect"] == "none"
    assert row["in_recovery_regime"] is False
    assert row["boost_allowed"] is False
    assert row["boost_reason"] == "not_in_recovery_regime"


def test_build_shadow_log_row_recovery_age_exceeds_max_blocks() -> None:
    idx = pd.date_range("2026-01-01", periods=25, freq="B")
    regime = pd.Series([RECOVERY_REGIME_NAME] * 25, index=idx)

    row = build_shadow_log_row(execution_regime=regime, ohlcv=_quiet_ohlcv(), max_age_days=20)

    assert row["in_recovery_regime"] is True
    assert row["recovery_age_days"] == 25
    assert row["age_allowed"] is False
    assert row["boost_allowed"] is False
    assert row["boost_reason"] == "recovery_age_exceeds_max"


def test_build_shadow_log_row_allows_when_quiet_and_within_age() -> None:
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    regime = pd.Series([RECOVERY_REGIME_NAME] * 5, index=idx)

    row = build_shadow_log_row(execution_regime=regime, ohlcv=_quiet_ohlcv(), max_age_days=20)

    assert row["age_allowed"] is True
    assert row["spillover_gate"]["crisis_regime"] is False
    assert row["boost_allowed"] is True
    assert row["boost_reason"] == "allowed"


def test_build_shadow_log_row_empty_regime_is_unavailable() -> None:
    row = build_shadow_log_row(execution_regime=pd.Series(dtype=str), ohlcv=_quiet_ohlcv())

    assert row["status"] == "unavailable"
    assert row["reason"] == "empty_execution_regime"


def test_append_shadow_log_row_dedupes_by_date(tmp_path) -> None:
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "available", "date": "2026-07-15", "boost_allowed": False}

    assert append_shadow_log_row(row, log_path) is True
    assert append_shadow_log_row(row, log_path) is False

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2026-07-15"


def test_append_shadow_log_row_skips_unavailable_rows(tmp_path) -> None:
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "unavailable", "reason": "empty_execution_regime"}

    assert append_shadow_log_row(row, log_path) is False
    assert not log_path.exists()
