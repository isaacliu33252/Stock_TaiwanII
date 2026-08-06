import numpy as np
import pandas as pd
import pytest

from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    _apply_action,
    _build_action_labels,
    _apply_partial_and_turnover_cap,
    _build_calibration_pairs,
    _predict_action_regrets,
    _predict_action_error_percentiles,
    _select_actions,
    _select_actions_stateful,
    _stateful_candidate_weights,
    _utility,
    _vix_relief_signal,
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


def test_reenter_00631l_step_label_rebuilds_part_of_prior_gap() -> None:
    weights = _apply_action(BASE_WEIGHTS, action="REENTER_00631L_5", prior_00631l_weight=0.10)

    assert weights["00631L.TW"] == pytest.approx(0.15)
    assert weights["0050.TW"] == pytest.approx(0.65)
    assert weights["cash"] == pytest.approx(0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_reenter_00631l_step_label_caps_at_a2118_target() -> None:
    weights = _apply_action(BASE_WEIGHTS, action="REENTER_00631L_10", prior_00631l_weight=0.15)

    assert weights["00631L.TW"] == pytest.approx(BASE_WEIGHTS["00631L.TW"])
    assert weights["0050.TW"] == pytest.approx(BASE_WEIGHTS["0050.TW"])
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


def test_reenter_step_label_rewards_rebuild_when_00631l_outperforms_0050() -> None:
    dates = pd.bdate_range("2026-01-01", periods=25)
    prices = pd.DataFrame(
        {
            "0050.TW": np.linspace(100.0, 101.0, 25),
            "00631L.TW": np.linspace(100.0, 120.0, 25),
            "00632R.TW": [10.0] * 25,
            "00679B.TWO": [30.0] * 25,
        },
        index=dates,
    )
    target_weights = pd.DataFrame([BASE_WEIGHTS] * len(dates), index=dates)

    labels = _build_action_labels(
        prices,
        target_weights,
        horizon=20,
        lambda_mdd=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
        cap10=0.10,
        actions=("KEEP", "REENTER_00631L_5", "REENTER_00631L_10"),
    )

    assert labels.iloc[0]["KEEP"] == pytest.approx(0.0)
    assert labels.iloc[0]["REENTER_00631L_5"] > 0.0
    assert labels.iloc[0]["REENTER_00631L_10"] > labels.iloc[0]["REENTER_00631L_5"]


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


def test_stateful_reenter_step_adds_00631l_from_0050_first() -> None:
    current = dict(BASE_WEIGHTS)
    current["0050.TW"] = 0.70
    current["00631L.TW"] = 0.10

    weights = _stateful_candidate_weights(
        BASE_WEIGHTS,
        current,
        action="REENTER_00631L_5",
        prior_a2118_00631l_weight=0.20,
        cap10=0.10,
        adjustment_fraction=1.0,
        turnover_cap=1.0,
    )

    assert weights["00631L.TW"] == pytest.approx(0.15)
    assert weights["0050.TW"] == pytest.approx(0.65)
    assert weights["cash"] == pytest.approx(0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_stateful_reenter_step_uses_cash_when_0050_is_insufficient() -> None:
    current = dict(BASE_WEIGHTS)
    current["0050.TW"] = 0.02
    current["00631L.TW"] = 0.10
    current["cash"] = 0.88

    weights = _stateful_candidate_weights(
        BASE_WEIGHTS,
        current,
        action="REENTER_00631L_5",
        prior_a2118_00631l_weight=0.20,
        cap10=0.10,
        adjustment_fraction=1.0,
        turnover_cap=1.0,
    )

    assert weights["00631L.TW"] == pytest.approx(0.15)
    assert weights["0050.TW"] == pytest.approx(0.0)
    assert weights["cash"] == pytest.approx(0.85)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_stateful_reenter_step_requires_position_below_a2118() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "NO_ADD": [0.0, 0.0],
            "CAP10": [0.0, 0.0],
            "REENTER": [0.0, 0.0],
            "REENTER_00631L_5": [0.01, 0.01],
            "REENTER_00631L_10": [0.0, 0.0],
        },
        index=dates,
    )

    weights, decisions = _select_actions_stateful(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=1.0,
        turnover_cap=1.0,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
    )

    assert (decisions["action"] == "KEEP").all()
    assert np.allclose(weights["00631L.TW"], BASE_WEIGHTS["00631L.TW"])


