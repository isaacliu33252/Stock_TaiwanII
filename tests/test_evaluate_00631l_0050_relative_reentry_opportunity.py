import numpy as np
import pandas as pd
import pytest
import json

from scripts.evaluate.evaluate_00631l_0050_relative_reentry_opportunity import (
    DEFAULT_ACTIONS,
    _parse_shift_step,
    _relative_weights,
    build_relative_features,
    build_relative_labels,
    build_permission_labels,
    predict_permission_probability,
    risk_up_permission_allowed,
    select_relative_actions,
    slow_bear_reentry_allowed,
)


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=30)
    return pd.DataFrame(
        {
            "0050.TW": np.linspace(100.0, 102.0, len(dates)),
            "00631L.TW": np.linspace(100.0, 125.0, len(dates)),
            "00632R.TW": [10.0] * len(dates),
            "00679B.TWO": [30.0] * len(dates),
        },
        index=dates,
    )


def test_parse_shift_step_and_weights() -> None:
    assert _parse_shift_step("KEEP") is None
    assert _parse_shift_step("SHIFT_00631L_5") == pytest.approx(0.05)

    weights = _relative_weights(0.05)

    assert weights["0050.TW"] == pytest.approx(0.95)
    assert weights["00631L.TW"] == pytest.approx(0.05)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_relative_labels_reward_shift_when_00631l_outperforms() -> None:
    labels = build_relative_labels(
        _prices(),
        horizon=20,
        lambda_mdd=0.0,
        gamma_turnover=0.0,
        eta_missed_rebound=0.0,
        actions=DEFAULT_ACTIONS,
    )

    assert labels.iloc[0]["KEEP"] == pytest.approx(0.0)
    assert labels.iloc[0]["SHIFT_00631L_2"] > 0.0
    assert labels.iloc[0]["SHIFT_00631L_5"] > labels.iloc[0]["SHIFT_00631L_2"]
    assert labels.iloc[0]["SHIFT_00631L_10"] > labels.iloc[0]["SHIFT_00631L_5"]


def test_build_relative_features_contains_spread_columns() -> None:
    features = build_relative_features(_prices())

    assert "spread_00631l_0050_5d" in features.columns
    assert features.iloc[6]["spread_00631l_0050_5d"] > 0.0


def test_select_relative_actions_uses_edge_and_reliability_gate() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "SHIFT_00631L_2": [0.0, 0.001],
            "SHIFT_00631L_5": [0.0, 0.002],
            "SHIFT_00631L_10": [0.0, 0.0005],
        },
        index=dates,
    )
    reliability = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "SHIFT_00631L_2": [0.0, 0.0],
            "SHIFT_00631L_5": [0.0, 0.9],
            "SHIFT_00631L_10": [0.0, 0.0],
        },
        index=dates,
    )

    decisions = select_relative_actions(
        predicted,
        edge_threshold=0.0005,
        regret_clip=0.02,
        actions=DEFAULT_ACTIONS,
        reliability_percentiles=reliability,
        max_error_percentile=0.7,
    )

    assert decisions.iloc[0]["action"] == "KEEP"
    assert decisions.iloc[1]["candidate_action_before_reliability"] == "SHIFT_00631L_5"
    assert decisions.iloc[1]["action"] == "KEEP"
    assert bool(decisions.iloc[1]["reliability_gate_pass"]) is False

    decisions_no_reliability = select_relative_actions(
        predicted,
        edge_threshold=0.0005,
        regret_clip=0.02,
        actions=DEFAULT_ACTIONS,
    )
    assert decisions_no_reliability.iloc[1]["action"] == "SHIFT_00631L_5"


def test_slow_bear_gate_blocks_only_when_all_conditions_match() -> None:
    dates = pd.bdate_range("2026-01-01", periods=4)
    features = pd.DataFrame(
        {
            "drawdown_0050_60d": [-0.09, -0.09, -0.03, -0.03],
            "ret_0050_20d": [-0.02, 0.01, -0.02, -0.04],
            "spread_00631l_0050_20d": [-0.03, -0.03, -0.03, -0.03],
        },
        index=dates,
    )

    allowed, reasons = slow_bear_reentry_allowed(
        features,
        enabled=True,
        drawdown_0050_60d_max=-0.08,
        ret_0050_20d_max=0.0,
        spread_00631l_0050_20d_max=0.0,
        momentum_ret_0050_20d_max=-0.03,
    )

    assert allowed.tolist() == [False, True, True, False]
    assert str(reasons.iloc[0]).startswith("slow_bear_block:deep_drawdown:")
    assert pd.isna(reasons.iloc[1])
    assert str(reasons.iloc[3]).startswith("slow_bear_block:momentum_breakdown:")


