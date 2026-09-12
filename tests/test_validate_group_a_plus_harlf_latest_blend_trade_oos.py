from __future__ import annotations

from scripts.evaluate.validate_group_a_plus_harlf_latest_blend_trade_oos import build_validation, branch_report_from_mapped_shadow


def test_harlf_trade_oos_validation_blocks_non_tradable_assets_and_missing_latest_weights() -> None:
    blend = {
        "decision": {"found_blend_ready_for_latest_strategy_review": True},
        "best_viable_blend": {"harlf_weight": 0.08, "latest_weight": 0.92},
    }
    branch = {
        "branch_returns": [
            {
                "month": "2026-01",
                "branch": "sentiment_only",
                "weights": {"0050": 0.5, "2330": 0.5},
            }
        ]
    }
    meta = {"monthly_decisions": [{"month": "2026-01", "selected_branch": "sentiment_only"}]}
    report = build_validation(
        blend_report=blend,
        branch_report=branch,
        meta_report=meta,
        comparison_report={"decision": {}},
    )

    assert report["status"] == "blocked"
    assert "harlf_uses_assets_outside_group_a_plus_tradable_universe" in report["blocking_reasons"]
    assert "missing_latest_strategy_historical_target_weight_series" in report["blocking_reasons"]
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False


def test_harlf_trade_oos_validation_keeps_research_only_when_blend_missing() -> None:
    report = build_validation(
        blend_report={},
        branch_report={},
        meta_report={},
        comparison_report={},
    )

    assert "missing_viable_harlf_latest_blend" in report["blocking_reasons"]
    assert report["decision"]["creates_orders"] is False


def test_harlf_trade_oos_validation_accepts_etf_mapped_branch_weights() -> None:
    blend = {
        "decision": {"found_blend_ready_for_latest_strategy_review": True},
        "best_viable_blend": {"harlf_weight": 0.08, "latest_weight": 0.92},
    }
    mapped_shadow = {
        "status": "available",
        "variants": {
            "drop_2330_renormalize": {
                "branch_returns": [
                    {
                        "month": "2026-01",
                        "branch": "sentiment_only",
                        "weights": {"0050": 0.5, "00631L": 0.5},
                    }
                ]
            }
        },
    }
    branch = branch_report_from_mapped_shadow(mapped_shadow, "drop_2330_renormalize")
    meta = {"monthly_decisions": [{"month": "2026-01", "selected_branch": "sentiment_only"}]}

    report = build_validation(
        blend_report=blend,
        branch_report=branch,
        meta_report=meta,
        comparison_report={"decision": {}},
    )

    assert "harlf_uses_assets_outside_group_a_plus_tradable_universe" not in report["blocking_reasons"]
    assert "missing_latest_strategy_historical_target_weight_series" in report["blocking_reasons"]
    assert report["tradability"]["non_tradable_assets"] == []


def test_harlf_trade_oos_validation_uses_latest_target_weight_coverage() -> None:
    blend = {
        "decision": {"found_blend_ready_for_latest_strategy_review": True},
        "best_viable_blend": {"harlf_weight": 0.08, "latest_weight": 0.92},
    }
    branch = {
        "branch_returns": [
            {
                "month": "2026-01",
                "branch": "sentiment_only",
                "weights": {"0050": 0.5, "00631L": 0.5},
            }
        ]
    }
    meta = {"monthly_decisions": [{"month": "2026-01", "selected_branch": "sentiment_only"}]}
    latest_weights = {
        "decision": {"historical_target_weight_series_available": True},
        "row_count": 20,
        "date_window": {"start": "2026-01-01", "end": "2026-01-31"},
    }

    report = build_validation(
        blend_report=blend,
        branch_report=branch,
        meta_report=meta,
        comparison_report={"decision": {}},
        latest_target_weights_report=latest_weights,
    )

    assert "missing_latest_strategy_historical_target_weight_series" not in report["blocking_reasons"]
    assert "missing_trade_level_execution_cost_replay_for_blend" in report["blocking_reasons"]
    assert report["trade_history_readiness"]["latest_strategy_historical_target_weight_series_available"] is True
    assert report["trade_history_readiness"]["latest_strategy_target_weight_rows"] == 20


def test_harlf_trade_oos_validation_uses_trade_replay_report() -> None:
    blend = {
        "decision": {"found_blend_ready_for_latest_strategy_review": True},
        "best_viable_blend": {"harlf_weight": 0.08, "latest_weight": 0.92},
    }
    branch = {
        "branch_returns": [
            {
                "month": "2026-01",
                "branch": "sentiment_only",
                "weights": {"0050": 0.5, "00631L": 0.5},
            }
        ]
    }
    meta = {"monthly_decisions": [{"month": "2026-01", "selected_branch": "sentiment_only"}]}
    latest_weights = {"decision": {"historical_target_weight_series_available": True}}
    replay = {
        "decision": {"trade_level_execution_cost_replay_available": True},
        "window": {"daily_rows": 20, "rebalance_count": 1},
        "metrics": {"total_return": 0.1},
        "cost_summary": {"total_cost": 100.0},
    }

    report = build_validation(
        blend_report=blend,
        branch_report=branch,
        meta_report=meta,
        comparison_report={"decision": {}},
        latest_target_weights_report=latest_weights,
        trade_replay_report=replay,
    )

    assert "missing_latest_strategy_historical_target_weight_series" not in report["blocking_reasons"]
    assert "missing_trade_level_execution_cost_replay_for_blend" not in report["blocking_reasons"]
    assert "missing_oos_window_beyond_blend_selection_window" in report["blocking_reasons"]
    assert report["trade_history_readiness"]["trade_level_execution_cost_replay_available"] is True
    assert report["trade_history_readiness"]["trade_replay_cost_summary"]["total_cost"] == 100.0
    assert report["next_required_work"] == ["Validate on an OOS window not used to choose the 8% HARLF blend."]


def test_harlf_trade_oos_validation_records_failed_temporal_oos() -> None:
    blend = {
        "decision": {"found_blend_ready_for_latest_strategy_review": True},
        "best_viable_blend": {"harlf_weight": 0.08, "latest_weight": 0.92},
    }
    branch = {
        "branch_returns": [
            {
                "month": "2026-01",
                "branch": "sentiment_only",
                "weights": {"0050": 0.5, "00631L": 0.5},
            }
        ]
    }
    meta = {"monthly_decisions": [{"month": "2026-01", "selected_branch": "sentiment_only"}]}
    latest_weights = {"decision": {"historical_target_weight_series_available": True}}
    replay = {"decision": {"trade_level_execution_cost_replay_available": True}}
    temporal_oos = {
        "decision": {"oos_window_available": True, "temporal_oos_passed": False},
        "blocking_reasons": ["no_train_viable_harlf_blend_under_drawdown_constraint"],
        "holdout_window": {"months": ["2026-05", "2026-06", "2026-07"], "n": 3},
    }

    report = build_validation(
        blend_report=blend,
        branch_report=branch,
        meta_report=meta,
        comparison_report={"decision": {}},
        latest_target_weights_report=latest_weights,
        trade_replay_report=replay,
        temporal_oos_report=temporal_oos,
    )

    assert "missing_oos_window_beyond_blend_selection_window" not in report["blocking_reasons"]
    assert "harlf_temporal_oos_validation_not_passed" in report["blocking_reasons"]
    assert report["trade_history_readiness"]["temporal_oos_window_available"] is True
    assert report["trade_history_readiness"]["temporal_oos_passed"] is False
