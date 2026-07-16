from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_specialist_routing_improvement_sweep import (
    SPECIALIST_CRASH_PARTIAL_REGIME,
    build_promotion_gate,
    _crash_partial_regime,
    _high_vol_confirmed_regime,
    _online_regret_guard_route_frame,
    _online_regret_route_frame,
    _regime_similarity_route_frame,
    _state_feature_frame,
    _weighted_route_scores,
)
from scripts.evaluate.evaluate_group_a_plus_specialist_routing_backtest import SPECIALIST_HIGH_REGIME


def test_high_vol_confirmed_requires_risk_and_negative_momentum() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    regimes = pd.Series(["golden1", "golden1", "golden1", "group_a_plus_defensive"], index=idx)
    route_frame = pd.DataFrame({"route": ["high_volatility"] * 4}, index=idx)
    frame = pd.DataFrame(
        {
            "total_risk_score": [6, 5, 8, 9],
            "exit_momentum": [-0.01, -0.02, 0.01, -0.03],
        },
        index=idx,
    )

    out = _high_vol_confirmed_regime(regimes, route_frame, frame)

    assert out.iloc[0] == SPECIALIST_HIGH_REGIME
    assert out.iloc[1] == "golden1"
    assert out.iloc[2] == "golden1"
    assert out.iloc[3] == "group_a_plus_defensive"


def test_crash_partial_only_maps_golden1_crash_days() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    regimes = pd.Series(["golden1", "group_a_plus_defensive", "golden1"], index=idx)
    route_frame = pd.DataFrame({"route": ["crash_deleverage", "crash_deleverage", "neutral"]}, index=idx)

    out = _crash_partial_regime(regimes, route_frame)

    assert out.iloc[0] == SPECIALIST_CRASH_PARTIAL_REGIME
    assert out.iloc[1] == "group_a_plus_defensive"
    assert out.iloc[2] == "golden1"


def test_online_regret_route_frame_falls_back_when_no_history(tmp_path) -> None:
    idx = pd.date_range("2026-01-01", periods=2, freq="B")
    route_frame = pd.DataFrame({"route": ["neutral", "high_volatility"]}, index=idx)

    out = _online_regret_route_frame(
        route_frame,
        db_path=tmp_path / "missing.duckdb",
        start="2026-01-01",
        end="2026-01-05",
    )

    assert out["route"].tolist() == ["neutral", "neutral"]
    assert out["online_regret_router"].tolist() == [True, True]


def test_online_regret_guard_route_frame_falls_back_when_no_history(tmp_path) -> None:
    idx = pd.date_range("2026-01-01", periods=2, freq="B")
    route_frame = pd.DataFrame({"route": ["neutral", "high_volatility"]}, index=idx)

    out = _online_regret_guard_route_frame(
        route_frame,
        db_path=tmp_path / "missing.duckdb",
        start="2026-01-01",
        end="2026-01-05",
        min_relative_improvement=0.10,
        confirm_days=2,
    )

    assert out["route"].tolist() == ["neutral", "neutral"]
    assert out["online_regret_guard_router"].tolist() == [True, True]
    assert out["online_regret_guard_confirm_days"].tolist() == [2, 2]


def test_state_feature_frame_includes_route_indicators() -> None:
    idx = pd.date_range("2026-01-01", periods=2, freq="B")
    route_frame = pd.DataFrame({"route": ["high_volatility", "crash_deleverage"]}, index=idx)
    frame = pd.DataFrame({"ma_gap": [0.1, -0.1], "drawdown": [0.0, -0.1]}, index=idx)

    features = _state_feature_frame(route_frame, frame)

    assert features.loc[idx[0], "route_high_vol"] == 1.0
    assert features.loc[idx[1], "route_crash"] == 1.0


def test_weighted_route_scores_prefers_lower_loss_in_similar_history() -> None:
    idx = pd.date_range("2026-01-01", periods=30, freq="B")
    losses = pd.DataFrame(
        {
            "neutral": [1.0] * 29 + [None],
            "crash_deleverage": [0.5] * 29 + [None],
        },
        index=idx,
    )
    features = pd.DataFrame({"ma_gap": [-0.1] * 30, "drawdown": [-0.08] * 30}, index=idx)

    scores = _weighted_route_scores(
        losses,
        features,
        idx[-1],
        lookback=252,
        time_halflife=63.0,
        similarity_bandwidth=2.0,
        min_effective_weight=1.0,
    )

    assert scores is not None
    assert scores.idxmin() == "crash_deleverage"


def test_regime_similarity_route_frame_falls_back_when_no_history(tmp_path) -> None:
    idx = pd.date_range("2026-01-01", periods=2, freq="B")
    route_frame = pd.DataFrame({"route": ["neutral", "high_volatility"]}, index=idx)
    frame = pd.DataFrame({"ma_gap": [0.0, 0.0]}, index=idx)

    out = _regime_similarity_route_frame(
        route_frame,
        frame,
        db_path=tmp_path / "missing.duckdb",
        start="2026-01-01",
        end="2026-01-05",
    )

    assert out["route"].tolist() == ["neutral", "neutral"]
    assert out["regime_similarity_router"].tolist() == [True, True]


def test_build_promotion_gate_requires_noop_sanity() -> None:
    rows = [
        {
            "window": "w1",
            "variant": "online_regret_soft_h100_s100_c100",
            "delta_final_value": 0.0,
            "delta_sharpe_ratio": 0.0,
            "delta_max_drawdown": 0.0,
            "changed_days": 0,
        },
        {
            "window": "w2",
            "variant": "candidate",
            "delta_final_value": 1.0,
            "delta_sharpe_ratio": 0.1,
            "delta_max_drawdown": 0.0,
            "changed_days": 2,
        },
        {
            "window": "w1",
            "variant": "candidate",
            "delta_final_value": 2.0,
            "delta_sharpe_ratio": 0.2,
            "delta_max_drawdown": 0.0,
            "changed_days": 1,
        },
    ]

    gate = build_promotion_gate(rows)

    assert gate["variants"]["online_regret_soft_h100_s100_c100"]["no_op_sanity_pass"] is True
    assert "candidate" in gate["eligible_variants"]
