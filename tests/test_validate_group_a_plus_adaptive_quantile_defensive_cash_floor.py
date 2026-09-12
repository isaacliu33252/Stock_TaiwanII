from __future__ import annotations

from scripts.evaluate.validate_group_a_plus_adaptive_quantile_defensive_cash_floor import validate_sweep


def test_validate_cash_floor_candidate_passes_changed_windows() -> None:
    sweep = {
        "report_type": "group_a_plus_adaptive_quantile_defensive_cash_floor_sweep",
        "top_variants": [{"variant": "cash55_risk7_tail1"}],
        "best_variant_detail": {
            "rows": [
                {
                    "date": "2025-03-03",
                    "raw_net_return": -0.02,
                    "variant_net_return": -0.01,
                    "changed": True,
                    "active": True,
                },
                {
                    "date": "2025-03-04",
                    "raw_net_return": 0.005,
                    "variant_net_return": 0.004,
                    "changed": True,
                    "active": True,
                },
                {
                    "date": "2026-07-28",
                    "raw_net_return": -0.015,
                    "variant_net_return": -0.01,
                    "changed": True,
                    "active": True,
                },
            ]
        },
    }

    result = validate_sweep(sweep)

    assert result["status"] == "ok"
    assert result["summary"]["fail_windows"] == []
    assert result["decision"]["promotion_decision"] == "shadow_candidate_for_fold_ablation"
    assert result["decision"]["target_weight_change_allowed"] is False


def test_validate_cash_floor_candidate_blocks_failed_changed_window() -> None:
    sweep = {
        "report_type": "group_a_plus_adaptive_quantile_defensive_cash_floor_sweep",
        "top_variants": [{"variant": "cash55_risk7_tail1"}],
        "best_variant_detail": {
            "rows": [
                {
                    "date": "2025-03-03",
                    "raw_net_return": 0.002,
                    "variant_net_return": -0.004,
                    "changed": True,
                    "active": True,
                },
                {
                    "date": "2025-03-04",
                    "raw_net_return": 0.001,
                    "variant_net_return": -0.002,
                    "changed": True,
                    "active": True,
                },
            ]
        },
    }

    result = validate_sweep(sweep)

    assert result["status"] == "ok"
    assert "full" in result["summary"]["fail_windows"]
    assert result["decision"]["promotion_decision"] == "do_not_promote"
    assert result["decision"]["auto_rebalance_allowed"] is False
