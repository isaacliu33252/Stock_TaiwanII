from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_promotion_blocked_diagnostic import build_diagnostic, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_promotion_blocked_diagnostic_extracts_gate_failures(tmp_path: Path) -> None:
    gate = _write(
        tmp_path / "promotion.json",
        {
            "decision": "blocked_deployment_consistency_and_model_gates",
            "blocking_gates": ["panel_drift", "multi_window", "deployment_consistency"],
            "metrics_gate": {
                "status": "fail",
                "formal_upgrade_pass_count": 0,
                "research_watchlist_pass_count": 0,
                "top_candidates": [
                    {
                        "variant": "top_by_final_value",
                        "promotion_objective_status": "fail:final_value_floor",
                        "final_value": 100.0,
                        "final_value_floor": 101.0,
                        "delta_final": -1.0,
                        "sharpe_non_worse_pass": True,
                        "max_drawdown_non_worse_pass": True,
                    }
                ],
            },
            "panel_drift_gate": {
                "status": "fail",
                "reason": "drift exceeds limits: h20_prob_up",
                "overlap_rows": 100,
                "checks": {
                    "h20_prob_up": {
                        "status": "fail",
                        "tier": "trigger_critical",
                        "max_abs_delta": 0.2,
                        "limit": 0.15,
                        "max_abs_delta_date": "2026-01-02",
                    },
                    "ensemble_prob_up": {"status": "pass"},
                },
            },
            "multi_window_gate": {
                "status": "fail",
                "reason": "no candidate passed the multi-window gate",
                "candidate_count": 6,
                "pass_candidates": [],
                "criteria": {"min_pass_ratio": 1.0},
            },
            "deployment_consistency_gate": {
                "status": "fail",
                "reason": "deployment consistency governance blocks promotion",
                "blocking_reasons": [],
                "hard_blocking_reasons": [],
                "manual_approval_pending_reasons": ["gift_signed_approval_record_missing_or_invalid"],
                "warning_reasons": ["source_freshness_soft_warning"],
                "all_reasons": [
                    "gift_signed_approval_record_missing_or_invalid",
                    "source_freshness_soft_warning",
                ],
            },
            "deployment_summary_gate": {"status": "pass", "reason": "deployment summary governance passed"},
        },
    )

    report = build_diagnostic(gate)

    assert report["status"] == "blocked"
    assert report["summary"]["panel_drift_failed"] is True
    assert report["summary"]["multi_window_failed"] is True
    assert report["summary"]["deployment_consistency_failed"] is True
    assert report["summary"]["deployment_summary_failed"] is False
    assert report["summary"]["manual_approval_pending"] is True
    assert report["panel_drift_gate"]["failed_checks"][0]["name"] == "h20_prob_up"
    assert report["metrics_gate"]["top_failures"][0]["promotion_objective_status"] == "fail:final_value_floor"
    assert report["deployment_consistency_gate"]["blocking_reasons"] == []
    assert report["deployment_consistency_gate"]["hard_blocking_reasons"] == []
    assert report["deployment_consistency_gate"]["manual_approval_pending_reasons"] == [
        "gift_signed_approval_record_missing_or_invalid"
    ]
    assert report["deployment_consistency_gate"]["warning_reasons"] == ["source_freshness_soft_warning"]
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["decision"]["keep_golden1_0531_unchanged"] is True


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    report = {
        "status": "blocked",
        "promotion_decision": "blocked_panel_drift",
        "blocking_gates": ["panel_drift"],
        "metrics_gate": {"status": "fail"},
        "panel_drift_gate": {
            "status": "fail",
            "reason": "drift exceeds limits",
            "failed_checks": [],
        },
        "multi_window_gate": {"status": "pass", "reason": "ok", "criteria": {}},
        "deployment_consistency_gate": {"status": "pass", "blocking_reasons": []},
        "deployment_summary_gate": {"status": "pass"},
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    output = tmp_path / "latest/promotion_blocked_diagnostic.json"
    output_md = tmp_path / "latest/promotion_blocked_diagnostic.md"
    history = tmp_path / "history"

    write_outputs(report, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ Promotion Blocked Diagnostic" in markdown
    assert "Golden1_0531 unchanged: `True`" in markdown
    assert list(history.glob("promotion_blocked_diagnostic_*.json"))
