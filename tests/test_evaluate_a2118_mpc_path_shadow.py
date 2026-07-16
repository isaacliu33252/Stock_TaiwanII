from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_a2118_mpc_path_shadow import (
    DEFAULT_PATHS,
    _add_realized_decision_outcomes,
    _mpc_gate_allows_path_search,
    _scale_00631l_to_0050,
    _score_path,
    _select_path,
)


def test_scale_00631l_to_0050_reduces_leverage_without_changing_cash() -> None:
    weights = _scale_00631l_to_0050(
        {"0050.TW": 0.60, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.20},
        0.5,
    )

    assert weights["00631L.TW"] == pytest.approx(0.10)
    assert weights["0050.TW"] == pytest.approx(0.70)
    assert weights["cash"] == pytest.approx(0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_path_score_uses_probabilities_not_realized_forward_labels() -> None:
    row = pd.Series(
        {
            "prob_up_h1": 0.20,
            "prob_up_h5": 0.25,
            "prob_up_h20": 0.30,
            "prob_fwd_mdd_gt5_h20": 0.90,
            "prob_fwd_gain_gt5_h20": 0.10,
            "confidence": 0.80,
            "forward_gain_h20": 0.50,
            "forward_mdd_h20": 0.00,
        }
    )

    score_with_labels = _score_path(
        DEFAULT_PATHS["P2_half_hold_then_reentry"],
        row,
        base_00631l_weight=0.20,
        lambda_drawdown=0.35,
        gamma_turnover=2.0,
        eta_missed_rebound=0.30,
        confidence_weight=0.50,
    )
    row_without_labels = row.drop(["forward_gain_h20", "forward_mdd_h20"])
    score_without_labels = _score_path(
        DEFAULT_PATHS["P2_half_hold_then_reentry"],
        row_without_labels,
        base_00631l_weight=0.20,
        lambda_drawdown=0.35,
        gamma_turnover=2.0,
        eta_missed_rebound=0.30,
        confidence_weight=0.50,
    )

    assert score_with_labels == score_without_labels


def test_select_path_prefers_hold_when_rebound_probability_is_high() -> None:
    row = pd.Series(
        {
            "prob_up_h1": 0.45,
            "prob_up_h5": 0.70,
            "prob_up_h20": 0.60,
            "prob_fwd_mdd_gt5_h20": 0.30,
            "prob_fwd_gain_gt5_h20": 0.90,
            "confidence": 0.70,
        }
    )

    name, path, _score, _all_scores = _select_path(
        row,
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.15,
        gamma_turnover=0.5,
        eta_missed_rebound=0.50,
        confidence_weight=0.50,
    )

    assert name == "P0_hold"
    assert path == DEFAULT_PATHS["P0_hold"]


def test_select_path_can_reduce_when_near_term_and_tail_risk_are_bearish() -> None:
    row = pd.Series(
        {
            "prob_up_h1": 0.15,
            "prob_up_h5": 0.15,
            "prob_up_h20": 0.40,
            "prob_fwd_mdd_gt5_h20": 0.85,
            "prob_fwd_gain_gt5_h20": 0.10,
            "confidence": 0.80,
        }
    )

    name, path, _score, _all_scores = _select_path(
        row,
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.50,
        gamma_turnover=0.5,
        eta_missed_rebound=0.10,
        confidence_weight=0.50,
    )

    assert name != "P0_hold"
    assert path[1] < 1.0


def test_path_value_scoring_prefers_hold_when_expected_edge_is_positive() -> None:
    row = pd.Series(
        {
            "prob_up_h1": 0.60,
            "prob_up_h5": 0.62,
            "prob_up_h20": 0.65,
            "prob_fwd_mdd_gt5_h20": 0.25,
            "prob_fwd_gain_gt5_h20": 0.75,
            "confidence": 0.80,
        }
    )

    name, path, _score, _all_scores = _select_path(
        row,
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.15,
        gamma_turnover=1.0,
        eta_missed_rebound=0.50,
        confidence_weight=0.50,
        scoring_mode="path_value",
        edge_scale=0.08,
        rebalance_cost_rate=0.003,
    )

    assert name == "P0_hold"
    assert path == DEFAULT_PATHS["P0_hold"]


def test_path_value_scoring_can_reduce_when_expected_edge_is_negative() -> None:
    row = pd.Series(
        {
            "prob_up_h1": 0.20,
            "prob_up_h5": 0.25,
            "prob_up_h20": 0.30,
            "prob_fwd_mdd_gt5_h20": 0.90,
            "prob_fwd_gain_gt5_h20": 0.20,
            "confidence": 0.80,
        }
    )

    name, path, _score, _all_scores = _select_path(
        row,
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.15,
        gamma_turnover=1.0,
        eta_missed_rebound=0.10,
        confidence_weight=0.50,
        scoring_mode="path_value",
        edge_scale=0.08,
        rebalance_cost_rate=0.003,
    )

    assert name != "P0_hold"
    assert path[1] < 1.0


def test_min_utility_edge_filters_marginal_path_selection() -> None:
    row = pd.Series(
        {
            "prob_up_h1": 0.20,
            "prob_up_h5": 0.25,
            "prob_up_h20": 0.30,
            "prob_fwd_mdd_gt5_h20": 0.90,
            "prob_fwd_gain_gt5_h20": 0.20,
            "confidence": 0.80,
        }
    )

    name, path, _score, _all_scores = _select_path(
        row,
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.15,
        gamma_turnover=1.0,
        eta_missed_rebound=0.10,
        confidence_weight=0.50,
        scoring_mode="path_value",
        edge_scale=0.08,
        rebalance_cost_rate=0.003,
        min_utility_edge=1.0,
    )

    assert name == "P0_hold"
    assert path == DEFAULT_PATHS["P0_hold"]


def test_realized_oracle_scoring_reduces_when_future_00631l_underperforms() -> None:
    dates = pd.bdate_range("2026-01-01", periods=25)
    prices = pd.DataFrame(
        {
            "0050.TW": [100 + i for i in range(25)],
            "00631L.TW": [100 - i for i in range(25)],
            "00632R.TW": [20.0] * 25,
            "00679B.TWO": [30.0] * 25,
        },
        index=dates,
    )

    name, path, _score, _all_scores = _select_path(
        pd.Series(dtype=float),
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
        confidence_weight=0.0,
        scoring_mode="realized_oracle",
        prices=prices,
        current_dt=dates[0],
        base_weights={"0050.TW": 0.60, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.20},
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
    )

    assert name != "P0_hold"
    assert path[1] < 1.0


def test_realized_oracle_scoring_uses_hold_when_future_window_is_missing() -> None:
    dates = pd.bdate_range("2026-01-01", periods=5)
    prices = pd.DataFrame(
        {
            "0050.TW": [100 + i for i in range(5)],
            "00631L.TW": [100 - i for i in range(5)],
            "00632R.TW": [20.0] * 5,
            "00679B.TWO": [30.0] * 5,
        },
        index=dates,
    )

    name, path, _score, _all_scores = _select_path(
        pd.Series(dtype=float),
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
        confidence_weight=0.0,
        scoring_mode="realized_oracle",
        prices=prices,
        current_dt=dates[0],
        base_weights={"0050.TW": 0.60, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.20},
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
    )

    assert name == "P0_hold"
    assert path == DEFAULT_PATHS["P0_hold"]


def test_realized_next_day_oracle_uses_only_first_step() -> None:
    dates = pd.bdate_range("2026-01-01", periods=25)
    prices = pd.DataFrame(
        {
            "0050.TW": [100 + i for i in range(25)],
            "00631L.TW": [100 - i for i in range(25)],
            "00632R.TW": [20.0] * 25,
            "00679B.TWO": [30.0] * 25,
        },
        index=dates,
    )

    name, path, _score, _all_scores = _select_path(
        pd.Series(dtype=float),
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
        confidence_weight=0.0,
        scoring_mode="realized_next_day_oracle",
        prices=prices,
        current_dt=dates[0],
        base_weights={"0050.TW": 0.60, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.20},
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
    )

    assert name != "P0_hold"
    assert path[1] < 1.0


def test_realized_next_day_oracle_holds_when_00631l_outperforms_next_day() -> None:
    dates = pd.bdate_range("2026-01-01", periods=25)
    prices = pd.DataFrame(
        {
            "0050.TW": [100 + i for i in range(25)],
            "00631L.TW": [100 + 2 * i for i in range(25)],
            "00632R.TW": [20.0] * 25,
            "00679B.TWO": [30.0] * 25,
        },
        index=dates,
    )

    name, path, _score, _all_scores = _select_path(
        pd.Series(dtype=float),
        base_00631l_weight=0.20,
        paths=DEFAULT_PATHS,
        lambda_drawdown=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
        confidence_weight=0.0,
        scoring_mode="realized_next_day_oracle",
        prices=prices,
        current_dt=dates[0],
        base_weights={"0050.TW": 0.60, "00631L.TW": 0.20, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.20},
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
    )

    assert name == "P0_hold"
    assert path == DEFAULT_PATHS["P0_hold"]


def test_mpc_gate_blocks_when_late_bull_condition_is_absent() -> None:
    row = pd.Series(
        {
            "prob_up_h20": 0.20,
            "prob_fwd_mdd_gt5_h20": 0.90,
            "confidence": 0.90,
        }
    )

    allowed, detail = _mpc_gate_allows_path_search(
        row,
        ma_gap=0.03,
        ma_gap_min=0.10,
        h20_max=0.33,
        mdd_min=0.60,
        confidence_min=0.55,
    )

    assert allowed is False
    assert detail["ma_gap_ok"] is False
    assert detail["risk_ok"] is True


def test_mpc_gate_allows_late_bull_confirmed_risk() -> None:
    row = pd.Series(
        {
            "prob_up_h20": 0.45,
            "prob_fwd_mdd_gt5_h20": 0.75,
            "confidence": 0.70,
        }
    )

    allowed, detail = _mpc_gate_allows_path_search(
        row,
        ma_gap=0.15,
        ma_gap_min=0.10,
        h20_max=0.33,
        mdd_min=0.60,
        confidence_min=0.55,
    )

    assert allowed is True
    assert detail["ma_gap_ok"] is True
    assert detail["risk_ok"] is True
    assert detail["confidence_ok"] is True


def test_mpc_gate_all_mode_requires_h20_and_mdd_confirmation() -> None:
    row = pd.Series(
        {
            "prob_up_h20": 0.45,
            "prob_fwd_mdd_gt5_h20": 0.75,
            "confidence": 0.70,
        }
    )

    allowed, detail = _mpc_gate_allows_path_search(
        row,
        ma_gap=0.15,
        ma_gap_min=0.10,
        h20_max=0.33,
        mdd_min=0.60,
        confidence_min=0.55,
        risk_mode="all",
    )

    assert allowed is False
    assert detail["h20_ok"] is False
    assert detail["mdd_ok"] is True
    assert detail["risk_ok"] is False


def test_realized_outcomes_are_added_after_decisions_for_diagnosis() -> None:
    dates = pd.to_datetime(
        [
            "2026-01-01",
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
        ]
    )
    decisions = pd.DataFrame(
        {
            "selected_path": ["P1_half_fast_reentry"] * len(dates),
            "first_step_multiplier": [0.5] * len(dates),
        },
        index=dates,
    )
    panel = pd.DataFrame(
        {
            "forward_gain_h20": [0.12] * len(dates),
            "forward_mdd_h20": [-0.03] * len(dates),
        },
        index=dates,
    )
    prices = pd.DataFrame(
        {
            "0050.TW": [100, 101, 102, 103, 104, 105],
            "00631L.TW": [100, 99, 98, 97, 96, 95],
        },
        index=dates,
    )

    out = _add_realized_decision_outcomes(decisions, panel, prices, horizons=(5,))

    assert out.loc[dates[0], "fwd_0050_ret_5d"] == pytest.approx(0.05)
    assert out.loc[dates[0], "fwd_00631l_ret_5d"] == pytest.approx(-0.05)
    assert bool(out.loc[dates[0], "hedge_would_help_5d"]) is True
    assert out.loc[dates[0], "forward_gain_h20"] == pytest.approx(0.12)
