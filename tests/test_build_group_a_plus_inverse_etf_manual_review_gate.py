from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_inverse_etf_manual_review_gate import build_report


def test_inverse_etf_manual_review_report_blocks_00632r_target_change(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "current_holdings": {"00632R.TW": 0},
                "target_shares": {"00632R.TW": 500},
                "requested_as_of_date": "2026-08-05",
                "actual_data_date": "2026-08-04",
                "planning_status": "ready",
                "manual_confirmation_required": False,
                "execution_regime": "golden1",
            }
        ),
        encoding="utf-8",
    )

    report = build_report(execution_plan_path=plan, as_of="2026-08-15")

    assert report["status"] == "blocked"
    assert report["guard"]["status"] == "blocked"
    assert report["guarded_target_shares"]["00632R.TW"] == 0
    assert report["decision"]["allow_00632r_auto_trade"] is False
    assert "inverse_etf_trade_requires_manual_review" in report["blocking_reasons"]


def test_inverse_etf_manual_review_report_allows_no_00632r_change_for_manual_review(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "current_holdings": {"00632R.TW": 0},
                "target_shares": {"00632R.TW": 0},
                "requested_as_of_date": "2026-08-14",
                "actual_data_date": "2026-08-13",
                "planning_status": "ready",
                "manual_confirmation_required": False,
                "execution_regime": "golden1",
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        execution_plan_path=plan,
        as_of="2026-08-15",
        realized_pnl_review_available=True,
        cost_basis_available=True,
        artifact_freshness_verified=True,
        hedge_rationale_available=True,
        manual_approval_record_available=True,
    )

    assert report["status"] == "available_for_manual_review"
    assert report["guard"]["status"] == "inactive"
    assert report["blocking_reasons"] == []


def test_inverse_etf_manual_review_report_does_not_block_missing_checks_when_00632r_unchanged(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "current_holdings": {"00632R.TW": 0},
                "target_shares": {"00632R.TW": 0},
                "requested_as_of_date": "2026-08-14",
                "actual_data_date": "2026-08-13",
                "planning_status": "ready",
                "manual_confirmation_required": False,
                "execution_regime": "golden1",
            }
        ),
        encoding="utf-8",
    )

    report = build_report(execution_plan_path=plan, as_of="2026-08-15")

    assert report["status"] == "available_for_manual_review"
    assert report["guard"]["status"] == "inactive"
    assert "missing_realized_pnl_review_available" not in report["blocking_reasons"]
