from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from group_a_plus.integrations.tail_conformal import (
    _walk_forward_aci_alpha,
    compute_tail_conformal_diagnostic,
)


def _write_631l_ohlcv(db_path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", "2026-07-10")
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)")
        price = 100.0
        for i, dt in enumerate(dates):
            if i % 47 == 0:
                price *= 0.91
            elif i % 19 == 0:
                price *= 1.035
            else:
                price *= 1.001
            con.execute(
                "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
                ["00631L.TW", str(dt.date()), price, price, price, price, 1000.0],
            )
    finally:
        con.close()


def test_tail_conformal_outputs_lower_bounds_and_warning_policy(tmp_path: Path) -> None:
    db_path = tmp_path / "market.duckdb"
    _write_631l_ohlcv(db_path)

    result = compute_tail_conformal_diagnostic(
        db_path=db_path,
        actual_date=pd.Timestamp("2026-07-10"),
        latest_features={"total_risk_score": 9, "tail_risk_score": 2},
    )

    assert result["status"] == "ok"
    assert result["policy"] == "diagnostic_warning_only_no_weight_change"
    assert result["auto_reduce_00631l"] is False
    assert result["ticker"] == "00631L.TW"
    assert "h5" in result["diagnostics"]
    assert "h10" in result["diagnostics"]
    assert result["diagnostics"]["h5"]["lower_tail_confidence_bound"] is not None
    assert result["diagnostics"]["h10"]["prob_mdd_lt_8pct"] is not None
    assert result["diagnostics"]["h5"]["adaptive"] is False
    assert result["diagnostics"]["h5"]["effective_alpha"] == result["diagnostics"]["h5"]["alpha"]


def test_tail_conformal_adaptive_mode_reports_effective_alpha(tmp_path: Path) -> None:
    db_path = tmp_path / "market.duckdb"
    _write_631l_ohlcv(db_path)

    result = compute_tail_conformal_diagnostic(
        db_path=db_path,
        actual_date=pd.Timestamp("2026-07-10"),
        adaptive=True,
    )

    assert result["status"] == "ok"
    h5 = result["diagnostics"]["h5"]
    assert h5["adaptive"] is True
    assert h5["calibration_scope"] == "aci_adaptive_no_bucket"
    assert h5["effective_alpha"] is not None
    assert 0.0 < h5["effective_alpha"] < 1.0


def test_walk_forward_aci_alpha_tightens_after_breach_and_relaxes_otherwise() -> None:
    dates = pd.bdate_range("2026-01-01", periods=200)
    rng = np.random.default_rng(0)
    # Mostly small residuals (no breach against a generous quantile), then a
    # deliberate run of large residuals (repeated breaches) starting at day 150.
    values = rng.normal(0.0, 0.01, size=len(dates))
    values[150:160] = 0.5  # force breaches: far above any reasonable quantile
    residuals = pd.Series(values, index=dates)

    alpha_series = _walk_forward_aci_alpha(
        residuals,
        base_alpha=0.10,
        gamma=0.05,
        min_alpha=0.02,
        max_alpha=0.40,
        calibration_window=100,
        warmup=30,
    )

    before_breach = alpha_series.iloc[149]
    during_breach = alpha_series.iloc[155:160]
    after_recovery = alpha_series.iloc[190:]

    # Repeated breaches must pull alpha down (tighter/more-conservative
    # interval) relative to right before the breach run started.
    assert during_breach.min() < before_breach
    # With no further breaches, alpha should relax back upward afterward.
    assert after_recovery.iloc[-1] > during_breach.min()
    assert alpha_series.dropna().between(0.02, 0.40).all()


def test_walk_forward_aci_alpha_defaults_to_base_alpha_during_warmup() -> None:
    dates = pd.bdate_range("2026-01-01", periods=10)
    residuals = pd.Series([0.01] * 10, index=dates)

    alpha_series = _walk_forward_aci_alpha(
        residuals, base_alpha=0.10, gamma=0.05, calibration_window=100, warmup=30
    )

    assert (alpha_series == 0.10).all()
