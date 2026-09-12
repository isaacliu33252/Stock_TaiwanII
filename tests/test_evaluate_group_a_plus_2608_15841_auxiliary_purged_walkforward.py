from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate import evaluate_group_a_plus_2608_15841_auxiliary_purged_walkforward as module


def _write_panels(left: Path, right: Path, *, rows: int = 180) -> None:
    left_rows = []
    right_rows = []
    for idx in range(rows):
        high_risk = idx % 4 == 0
        date = pd.Timestamp("2025-01-01") + pd.offsets.BDay(idx)
        left_rows.append(
            {
                "date": str(date.date()),
                "ensemble_prob_up": 0.35 if high_risk else 0.65,
                "confidence": 0.8,
                "prob_fwd_mdd_gt5_h20": 0.8 if high_risk else 0.2,
                "prob_fwd_gain_gt5_h20": 0.2 if high_risk else 0.8,
                "tail_reward_risk_score_h20": -0.4 if high_risk else 0.4,
                "forward_gain_h20": -0.02 if high_risk else 0.06,
                "forward_mdd_h20": -0.08 if high_risk else -0.01,
                "actual_fwd_mdd_gt5_h20": int(high_risk),
            }
        )
        right_rows.append(
            {
                "date": str(date.date()),
                "ensemble_prob_up": 0.65 if high_risk else 0.35,
                "confidence": 0.8,
                "prob_fwd_mdd_gt5_h20": 0.2 if high_risk else 0.8,
                "prob_fwd_gain_gt5_h20": 0.8 if high_risk else 0.2,
                "tail_reward_risk_score_h20": 0.4 if high_risk else -0.4,
            }
        )
    pd.DataFrame(left_rows).to_csv(left, index=False)
    pd.DataFrame(right_rows).to_csv(right, index=False)


def test_build_report_passes_consistent_purged_score_separation(tmp_path: Path) -> None:
    left = tmp_path / "631.csv"
    right = tmp_path / "632.csv"
    _write_panels(left, right)

    report = module.build_report(left, right, n_splits=3, purge=20, min_train_size=60)

    assert report["policy"] == "research_only_no_weight_change"
    assert report["summary"]["purged_walk_forward_policy_impact_passed"] is True
    assert report["summary"]["by_score"]["downside_score"]["passed"] is True
    assert report["decision"]["promotion_allowed"] is False


def test_write_markdown_renders_summary(tmp_path: Path) -> None:
    left = tmp_path / "631.csv"
    right = tmp_path / "632.csv"
    _write_panels(left, right)
    report = module.build_report(left, right, n_splits=3, purge=20, min_train_size=60)
    output = tmp_path / "wf.md"

    module.write_markdown(report, output)

    text = output.read_text(encoding="utf-8")
    assert "2608.15841 Auxiliary Purged Walk-Forward" in text
    assert "downside_score" in text
