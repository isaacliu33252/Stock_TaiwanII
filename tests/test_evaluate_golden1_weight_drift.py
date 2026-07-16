from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_golden1_weight_drift import _dynamic_daily_curve, _static_curve, load_weight_history


def _write_signal(path: Path, date: str, weight_0050: float, weight_631l: float) -> None:
    path.write_text(
        json.dumps(
            {
                "actual_data_date": date,
                "target_weights": {
                    "0050.TW": weight_0050,
                    "00631L.TW": weight_631l,
                    "00632R.TW": 0.0,
                    "00679B.TWO": 0.0,
                },
                "target_cash_weight": max(0.0, 1.0 - weight_0050 - weight_631l),
            }
        ),
        encoding="utf-8",
    )


def test_load_weight_history_deduplicates_by_signal_date(tmp_path: Path) -> None:
    _write_signal(tmp_path / "signal_group_a_20260101_010000.json", "2026-01-01", 0.8, 0.1)
    _write_signal(tmp_path / "signal_group_a_20260101_020000.json", "2026-01-01", 0.7, 0.2)
    _write_signal(tmp_path / "signal_group_a_20260102_010000.json", "2026-01-02", 0.6, 0.3)

    history = load_weight_history(tmp_path)

    assert history["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01", "2026-01-02"]
    assert np.isclose(history.iloc[0]["00631L.TW"], 0.2)
    assert np.isclose(history.iloc[1]["00631L.TW"], 0.3)


def test_dynamic_daily_curve_uses_previous_day_weights() -> None:
    dates = pd.date_range("2026-01-01", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 100.0],
            "00631L.TW": [100.0, 110.0, 121.0],
            "00632R.TW": [100.0, 100.0, 100.0],
            "00679B.TWO": [100.0, 100.0, 100.0],
        },
        index=dates,
    )
    history = pd.DataFrame(
        {
            "date": dates,
            "0050.TW": [0.0, 1.0, 1.0],
            "00631L.TW": [1.0, 0.0, 0.0],
            "00632R.TW": [0.0, 0.0, 0.0],
            "00679B.TWO": [0.0, 0.0, 0.0],
            "cash": [0.0, 0.0, 0.0],
        }
    )

    curve, _weights = _dynamic_daily_curve(prices, history, 100.0)

    assert np.isclose(curve.iloc[0], 100.0)
    assert np.isclose(curve.iloc[1], 110.0)
    assert np.isclose(curve.iloc[2], 110.0)


def test_static_curve_respects_cash_weight() -> None:
    dates = pd.date_range("2026-01-01", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 110.0],
            "00631L.TW": [100.0, 100.0],
            "00632R.TW": [100.0, 100.0],
            "00679B.TWO": [100.0, 100.0],
        },
        index=dates,
    )

    curve = _static_curve(prices, {"0050.TW": 0.5, "cash": 0.5}, 100.0)

    assert np.isclose(curve.iloc[-1], 105.0)