def test_vix_relief_signal_fires_only_after_a_meaningful_fall_from_peak() -> None:
    dates = pd.bdate_range("2026-01-01", periods=10)
    # VIX spikes to 30 on day 3, then decays back down.
    vix = pd.Series([18, 18, 30, 28, 26, 24, 22, 20, 18, 17], index=dates, dtype=float)

    relief = _vix_relief_signal(dates, vix, lookback_days=20, relief_ratio=0.85)

    # T-1 shifted -- day 0 has no prior VIX at all, so never relief.
    assert relief.iloc[0] == False  # noqa: E712
    # Right after the spike (days 3-4), VIX (T-1) is still near its own peak.
    assert relief.iloc[3] == False  # noqa: E712
    # By day 9, T-1 VIX (17) is well under 0.85 * peak-so-far (30) -- relief.
    assert relief.iloc[9] == True  # noqa: E712


def test_relief_gate_forces_reenter_that_the_regret_model_would_never_pick() -> None:
    dates = pd.bdate_range("2026-01-01", periods=3)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0, 0.0],
            "NO_ADD": [0.0, 0.0, 0.0],
            "CAP10": [0.005, 0.0, 0.0],
            # REENTER's predicted regret never clears any threshold on day 2 --
            # this is the data-starved case: without the relief gate it would
            # stay KEEP (capped) forever.
            "REENTER": [0.0, -0.01, -0.01],
        },
        index=dates,
    )
    relief_signal = pd.Series([False, False, True], index=dates)

    weights, decisions = _select_actions_stateful(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.5,
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
        relief_signal=relief_signal,
    )

    assert decisions.iloc[0]["action"] == "CAP10"
    assert decisions.iloc[1]["action"] == "KEEP"
    assert decisions.iloc[1]["relief_triggered"] == False  # noqa: E712
    assert decisions.iloc[2]["action"] == "REENTER"
    assert decisions.iloc[2]["relief_triggered"] == True  # noqa: E712
    assert weights.iloc[2]["00631L.TW"] > weights.iloc[1]["00631L.TW"]


def test_relief_gate_is_a_no_op_when_position_is_not_below_a2118() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {"KEEP": [0.0, 0.0], "NO_ADD": [0.0, 0.0], "CAP10": [0.0, 0.0], "REENTER": [0.0, 0.0]},
        index=dates,
    )
    relief_signal = pd.Series([True, True], index=dates)

    _weights, decisions = _select_actions_stateful(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.5,
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
        relief_signal=relief_signal,
    )

    assert (decisions["action"] == "KEEP").all()
    assert (decisions["relief_triggered"] == False).all()  # noqa: E712


def test_relief_gate_min_holding_days_suppresses_consecutive_forced_reenters() -> None:
    dates = pd.bdate_range("2026-01-01", periods=4)
    target_weights = pd.DataFrame([BASE_WEIGHTS] * 4, index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0] * 4,
            "NO_ADD": [0.0] * 4,
            "CAP10": [0.005, 0.0, 0.0, 0.0],
            # REENTER never wins on its own -- data-starved, as in production.
            "REENTER": [0.0, -0.01, -0.01, -0.01],
        },
        index=dates,
    )
    # Relief holds every day after the CAP10 -- without a cooldown this would
    # force REENTER on days 2-4 too (turnover-heavy prototype behavior).
    relief_signal = pd.Series([False, True, True, True], index=dates)

    weights, decisions = _select_actions_stateful(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.5,
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
        relief_signal=relief_signal,
        relief_min_holding_days=1,
    )

    assert decisions.iloc[0]["action"] == "CAP10"
    assert decisions.iloc[1]["action"] == "REENTER"
    assert decisions.iloc[1]["relief_triggered"] == True  # noqa: E712
    # Day 3 (index 2): still below a2118, relief still True, but the 1-day
    # cooldown since day 2's relief action isn't satisfied yet.
    assert decisions.iloc[2]["action"] == "KEEP"
    assert decisions.iloc[2]["relief_triggered"] == False  # noqa: E712
    # Day 4 (index 3): cooldown satisfied -- fires again.
    assert decisions.iloc[3]["action"] == "REENTER"
    assert decisions.iloc[3]["relief_triggered"] == True  # noqa: E712
    assert weights.iloc[3]["00631L.TW"] > weights.iloc[1]["00631L.TW"]


