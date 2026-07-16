from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.evaluate.build_ncf_pit_historical_panel import build_pit_panel


def _write_panel(path: Path, dates: list[str]) -> None:
    pd.DataFrame(
        {
            "date": dates,
            "prob_up_h1": [0.51] * len(dates),
            "prob_up_h5": [0.52] * len(dates),
            "prob_up_h20": [0.53] * len(dates),
            "ensemble_prob_up": [0.54] * len(dates),
            "confidence": [0.08] * len(dates),
            "prob_fwd_mdd_gt5_h20": [0.30] * len(dates),
            "actual_fwd_mdd_gt5_h20": [1.0] * len(dates),
            "forward_mdd_h20": [-0.07] * len(dates),
            "prob_fwd_gain_gt5_h20": [0.40] * len(dates),
            "actual_fwd_gain_gt5_h20": [0.0] * len(dates),
            "forward_gain_h20": [0.02] * len(dates),
            "tail_reward_risk_score_h20": [0.10] * len(dates),
            "is_live": [False] * len(dates),
        }
    ).to_csv(path, index=False, encoding="utf-8-sig")


def test_pit_panel_drops_realized_forward_columns(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.csv"
    _write_panel(panel_path, ["2026-01-02", "2026-01-05"])

    panel, manifest = build_pit_panel([f"{panel_path}=unit"])

    assert len(panel) == 2
    assert "actual_fwd_mdd_gt5_h20" not in panel.columns
    assert "actual_fwd_gain_gt5_h20" not in panel.columns
    assert "forward_mdd_h20" not in panel.columns
    assert "forward_gain_h20" not in panel.columns
    assert "prob_fwd_mdd_gt5_h20" in panel.columns
    assert "prob_fwd_gain_gt5_h20" in panel.columns
    assert panel.loc[0, "asof_date"] == "2026-01-02"
    assert panel.loc[0, "next_trading_date_in_source"] == "2026-01-05"
    assert manifest["sources"][0]["dropped_leakage_columns"] == [
        "actual_fwd_mdd_gt5_h20",
        "forward_mdd_h20",
        "actual_fwd_gain_gt5_h20",
        "forward_gain_h20",
    ]


def test_pit_panel_rejects_overlapping_source_dates(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_panel(first, ["2026-01-02"])
    _write_panel(second, ["2026-01-02"])

    with pytest.raises(ValueError, match="Overlapping source panels"):
        build_pit_panel([f"{first}=first", f"{second}=second"])
