from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_weighted_rank_baseline import (
    backtest_rank_strategy,
    build_factor_frames,
    target_weights_from_score,
    weighted_rank_score,
)


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=80, freq="B")
    rows = []
    for ticker, drift in [("AAA.TW", 1.004), ("BBB.TW", 1.001), ("CCC.TW", 0.998)]:
        close = 100.0
        for i, date in enumerate(dates):
            close *= drift
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.98,
                    "close": close,
                    "volume": 1_000_000 + i * 1000,
                }
            )
    return pd.DataFrame(rows)


def test_weighted_rank_score_prefers_stronger_momentum() -> None:
    factors = build_factor_frames(_sample_ohlcv())
    score, used = weighted_rank_score(
        factors,
        {"momentum_20d": 1.0, "institutional_flow_20d": 1.0},
    )

    last = score.dropna(how="all").iloc[-1].sort_values(ascending=False)

    assert used == {"momentum_20d": 1.0}
    assert last.index[0] == "AAA.TW"
    assert last.index[-1] == "CCC.TW"


def test_target_weights_rebalance_top_n_only() -> None:
    score = pd.DataFrame(
        {
            "AAA.TW": [0.9, 0.1, 0.1],
            "BBB.TW": [0.2, 0.8, 0.8],
            "CCC.TW": [0.1, 0.7, 0.7],
        },
        index=pd.date_range("2026-01-01", periods=3, freq="B"),
    )

    weights = target_weights_from_score(score, top_n=2, rebalance_days=2)

    assert weights.iloc[0].to_dict() == {"AAA.TW": 0.5, "BBB.TW": 0.5, "CCC.TW": 0.0}
    assert weights.iloc[1].to_dict() == {"AAA.TW": 0.5, "BBB.TW": 0.5, "CCC.TW": 0.0}
    assert weights.iloc[2].to_dict() == {"AAA.TW": 0.0, "BBB.TW": 0.5, "CCC.TW": 0.5}


def test_backtest_applies_weights_with_one_day_lag() -> None:
    dates = pd.date_range("2026-01-01", periods=4, freq="B")
    close = pd.DataFrame(
        {
            "AAA.TW": [100.0, 110.0, 121.0, 133.1],
            "BBB.TW": [100.0, 100.0, 100.0, 100.0],
        },
        index=dates,
    )
    weights = pd.DataFrame(
        {
            "AAA.TW": [1.0, 1.0, 1.0, 1.0],
            "BBB.TW": [0.0, 0.0, 0.0, 0.0],
        },
        index=dates,
    )

    report = backtest_rank_strategy(close, weights, cost_bps=0.0, benchmark=None, initial_cash=100.0)

    # First day's target is only effective on the second return observation:
    # net returns are [0.0, 0.10, 0.10, 0.10].
    assert np.isclose(report["strategy"]["final_value"], 133.1)
    assert np.isclose(report["strategy"]["total_return"], 0.331)
