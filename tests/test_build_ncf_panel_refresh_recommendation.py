from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_ncf_panel_refresh_recommendation import build_refresh_recommendation, write_outputs


def _write_audit(path: Path, column_summary: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "ncf_panel_drift_audit",
                "baseline_panel": "/tmp/pinned.csv",
                "candidate_panel": "/tmp/candidate.csv",
                "overlap_start": "2025-01-02",
                "overlap_end": "2026-07-24",
                "overlap_rows": 599,
                "window_start": None,
                "column_summary": column_summary,
            }
        ),
        encoding="utf-8",
    )


def _column(candidate: int, baseline: int, resolved: int, risk_delta: float = 0.12) -> dict:
    return {
        "max_abs_delta": 0.20,
        "max_abs_delta_date": "2026-02-26",
        "outcome_aware": {
            "actual_column": "actual_up_h20",
            "resolved_rows": resolved,
            "candidate_favorable_rows": candidate,
            "baseline_favorable_rows": baseline,
            "tie_rows": resolved - candidate - baseline,
            "risk_relevant_max_abs_delta": risk_delta,
            "risk_relevant_max_abs_delta_date": "2026-02-26",
        },
    }


def test_refresh_recommendation_keeps_pin_when_candidate_not_more_accurate(tmp_path: Path) -> None:
    audit = tmp_path / "drift.json"
    _write_audit(
        audit,
        {
            "h20_prob_up": _column(candidate=170, baseline=210, resolved=400),
            "prob_fwd_mdd_gt5_h20": _column(candidate=185, baseline=205, resolved=400),
            "prob_fwd_gain_gt5_h20": _column(candidate=197, baseline=203, resolved=400),
        },
    )

    report = build_refresh_recommendation(audit)

    assert report["summary"]["recommendation"] == "keep_current_pin"
    assert report["summary"]["reason"] == "candidate_not_more_accurate_on_resolved_outcomes"
    assert report["summary"]["low_accuracy_columns"] == [
        "h20_prob_up",
        "prob_fwd_mdd_gt5_h20",
        "prob_fwd_gain_gt5_h20",
    ]
    assert report["decision"]["auto_pin_update_allowed"] is False


def test_refresh_recommendation_supports_candidate_when_accuracy_and_risk_pass(tmp_path: Path) -> None:
    audit = tmp_path / "drift.json"
    _write_audit(
        audit,
        {
            "h20_prob_up": _column(candidate=240, baseline=150, resolved=400, risk_delta=0.08),
            "prob_fwd_mdd_gt5_h20": _column(candidate=230, baseline=160, resolved=400, risk_delta=0.09),
            "prob_fwd_gain_gt5_h20": _column(candidate=225, baseline=165, resolved=400, risk_delta=0.10),
        },
    )

    report = build_refresh_recommendation(audit)

    assert report["summary"]["recommendation"] == "refresh_candidate_supported"
    assert report["summary"]["reason"] == "candidate_more_accurate_and_risk_relevant_drift_within_limits"
    assert report["summary"]["supported_columns"] == [
        "h20_prob_up",
        "prob_fwd_mdd_gt5_h20",
        "prob_fwd_gain_gt5_h20",
    ]


def test_refresh_recommendation_manual_review_when_outcomes_are_sparse(tmp_path: Path) -> None:
    audit = tmp_path / "drift.json"
    _write_audit(audit, {"h20_prob_up": _column(candidate=8, baseline=6, resolved=20)})

    report = build_refresh_recommendation(audit)

    assert report["summary"]["recommendation"] == "manual_review"
    assert report["summary"]["reason"] == "outcome_aware_evidence_unavailable_or_too_sparse"
    assert report["columns"][0]["verdict"] == "insufficient_resolved_outcomes"


def test_write_outputs_writes_latest_markdown_history_and_snapshot(tmp_path: Path) -> None:
    report = {
        "summary": {"recommendation": "keep_current_pin", "reason": "candidate_not_more_accurate"},
        "baseline_panel": "/tmp/pinned.csv",
        "candidate_panel": "/tmp/candidate.csv",
        "columns": [],
        "decision": {
            "auto_pin_update_allowed": False,
            "target_weight_change_allowed": False,
            "creates_orders": False,
        },
    }
    output = tmp_path / "latest" / "ncf_panel_refresh_recommendation.json"
    output_md = tmp_path / "latest" / "ncf_panel_refresh_recommendation.md"
    snapshot = tmp_path / "results" / "ncf_panel_refresh_recommendation_20260730.json"
    history = tmp_path / "history"

    write_outputs(report, output=output, output_md=output_md, snapshot_output=snapshot, history_dir=history)

    assert output.exists()
    assert output_md.exists()
    assert snapshot.exists()
    assert json.loads(snapshot.read_text(encoding="utf-8"))["summary"]["recommendation"] == "keep_current_pin"
    assert list(history.glob("ncf_panel_refresh_recommendation_*.json"))
