import numpy as np
import pandas as pd
import pytest

from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    _apply_action,
    _apply_partial_and_turnover_cap,
    _predict_action_regrets,
    _predict_action_error_percentiles,
    _select_actions,
    _select_actions_stateful,
    _utility,
)


BASE_WEIGHTS = {
    "0050.TW": 0.60,
    "00631L.TW": 0.20,
    "00632R.TW": 0.0,
    "00679B.TWO": 0.0,
    "cash": 0.20,
}


def test_no_add_caps_00631l_at_prior_weight_and_moves_excess_to_cash() -> None:
    weights = _apply_action(BASE_WEIGHTS, action="NO_ADD", prior_00631l_weight=0.10)

    assert weights["00631L.TW"] == pytest.approx(0.10)
    assert weights["cash"] == pytest.approx(0.30)
    assert weights["0050.TW"] == pytest.approx(0.60)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_cap10_caps_00631l_and_moves_excess_to_0050() -> None:
    weights = _apply_action(BASE_WEIGHTS, action="CAP10", prior_00631l_weight=0.20, cap10=0.10)

    assert weights["00631L.TW"] == pytest.approx(0.10)
    assert weights["0050.TW"] == pytest.approx(0.70)
    assert weights["cash"] == pytest.approx(0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_cap12_caps_00631l_and_moves_excess_to_0050() -> None:
    weights = _apply_action(BASE_WEIGHTS, action="CAP12", prior_00631l_weight=0.20, cap10=0.10)

    assert weights["00631L.TW"] == pytest.approx(0.12)
    assert weights["0050.TW"] == pytest.approx(0.68)
    assert weights["cash"] == pytest.approx(0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_utility_regret_rewards_cap_when_00631l_underperforms() -> None:
    dates = pd.bdate_range("2026-01-01", periods=21)
    prices = pd.DataFrame(
        {
            "0050.TW": np.linspace(100.0, 105.0, 21),
            "00631L.TW": np.linspace(100.0, 80.0, 21),
            "00632R.TW": [10.0] * 21,
            "00679B.TWO": [30.0] * 21,
        },
        index=dates,
    )
    cap = _apply_action(BASE_WEIGHTS, action="CAP10", prior_00631l_weight=0.20, cap10=0.10)

    result = _utility(
        prices,
        0,
        action_weights=cap,
        keep_weights=BASE_WEIGHTS,
        horizon=20,
        lambda_mdd=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
    )

    assert result["action_regret"] > 0.0


def test_partial_adjustment_respects_turnover_cap() -> None:
    action = _apply_action(BASE_WEIGHTS, action="CAP10", prior_00631l_weight=0.20, cap10=0.10)

    adjusted = _apply_partial_and_turnover_cap(
        BASE_WEIGHTS,
        action,
        adjustment_fraction=1.0,
        turnover_cap=0.05,
    )
    diff = sum(abs(adjusted[key] - BASE_WEIGHTS[key]) for key in BASE_WEIGHTS)

    assert diff == pytest.approx(0.05)
    assert adjusted["00631L.TW"] > 0.10


def test_predict_action_regrets_uses_only_past_labels_and_clips() -> None:
    dates = pd.bdate_range("2026-01-01", periods=8)
    features = pd.DataFrame(
        {
            "prob_up_h1": range(8),
            "prob_up_h5": range(8),
            "prob_up_h20": range(8),
            "prob_fwd_mdd_gt5_h20": range(8),
            "prob_fwd_gain_gt5_h20": range(8),
            "confidence": range(8),
            "ma_gap": range(8),
            "total_risk_score": range(8),
            "w_0050": range(8),
            "w_00631l": range(8),
            "ret_0050_5d": range(8),
            "ret_00631l_5d": range(8),
            "spread_00631l_0050_5d": range(8),
        },
        index=dates,
        dtype=float,
    )
    labels = pd.DataFrame(
        {
            "KEEP": [0.0] * 8,
            "NO_ADD": [10.0] * 8,
            "CAP10": [-10.0] * 8,
            "REENTER": [0.5] * 8,
        },
        index=dates,
    )

    preds = _predict_action_regrets(
        features,
        labels,
        min_train_days=5,
        train_window_days=0,
        ridge_alpha=1.0,
        regret_clip=0.03,
    )

    assert preds.iloc[4]["NO_ADD"] == pytest.approx(0.0)
    assert preds.iloc[5]["NO_ADD"] == pytest.approx(0.03)
    assert preds.iloc[5]["CAP10"] == pytest.approx(-0.03)
    assert preds.iloc[5]["KEEP"] == pytest.approx(0.0)


def test_predict_action_error_percentiles_uses_past_prediction_errors() -> None:
    dates = pd.bdate_range("2026-01-01", periods=8)
    features = pd.DataFrame(
        {
            "prob_up_h1": range(8),
            "prob_up_h5": range(8),
            "prob_up_h20": range(8),
            "prob_fwd_mdd_gt5_h20": range(8),
            "prob_fwd_gain_gt5_h20": range(8),
            "confidence": range(8),
            "ma_gap": range(8),
            "total_risk_score": range(8),
            "w_0050": range(8),
            "w_00631l": range(8),
            "ret_0050_5d": range(8),
            "ret_00631l_5d": range(8),
            "spread_00631l_0050_5d": range(8),
        },
        index=dates,
        dtype=float,
    )
    labels = pd.DataFrame(
        {
            "KEEP": [0.0] * 8,
            "NO_ADD": [0.0] * 8,
            "CAP10": [0.001] * 8,
            "REENTER": [0.0] * 8,
        },
        index=dates,
    )
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0] * 8,
            "NO_ADD": [0.0] * 8,
            "CAP10": [0.001] * 8,
            "REENTER": [0.0] * 8,
        },
        index=dates,
    )

    percentiles = _predict_action_error_percentiles(
        features,
        labels,
        predicted,
        min_train_days=5,
        train_window_days=0,
        ridge_alpha=1.0,
    )

    assert percentiles.iloc[4]["CAP10"] == pytest.approx(1.0)
    assert 0.0 <= percentiles.iloc[5]["CAP10"] <= 1.0
    assert percentiles.iloc[5]["KEEP"] == pytest.approx(0.0)


