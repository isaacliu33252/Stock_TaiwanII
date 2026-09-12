from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.event_aware_execution_quality import (
    append_event_aware_execution_quality_log,
    build_event_aware_execution_quality,
)


def _live(
    *,
    stale: int = 0,
    allowed: bool = True,
    weights: dict[str, float] | None = None,
    total_risk: int = 2,
    tail_risk: int = 0,
    ma_gap: float = 0.04,
    momentum: float = 0.03,
    drawdown: float = -0.03,
) -> dict:
    return {
        "success": True,
        "data": {
            "requested_as_of_date": "2026-08-10",
            "actual_data_date": "2026-08-07",
            "business_stale_days": stale,
            "execution_allowed": allowed,
            "execution_regime": "golden1",
            "target_weights": weights or {"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.0, "cash": 0.7},
            "latest_features": {
                "total_risk_score": total_risk,
                "tail_risk_score": tail_risk,
                "ma_gap": ma_gap,
                "exit_momentum_5d": momentum,
                "drawdown": drawdown,
            },
            "market_state": {"state": "choppy_range_low_risk"},
        },
    }


def _plan(current: dict[str, int] | None = None, staged: list[dict] | None = None) -> dict:
    return {
        "success": True,
        "data": {
            "current_total_assets": 1000000.0,
            "current_cash_input": 500000.0,
            "current_holdings": current or {"0050.TW": 3000, "00631L.TW": 0, "00632R.TW": 0, "00679B.TWO": 0},
            "current_prices": {"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0, "00679B.TWO": 26.0},
            "staged_buys": staged or [],
            "guard_impact_summary": {"active_guard_names": [], "blocked_guard_names": []},
        },
    }


def test_event_quality_blocks_when_guard_or_freshness_fails() -> None:
    report = build_event_aware_execution_quality(_live(stale=2, allowed=False), _plan(), {})

    assert report["status"] == "blocked_review_only"
    assert "execution_guard_satisfied" in report["blockers"]
    assert "source_fresh_enough" in report["blockers"]
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False


def test_event_quality_warns_on_00631l_add_after_extended_move() -> None:
    report = build_event_aware_execution_quality(
        _live(
            weights={"0050.TW": 0.3, "00631L.TW": 0.2, "00632R.TW": 0.0, "cash": 0.5},
            ma_gap=0.10,
            momentum=0.12,
            drawdown=-0.02,
        ),
        _plan(current={"0050.TW": 3000, "00631L.TW": 0, "00632R.TW": 0, "00679B.TWO": 0}),
        {"thesis_class": "maintain_unlevered_beta_preferred"},
    )

    assert report["status"] == "caution_review_only"
    assert "no_00631l_add_when_extended" in report["warnings"]
    assert "00631l_add_has_reentry_context" in report["warnings"]


def test_event_quality_blocks_00632r_add_without_short_term_thesis() -> None:
    report = build_event_aware_execution_quality(
        _live(weights={"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.25, "cash": 0.45}),
        _plan(current={"0050.TW": 3000, "00631L.TW": 0, "00632R.TW": 0, "00679B.TWO": 0}),
        {"thesis_class": "maintain_unlevered_beta_preferred"},
    )

    assert report["status"] == "blocked_review_only"
    assert "00632r_open_is_review_gated" in report["blockers"]
    assert "no_large_00632r_chase_without_staging" in report["warnings"]
    assert report["decision"]["allow_00632r_open"] is False


def test_event_quality_warns_large_00632r_add_when_liquidity_feedback_is_risky() -> None:
    report = build_event_aware_execution_quality(
        _live(weights={"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.25, "cash": 0.45}),
        _plan(
            current={"0050.TW": 3000, "00631L.TW": 0, "00632R.TW": 0, "00679B.TWO": 0},
            staged=[{"ticker": "00632R.TW"}],
        ),
        {"thesis_class": "short_term_inverse_hedge_review_only"},
        {
            "summary": {"ready_for_manual_review": True},
            "event_metrics": {"00632R.TW": {"fwd_return_20d": {"negative_rate": 0.75}}},
        },
    )

    assert report["status"] == "caution_review_only"
    assert "large_00632r_add_respects_liquidity_feedback_watch" in report["warnings"]
    assert report["inputs"]["liquidity_feedback_backtest_ready"] is True
    assert report["decision"]["target_weight_change_allowed"] is False


def test_event_quality_log_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "quality.jsonl"
    report = build_event_aware_execution_quality(_live(), _plan(), {})

    append_event_aware_execution_quality_log(log, report, date="2026-08-07")
    append_event_aware_execution_quality_log(log, report | {"quality_score": 0.1}, date="2026-08-07")

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["quality_score"] == 0.1
