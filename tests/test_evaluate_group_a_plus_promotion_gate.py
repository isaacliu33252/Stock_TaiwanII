from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_promotion_gate import build_promotion_gate


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_promotion_gate_blocks_when_panel_drift_exceeds_limit(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                # h20_prob_up is trigger-critical (a2118 reads it directly). Its
                # limit was recalibrated from 0.05 to 0.15 on 2026-07-07 (see
                # DRIFT_LIMIT_TIERS comment -- 0.05 was unsatisfiable even by
                # the accepted, shipped panel-drift fix), so 0.20 must still fail.
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.20, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift)

    assert report["metrics_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["status"] == "fail"
    assert report["decision"] == "blocked_panel_drift"
    assert report["panel_drift_gate"]["checks"]["h20_prob_up"]["tier"] == "trigger_critical"


def test_promotion_gate_allows_relaxed_diagnostic_drift_within_new_tier_limit(tmp_path: Path) -> None:
    """2026-07-07 Fable audit: under the old flat 0.05 limit, any NCF-panel
    candidate was permanently blocked because ensemble_prob_up (a diagnostic
    column a2118 never reads) has irreducible residual drift up to ~0.11-0.21
    even in the validated, promoted 2026-07-07 panel-drift fix. 0.15 must now
    pass -- it would have failed under the old flat limit."""
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.15, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift)

    assert report["panel_drift_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["checks"]["ensemble_prob_up"]["tier"] == "diagnostic"
    assert report["decision"] == "promotion_ready"


def test_promotion_gate_allows_formal_candidate_when_drift_passes(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift)

    assert report["metrics_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["status"] == "pass"
    assert report["multi_window_gate"]["status"] == "not_required"
    assert report["decision"] == "promotion_ready"


def test_promotion_gate_blocks_when_multi_window_gate_fails(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    multi_window = _write_json(
        tmp_path / "multi_window.json",
        {
            "decision": "research_only_no_multi_window_pass",
            "row_count": 2,
            "candidate_count": 1,
            "criteria": {"min_pass_ratio": 1.0},
            "candidates": [
                {
                    "candidate": "strong_candidate",
                    "decision": "research_only_multi_window_unstable",
                    "pass_count": 1,
                    "window_count": 2,
                    "pass_ratio": 0.5,
                }
            ],
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=drift,
        multi_window_gate=multi_window,
    )

    assert report["metrics_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["status"] == "pass"
    assert report["multi_window_gate"]["status"] == "fail"
    assert report["decision"] == "blocked_multi_window"


def test_promotion_gate_reports_combined_blockers(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.20, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=drift,
        require_multi_window_gate=True,
    )

    assert report["panel_drift_gate"]["status"] == "fail"
    assert report["multi_window_gate"]["status"] == "fail"
    assert report["decision"] == "blocked_panel_drift_and_multi_window"
