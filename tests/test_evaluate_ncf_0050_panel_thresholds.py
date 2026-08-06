from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate.evaluate_ncf_0050_panel_thresholds import evaluate_thresholds


def test_evaluate_thresholds_recommends_worse_h20_bucket(tmp_path: Path) -> None:
    rows = []
    for i in range(40):
        weak = i < 20
        rows.append(
            {
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "prob_up_h1": 0.4 if weak else 0.7,
                "prob_up_h5": 0.4 if weak else 0.7,
                "prob_up_h20": 0.3 if weak else 0.7,
                "confidence": 0.2,
                "actual_up_h1": 0 if weak else 1,
                "actual_up_h5": 0 if weak else 1,
                "actual_up_h20": 0 if weak else 1,
                "prob_fwd_mdd_gt5_h20": 0.7 if weak else 0.2,
                "actual_fwd_mdd_gt5_h20": 1 if weak else 0,
                "forward_mdd_h20": -0.08 if weak else -0.01,
                "prob_fwd_gain_gt5_h20": 0.2 if weak else 0.7,
                "actual_fwd_gain_gt5_h20": 0 if weak else 1,
                "forward_gain_h20": -0.02 if weak else 0.08,
                "is_live": False,
            }
        )
    panel = tmp_path / "panel.csv"
    pd.DataFrame(rows).to_csv(panel, index=False)

    report = evaluate_thresholds(
        panel,
        h20_thresholds=[0.35],
        confidence_thresholds=[0.1],
        min_active_rows=10,
    )

    assert report["metrics"]["h20_direction"]["auc"] == 1.0
    candidate = report["recommendation"]["candidate"]
    assert candidate["h20_prob_up_max"] == 0.35
    assert candidate["confidence_min"] == 0.1
    assert candidate["active_rows"] == 20
    assert candidate["active_actual_up_rate_h20"] == 0.0
    assert candidate["active_mdd_gt5_rate_h20"] == 1.0
