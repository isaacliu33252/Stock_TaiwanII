#!/usr/bin/env python3
"""Day-by-day diagnostic: where does the remaining ~1.9pp MDD gap between
cap20_seed7 (independent PPO, 00631L cap 20%) and production golden1_0531
come from, on the one genuinely fair window (active_2025_2026)?

Not another parameter sweep -- follows the memory file's own "How to apply"
recommendation to actually inspect regime-switch timing day by day instead
of guessing another hyperparameter.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _switch_returns
from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _trade_cost
from group_a_plus.runners.a2111 import _build_switch_rule
from group_a_plus.runners.a2118 import run_a2118
from backtest_group_a_plus_policy_signal import TICKERS as ALL_TICKERS, _normalize

RULE = _build_switch_rule()
TICKERS = list(ALL_TICKERS)
DEFENSIVE = dict(DEFENSIVE_BASKETS["bond0_cash60"])
INITIAL_VALUE = 1_000_000.0
COMMISSION = 0.001425
SLIPPAGE = 0.0005
SELL_TAX = 0.001
PRODUCTION_KW = dict(risk_score_lookback_days=5, momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.08)

START, END = "2025-01-02", "2026-09-04"

MODEL_RESULT_FILES = [
    "results/group_a_backtest_20200102_20201231_20260908_224950.json",
    "results/group_a_backtest_20220103_20221230_20260908_224959.json",
    "results/group_a_backtest_20240101_20260904_20260908_224431.json",
]


def load_model_daily_weights(paths: list[str]) -> dict[str, dict[str, float]]:
    weights_by_date: dict[str, dict[str, float]] = {}
    for rel in paths:
        payload = json.loads((PROJECT_ROOT / rel).read_text(encoding="utf-8"))
        history = payload["group_a"]["result"]["daily_target_weight_history"]
        for row in history:
            weights_by_date[row["execution_date"]] = dict(row["final_target_weights"])
    return weights_by_date


def simulate_new_model(prices, regimes, model_weights):
    shares = {t: 0.0 for t in TICKERS}
    cash = INITIAL_VALUE
    rows = []
    for dt, price_row in prices.iterrows():
        gross = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(regimes.loc[dt])
        date_str = str(dt.date())
        model_w = model_weights.get(date_str) if regime == "golden1" else None
        if regime == "golden1" and model_w is not None:
            weights = {t: float(model_w.get(t, 0.0)) for t in TICKERS}
        elif regime == "golden1":
            weights = {t: shares[t] * float(price_row[t]) / gross if gross > 0 else 0.0 for t in TICKERS}
        else:
            weights = {t: w for t, w in _normalize(DEFENSIVE).items() if t in TICKERS}
        target_values = {t: gross * weights.get(t, 0.0) for t in TICKERS}
        current_values = {t: shares[t] * float(price_row[t]) for t in TICKERS}
        net_value = gross
        for _ in range(3):
            cost, _ = _trade_cost(current_values, target_values, COMMISSION, SLIPPAGE, SELL_TAX)
            net_value = max(gross - cost, 0.0)
            scale = net_value / gross if gross > 0 else 0.0
            target_values = {t: v * scale for t, v in target_values.items()}
        shares = {t: target_values[t] / max(float(price_row[t]), 1e-12) for t in TICKERS}
        cash = max(net_value - sum(target_values.values()), 0.0)
        rows.append({
            "date": dt, "value": net_value, "regime": regime,
            "00631L_weight": weights.get("00631L.TW", 0.0),
            "0050_weight": weights.get("0050.TW", 0.0),
        })
    return pd.DataFrame(rows).set_index("date")


def main() -> None:
    model_weights = load_model_daily_weights(MODEL_RESULT_FILES)
    load_start = (pd.Timestamp(START) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    prices = _load_prices(DB_PATH, TICKERS, load_start, END)
    chip_features = _load_chip_features(DB_PATH, prices.index, load_start, END)
    events, frame = _switch_returns(prices, chip_features, RULE, **PRODUCTION_KW)
    regimes = frame["regime"].astype(str)

    model_df = simulate_new_model(prices, regimes, model_weights)
    model_df = model_df.loc[START:END]
    model_df["value_norm"] = model_df["value"] / model_df["value"].iloc[0] * INITIAL_VALUE
    model_df["running_max"] = model_df["value_norm"].cummax()
    model_df["drawdown"] = model_df["value_norm"] / model_df["running_max"] - 1.0

    report, prod_frame = run_a2118(START, END, INITIAL_VALUE, DB_PATH)
    prod = prod_frame.loc[START:END, ["portfolio_value"]].copy()
    prod["running_max"] = prod["portfolio_value"].cummax()
    prod["drawdown"] = prod["portfolio_value"] / prod["running_max"] - 1.0

    combined = model_df[["value_norm", "drawdown", "regime", "00631L_weight", "0050_weight"]].join(
        prod[["portfolio_value", "drawdown"]].rename(columns={"portfolio_value": "prod_value", "drawdown": "prod_drawdown"}),
        how="inner",
    )
    combined["dd_gap"] = combined["drawdown"] - combined["prod_drawdown"]  # more negative = model worse

    print(f"cap20_seed7 MDD: {combined['drawdown'].min()*100:.2f}%  on {combined['drawdown'].idxmin().date()}")
    print(f"production   MDD: {combined['prod_drawdown'].min()*100:.2f}%  on {combined['prod_drawdown'].idxmin().date()}")
    print()
    worst_gap_date = combined["dd_gap"].idxmin()
    print(f"Worst single-day dd_gap (model drawdown minus production drawdown): "
          f"{combined['dd_gap'].min()*100:.2f}pp on {worst_gap_date.date()}")
    print()

    print("=== 20 trading days around the model's worst drawdown gap ===")
    window = combined.loc[worst_gap_date - pd.Timedelta(days=25): worst_gap_date + pd.Timedelta(days=10)]
    with pd.option_context("display.max_rows", 100, "display.width", 160):
        print(window[["regime", "00631L_weight", "0050_weight", "drawdown", "prod_drawdown", "dd_gap"]].round(4))
    print()

    print("=== Regime day-count comparison (does the model spend more days in golden1 during the drawdown window?) ===")
    dd_window = combined.loc[worst_gap_date - pd.Timedelta(days=40): worst_gap_date]
    print(dd_window["regime"].value_counts())
    print()
    print("=== Days where model was in golden1 with high 00631L weight while its drawdown was already worse than production's ===")
    flagged = combined[(combined["regime"] == "golden1") & (combined["00631L_weight"] > 0.10) & (combined["dd_gap"] < -0.01)]
    print(f"{len(flagged)} such days")
    if len(flagged):
        print(flagged[["00631L_weight", "0050_weight", "drawdown", "prod_drawdown", "dd_gap"]].round(4).to_string())


if __name__ == "__main__":
    main()
