from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_specialist_routing_backtest import (
    SPECIALIST_CRASH_REGIME,
    SPECIALIST_HIGH_REGIME,
    SPECIALIST_SEMI_REGIME,
    _garman_klass_variance,
    _ncf_overlay_from_semiconductor,
    _risk_forecast_candidates,
    _route_regime,
    _scale_00631l,
    build_specialist_route_frame,
)


def test_scale_00631l_moves_reduction_to_destination() -> None:
    weights = _scale_00631l(
        {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2},
        0.5,
        destination="0050.TW",
    )

    assert weights["00631L.TW"] == pytest.approx(0.1)
    assert weights["0050.TW"] == pytest.approx(0.7)
    assert weights["cash"] == pytest.approx(0.2)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_route_regime_combined_maps_only_golden1_days() -> None:
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    regimes = pd.Series(["golden1", "golden1", "golden1", "group_a_plus_defensive", "golden1"], index=idx)
    route_frame = pd.DataFrame(
        {
            "route": [
                "high_volatility",
                "semiconductor_risk",
                "crash_deleverage",
                "high_volatility",
                "neutral",
            ]
        },
        index=idx,
    )

    out = _route_regime(regimes, route_frame, mode="combined")

    assert out.iloc[0] == SPECIALIST_HIGH_REGIME
    assert out.iloc[1] == SPECIALIST_SEMI_REGIME
    assert out.iloc[2] == SPECIALIST_CRASH_REGIME
    assert out.iloc[3] == "group_a_plus_defensive"
    assert out.iloc[4] == "golden1"


def test_ncf_overlay_from_semiconductor_marks_risk_state() -> None:
    overlay = _ncf_overlay_from_semiconductor(
        pd.Series(
            {
                "available": True,
                "state": "tsmc_weak_confirmed",
                "ret_2330_5d": -0.03,
                "ret_soxx_5d": -0.04,
                "ret_0050_ex_tsmc_5d": -0.01,
            }
        )
    )

    health = overlay["tsmc_0050_health"]
    assert health["status"] == "available"
    assert health["state"] == "tsmc_weak_confirmed"
    assert health["reference_guidance"]["allow_00631l_add"] is False


def test_build_specialist_route_frame_prioritizes_crash_over_high_vol() -> None:
    idx = pd.date_range("2026-01-01", periods=1, freq="B")
    frame = pd.DataFrame(
        {
            "execution_regime": ["golden1"],
            "ma_gap": [-0.10],
            "drawdown": [-0.08],
            "exit_momentum": [-0.04],
            "total_risk_score": [10],
            "tail_risk_score": [2],
        },
        index=idx,
    )
    gate = pd.DataFrame(
        {
            "high_vol_gate": [True],
            "low_vol_gate": [False],
            "garch_proxy_vol_ratio": [1.3],
            "garch_proxy_vol_percentile": [0.8],
            "return_0050_5d": [-0.03],
        },
        index=idx,
    )
    semi = pd.DataFrame({"available": [False]}, index=idx)

    routes = build_specialist_route_frame(frame, gate, semi)

    assert routes.iloc[0]["route"] == "crash_deleverage"


def test_garman_klass_variance_is_positive_for_valid_ohlc() -> None:
    idx = pd.date_range("2026-01-01", periods=2, freq="B")
    ohlc = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [105.0, 104.0],
            "low": [99.0, 100.0],
            "close": [103.0, 102.0],
        },
        index=idx,
    )

    variance = _garman_klass_variance(ohlc)

    assert len(variance) == 2
    assert (variance > 0).all()


def test_risk_forecast_candidates_include_all_routes() -> None:
    idx = pd.date_range("2026-01-01", periods=25, freq="B")
    realized = pd.Series([0.001 + i * 0.0001 for i in range(25)], index=idx)

    forecasts = _risk_forecast_candidates(realized)

    assert set(forecasts.columns) == {
        "low_volatility",
        "neutral",
        "high_volatility",
        "semiconductor_risk",
        "crash_deleverage",
    }
    assert forecasts.iloc[-1]["crash_deleverage"] >= forecasts.iloc[-1]["neutral"]
