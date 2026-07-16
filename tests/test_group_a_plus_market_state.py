from __future__ import annotations

import json
import tempfile
from pathlib import Path

from group_a_plus.operations.market_state import (
    append_market_state_shadow_log,
    classify_market_state,
)


def test_bull_trend_can_split_acceleration_and_late_overheat() -> None:
    acceleration = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.06,
            "drawdown": -0.01,
            "exit_momentum_5d": 0.03,
            "total_risk_score": 2,
            "tail_risk_score": 0,
        },
    )
    overheat = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.14,
            "drawdown": -0.02,
            "exit_momentum_5d": 0.02,
            "total_risk_score": 6,
            "tail_risk_score": 0,
        },
    )

    assert acceleration["bucket"] == "bull_trend"
    assert acceleration["state"] == "bull_acceleration"
    assert acceleration["allocation_bias"] == "00631L high weight"
    assert overheat["bucket"] == "bull_trend"
    assert overheat["state"] == "late_bull_overheat"


def test_bull_pullback_splits_shallow_and_deep() -> None:
    shallow = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.01,
            "drawdown": -0.04,
            "exit_momentum_5d": -0.01,
            "total_risk_score": 4,
            "tail_risk_score": 0,
        },
    )
    deep = classify_market_state(
        "golden1",
        {
            "ma_gap": -0.01,
            "drawdown": -0.08,
            "exit_momentum_5d": -0.02,
            "total_risk_score": 5,
            "tail_risk_score": 0,
        },
    )

    assert shallow["bucket"] == "bull_pullback"
    assert shallow["state"] == "bull_pullback_shallow"
    assert deep["bucket"] == "bull_pullback"
    assert deep["state"] == "bull_pullback_deep"


def test_recovery_splits_early_and_confirmed() -> None:
    early = classify_market_state(
        "group_a_plus_recovery",
        {
            "ma_gap": 0.0,
            "drawdown": -0.07,
            "exit_momentum_5d": 0.005,
            "total_risk_score": 5,
            "tail_risk_score": 0,
        },
    )
    confirmed = classify_market_state(
        "group_a_plus_recovery",
        {
            "ma_gap": 0.02,
            "drawdown": -0.04,
            "exit_momentum_5d": 0.02,
            "total_risk_score": 4,
            "tail_risk_score": 0,
        },
    )

    assert early["state"] == "recovery_early"
    assert confirmed["state"] == "recovery_confirmed"


def test_choppy_range_splits_by_risk_and_alignment() -> None:
    low_risk = classify_market_state(
        "golden1",
        {
            "ma_gap": -0.01,
            "drawdown": -0.04,
            "exit_momentum_5d": 0.01,
            "total_risk_score": 3,
            "tail_risk_score": 0,
        },
    )
    high_risk = classify_market_state(
        "golden1",
        {
            "ma_gap": -0.04,
            "drawdown": -0.05,
            "exit_momentum_5d": 0.0,
            "total_risk_score": 7,
            "tail_risk_score": 0,
        },
        signal_alignment={"alignment": "bearish_alignment", "dominant_direction": "bearish"},
    )

    assert low_risk["state"] == "choppy_range_low_risk"
    assert high_risk["state"] == "choppy_range_high_risk"


def test_active_late_bull_hedge_always_classifies_as_overheat() -> None:
    """2026-07-04 audit fix: a live ncf_late_bull_hedge/soft regime must never
    fall through to bull_acceleration/bull_trend, whose allocation_bias
    ("00631L high weight") would contradict the de-leverage actually being
    executed that day. Before the fix, ma_gap in (0.10, 0.12) combined with
    total_risk_score < 6 hit this exact contradiction.
    """
    hedge = classify_market_state(
        "ncf_late_bull_hedge",
        {
            "ma_gap": 0.11,
            "drawdown": -0.02,
            "exit_momentum_5d": 0.01,
            "total_risk_score": 3,
            "tail_risk_score": 0,
        },
    )
    soft_hedge = classify_market_state(
        "ncf_late_bull_hedge_soft",
        {
            "ma_gap": 0.105,
            "drawdown": -0.01,
            "exit_momentum_5d": 0.02,
            "total_risk_score": 2,
            "tail_risk_score": 0,
        },
    )

    assert hedge["state"] == "late_bull_overheat"
    assert hedge["allocation_bias"] == "0050 core with reduced 00631L"
    assert soft_hedge["state"] == "late_bull_overheat"