def test_relief_gate_min_gap_suppresses_no_op_reenter_against_a_tiny_residual() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    relief_signal = pd.Series([False, True], index=dates)

    # Day 1: a tiny CAP10 (predicted regret just above edge_threshold) with a
    # small partial-adjustment fraction leaves only a near-noise residual gap
    # by day 2 -- exactly the "already basically at target" case found in
    # live_2024_2026/active_2025_2026 (see Part H4 of the handoff doc).
    predicted_tiny_cap = pd.DataFrame(
        {"KEEP": [0.0, 0.0], "NO_ADD": [0.0, 0.0], "CAP10": [0.0021, 0.0], "REENTER": [0.0, -0.01]},
        index=dates,
    )
    _weights, decisions_tiny = _select_actions_stateful(
        target_weights,
        predicted_tiny_cap,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.01,  # tiny partial step -> tiny residual gap
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
        relief_signal=relief_signal,
        relief_min_gap=0.01,
    )
    assert decisions_tiny.iloc[0]["action"] == "CAP10"
    gap = decisions_tiny.iloc[0]["base_00631l_weight"] - decisions_tiny.iloc[0]["final_00631l_weight"]
    assert gap < 0.01  # confirm the residual really is below the min-gap threshold
    # Day 2: below a2118 by only that tiny residual, relief signal True, but
    # the gap doesn't clear relief_min_gap=0.01 -- must not force REENTER.
    assert decisions_tiny.iloc[1]["action"] == "KEEP"
    assert decisions_tiny.iloc[1]["relief_triggered"] == False  # noqa: E712

    # Same setup but relief_min_gap=0.0 (old behavior) -- should fire.
    _weights2, decisions_no_min_gap = _select_actions_stateful(
        target_weights,
        predicted_tiny_cap,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.01,
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
        relief_signal=relief_signal,
        relief_min_gap=0.0,
    )
    assert decisions_no_min_gap.iloc[1]["action"] == "REENTER"
    assert decisions_no_min_gap.iloc[1]["relief_triggered"] == True  # noqa: E712


def test_relief_gate_respects_action_allowed_gate() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    target_weights = pd.DataFrame([BASE_WEIGHTS, BASE_WEIGHTS], index=dates)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "NO_ADD": [0.0, 0.0],
            "CAP10": [0.005, 0.0],
            "REENTER": [0.0, -0.01],
        },
        index=dates,
    )
    relief_signal = pd.Series([False, True], index=dates)
    action_allowed = pd.Series([True, False], index=dates)

    _weights, decisions = _select_actions_stateful(
        target_weights,
        predicted,
        edge_threshold=0.002,
        regret_clip=0.03,
        adjustment_fraction=0.5,
        turnover_cap=0.10,
        cap10=0.10,
        reenter_edge_threshold=-0.0005,
        action_allowed=action_allowed,
        relief_signal=relief_signal,
    )

    assert decisions.iloc[0]["action"] == "CAP10"
    # Day 2 is below-a2118 and relief=True, but action_allowed=False -- must
    # stay KEEP, not be force-reentered.
    assert decisions.iloc[1]["action"] == "KEEP"
    assert decisions.iloc[1]["relief_triggered"] == False  # noqa: E712