def test_select_relative_actions_respects_slow_bear_action_allowed_gate() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    predicted = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0],
            "SHIFT_00631L_2": [0.0, 0.0],
            "SHIFT_00631L_5": [0.002, 0.002],
            "SHIFT_00631L_10": [0.0, 0.0],
        },
        index=dates,
    )
    allowed = pd.Series([False, True], index=dates)
    reasons = pd.Series(["slow_bear_block:test", None], index=dates)

    decisions = select_relative_actions(
        predicted,
        edge_threshold=0.0005,
        regret_clip=0.02,
        actions=DEFAULT_ACTIONS,
        action_allowed=allowed,
        block_reasons=reasons,
        permission_probability=pd.Series([0.40, 0.80], index=dates),
    )

    assert decisions.iloc[0]["candidate_action_before_reliability"] == "SHIFT_00631L_5"
    assert decisions.iloc[0]["action"] == "KEEP"
    assert bool(decisions.iloc[0]["action_allowed"]) is False
    assert decisions.iloc[0]["block_reason"] == "slow_bear_block:test"
    assert decisions.iloc[0]["risk_up_permission_probability"] == pytest.approx(0.40)
    assert decisions.iloc[1]["action"] == "SHIFT_00631L_5"


def test_permission_labels_mark_positive_realized_edge() -> None:
    labels = pd.DataFrame(
        {
            "KEEP": [0.0, 0.0, 0.0],
            "SHIFT_00631L_5": [-0.001, 0.0, 0.002],
        },
        index=pd.bdate_range("2026-01-01", periods=3),
    )

    permission = build_permission_labels(labels, action="SHIFT_00631L_5", min_realized_edge=0.0)

    assert permission.tolist() == [0.0, 0.0, 1.0]


def test_predict_permission_probability_uses_only_past_rows() -> None:
    dates = pd.bdate_range("2026-01-01", periods=8)
    features = pd.DataFrame({col: range(8) for col in [
        "prob_up_h1",
        "prob_up_h5",
        "prob_up_h20",
        "prob_fwd_mdd_gt5_h20",
        "prob_fwd_gain_gt5_h20",
        "confidence",
        "ret_0050_1d",
        "ret_0050_5d",
        "ret_0050_20d",
        "ret_00631l_1d",
        "ret_00631l_5d",
        "ret_00631l_20d",
        "spread_00631l_0050_1d",
        "spread_00631l_0050_5d",
        "spread_00631l_0050_20d",
        "vol_0050_20d",
        "vol_00631l_20d",
        "drawdown_0050_60d",
        "drawdown_00631l_60d",
    ]}, index=dates, dtype=float)
    permission_labels = pd.Series([0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=dates)

    prob = predict_permission_probability(
        features,
        permission_labels,
        min_train_days=5,
        train_window_days=0,
        ridge_alpha=1.0,
    )

    assert prob.iloc[4] == pytest.approx(0.5)
    assert 0.0 <= prob.iloc[5] <= 1.0


def test_risk_up_permission_allowed_returns_reasons() -> None:
    dates = pd.bdate_range("2026-01-01", periods=3)
    probability = pd.Series([0.40, 0.55, 0.80], index=dates)

    allowed, reasons = risk_up_permission_allowed(probability, enabled=True, min_probability=0.55)

    assert allowed.tolist() == [False, True, True]
    assert str(reasons.iloc[0]).startswith("risk_up_permission_block:")
    assert pd.isna(reasons.iloc[1])


def test_cli_writes_latest_output(tmp_path) -> None:
    import subprocess
    import sys

    output = tmp_path / "result.json"
    latest = tmp_path / "latest" / "relative_reentry_opportunity_shadow.json"
    windows = "smoke:2026-01-02:2026-02-20:results/ncf_00631l_panel_latest_20260804.csv:custom"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate/evaluate_00631l_0050_relative_reentry_opportunity.py",
            "--windows",
            windows,
            "--min-train-days",
            "5",
            "--output",
            str(output),
            "--latest-output",
            str(latest),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert output.exists()
    assert latest.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == json.loads(latest.read_text(encoding="utf-8"))
    window = payload["results"][0]
    assert window["latest_inference"]["enabled"] is True
    assert window["latest_inference"]["feature_only_decision_rows"] > 0
    assert window["recent_decisions"][-1]["date"] == window["window"]["end"]
    assert "Latest JSON:" in completed.stdout
