from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_harlf_branch_ablation_shadow import build_ablation


def test_harlf_branch_ablation_builds_market_sentiment_and_combined_metrics() -> None:
    dates = pd.bdate_range("2025-01-01", "2025-06-30")
    close = pd.DataFrame(
        {
            "0050": 100.0 * np.cumprod(1.0 + np.linspace(0.0001, 0.001, len(dates))),
            "00631L": 80.0 * np.cumprod(1.0 + np.linspace(0.001, -0.0002, len(dates))),
            "2330": 120.0 * np.cumprod(1.0 + np.linspace(-0.0001, 0.0008, len(dates))),
        },
        index=dates,
    )
    sentiment = pd.DataFrame(
        {
            "month": ["2025-01", "2025-01", "2025-02", "2025-02", "2025-03", "2025-03"],
            "ticker": ["0050", "00631L", "0050", "00631L", "0050", "00631L"],
            "sentiment_score": [0.1, -0.2, 0.2, -0.1, -0.1, 0.3],
            "news_intensity": [10, 5, 9, 7, 6, 3],
        }
    )

    report = build_ablation(close=close, sentiment=sentiment, start_month="2025-01", end_month="2025-05")

    assert report["report_type"] == "group_a_plus_harlf_branch_ablation_shadow"
    assert report["status"] == "available"
    assert "market_only" in report["branch_metrics"]
    assert "sentiment_only" in report["branch_metrics"]
    assert "combined" in report["branch_metrics"]
    assert report["decision"]["market_only_base_agent_oos_backtest_available"] is True
    assert report["decision"]["sentiment_only_base_agent_oos_backtest_available"] is True
    assert report["decision"]["changes_target_weights"] is False
