from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate import build_group_a_plus_2608_15841_auxiliary_lifecycle_audit as module


def _write_panel(path: Path, *, weak_recent: bool = False, redundant: bool = False) -> None:
    rows = []
    for idx in range(180):
        actual = idx % 2
        good = 0.8 if actual else 0.2
        bad = 0.2 if actual else 0.8
        draw_prob = bad if weak_recent and idx >= 54 else good
        gain_prob = draw_prob if redundant else (good + (0.05 if idx % 3 == 0 else -0.03))
        tail_score = gain_prob if redundant else (good + (0.04 if idx % 3 == 0 else -0.04))
        rows.append(
            {
                "date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx)).strftime("%Y-%m-%d"),
                "prob_fwd_mdd_gt5_h20": draw_prob,
                "actual_fwd_mdd_gt5_h20": actual,
                "prob_fwd_gain_gt5_h20": gain_prob,
                "actual_fwd_gain_gt5_h20": actual,
                "tail_reward_risk_score_h20": tail_score,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_lifecycle_audit_marks_retire_candidate_for_recent_and_regime_failure(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel, weak_recent=True)

    report = module.build_report(
        [("00631L.TW", panel)],
        regime_decay={
            "summary": {
                "failed_tasks": [
                    {"ticker": "00631L.TW", "task": "h20_forward_drawdown_gt5", "blockers": ["recent_auc_below_floor"]}
                ]
            }
        },
        min_recent_auc=0.52,
    )

    drawdown = next(item for item in report["heads"] if item["head"] == "h20_forward_drawdown_gt5")
    assert drawdown["status"] == "retire_candidate"
    assert "head_lifecycle_review_required" in report["summary"]["blockers"]
    assert report["summary"]["promotion_allowed"] is False


def test_lifecycle_audit_marks_redundant_candidate(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel, redundant=True)

    report = module.build_report([("00631L.TW", panel)], corr_threshold=0.85)

    assert report["redundancy_pairs"]
    assert any(item["status"] == "redundant_candidate" for item in report["heads"])


def test_lifecycle_audit_keeps_stable_nonredundant_heads(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel)

    report = module.build_report([("00631L.TW", panel)], corr_threshold=1.0001)

    assert report["summary"]["head_lifecycle_passed"] is True
    assert {item["status"] for item in report["heads"]} == {"keep_shadow"}
