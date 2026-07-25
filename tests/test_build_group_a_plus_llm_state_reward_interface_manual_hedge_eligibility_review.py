from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _windowed(path: Path) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "latest_rolling_by_target": {
                    "00632R.TW": {
                        "63": {"latest_correlation": -0.98, "latest_beta": -1.01},
                        "126": {"latest_correlation": -0.97, "latest_beta": -1.00},
                        "252": {"latest_correlation": -0.96, "latest_beta": -0.99},
                    }
                },
                "recent_0050_drawdown_extreme_days": 1,
                "recent_0050_reward_extreme_days": 1,
            },
            "stress_window_relationships": [
                {
                    "name": "taiwan_2026_recent",
                    "relationships": [
                        {
                            "target": "00632R.TW",
                            "correlation": -0.98,
                            "beta": -1.02,
                            "relationship": "high_negative_benchmark_correlation",
                        }
                    ],
                }
            ],
            "decision": {
                "outputs_actions": False,
                "outputs_target_weights": False,
                "allow_00632r_open": False,
            },
        },
    )


def _letf(path: Path, *, live_ready: bool = False, tail_ready: bool = False) -> Path:
    return _write(
        path,
        {
            "status": "blocked" if not live_ready else "available_for_manual_review",
            "decision": {
                "allow_00632r_open": live_ready,
                "allow_00631l_add": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
            },
            "parameter_threshold_review": {
                "checks": {
                    "00632r_60d_abs_beta_error_ceiling": {"value": 0.02, "threshold": 0.1, "passed": True},
                    "00632r_60d_correlation_ceiling": {"value": -0.98, "threshold": -0.95, "passed": True},
                    "00632r_30d_p05_tracking_error_floor": {
                        "value": -0.02 if tail_ready else -0.04,
                        "threshold": -0.03,
                        "passed": tail_ready,
                    },
                    "effective_fee_proxy_independently_validated": {
                        "value": live_ready,
                        "threshold": True,
                        "passed": live_ready,
                    },
                    "live_hedge_policy_validated": {
                        "value": live_ready,
                        "threshold": True,
                        "passed": live_ready,
                    },
                }
            },
        },
    )


def _market(path: Path, *, ready: bool = False) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_review" if ready else "blocked",
            "decision": {
                "target_weight_change_allowed": ready,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
            },
        },
    )


def _research(path: Path, *, ready: bool = False) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_review" if ready else "blocked",
            "decision": {
                "allow_00632r_open": ready,
                "allow_00631l_add": False,
                "target_weight_change_allowed": ready,
                "auto_rebalance_allowed": False,
            },
        },
    )


def test_review_blocks_manual_hedge_when_live_gates_fail(tmp_path: Path) -> None:
    review = build_review(
        windowed_stability_path=_windowed(tmp_path / "windowed.json"),
        letf_tracking_path=_letf(tmp_path / "letf.json", live_ready=False, tail_ready=False),
        market_impact_path=_market(tmp_path / "market.json", ready=False),
        research_shadow_path=_research(tmp_path / "research.json", ready=False),
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review"
    assert review["status"] == "blocked"
    assert review["summary"]["hedge_evidence_available"] is True
    assert review["summary"]["manual_hedge_discussion_allowed"] is False
    assert "00632r_tail_tracking_error_gate_failed" in review["blocking_reasons"]
    assert "live_hedge_policy_not_validated" in review["blocking_reasons"]
    assert "market_impact_blocks_trade_or_weight_change" in review["blocking_reasons"]
    assert "research_shadow_blocks_00632r_open" in review["blocking_reasons"]
    assert review["decision"]["manual_hedge_discussion_blocked"] is True
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_review_can_allow_manual_discussion_without_live_order_permission(tmp_path: Path) -> None:
    review = build_review(
        windowed_stability_path=_windowed(tmp_path / "windowed.json"),
        letf_tracking_path=_letf(tmp_path / "letf.json", live_ready=True, tail_ready=True),
        market_impact_path=_market(tmp_path / "market.json", ready=True),
        research_shadow_path=_research(tmp_path / "research.json", ready=True),
        as_of="2026-07-20",
    )

    assert review["status"] == "eligible_for_manual_hedge_discussion"
    assert review["summary"]["hedge_evidence_available"] is True
    assert review["summary"]["manual_hedge_discussion_allowed"] is True
    assert review["blocking_reasons"] == []
    assert review["decision"]["manual_hedge_discussion_allowed"] is True
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "manual_hedge.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_manual_hedge_eligibility_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
