from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate import backtest_group_a_plus_llm_state_reward_regime_filtered_micro_tilt_shadow as regime


def test_active_regime_rules() -> None:
    row = pd.Series(
        {
            "ema_cross_strength": 0.2,
            "realized_volatility": 0.01,
            "downside_deviation": 0.005,
            "drawdown_depth": 0.1,
        }
    )
    thresholds = {
        "trend_median": 0.0,
        "vol_70q": 0.02,
        "downside_70q": 0.01,
        "drawdown_70q": 0.2,
    }

    assert regime._active_regime(row, thresholds, "trend_above_train_median") is True
    assert regime._active_regime(row, thresholds, "vol_below_train_70q") is True
    assert regime._active_regime(row, thresholds, "trend_vol_downside") is True

    row["realized_volatility"] = 0.03
    assert regime._active_regime(row, thresholds, "trend_and_vol") is False
    assert regime._active_regime(row, thresholds, "trend_and_downside") is True


def test_daily_regime_averages_eligible_tickers_only() -> None:
    panel = pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "ticker": "0050.TW",
                "realized_volatility": 0.01,
                "downside_deviation": 0.02,
                "drawdown_depth": 0.03,
                "ema_cross_strength": 0.04,
            },
            {
                "date": "2026-01-01",
                "ticker": "0056.TW",
                "realized_volatility": 0.03,
                "downside_deviation": 0.04,
                "drawdown_depth": 0.05,
                "ema_cross_strength": 0.06,
            },
            {
                "date": "2026-01-01",
                "ticker": "00631L.TW",
                "realized_volatility": 1.0,
                "downside_deviation": 1.0,
                "drawdown_depth": 1.0,
                "ema_cross_strength": 1.0,
            },
        ]
    )
    panel["date"] = pd.to_datetime(panel["date"])

    daily = regime._daily_regime(panel, ["0050.TW", "0056.TW"])

    assert daily.loc[pd.Timestamp("2026-01-01"), "realized_volatility"] == 0.02
    assert daily.loc[pd.Timestamp("2026-01-01"), "ema_cross_strength"] == 0.05


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "regime.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_regime_filtered_micro_tilt_shadow_backtest",
        "as_of": "2026-07-21",
    }

    regime.write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_regime_filtered_micro_tilt_shadow_backtest_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
