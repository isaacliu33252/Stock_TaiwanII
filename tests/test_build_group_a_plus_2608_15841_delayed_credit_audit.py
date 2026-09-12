from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate import build_group_a_plus_2608_15841_delayed_credit_audit as module


def _write_panel(path: Path, *, inverted_gain: bool = False) -> None:
    rows = []
    for idx in range(160):
        actual = idx % 2
        gain_prob = 0.8 if actual else 0.2
        if inverted_gain:
            gain_prob = 1.0 - gain_prob
        drawdown_prob = 0.8 if not actual else 0.2
        rows.append(
            {
                "date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx)).strftime("%Y-%m-%d"),
                "ensemble_prob_up": gain_prob,
                "prob_fwd_mdd_gt5_h20": drawdown_prob,
                "prob_fwd_gain_gt5_h20": gain_prob,
                "tail_reward_risk_score_h20": gain_prob,
                "actual_up_h1": actual,
                "actual_up_h5": actual,
                "actual_up_h20": actual,
                "actual_fwd_mdd_gt5_h20": 1 - actual,
                "actual_fwd_gain_gt5_h20": actual,
                "forward_gain_h20": 0.08 if actual else -0.03,
                "forward_mdd_h20": -0.02 if actual else -0.08,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_delayed_credit_audit_passes_when_heads_align_with_future_outcomes(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel)

    report = module.build_report([("00631L.TW", panel)], min_h20_auc=0.52)

    assert report["summary"]["delayed_credit_passed"] is True
    assert report["summary"]["promotion_allowed"] is False
    assert all(item["passed"] for item in report["heads"])


def test_delayed_credit_audit_blocks_inverted_gain_head(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel, inverted_gain=True)

    report = module.build_report([("00631L.TW", panel)], min_h20_auc=0.52)

    assert report["summary"]["delayed_credit_passed"] is False
    assert "delayed_credit_alignment_failed" in report["summary"]["blockers"]
    assert any(item["head"] == "gain_prob" for item in report["summary"]["failed_heads"])
