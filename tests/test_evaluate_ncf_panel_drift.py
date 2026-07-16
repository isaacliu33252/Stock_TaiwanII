from __future__ import annotations

from pathlib import Path

import pandas as pd

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