def test_select_actions_requires_positive_edge_threshold() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    add_weights = dict(BASE_WEIGHTS)
    add_weights["00631L.TW"] = 0.25
    add_weights["cash"] = 0.15
    target_weights = pd.DataFrame([BASE_WEIGHTS, add_weights], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "NO_ADD": [0.001, 0.005],
            "CAP10": [0.0, 0.0],
            "REENTER": [0.0, 0.0],
        },
        index=dates,
    )

    weights, decisions = _select_actions(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.4,
        turnover_cap=0.10,
        cap10=0.10,
    )

    assert decisions.iloc[0]["action"] == "KEEP"
    assert decisions.iloc[1]["action"] == "NO_ADD"
    assert weights.iloc[1]["00631L.TW"] < add_weights["00631L.TW"]


def test_select_actions_reliability_gate_can_reject_to_keep() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "NO_ADD": [0.0, 0.0],
            "CAP10": [0.01, 0.01],
            "REENTER": [0.0, 0.0],
        },
        index=dates,
    )
    reliability = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "NO_ADD": [0.0, 0.0],
            "CAP10": [0.9, 0.2],
            "REENTER": [0.0, 0.0],
        },
        index=dates,
    )

    weights, decisions = _select_actions(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.4,
        turnover_cap=0.10,
        cap10=0.10,
        reliability_percentiles=reliability,
        max_error_percentile=0.7,
    )

    assert decisions.iloc[0]["candidate_action_before_reliability"] == "CAP10"
    assert decisions.iloc[0]["action"] == "KEEP"
    assert bool(decisions.iloc[0]["reliability_gate_pass"]) is False
    assert weights.iloc[0]["00631L.TW"] == pytest.approx(BASE_WEIGHTS["00631L.TW"])
    assert decisions.iloc[1]["action"] == "CAP10"


def test_select_actions_respects_action_allowed_gate() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "NO_ADD": [0.0, 0.0],
            "CAP10": [0.01, 0.01],
            "REENTER": [0.0, 0.0],
        },
        index=dates,
    )
    action_allowed = pd.Series([False, True], index=dates)

    weights, decisions = _select_actions(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.4,
        turnover_cap=0.10,
        cap10=0.10,
        action_allowed=action_allowed,
    )

    assert decisions.iloc[0]["action"] == "KEEP"
    assert weights.iloc[0]["00631L.TW"] == pytest.approx(BASE_WEIGHTS["00631L.TW"])
    assert decisions.iloc[1]["action"] == "CAP10"


def test_stateful_keep_preserves_trim_and_reenter_restores_toward_a2118() -> None:
    dates = pd.bdate_range("2026-01-01", periods=3)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0, 0.0],
            "NO_ADD": [0.0, 0.0, 0.0],
            "CAP10": [0.005, 0.0, 0.0],
            "REENTER": [0.0, -0.001, 0.005],
        },
        index=dates,
    )

    weights, decisions = _select_actions_stateful(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.5,
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
    )

    assert decisions.iloc[0]["action"] == "CAP10"
    assert weights.iloc[0]["00631L.TW"] < BASE_WEIGHTS["00631L.TW"]
    assert decisions.iloc[1]["action"] == "KEEP"
    assert weights.iloc[1]["00631L.TW"] == pytest.approx(weights.iloc[0]["00631L.TW"])
    assert decisions.iloc[2]["action"] == "REENTER"
    assert weights.iloc[2]["00631L.TW"] > weights.iloc[1]["00631L.TW"]
    assert weights.iloc[2]["00631L.TW"] < BASE_WEIGHTS["00631L.TW"]
