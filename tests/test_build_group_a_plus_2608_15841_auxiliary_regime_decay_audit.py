from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate import build_group_a_plus_2608_15841_auxiliary_regime_decay_audit as module


def _write_panel(path: Path, *, degrading: bool) -> None:
    rows = []
    for idx in range(160):
        actual = idx % 2
        good_prob = 0.8 if actual else 0.2
        bad_prob = 0.2 if actual else 0.8
        prob = bad_prob if degrading and idx >= 80 else good_prob
        rows.append(
            {
                "date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx)).strftime("%Y-%m-%d"),
                "direction": "UP" if idx % 3 else "DOWN",
                "confidence": 0.8 if idx % 4 in {0, 1} else 0.2,
                "tail_reward_risk_score_h20": 0.7 if idx % 5 else -0.1,
                "prob_fwd_mdd_gt5_h20": prob,
                "actual_fwd_mdd_gt5_h20": actual,
                "prob_fwd_gain_gt5_h20": prob,
                "actual_fwd_gain_gt5_h20": actual,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_regime_decay_audit_blocks_recent_auc_decay(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel, degrading=True)

    report = module.build_report(
        [("00631L.TW", panel)],
        min_slice_rows=20,
        min_recent_auc=0.52,
        max_auc_decay=0.15,
    )

    assert report["summary"]["temporal_regime_stability_passed"] is False
    assert report["summary"]["promotion_allowed"] is False
    assert "unstable_auxiliary_task_slices" in report["summary"]["blockers"]
    assert report["summary"]["failed_tasks"]


def test_regime_decay_audit_passes_when_slices_are_stable(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel, degrading=False)

    report = module.build_report(
        [("00631L.TW", panel)],
        min_slice_rows=20,
        min_recent_auc=0.52,
        max_auc_decay=0.15,
    )

    assert report["summary"]["temporal_regime_stability_passed"] is True
    assert report["summary"]["promotion_allowed"] is False