def test_build_calibration_pairs_excludes_cold_start_days() -> None:
    dates = pd.bdate_range("2026-01-01", periods=8)
    labels = pd.DataFrame(
        {
            "KEEP": [0.0] * 8,
            "NO_ADD": [10.0] * 8,
            "CAP10": [-10.0] * 8,
            "REENTER": [0.5] * 8,
        },
        index=dates,
    )
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0] * 8,
            "NO_ADD": [0.01] * 8,
            "CAP10": [-0.01] * 8,
            "REENTER": [0.0] * 8,
        },
        index=dates,
    )

    pairs = _build_calibration_pairs(
        labels,
        predicted,
        min_train_days=5,
        train_window_days=0,
    )

    # Day index 0-4 (positions with fewer than 5 prior labeled days) must be
    # excluded -- same warm-up `_predict_action_regrets` itself requires.
    seen_dates = {row["date"] for row in pairs}
    for excluded_dt in dates[:5]:
        assert str(excluded_dt.date()) not in seen_dates
    for included_dt in dates[5:]:
        assert str(included_dt.date()) in seen_dates


def test_build_calibration_pairs_excludes_keep_and_pairs_correctly() -> None:
    dates = pd.bdate_range("2026-01-01", periods=6)
    labels = pd.DataFrame(
        {
            "KEEP": [0.0] * 6,
            "NO_ADD": [1.0] * 6,
            "CAP10": [-1.0] * 6,
            "REENTER": [0.2] * 6,
        },
        index=dates,
    )
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0] * 6,
            "NO_ADD": [0.02] * 6,
            "CAP10": [-0.02] * 6,
            "REENTER": [0.01] * 6,
        },
        index=dates,
    )

    pairs = _build_calibration_pairs(
        labels,
        predicted,
        min_train_days=2,
        train_window_days=0,
    )

    actions_seen = {row["action"] for row in pairs}
    assert "KEEP" not in actions_seen
    assert actions_seen == {"NO_ADD", "CAP10", "REENTER"}

    last_date = str(dates[-1].date())
    no_add_row = next(row for row in pairs if row["date"] == last_date and row["action"] == "NO_ADD")
    assert no_add_row["predicted_regret"] == pytest.approx(0.02)
    assert no_add_row["realized_regret"] == pytest.approx(1.0)


def test_build_calibration_pairs_skips_dates_without_realized_label() -> None:
    dates = pd.bdate_range("2026-01-01", periods=6)
    # labels only covers the first 4 dates -- the tail 2 days lack a full
    # forward horizon in the real evaluator (see _build_action_labels).
    labels = pd.DataFrame(
        {
            "KEEP": [0.0] * 4,
            "NO_ADD": [1.0] * 4,
            "CAP10": [-1.0] * 4,
            "REENTER": [0.2] * 4,
        },
        index=dates[:4],
    )
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0] * 6,
            "NO_ADD": [0.02] * 6,
            "CAP10": [-0.02] * 6,
            "REENTER": [0.01] * 6,
        },
        index=dates,
    )

    pairs = _build_calibration_pairs(
        labels,
        predicted,
        min_train_days=1,
        train_window_days=0,
    )

    seen_dates = {row["date"] for row in pairs}
    for excluded_dt in dates[4:]:
        assert str(excluded_dt.date()) not in seen_dates


def test_build_calibration_pairs_attaches_total_risk_score_when_features_given() -> None:
    dates = pd.bdate_range("2026-01-01", periods=6)
    labels = pd.DataFrame(
        {
            "KEEP": [0.0] * 6,
            "NO_ADD": [1.0] * 6,
            "CAP10": [-1.0] * 6,
            "REENTER": [0.2] * 6,
        },
        index=dates,
    )
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0] * 6,
            "NO_ADD": [0.02] * 6,
            "CAP10": [-0.02] * 6,
            "REENTER": [0.01] * 6,
        },
        index=dates,
    )
    features = pd.DataFrame({"total_risk_score": [0, 1, 2, 3, 4, 5]}, index=dates)

    pairs_with_features = _build_calibration_pairs(
        labels, predicted, min_train_days=2, train_window_days=0, features=features
    )
    pairs_without_features = _build_calibration_pairs(
        labels, predicted, min_train_days=2, train_window_days=0
    )

    assert all("total_risk_score" in row for row in pairs_with_features)
    last_date = str(dates[-1].date())
    row = next(r for r in pairs_with_features if r["date"] == last_date and r["action"] == "CAP10")
    assert row["total_risk_score"] == pytest.approx(5.0)
    assert all("total_risk_score" not in row for row in pairs_without_features)
