from __future__ import annotations

from scripts.evaluate.evaluate_00631l_compounding_execution_replay_shadow import replay_compounding_execution_plan


def _plan() -> dict:
    return {
        "actual_data_date": "2026-07-15",
        "execution_regime": "golden1",
        "current_holdings": {"00631L.TW": 100},
        "theoretical_target_shares": {"00631L.TW": 200},
        "staged_target_shares_before_guards": {"00631L.TW": 140},
        "target_shares": {"00631L.TW": 140},
        "current_prices": {"00631L.TW": 50.0},
        "pre_trade_guards": [],
        "execution_guard_reasons": [],
    }


def test_trend_persistent_replay_fast_reenter_uses_theoretical_target() -> None:
    out = replay_compounding_execution_plan(
        _plan(),
        {"date": "2026-07-15", "compounding_regime": "TREND_PERSISTENT"},
        baseline_add_fraction=0.4,
        trend_persistent_add_fraction=1.0,
    )

    assert out["raw_action"] == "FAST_REENTER_CANDIDATE"
    assert out["recommended_action"] == "FAST_REENTER_CANDIDATE"
    assert out["shadow_target_shares_before_hard_guards"] == 200
    assert out["shadow_delta_shares_before_hard_guards"] == 100


def test_mean_reverting_replay_blocks_incremental_add() -> None:
    out = replay_compounding_execution_plan(
        _plan(),
        {"date": "2026-07-15", "compounding_regime": "MEAN_REVERTING"},
        baseline_add_fraction=0.4,
        mean_reversion_add_fraction=0.0,
    )

    assert out["raw_action"] == "SLOW_ADD"
    assert out["recommended_action"] == "SLOW_ADD"
    assert out["shadow_target_shares_before_hard_guards"] == 100
    assert out["shadow_delta_shares_before_hard_guards"] == 0


def test_hard_blocker_overrides_trend_persistent_replay() -> None:
    plan = _plan()
    plan["pre_trade_guards"] = [{"name": "volatility_gate_no_00631l_add", "status": "blocked"}]
    plan["execution_guard_reasons"] = ["manual review required"]

    out = replay_compounding_execution_plan(
        plan,
        {"date": "2026-07-15", "compounding_regime": "TREND_PERSISTENT"},
        baseline_add_fraction=0.4,
        trend_persistent_add_fraction=1.0,
    )

    assert out["raw_action"] == "FAST_REENTER_CANDIDATE"
    assert out["recommended_action"] == "BLOCKED_BY_HARD_GUARD"
    assert "manual review required" in out["hard_blockers"]
    assert "blocked pre-trade guard: volatility_gate_no_00631l_add" in out["hard_blockers"]


def test_ce20_negative_weak_trend_gate_reduces_fast_reentry_fraction() -> None:
    out = replay_compounding_execution_plan(
        _plan(),
        {
            "date": "2026-07-15",
            "compounding_regime": "TREND_PERSISTENT",
            "compounding_effect_20d": -0.01,
        },
        baseline_add_fraction=0.4,
        trend_persistent_add_fraction=1.0,
        weak_trend_edge_gate="ce20_negative",
        weak_trend_add_fraction=0.9,
    )

    assert out["raw_action"] == "FAST_REENTER_CANDIDATE"
    assert out["weak_trend_edge_active"] is True
    assert out["allowed_fraction_for_regime"] == 0.9
    assert out["shadow_target_shares_before_hard_guards"] == 190