def test_defensive_and_crash_states_remain_separate() -> None:
    breakdown = classify_market_state(
        "group_a_plus_defensive",
        {
            "ma_gap": -0.03,
            "drawdown": -0.09,
            "exit_momentum_5d": -0.02,
            "total_risk_score": 7,
            "tail_risk_score": 0,
        },
    )
    crash = classify_market_state(
        "group_a_plus_defensive",
        {
            "ma_gap": -0.05,
            "drawdown": -0.07,
            "exit_momentum_5d": -0.03,
            "total_risk_score": 9,
            "tail_risk_score": 1,
        },
    )

    assert breakdown["state"] == "bear_breakdown"
    assert breakdown["allocation_bias"] == "cash"
    assert crash["state"] == "crash_risk"
    assert crash["allocation_bias"] == "00632R hedge or full defense"


def test_crash_risk_can_fire_while_execution_regime_stays_golden1_by_design() -> None:
    """2026-07-04 Fable audit, decision item A: replaying 2025-01-02 ~
    2026-07-02 found 9 days where this classifier scored `crash_risk`
    (allocation_bias "00632R hedge or full defense") while a2118's actual
    `execution_regime` was still `golden1` (full leverage, no hedge). This
    is not a bug -- `classify_market_state` is diagnostic-only and its
    return value has no `target_weights`/`target_shares` key, so it cannot
    change what a2118 actually does (see this module's docstring). This
    test pins that the disagreement itself is still reproducible: a
    tail-risk spike (tail_risk_score >= 2) scores `crash_risk` regardless
    of the coarse execution_regime label passed in, including "golden1".
    If a future change makes this disagreement disappear silently (e.g. by
    making the classifier defer to execution_regime), that would be a
    real behavior change to review, not a silent drift -- hence pinning it
    here rather than leaving it as an unrecorded audit observation.
    """
    crash_during_golden1 = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.03,
            "drawdown": -0.04,
            "exit_momentum_5d": -0.01,
            "total_risk_score": 5,
            "tail_risk_score": 2,
        },
    )

    assert crash_during_golden1["state"] == "crash_risk"
    assert crash_during_golden1["allocation_bias"] == "00632R hedge or full defense"
    assert crash_during_golden1["inputs"]["execution_regime"] == "golden1"
    assert "target_weights" not in crash_during_golden1
    assert "target_shares" not in crash_during_golden1


def test_append_market_state_shadow_log_is_idempotent_per_date() -> None:
    """2026-07-09: the a2118-vs-market_state arbitration decision (see this
    module's docstring) was made on only 9-10 real crash_risk trigger days
    because classify_market_state's output was never logged historically.
    This log closes that gap; mirrors garch_regime_shadow's and
    signal_alignment's idempotent-per-date append pattern so re-running
    daily_signal same-day doesn't skew the forward-observation count."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "market_state_shadow_log.jsonl"
        day1 = classify_market_state(
            "golden1",
            {"ma_gap": 0.03, "drawdown": -0.04, "exit_momentum_5d": -0.01,
             "total_risk_score": 5, "tail_risk_score": 2},
        )
        day2 = classify_market_state(
            "golden1",
            {"ma_gap": 0.06, "drawdown": -0.01, "exit_momentum_5d": 0.03,
             "total_risk_score": 2, "tail_risk_score": 0},
        )
        day1_rerun = classify_market_state(
            "golden1",
            {"ma_gap": 0.14, "drawdown": -0.02, "exit_momentum_5d": 0.02,
             "total_risk_score": 6, "tail_risk_score": 0},
        )

        append_market_state_shadow_log(log_path, day1, date="2026-07-01", execution_regime="golden1")
        append_market_state_shadow_log(log_path, day2, date="2026-07-02", execution_regime="golden1")
        append_market_state_shadow_log(log_path, day1_rerun, date="2026-07-01", execution_regime="golden1")

        lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(lines) == 2
    by_date = {row["date"]: row for row in lines}
    assert by_date["2026-07-01"]["state"] == "late_bull_overheat"
    assert by_date["2026-07-02"]["state"] == "bull_acceleration"
    assert by_date["2026-07-01"]["logged_execution_regime"] == "golden1"
