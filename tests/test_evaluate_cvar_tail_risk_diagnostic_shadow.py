from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import _summarize_returns


def test_summarize_returns_includes_rachev_tail_gain_metrics() -> None:
    returns = pd.Series(
        [-0.06, -0.04, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.05, 0.08],
        index=pd.bdate_range("2026-01-01", periods=10),
    )

    summary = _summarize_returns(returns)

    assert summary["expected_tail_gain_95"] is not None
    assert summary["expected_shortfall_loss_95"] is not None
    assert summary["rachev_95_95"] is not None
    assert summary["rachev_95_95"] > 0
