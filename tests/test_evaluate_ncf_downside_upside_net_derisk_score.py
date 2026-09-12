from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_ncf_downside_upside_net_derisk_score import _score_behavior_summary


def test_score_behavior_summary_tracks_churn_and_missed_upside() -> None:
    index = pd.date_range("2026-01-01", periods=5, freq="D")
    score = pd.Series([0.0, 0.2, 0.2, 0.0, 0.4], index=index)
    golden_mask = pd.Series([True, True, True, False, True], index=index)
    forward_gain = pd.Series([0.01, 0.03, -0.02, 0.04, 0.05], index=index)

    summary = _score_behavior_summary(score, golden_mask, forward_gain)

    assert summary["golden1_days_score_gt_0"] == 3
    assert summary["golden1_score_change_days"] == 2
    assert summary["missed_upside_proxy_days"] == 2
    assert summary["mean_forward_gain_h20_when_active"] == (0.03 - 0.02 + 0.05) / 3
