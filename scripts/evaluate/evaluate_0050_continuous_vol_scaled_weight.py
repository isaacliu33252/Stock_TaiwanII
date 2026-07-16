#!/usr/bin/env python3
"""Does continuous inverse-volatility position sizing improve 0050.TW's
risk-adjusted return, independent of any return forecast?

Research-only, motivated by Pinelis & Ruppert (2020, arXiv:2003.00656),
"Machine Learning Portfolio Allocation". That paper's own out-of-sample
results show return forecasting barely works (R^2 = 0.52%, essentially
noise) while volatility forecasting works well (R^2 ~ 50-55%) -- consistent
with everything found on 0050.TW/00631L.TW this session (Wang & Yan
downside-vol, GNHAR, RSJ proxy, TXO positioning: all null on return
predictability). The one piece of that paper NOT already tested this
session: its "Base" strategy (no ML at all -- just historical mean return
divided by lagged realized volatility, `w_t = c / sigma_t^2`) beats
buy-and-hold on Sharpe (0.57 -> 0.67) using ONLY volatility-timing, with NO
return-forecasting skill required. This is a different, weaker, and more
robust claim than anything tested today: not "does volatility predict
returns" (tested repeatedly, null), but "does scaling position size
inversely to (persistent, well-forecastable) volatility improve realized
Sharpe regardless of whether returns are predictable at all."

This is also mechanically the same idea as Moreira & Muir (2017)
volatility-managed portfolios and group_a_plus/integrations/
garch_regime_shadow.py's volatility_gate_reference -- but that gate uses
DISCRETE buckets (shadow-only, never continuous), and every downside-vol
test this session asked whether vol *predicts returns* (a return-timing
question), not whether continuous vol-scaling improves *realized Sharpe* (a
pure risk-timing question that does not require return predictability).

Method: simplest possible test, matching the paper's own "Base" strategy.
  w_t = clip(c / sigma_t^2, 0, cap), sigma_t = trailing 21-trading-day
  realized volatility (annualized) of 0050.TW daily returns.
  c is calibrated post-hoc so mean(w_t) over the full sample equals 1.0
  (same average exposure as buy-and-hold, for a fair Sharpe comparison --
  same logic as Moreira & Muir's own c-calibration).
Compared against plain buy-and-hold (w=1.0 always), with and without a
simple round-trip transaction cost estimate (this project's standard
commission+slippage+tax assumptions) to check the mechanism survives costs
before any consideration of wiring it into golden1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from scripts.evaluate.evaluate_downside_vol_return_timing import _load_close

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "0050_continuous_vol_scaled_weight_latest.json"
REALIZED_VOL_WINDOW = 21  # trading days, ~1 month, matches the paper's convention
WEIGHT_CAP = 1.5  # matches the paper's realistic 150% leverage constraint
COMMISSION_RATE = 0.001425
SLIPPAGE_RATE = 0.0005
SELL_TAX = 0.001


def _realized_vol_annualized(returns: pd.Series, window: int = REALIZED_VOL_WINDOW) -> pd.Series:
    return returns.rolling(window, min_periods=window).std() * np.sqrt(252)


def _simulate(
    close: pd.Series,
    weight: pd.Series,
    initial_value: float,
    *,
    apply_costs: bool,
) -> tuple[pd.Series, dict]:
    returns = close.pct_change().fillna(0.0)
    values = [initial_value]
    total_cost = 0.0
    total_turnover = 0.0
    prev_w = 0.0
    for i in range(1, len(close)):
        dt = close.index[i]
        w = float(weight.loc[dt]) if dt in weight.index and pd.notna(weight.loc[dt]) else prev_w
        gross_value = values[-1] * (1.0 + prev_w * returns.iloc[i])
        if apply_costs and abs(w - prev_w) > 1e-9:
            trade = abs(w - prev_w) * gross_value
            cost = trade * (COMMISSION_RATE + SLIPPAGE_RATE) + (
                trade * SELL_TAX if w < prev_w else 0.0
            )
            gross_value -= cost
            total_cost += cost
            total_turnover += trade
        values.append(gross_value)
        prev_w = w
    return pd.Series(values, index=close.index, dtype=float), {
        "transaction_cost": total_cost,
        "turnover_value": total_turnover,
    }


def evaluate(ticker: str, start: str, end: str, initial_value: float, *, monthly_rebalance: bool) -> dict:
    close = _load_close(DB_PATH, ticker).loc[start:end]
    returns = close.pct_change().fillna(0.0)
    vol = _realized_vol_annualized(returns)
    vol2 = vol**2

    valid_vol2 = vol2.replace(0.0, np.nan)
    inv_vol2 = 1.0 / valid_vol2
    raw_weight = inv_vol2.shift(1)  # causal: today's weight uses yesterday's vol estimate
    if monthly_rebalance:
        # Matches the paper's actual design: vol estimated once per month,
        # weight held fixed intra-month. Forward-fill each month's first
        # trading-day weight through the rest of that month.
        month_start_mask = ~close.index.to_period("M").duplicated()
        raw_weight = raw_weight.where(month_start_mask).ffill()
    c = 1.0 / raw_weight.dropna().mean() if raw_weight.notna().any() else 1.0
    vol_scaled_weight = (c * raw_weight).clip(lower=0.0, upper=WEIGHT_CAP).fillna(0.0)

    buy_hold_weight = pd.Series(1.0, index=close.index)

    results = {}
    for label, weight in (("buy_hold", buy_hold_weight), ("vol_scaled", vol_scaled_weight)):
        for cost_label, apply_costs in (("gross", False), ("net_of_costs", True)):
            curve, sim = _simulate(close, weight, initial_value, apply_costs=apply_costs)
            metrics = _metrics(curve, initial_value)
            results[f"{label}_{cost_label}"] = {
                "sharpe_ratio": metrics["sharpe_ratio"],
                "annual_return": metrics.get("annual_return"),
                "max_drawdown": metrics["max_drawdown"],
                "final_value": metrics["final_value"],
                "transaction_cost": sim["transaction_cost"],
                "mean_weight": float(weight.mean()),
            }

    return {
        "ticker": ticker,
        "window": {"start": start, "end": end},
        "calibrated_c": float(c),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--monthly-rebalance", action="store_true", default=True)
    parser.add_argument("--daily-rebalance", dest="monthly_rebalance", action="store_false")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end, args.initial_value, monthly_rebalance=args.monthly_rebalance)
    print(f"{payload['ticker']} {payload['window']['start']}..{payload['window']['end']} (c={payload['calibrated_c']:.4f})")
    for name, res in payload["results"].items():
        print(
            f"  {name}: sharpe={res['sharpe_ratio']:.4f} mdd={res['max_drawdown']:.4f} "
            f"final={res['final_value']:.0f} mean_w={res['mean_weight']:.3f} cost={res['transaction_cost']:.0f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
