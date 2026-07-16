from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_specialist_routing_shadow import (
    _forward_drawdown,
    _forward_return,
    build_forward_frame,
    build_shadow_scorecard,
    summarize_routes,
)


def test_forward_return_uses_trading_rows() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    close = pd.Series([100.0, 105.0, 110.0, 99.0], index=idx)

    out = _forward_return(close, 2)

    assert out.iloc[0] == pytest.approx(0.10)
    assert out.iloc[1] == pytest.approx(-0.0571428571)
    assert pd.isna(out.iloc[2])


def test_forward_drawdown_measures_worst_path_loss() -> None:
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    close = pd.Series([100.0, 98.0, 103.0, 95.0, 110.0], index=idx)

    out = _forward_drawdown(close, 3)

    assert out.iloc[0] == pytest.approx(-0.05)
    assert out.iloc[1] == pytest.approx(-0.0306122449)
    assert pd.isna(out.iloc[-1])


def test_build_forward_frame_adds_ticker_horizon_columns() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    log = pd.DataFrame({"route": ["low_volatility", "high_volatility"]}, index=idx[:2])
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 102.0, 101.0, 105.0],
            "00631L.TW": [100.0, 104.0, 102.0, 110.0],
        },
        index=idx,
    )

    out = build_forward_frame(log, prices, horizons=(1, 2))

    assert out.loc[idx[0], "0050.TW_fwd_ret_1d"] == pytest.approx(0.02)
    assert out.loc[idx[0], "00631L.TW_fwd_ret_2d"] == pytest.approx(0.02)
    assert "0050.TW_fwd_mdd_2d" in out.columns


def test_summarize_routes_groups_by_route() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    frame = pd.DataFrame(
        {
            "route": ["low_volatility", "low_volatility", "high_volatility"],
            "risk_level": ["low", "low", "medium"],
            "logged_execution_regime": ["golden1", "golden1", "golden1"],
            "0050.TW_fwd_ret_1d": [0.01, -0.02, -0.03],
            "0050.TW_fwd_mdd_1d": [0.0, -0.02, -0.03],
        },
        index=idx,
    )

    summary = summarize_routes(frame, tickers=("0050.TW",), horizons=(1,))

    assert summary["route_count"] == 2
    low = summary["routes"]["low_volatility"]["tickers"]["0050.TW"]["fwd_ret_1d"]
    assert low["count"] == 2
    assert low["win_rate"] == pytest.approx(0.5)
    high = summary["routes"]["high_volatility"]["tickers"]["0050.TW"]["fwd_mdd_1d"]
    assert high["min"] == pytest.approx(-0.03)


def test_build_shadow_scorecard_focuses_latest_route() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    frame = pd.DataFrame(
        {
            "route": ["neutral", "high_volatility", "high_volatility", "high_volatility"],
            "0050.TW_fwd_ret_1d": [0.0, 0.01, -0.02, 0.03],
            "0050.TW_fwd_mdd_1d": [0.0, -0.01, -0.02, 0.0],
        },
        index=idx,
    )

    scorecard = build_shadow_scorecard(frame, tickers=("0050.TW",), horizons=(1,), lookbacks=(2,))

    assert scorecard["latest_route"] == "high_volatility"
    assert scorecard["lookbacks"]["2"]["rows"] == 2
    metrics = scorecard["lookbacks"]["2"]["tickers"]["0050.TW"]["fwd_ret_1d"]
    assert metrics["count"] == 2
    assert metrics["win_rate"] == pytest.approx(0.5)
