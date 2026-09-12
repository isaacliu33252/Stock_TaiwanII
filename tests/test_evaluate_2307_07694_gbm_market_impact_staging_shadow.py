from __future__ import annotations

import numpy as np

from scripts.evaluate.evaluate_2307_07694_gbm_market_impact_staging_shadow import _run_policy


def test_staged_execution_reduces_convex_impact_cost_on_flat_path() -> None:
    tickers = ["0050.TW"]
    price_path = np.full((6, 1), 100.0, dtype=float)
    common = {
        "price_path": price_path,
        "tickers": tickers,
        "current_shares": {"0050.TW": 0},
        "current_cash": 1_000_000.0,
        "staged_target": {"0050.TW": 4000},
        "full_target": {"0050.TW": 10000},
        "defer_days": 5,
        "commission_rate": 0.0,
        "slippage_rate": 0.0,
        "equity_etf_sell_tax": 0.0,
        "impact_scale": 3.0,
    }

    full = _run_policy(policy="full_day0", **common)
    staged = _run_policy(policy="staged_then_full", **common)

    assert staged["transaction_cost"] < full["transaction_cost"]
    assert staged["turnover_notional"] == full["turnover_notional"]
    assert staged["final_value"] > full["final_value"]
