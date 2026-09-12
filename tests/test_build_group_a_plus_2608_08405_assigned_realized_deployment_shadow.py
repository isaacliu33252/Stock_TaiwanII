from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_2608_08405_assigned_realized_deployment_shadow as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_assigned_realized_shadow_blocks_without_authoritative_realized_positions(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    broker = tmp_path / "broker.json"
    reconciliation = tmp_path / "reconciliation.json"
    _write_json(
        live,
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-09-04",
                "target_weights": {"0050.TW": 0.53, "00631L.TW": 0.17, "cash": 0.30},
                "reference_target_shares_before_cost": {"0050.TW": 4883, "00631L.TW": 4722},
            },
        },
    )
    _write_json(
        plan,
        {
            "actual_data_date": "2026-08-31",
            "target_shares": {"0050.TW": 5432, "00631L.TW": 2241},
        },
    )
    _write_json(
        broker,
        {
            "authoritative_broker_export": False,
            "coverage": {"last_transaction_date": "2026-07-17"},
            "latest_positions": {"0050.TW": -2304, "00631L.TW": 500},
        },
    )
    _write_json(reconciliation, {"decision": {"broker_holdings_reconciled": False}})

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        broker_sample_path=broker,
        broker_reconciliation_path=reconciliation,
    )

    assert report["status"] == "blocked"
    assert "execution_plan_stale_vs_live_signal" in report["blocking_reasons"]
    assert "broker_positions_not_authoritative" in report["blocking_reasons"]
    assert "realized_fill_or_deployment_series_missing" in report["blocking_reasons"]
    assert report["decision"]["capacity_scaling_allowed"] is False
    assert report["comparison"][0]["ticker"] == "0050.TW"


def test_assigned_realized_shadow_ready_when_authoritative_and_reconciled(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    plan = tmp_path / "plan.json"
    broker = tmp_path / "broker.json"
    reconciliation = tmp_path / "reconciliation.json"
    _write_json(
        live,
        {
            "actual_data_date": "2026-09-04",
            "target_weights": {"0050.TW": 0.53, "00631L.TW": 0.17, "cash": 0.30},
            "reference_target_shares_before_cost": {"0050.TW": 4883, "00631L.TW": 4722},
        },
    )
    _write_json(
        plan,
        {
            "actual_data_date": "2026-09-04",
            "target_shares": {"0050.TW": 4883, "00631L.TW": 4722},
        },
    )
    _write_json(
        broker,
        {
            "authoritative_broker_export": True,
            "coverage": {"last_transaction_date": "2026-09-04"},
            "latest_positions": {"0050.TW": 4883, "00631L.TW": 4722},
        },
    )
    _write_json(reconciliation, {"decision": {"broker_holdings_reconciled": True}})

    report = module.build_report(
        live_signal_path=live,
        execution_plan_path=plan,
        broker_sample_path=broker,
        broker_reconciliation_path=reconciliation,
    )
    markdown = module._markdown(report)

    assert report["status"] == "ready_for_capacity_shadow_review"
    assert report["blocking_reasons"] == []
    assert report["coverage"]["realized_authoritative_positions_logged"] is True
    assert report["decision"]["latest_strategy_change_allowed"] is False
    assert "## Comparison" in markdown
