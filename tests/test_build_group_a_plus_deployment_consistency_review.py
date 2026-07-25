from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_deployment_consistency_review import build_review, write_review


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_write_review_writes_latest_and_history_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "deployment_consistency_review.json"
    history_dir = tmp_path / "history"
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_deployment_consistency_review",
        "status": "manual_review_required",
        "as_of": "2026-07-18",
    }

    write_review(review, output_path=output, history_dir=history_dir)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history_dir / "20260718.json").read_text(encoding="utf-8")) == review


def test_build_review_marks_cash_zero_trade_plan_not_broker_actionable(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-18",
                "actual_data_date": "2026-07-17",
                "strategy_id": "s1",
                "target_weights": {"0050.TW": 0.5, "cash": 0.5},
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-17",
                "strategy_id": "s1",
                "current_cash_input": 0.0,
                "cash_assumption": "workbook has no cash field; using explicit --cash-balance input",
                "execution_allowed": False,
                "manual_confirmation_required": True,
                "current_holdings": {"0050.TW": 1},
                "target_shares": {"0050.TW": 2},
                "trades": [{"ticker": "0050.TW", "delta_shares": 1}],
                "pre_trade_guards": [{"name": "guard", "status": "blocked"}],
                "guard_impact_summary": {"combined_blocked_trade_count": 1, "combined_blocked_buy_notional": 100.0},
            },
        },
    )
    daily = _write(
        tmp_path / "daily.json",
        {
            "overall_status": "warn",
            "checks": [
                {"name": "source_freshness", "status": "ok"},
                {"name": "execution_plan_pre_trade_guard", "status": "ok"},
            ],
        },
    )
    ops = _write(tmp_path / "ops.json", {"status": "warning", "errors": [], "warnings": ["x"]})

    review = build_review(
        live_signal_path=live,
        execution_plan_path=plan,
        daily_status_path=daily,
        ops_health_path=ops,
    )

    assert review["status"] == "manual_review_required"
    assert review["decision"]["broker_actionable"] is False
    assert "cash_balance_zero_with_nonzero_trades" in review["warning_reasons"]
    assert "execution_plan_not_allowed" in review["warning_reasons"]
    assert review["computed"]["dates_aligned"] is True
    assert review["computed"]["guard_summary"]["blocked_trade_count"] == 1


def test_build_review_surfaces_gift_signed_approval_governance_warning(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-22",
                "actual_data_date": "2026-07-21",
                "strategy_id": "s1",
                "target_weights": {"0050.TW": 1.0},
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-21",
                "strategy_id": "s1",
                "current_cash_input": 1000.0,
                "cash_assumption": "explicit --cash-balance input",
                "execution_allowed": True,
                "manual_confirmation_required": False,
                "current_holdings": {"0050.TW": 1},
                "target_shares": {"0050.TW": 1},
                "trades": [],
                "pre_trade_guards": [{"name": "guard", "status": "active"}],
                "guard_impact_summary": {"combined_blocked_trade_count": 0},
            },
        },
    )
    daily = _write(
        tmp_path / "daily.json",
        {
            "overall_status": "warn",
            "checks": [
                {"name": "source_freshness", "status": "ok"},
                {"name": "execution_plan_pre_trade_guard", "status": "ok"},
            ],
            "group_a_plus": {
                "gift_signed_approval_governance": {
                    "validation_status": "blocked",
                    "signed_approval_record_valid": False,
                    "human_exception_approved": False,
                    "non_ppo_shadow_queue_review_allowed": False,
                    "training_queue_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                    "manual_approval_to_queue_training_allowed": False,
                    "training_queue_blocking_reasons": [
                        "signed_human_exception_approval_record_missing_or_invalid"
                    ],
                    "signed_approval_warnings": [
                        "llm_state_reward_signed_approval_validation:missing_signed_human_exception_approval_record"
                    ],
                    "checklist_status": "manual_completion_pending",
                    "checklist_manual_completion_ready": True,
                    "checklist_manual_completion_pending": True,
                    "checklist_signed_record_exists": False,
                    "validator_smoke_status": "passed",
                    "validator_smoke_passed": True,
                    "validator_smoke_blocks_00631l_add": True,
                    "validator_smoke_blocks_model_training": True,
                    "formal_signed_record_written_by_smoke": False,
                }
            },
        },
    )
    ops = _write(tmp_path / "ops.json", {"status": "ok", "errors": [], "warnings": []})

    review = build_review(
        live_signal_path=live,
        execution_plan_path=plan,
        daily_status_path=daily,
        ops_health_path=ops,
    )

    gift = review["computed"]["gift_signed_approval_governance"]
    assert review["status"] == "manual_review_required"
    assert "gift_signed_approval_record_missing_or_invalid" in review["warning_reasons"]
    assert "gift_human_exception_not_approved" in review["warning_reasons"]
    assert gift["validation_status"] == "blocked"
    assert gift["signed_approval_record_valid"] is False
    assert gift["human_exception_approved"] is False
    assert gift["training_queue_allowed"] is False
    assert gift["model_training_allowed"] is False
    assert gift["ppo_training_allowed"] is False
    assert gift["promote_to_live"] is False
    assert gift["checklist_status"] == "manual_completion_pending"
    assert gift["checklist_manual_completion_ready"] is True
    assert gift["checklist_manual_completion_pending"] is True
    assert gift["checklist_signed_record_exists"] is False
    assert gift["validator_smoke_status"] == "passed"
    assert gift["validator_smoke_passed"] is True
    assert gift["validator_smoke_blocks_00631l_add"] is True
    assert gift["validator_smoke_blocks_model_training"] is True
    assert gift["formal_signed_record_written_by_smoke"] is False
    assert "gift_signed_approval_manual_completion_pending" in review["warning_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True


def test_build_review_treats_soft_source_freshness_as_warning_only(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-23",
                "actual_data_date": "2026-07-22",
                "strategy_id": "s1",
                "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-22",
                "strategy_id": "s1",
                "current_cash_input": 1000.0,
                "cash_assumption": "explicit --cash-balance input",
                "execution_allowed": True,
                "manual_confirmation_required": False,
                "trades": [],
                "pre_trade_guards": [{"name": "guard", "status": "blocked"}],
            },
        },
    )
    daily = _write(
        tmp_path / "daily.json",
        {
            "overall_status": "warn",
            "checks": [
                {
                    "name": "source_freshness",
                    "status": "warn",
                    "detail": "soft strategy sources are stale or missing: ['securities_lending_0050']; securities_lending_0050",
                },
                {"name": "execution_plan_pre_trade_guard", "status": "ok"},
            ],
        },
    )
    ops = _write(tmp_path / "ops.json", {"status": "ok", "errors": [], "warnings": []})
    source_status = _write(
        tmp_path / "securities_lending_source_status.json",
        {
            "status": "provider_no_rows",
            "summary": {
                "provider_no_rows_confirmed": True,
                "latest_available_dt": "2026-07-17",
                "query_end": "2026-07-22",
                "keep_golden1_0531_unchanged": True,
            },
            "decision": {"blocks_deployment": False},
        },
    )

    review = build_review(
        live_signal_path=live,
        execution_plan_path=plan,
        daily_status_path=daily,
        ops_health_path=ops,
        securities_lending_source_status_path=source_status,
    )

    assert review["status"] == "manual_review_required"
    assert "source_freshness_not_ok" not in review["blocking_reasons"]
    assert "source_freshness_soft_warning" in review["warning_reasons"]
    assert review["computed"]["source_freshness"]["has_soft_stale"] is True
    assert review["computed"]["source_freshness"]["blocks_deployment"] is False
    assert review["computed"]["securities_lending_0050_source_status"]["status"] == "provider_no_rows"
    assert (
        review["computed"]["securities_lending_0050_source_status"]["summary"]["provider_no_rows_confirmed"]
        is True
    )


