from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plusplus_2609_04917_joint_execution_readiness as module


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_joint_execution_blocks_date_mismatch_and_cost_blockers(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    impact = tmp_path / "impact.json"
    promo = tmp_path / "promo.json"
    profit = tmp_path / "profit.json"
    _write(live, {"actual_data_date": "2026-09-09", "target_weights": {"0050.TW": 0.4}})
    _write(plan, {"actual_data_date": "2026-09-08", "execution_allowed": False})
    _write(impact, {"status": "blocked"})
    _write(promo, {"status": "blocked"})
    _write(profit, {"turnover_cost_robustness_review": {"status": "blocked_for_live_promotion"}})

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        market_impact_path=impact,
        execution_plan_promotion_path=promo,
        profit_readiness_path=profit,
    )

    assert report["status"] == "blocked"
    assert "signal_execution_plan_date_mismatch" in report["blocking_reasons"]
    assert "execution_plan_disallows_execution" in report["blocking_reasons"]
    assert report["decision"]["creates_orders"] is False


def test_joint_execution_can_be_available_for_manual_review(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    impact = tmp_path / "impact.json"
    promo = tmp_path / "promo.json"
    profit = tmp_path / "profit.json"
    _write(live, {"actual_data_date": "2026-09-09", "target_weights": {"cash": 1.0}})
    _write(plan, {"actual_data_date": "2026-09-09", "execution_allowed": True})
    _write(impact, {"status": "available_for_manual_review"})
    _write(promo, {"status": "available_for_manual_review"})
    _write(profit, {"turnover_cost_robustness_review": {"status": "available"}})

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        market_impact_path=impact,
        execution_plan_promotion_path=promo,
        profit_readiness_path=profit,
    )

    assert report["status"] == "available_for_manual_review"
    assert report["blocking_reasons"] == []
