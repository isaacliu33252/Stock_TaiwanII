from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_2412_05431_smart_leverage_ir_lite_shadow import (
    BENCHMARK_WEIGHTS,
    CandidateWeights,
    _cap_weight_move,
    _candidate_pass,
    _simulate_targets_lot_rounded,
    candidate_grid,
    information_ratio,
    select_ir_lite_weights,
)


def test_candidate_grid_respects_no_portfolio_leverage_constraints() -> None:
    candidates = candidate_grid(max_00631l_weight=0.20, max_effective_beta=1.05, step=0.10)

    assert candidates
    assert all(item.weights["00632R.TW"] == 0.0 for item in candidates)
    assert all(item.weights["00631L.TW"] <= 0.20 + 1e-12 for item in candidates)
    assert all(item.effective_equity_beta <= 1.05 + 1e-12 for item in candidates)
    assert all(abs(sum(item.weights.values()) - 1.0) <= 1e-12 for item in candidates)


def test_information_ratio_prefers_stable_positive_excess_return() -> None:
    idx = pd.date_range("2026-01-01", periods=80, freq="B")
    benchmark = pd.Series(0.001, index=idx)
    candidate = pd.Series(0.0015, index=idx)
    candidate.iloc[::2] = 0.0014

    assert information_ratio(candidate, benchmark) > 0.0


def test_select_ir_lite_weights_can_choose_00631l_when_tail_filter_passes() -> None:
    idx = pd.date_range("2026-01-01", periods=260, freq="B")
    returns = pd.DataFrame(
        {
            "0050.TW": np.full(len(idx), 0.001),
            "00631L.TW": 0.0022 + np.sin(np.arange(len(idx))) * 0.00005,
            "00632R.TW": np.zeros(len(idx)),
            "00679B.TWO": np.full(len(idx), 0.0001),
        },
        index=idx,
    )
    candidates = [
        CandidateWeights("benchmark_like", dict(BENCHMARK_WEIGHTS)),
        CandidateWeights(
            "smart_letf",
            {"0050.TW": 0.50, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.30, "cash": 0.0},
        ),
    ]

    selected, info = select_ir_lite_weights(returns, candidates)

    assert selected.name == "smart_letf"
    assert info["selected"]["weights"]["00631L.TW"] == 0.20


def test_candidate_pass_blocks_benchmark_drawdown_degradation() -> None:
    window = {
        "delta_vs_benchmark": {"final_value": 10_000.0, "sharpe_ratio": 0.1, "max_drawdown": -0.05},
        "delta_vs_latest_a2118": {"max_drawdown": 0.0},
    }

    assert _candidate_pass(window) is False


def test_drawdown_penalty_can_prefer_lower_drawdown_candidate() -> None:
    idx = pd.date_range("2026-01-01", periods=260, freq="B")
    shock = np.zeros(len(idx))
    shock[120] = -0.50
    returns = pd.DataFrame(
        {
            "0050.TW": 0.0008 + np.sin(np.arange(len(idx))) * 0.00005,
            "00631L.TW": 0.0018 + shock,
            "00632R.TW": np.zeros(len(idx)),
            "00679B.TWO": np.full(len(idx), 0.0002),
        },
        index=idx,
    )
    candidates = [
        CandidateWeights("high_letf", {"0050.TW": 0.50, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.30, "cash": 0.0}),
        CandidateWeights("low_letf", {"0050.TW": 0.75, "00631L.TW": 0.00, "00632R.TW": 0.0, "00679B.TWO": 0.25, "cash": 0.0}),
    ]

    selected, info = select_ir_lite_weights(
        returns,
        candidates,
        benchmark_mdd_slack=1.0,
        worst_20d_slack=1.0,
        drawdown_penalty=1000.0,
        worst_20d_penalty=0.0,
    )

    assert selected.name == "low_letf"
    assert info["selected"]["drawdown_degradation"] == 0.0


def test_cap_weight_move_respects_turnover_cap() -> None:
    current = dict(BENCHMARK_WEIGHTS)
    target = {"0050.TW": 0.50, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.30, "cash": 0.0}

    applied, info = _cap_weight_move(current, target, max_turnover=0.20, no_trade_band=0.0)

    assert info["turnover_cap_applied"] is True
    assert info["applied_turnover"] <= 0.20 + 1e-12
    assert 0.0 < applied["00631L.TW"] < target["00631L.TW"]


def test_cap_weight_move_uses_no_trade_band() -> None:
    current = dict(BENCHMARK_WEIGHTS)
    target = {"0050.TW": 0.69, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.31, "cash": 0.0}

    applied, info = _cap_weight_move(current, target, max_turnover=None, no_trade_band=0.03)

    assert applied == current
    assert info["no_trade_band_applied"] is True


def test_lot_rounded_simulation_keeps_uninvested_cash_when_lots_are_large() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 101.0, 102.0],
            "00631L.TW": [200.0, 202.0, 204.0],
            "00632R.TW": [10.0, 10.0, 10.0],
            "00679B.TWO": [50.0, 50.0, 50.0],
        },
        index=idx,
    )
    targets = pd.DataFrame([BENCHMARK_WEIGHTS for _ in idx], index=idx)

    curve, execution = _simulate_targets_lot_rounded(
        prices,
        targets,
        initial_value=10_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
        lot_size=1_000,
    )

    assert execution["rebalance_count"] == 1
    assert execution["turnover_value"] == 0.0
    assert curve.iloc[0] == 10_000.0
