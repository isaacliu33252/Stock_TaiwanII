from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_deployment_summary import build_summary, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_deployment_summary_compacts_latest_state_without_actions(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-23",
                "actual_data_date": "2026-07-22",
                "strategy_id": "a2118",
                "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-07-23",
                "actual_data_date": "2026-07-22",
                "strategy_id": "a2118",
                "target_shares": {"0050.TW": 3257, "00631L.TW": 0},
                "current_cash_input": 1_000_000.0,
                "cash_assumption": "workbook has no cash field; using explicit --cash-balance input",
                "execution_allowed": True,
                "manual_confirmation_required": False,
                "trades": [{"ticker": "0050.TW", "side": "buy", "delta_shares": 10, "price": 100.0}],
                "pre_trade_guards": [{"name": "volatility_gate_no_00631l_add", "status": "blocked"}],
                "guard_impact_summary": {
                    "combined_blocked_buys": [
                        {
                            "ticker": "00631L.TW",
                            "staged_target_shares": 2908,
                            "final_target_shares": 0,
                            "blocked_delta_shares": 2908,
                        }
                    ]
                },
            },
        },
    )
    deployment = _write(
        tmp_path / "deployment.json",
        {
            "status": "manual_review_required",
            "as_of": "2026-07-23",
            "blocking_reasons": [],
            "warning_reasons": ["source_freshness_soft_warning"],
            "decision": {
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "broker_actionable": True,
                "allow_00631l_add": False,
                "keep_golden1_0531_unchanged": True,
            },
            "computed": {
                "source_freshness": {"status": "warn", "blocks_deployment": False},
                "securities_lending_0050_source_status": {"status": "provider_no_rows"},
                "cash_source_explicit": True,
            },
        },
    )

    summary = build_summary(live_signal_path=live, execution_plan_path=plan, deployment_path=deployment)

    assert summary["status"] == "manual_review_required"
    assert summary["broker_actionable"] is True
    assert summary["actual_data_date"] == "2026-07-22"
    assert summary["target_weights"]["00631L.TW"] == 0.2
    assert summary["final_target_shares"]["00631L.TW"] == 0
    assert summary["planned_trades"][0]["ticker"] == "0050.TW"
    assert summary["execution_plan_cash"]["current_cash_input"] == 1_000_000.0
    assert summary["execution_plan_cash"]["nonzero_trade_count"] == 1
    assert summary["execution_plan_cash"]["cash_source_explicit"] is True
    assert summary["execution_plan_cash"]["manual_confirmation_required"] is False
    assert summary["blocked_buys"][0]["ticker"] == "00631L.TW"
    assert summary["securities_lending_0050_source_status"]["status"] == "provider_no_rows"
    assert summary["decision"]["summary_only"] is True
    assert summary["decision"]["creates_orders"] is False
    assert summary["decision"]["target_weight_change_allowed"] is False
    assert summary["decision"]["auto_rebalance_allowed"] is False
    assert summary["decision"]["allow_00631l_add"] is False
    assert summary["decision"]["allow_00632r_open"] is False
    assert summary["decision"]["keep_golden1_0531_unchanged"] is True
    assert summary["consistency_review"]["status"] == "ok"
    assert summary["consistency_review"]["errors"] == []


def test_deployment_summary_flags_consistency_errors(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "requested_as_of_date": "2026-07-23",
            "actual_data_date": "2026-07-22",
            "strategy_id": "a2118",
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "actual_data_date": "2026-07-22",
            "strategy_id": "a2118",
            "trades": [],
        },
    )
    deployment = _write(
        tmp_path / "deployment.json",
        {
            "status": "ok",
            "as_of": "2026-07-23",
            "blocking_reasons": [],
            "warning_reasons": [],
            "decision": {
                "target_weight_change_allowed": True,
                "auto_rebalance_allowed": False,
                "broker_actionable": False,
                "allow_00631l_add": False,
                "keep_golden1_0531_unchanged": True,
            },
        },
    )

    summary = build_summary(live_signal_path=live, execution_plan_path=plan, deployment_path=deployment)

    assert summary["broker_actionable"] is False
    review = summary["consistency_review"]
    assert review["status"] == "error"
    assert "deployment_decision_target_weight_change_allowed_mismatch" in review["errors"]


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    summary = {
        "as_of": "2026-07-23",
        "status": "manual_review_required",
        "broker_actionable": True,
        "actual_data_date": "2026-07-22",
        "strategy_id": "a2118",
        "target_weights": {"0050.TW": 0.5},
        "final_target_shares": {"0050.TW": 1},
        "execution_plan_cash": {"current_cash_input": 1_000_000.0, "nonzero_trade_count": 2},
        "planned_trades": [],
        "blocked_buys": [],
        "warning_reasons": [],
        "decision": {"keep_golden1_0531_unchanged": True},
    }
    output = tmp_path / "latest" / "deployment_summary.json"
    output_md = tmp_path / "latest" / "deployment_summary.md"
    history = tmp_path / "history"

    write_outputs(summary, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == summary
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ Deployment Summary" in markdown
    assert "Cash input: `1000000.0`" in markdown
    assert "Nonzero trades: `2`" in markdown
    assert (history / "deployment_summary_20260723.json").exists()
