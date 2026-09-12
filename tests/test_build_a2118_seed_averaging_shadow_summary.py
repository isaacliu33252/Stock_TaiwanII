from __future__ import annotations

import copy

from scripts.evaluate.build_a2118_seed_averaging_shadow_summary import build_summary


def _report() -> dict:
    return {
        "individual": {
            "42": {"full": {"sharpe": 1.91, "max_drawdown": -0.29}, "sub_periods": {}},
            "43": {"full": {"sharpe": 1.96, "max_drawdown": -0.30}, "sub_periods": {}},
            "45": {"full": {"sharpe": 1.82, "max_drawdown": -0.36}, "sub_periods": {}},
        },
        "ensembles": {
            "42+43+44": {
                "full": {"sharpe": 1.955, "max_drawdown": -0.288},
                "sub_periods": {
                    "2024": {"sharpe": 1.5, "max_drawdown": -0.26},
                    "2025_2026": {"sharpe": 2.3, "max_drawdown": -0.27},
                },
                "num_trades": 71,
            },
        },
    }


def test_seed_averaging_summary_passes_when_ensemble_near_best_and_reduces_tail() -> None:
    result = build_summary(_report())

    assert result["decision"]["shadow_gate"] == "pass"
    assert result["decision"]["shadow_queue"] == "candidate_for_forward_shadow_monitoring"
    assert result["decision"]["production"] == "do_not_promote"
    assert "forward_shadow_monitoring_missing" in result["decision"]["production_blockers"]


def test_seed_averaging_summary_uses_forward_monitor_blocker_when_monitor_exists() -> None:
    result = build_summary(
        _report(),
        forward_monitor={
            "production_blockers": [
                "latest_live_action_parity_not_validated",
                "forward_shadow_monitoring_history_insufficient",
                "no_production_promotion_gate",
            ],
        },
    )

    assert "forward_shadow_monitoring_missing" not in result["decision"]["production_blockers"]
    assert "inference_integration_not_implemented" not in result["decision"]["production_blockers"]
    assert "forward_shadow_monitoring_history_insufficient" in result["decision"]["production_blockers"]


def test_seed_averaging_summary_uses_promotion_gate_blockers_when_gate_exists() -> None:
    result = build_summary(
        _report(),
        forward_monitor={
            "production_blockers": [
                "latest_live_action_parity_not_validated",
                "no_production_promotion_gate",
            ],
        },
        promotion_gate={
            "status": "blocked",
            "blockers": [
                "forward_shadow_monitoring_history_insufficient",
                "latest_live_action_parity_pass_rate_below_threshold",
            ],
        },
    )

    blockers = result["decision"]["production_blockers"]
    assert "no_production_promotion_gate" not in blockers
    assert "latest_live_action_parity_not_validated" in blockers
    assert "forward_shadow_monitoring_history_insufficient" in blockers
    assert "latest_live_action_parity_pass_rate_below_threshold" in blockers


def test_seed_averaging_summary_fails_when_ensemble_sharpe_is_weak() -> None:
    report = copy.deepcopy(_report())
    report["ensembles"]["42+43+44"]["full"]["sharpe"] = 1.70

    result = build_summary(report)

    assert result["decision"]["shadow_gate"] == "fail"
    assert any(
        check["name"] == "ensemble_sharpe_above_individual_mean" and not check["passed"]
        for check in result["checks"]
    )


def test_seed_averaging_summary_fails_when_bad_seed_tail_not_reduced() -> None:
    report = copy.deepcopy(_report())
    report["ensembles"]["42+43+44"]["full"]["max_drawdown"] = -0.34

    result = build_summary(report)

    assert result["decision"]["shadow_gate"] == "fail"
    assert any(
        check["name"] == "ensemble_avoids_bad_seed_mdd_tail" and not check["passed"]
        for check in result["checks"]
    )
