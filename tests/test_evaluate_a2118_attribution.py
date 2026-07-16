from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_a2118_attribution import (
    compare_frames,
    regime_attribution,
    transition_events,
)


def _frame(values: list[float], regimes: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="B")
    return pd.DataFrame(
        {
            "portfolio_value": values,
            "execution_regime": regimes,
            "base_regime": regimes,
            "strategy_return": pd.Series(values, index=idx).pct_change().fillna(0.0).to_numpy(),
        },
        index=idx,
    )


def test_regime_attribution_and_transitions() -> None:
    frame = _frame([100.0, 101.0, 99.0, 100.0], ["golden1", "golden1", "defensive", "golden1"])

    by_regime = regime_attribution(frame)
    events = transition_events(frame, lookahead_days=2)

    assert by_regime["golden1"]["rows"] == 3
    assert by_regime["defensive"]["rows"] == 1
    assert [event["to"] for event in events] == ["golden1", "defensive", "golden1"]


def test_compare_frames_counts_regime_differences() -> None:
    baseline = _frame([100.0, 101.0, 102.0], ["golden1", "defensive", "golden1"])
    candidate = _frame([100.0, 102.0, 103.0], ["golden1", "golden1", "golden1"])

    result = compare_frames(baseline, candidate)

    assert result["rows"] == 3
    assert result["regime_different_days"] == 1
    assert result["final_value_delta"] == 1.0
