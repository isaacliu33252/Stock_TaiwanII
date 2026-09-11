from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from scripts.evaluate.replay_group_a_plus_2609_08106_latest_target_weights import (
    _apply_sleeve,
    _load_target_weights,
    build_report,
)


def test_load_target_weights_maps_short_assets_to_tickers(tmp_path: Path) -> None:
    csv_path = tmp_path / "weights.csv"
    csv_path.write_text(
        "date,execution_regime,target_weight_0050,target_weight_00631L,target_weight_00632R,target_weight_00679B,target_weight_cash\n"
        "2026-01-02,golden1,0.50,0.20,0.00,0.10,0.20\n",
        encoding="utf-8",
    )

    weights = _load_target_weights(csv_path)

    assert weights.loc[pd.Timestamp("2026-01-02"), "0050.TW"] == 0.50
    assert weights.loc[pd.Timestamp("2026-01-02"), "00631L.TW"] == 0.20
    assert weights.loc[pd.Timestamp("2026-01-02"), "00679B.TWO"] == 0.10
    assert weights.loc[pd.Timestamp("2026-01-02"), "cash"] == 0.20


def test_apply_sleeve_shifts_only_existing_00631l_weight() -> None:
    idx = pd.to_datetime(["2026-01-02", "2026-01-05"])
    weights = pd.DataFrame(
        {
            "0050.TW": [0.5, 0.5],
            "00631L.TW": [0.02, 0.0],
            "00632R.TW": [0.0, 0.0],
            "00679B.TWO": [0.1, 0.1],
            "00713.TW": [0.1, 0.1],
            "00751B.TWO": [0.0, 0.0],
            "00878.TW": [0.0, 0.0],
            "cash": [0.28, 0.3],
        },
        index=idx,
    )
    scores = pd.DataFrame(
        {
            "best_bond": ["00679B.TWO", "00679B.TWO"],
            "best_bond_score": [2.0, 2.0],
            "score_00631l": [-1.0, -1.0],
            "momentum_5d_00631l": [-0.01, -0.01],
            "drawdown_window_00631l": [-0.02, -0.02],
            "ann_vol_00631l": [0.5, 0.5],
        },
        index=idx,
    )

    adjusted, events = _apply_sleeve(
        weights,
        scores,
        shift_weight=0.03,
        threshold=2.0,
        momentum_5d_max=0.0,
        drawdown_max=-0.03,
        ann_vol_min=0.35,
    )

    assert len(events) == 1
    assert events[0]["shift_from_00631l"] == 0.02
    assert adjusted.loc[idx[0], "00631L.TW"] == 0.0
    assert adjusted.loc[idx[0], "00679B.TWO"] == pytest.approx(0.12)
    assert adjusted.loc[idx[1], "00631L.TW"] == 0.0


def test_build_report_blocks_live_when_latest_weights_have_no_00631l_events(tmp_path: Path) -> None:
    db_path = tmp_path / "prices.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        dates = pd.bdate_range("2025-12-01", "2026-01-15")
        tickers = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW", "00751B.TWO", "00878.TW")
        for i, dt in enumerate(dates):
            for j, ticker in enumerate(tickers):
                con.execute("INSERT INTO ohlcv VALUES (?, ?, ?)", [dt.date(), ticker, 100.0 + i + j])
    finally:
        con.close()
    weights_csv = tmp_path / "weights.csv"
    weights_csv.write_text(
        "date,execution_regime,target_weight_0050,target_weight_00631L,target_weight_00632R,target_weight_00679B,target_weight_cash\n"
        "2026-01-02,golden1,0.60,0.00,0.00,0.10,0.30\n"
        "2026-01-05,golden1,0.60,0.00,0.00,0.10,0.30\n",
        encoding="utf-8",
    )

    report = build_report(
        argparse.Namespace(
            db=db_path,
            target_weights=weights_csv,
            start=None,
            end=None,
            window=5,
            threshold=2.0,
            shift_weight=0.03,
            cost_bps=10.0,
            momentum_5d_max=0.0,
            drawdown_max=-0.03,
            ann_vol_min=0.35,
            initial_value=1_000_000.0,
        )
    )

    assert report["event_count"] == 0
    assert report["decision"]["target_weight_change_allowed"] is False
    assert "no_sleeve_events_on_latest_target_weights" in report["decision"]["blockers"]
    assert report["coverage"]["days_with_00631l_weight"] == 0
