from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.evaluate.evaluate_ncf_panel_drift import evaluate_panel_drift


def test_evaluate_panel_drift_summarizes_overlap_and_focus_date(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.60, "confidence": 0.20},
            {"date": "2025-01-03", "h20_prob_up": 0.70, "confidence": 0.30},
        ]
    ).to_csv(baseline, index=False)
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.65, "confidence": 0.10},
            {"date": "2025-01-03", "h20_prob_up": 0.68, "confidence": 0.55},
            {"date": "2025-01-06", "h20_prob_up": 0.50, "confidence": 0.50},
        ]
    ).to_csv(candidate, index=False)

    summary, drift = evaluate_panel_drift(
        baseline,
        candidate,
        columns=["h20_prob_up", "confidence"],
        focus_dates=["2025-01-03"],
        top_n=1,
    )

    assert summary["overlap_rows"] == 2
    assert summary["candidate_rows"] == 3
    assert summary["column_summary"]["confidence"]["max_abs_delta"] == 0.25000000000000006
    assert summary["column_summary"]["confidence"]["max_abs_delta_date"] == "2025-01-03"
    assert summary["focus_rows"][0]["date"] == "2025-01-03"
    assert summary["focus_rows"][0]["confidence_delta"] == 0.25000000000000006
    assert len(summary["top_drift_rows"]) == 1
    assert list(drift["date"]) == ["2025-01-03", "2025-01-02"]
    assert summary["window_start"] is None
    assert summary["full_overlap_start"] == "2025-01-02"
    assert summary["full_overlap_end"] == "2025-01-03"
    assert summary["full_overlap_rows"] == 2


def test_evaluate_panel_drift_window_start_restricts_summary_but_not_full_overlap(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.60, "confidence": 0.20},
            {"date": "2025-01-03", "h20_prob_up": 0.70, "confidence": 0.30},
        ]
    ).to_csv(baseline, index=False)
    pd.DataFrame(
        [
            # 2025-01-02 has the largest delta but is excluded by window_start.
            {"date": "2025-01-02", "h20_prob_up": 0.05, "confidence": 0.90},
            {"date": "2025-01-03", "h20_prob_up": 0.68, "confidence": 0.55},
        ]
    ).to_csv(candidate, index=False)

    summary, drift = evaluate_panel_drift(
        baseline,
        candidate,
        columns=["h20_prob_up", "confidence"],
        window_start="2025-01-03",
    )

    assert summary["overlap_rows"] == 1
    assert summary["window_start"] == "2025-01-03"
    assert summary["full_overlap_start"] == "2025-01-02"
    assert summary["full_overlap_rows"] == 2
    assert list(drift["date"]) == ["2025-01-03"]
    # Excluding 2025-01-02 means the large synthetic delta on that date no
    # longer dominates column_summary -- this is the fix for the
    # full-history max never being supersedable by future observations.
    assert summary["column_summary"]["confidence"]["max_abs_delta_date"] == "2025-01-03"
    assert summary["column_summary"]["confidence"]["max_abs_delta"] == 0.25000000000000006


def test_evaluate_panel_drift_outcome_aware_excludes_candidate_favorable_dates(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame(
        [
            # 2025-01-02: baseline way off (0.9 vs actual 0), candidate closer
            # (0.5) -- large delta, but candidate was the *better* call.
            {"date": "2025-01-02", "h20_prob_up": 0.9, "actual_up_h20": 0.0},
            # 2025-01-03: baseline closer (0.5 vs actual 0), candidate worse
            # (0.9) -- same-sized delta, but this time candidate was wrong.
            {"date": "2025-01-03", "h20_prob_up": 0.5, "actual_up_h20": 0.0},
            # 2025-01-04: unresolved label (still live) -- smaller delta,
            # conservatively still counted as risk-relevant.
            {"date": "2025-01-04", "h20_prob_up": 0.5, "actual_up_h20": None},
        ]
    ).to_csv(baseline, index=False)
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.5, "actual_up_h20": 0.0},
            {"date": "2025-01-03", "h20_prob_up": 0.9, "actual_up_h20": 0.0},
            {"date": "2025-01-04", "h20_prob_up": 0.7, "actual_up_h20": None},
        ]
    ).to_csv(candidate, index=False)

    summary, _drift = evaluate_panel_drift(
        baseline,
        candidate,
        columns=["h20_prob_up"],
        outcome_aware=True,
    )

    h20 = summary["column_summary"]["h20_prob_up"]
    # Raw max is unaffected by outcome-awareness (backward compatible) --
    # both 2025-01-02 and 2025-01-03 tie at abs delta 0.4; raw picks the
    # first chronologically.
    assert h20["max_abs_delta"] == pytest.approx(0.4)
    assert h20["max_abs_delta_date"] == "2025-01-02"

    oa = h20["outcome_aware"]
    assert oa["actual_column"] == "actual_up_h20"
    assert oa["resolved_rows"] == 2
    assert oa["candidate_favorable_rows"] == 1
    assert oa["baseline_favorable_rows"] == 1
    assert oa["tie_rows"] == 0
    # The candidate-favorable date (2025-01-02) is excluded from the
    # risk-relevant max -- it should land on 2025-01-03 instead, where the
    # candidate was actually the worse call.
    assert oa["risk_relevant_max_abs_delta"] == pytest.approx(0.4)
    assert oa["risk_relevant_max_abs_delta_date"] == "2025-01-03"


def test_evaluate_panel_drift_confidence_has_no_outcome_aware_block(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame([{"date": "2025-01-02", "confidence": 0.2}]).to_csv(baseline, index=False)
    pd.DataFrame([{"date": "2025-01-02", "confidence": 0.8}]).to_csv(candidate, index=False)

    summary, _drift = evaluate_panel_drift(
        baseline, candidate, columns=["confidence"], outcome_aware=True
    )

    assert "outcome_aware" not in summary["column_summary"]["confidence"]
