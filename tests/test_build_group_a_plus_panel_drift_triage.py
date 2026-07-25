from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_panel_drift_triage import build_triage, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_panel_drift_triage_extracts_hypotheses_and_column_details(tmp_path: Path) -> None:
    diagnosis = _write(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "overlap_start": "2025-01-02",
            "overlap_end": "2026-06-30",
            "overlap_rows": 359,
            "exceeded_columns": ["ensemble_prob_up", "h20_prob_up", "confidence"],
            "trigger_critical_exceeded": ["h20_prob_up", "confidence"],
            "columns": {
                "ensemble_prob_up": {
                    "tier": "diagnostic",
                    "limit": 0.15,
                    "max_abs_delta": 0.24,
                    "max_abs_delta_date": "2025-05-09",
                    "signed_delta_at_max": 0.24,
                    "baseline_value_at_max": 0.65,
                    "candidate_value_at_max": 0.89,
                    "top_months_by_exceed_count": [
                        {"month": "2025-03", "exceed_count": 5, "row_count": 21, "mean_abs_delta": 0.09},
                        {"month": "2025-05", "exceed_count": 2, "row_count": 20, "mean_abs_delta": 0.07},
                    ],
                },
                "h20_prob_up": {
                    "tier": "trigger_critical",
                    "limit": 0.15,
                    "max_abs_delta": 0.26,
                    "max_abs_delta_date": "2025-09-18",
                    "signed_delta_at_max": -0.26,
                    "top_months_by_exceed_count": [
                        {"month": "2025-09", "exceed_count": 3, "row_count": 21, "mean_abs_delta": 0.10}
                    ],
                },
                "confidence": {
                    "tier": "trigger_critical",
                    "limit": 0.28,
                    "max_abs_delta": 0.49,
                    "max_abs_delta_date": "2025-05-09",
                    "signed_delta_at_max": 0.49,
                    "top_months_by_exceed_count": [
                        {"month": "2025-05", "exceed_count": 4, "row_count": 20, "mean_abs_delta": 0.12}
                    ],
                },
            },
            "source_diagnosis": {
                "model_sets": {"status": "changed"},
                "panel_methods": {
                    "baseline_has_horizon_ensemble_method": False,
                    "candidate_has_horizon_ensemble_method": True,
                    "baseline_has_ensemble_weights": False,
                    "candidate_has_ensemble_weights": True,
                },
                "run_context": {
                    "candidate_stale_sources": ["external_market_ohlcv"],
                    "settings": {
                        "external_features": {"changed": False},
                        "feature_selection": {"changed": True},
                    },
                },
                "sensitivity_audit": {
                    "status": "available",
                    "column_summary": {"confidence": {"max_abs_delta": 0.6}},
                },
            },
        },
    )

    report = build_triage(diagnosis)

    assert report["status"] == "blocked"
    assert report["summary"]["trigger_critical_exceeded"] == ["h20_prob_up", "confidence"]
    assert report["summary"]["source_hypotheses"] == [
        "model_set_changed",
        "run_context_settings_changed",
        "candidate_external_source_stale",
        "panel_method_schema_changed",
        "external_feature_sensitivity_visible",
        "horizon_ensemble_or_confidence_blend_check_needed",
    ]
    assert report["summary"]["top_exceed_months"][0] == {"month": "2025-05", "exceed_count": 6}
    h20 = [item for item in report["columns"] if item["column"] == "h20_prob_up"][0]
    assert h20["direction"] == "negative"
    assert h20["tier"] == "trigger_critical"
    assert "inspect horizon ensemble weights/confidence blend" in report["summary"]["next_checks"][2]
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["decision"]["keep_golden1_0531_unchanged"] is True


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    report = {
        "status": "blocked",
        "summary": {
            "exceeded_columns": ["confidence"],
            "trigger_critical_exceeded": ["confidence"],
            "source_hypotheses": ["horizon_ensemble_or_confidence_blend_check_needed"],
            "next_checks": ["inspect horizon ensemble weights"],
        },
        "columns": [
            {
                "column": "confidence",
                "tier": "trigger_critical",
                "max_abs_delta": 0.49,
                "limit": 0.28,
                "max_abs_delta_date": "2025-05-09",
                "direction": "positive",
            }
        ],
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    output = tmp_path / "latest/panel_drift_triage.json"
    output_md = tmp_path / "latest/panel_drift_triage.md"
    history = tmp_path / "history"

    write_outputs(report, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ Panel Drift Triage" in markdown
    assert "Golden1_0531 unchanged: `True`" in markdown
    assert list(history.glob("panel_drift_triage_*.json"))