def test_build_review_still_blocks_required_source_freshness(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-23",
                "actual_data_date": "2026-07-22",
                "strategy_id": "s1",
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-22",
                "strategy_id": "s1",
                "current_cash_input": 1000.0,
                "cash_assumption": "explicit --cash-balance input",
                "execution_allowed": True,
                "manual_confirmation_required": False,
                "pre_trade_guards": [{"name": "guard", "status": "active"}],
            },
        },
    )
    daily = _write(
        tmp_path / "daily.json",
        {
            "overall_status": "block",
            "checks": [
                {
                    "name": "source_freshness",
                    "status": "block",
                    "detail": "required strategy sources are stale or missing: ['institutional_0050']",
                }
            ],
        },
    )
    ops = _write(tmp_path / "ops.json", {"status": "ok", "errors": [], "warnings": []})

    review = build_review(
        live_signal_path=live,
        execution_plan_path=plan,
        daily_status_path=daily,
        ops_health_path=ops,
    )

    assert review["status"] == "blocked"
    assert "source_freshness_not_ok" in review["blocking_reasons"]
    assert review["computed"]["source_freshness"]["has_required_stale"] is True
    assert review["computed"]["source_freshness"]["blocks_deployment"] is True


def test_build_review_blocks_if_gift_governance_unexpectedly_allows_training(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-22",
                "actual_data_date": "2026-07-21",
                "strategy_id": "s1",
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-21",
                "strategy_id": "s1",
                "current_cash_input": 1000.0,
                "cash_assumption": "explicit --cash-balance input",
                "execution_allowed": True,
                "manual_confirmation_required": False,
                "pre_trade_guards": [{"name": "guard", "status": "active"}],
            },
        },
    )
    daily = _write(
        tmp_path / "daily.json",
        {
            "overall_status": "ok",
            "checks": [{"name": "source_freshness", "status": "ok"}],
            "group_a_plus": {
                "gift_signed_approval_governance": {
                    "signed_approval_record_valid": True,
                    "human_exception_approved": True,
                    "training_queue_allowed": True,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                }
            },
        },
    )
    ops = _write(tmp_path / "ops.json", {"status": "ok", "errors": [], "warnings": []})

    review = build_review(
        live_signal_path=live,
        execution_plan_path=plan,
        daily_status_path=daily,
        ops_health_path=ops,
    )

    assert review["status"] == "blocked"
    assert "gift_governance_unexpectedly_allows_training_queue" in review["blocking_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False


def test_write_review_can_disable_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "deployment_consistency_review.json"
    history_dir = tmp_path / "history"
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_deployment_consistency_review",
        "status": "ok",
        "as_of": "2026-07-18",
    }

    write_review(review, output_path=output, history_dir=None)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert not history_dir.exists()
