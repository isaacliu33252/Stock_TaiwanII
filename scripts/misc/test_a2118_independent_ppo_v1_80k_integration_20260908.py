#!/usr/bin/env python3
"""Integrate the new, golden1_0531-independent PPO model
(a2118_independent_ppo_v1_80k, trained 2017-2019, pva_drift_threshold=0.06)
into an a2118-style switch-rule + defensive-basket replay, and compare
against a real run_a2118() baseline (which uses golden1_0531) across the
same 4 windows used throughout today's session.

Unlike the earlier direction-6 "a2118-faithful" script, this does NOT hit
the H3 static-snapshot limitation for the golden1 side: the new model's
own backtest already produced a genuine daily target-weight trajectory
(results/group_a_backtest_*.json -> group_a.result.daily_target_weight_history),
one independent backtest per window (2020, 2022, 2024-2026), so golden1-regime
days here use the model's real per-day weight, not a frozen snapshot. The
switch rule itself (golden1 vs group_a_plus_defensive) still comes from
a2111._build_switch_rule() against real price/chip data, same as every
other script in this round.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
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

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "2026-09-04"),
    ("active_2025_2026", "2025-01-02", "2026-09-04"),
]

MODEL_RESULT_FILES = [
    "results/group_a_backtest_20200102_20201231_20260908_182423.json",
    "results/group_a_backtest_20220103_20221230_20260908_182450.json",
    "results/group_a_backtest_20240101_20260904_20260908_180917.json",
]

if len(sys.argv) > 1 and sys.argv[1] == "--result-files":
    MODEL_RESULT_FILES = sys.argv[2:5]
    MODEL_LABEL = sys.argv[5] if len(sys.argv) > 5 else "new_model"
else:
    MODEL_LABEL = "new_model_80k"


def load_model_daily_weights(paths: list[str]) -> dict[str, dict[str, float]]:
    weights_by_date: dict[str, dict[str, float]] = {}
    for rel in paths:
        payload = json.loads((PROJECT_ROOT / rel).read_text(encoding="utf-8"))
        history = payload["group_a"]["result"]["daily_target_weight_history"]
        for row in history:
            weights_by_date[row["execution_date"]] = dict(row["final_target_weights"])
    return weights_by_date


def simulate_new_model(
    prices: pd.DataFrame,
    regimes: pd.Series,
    model_weights: dict[str, dict[str, float]],
) -> tuple[pd.Series, dict[str, int]]:
    shares = {t: 0.0 for t in TICKERS}
    cash = INITIAL_VALUE
    values = []
    coverage = {"golden1_days": 0, "golden1_days_with_model_weight": 0, "defensive_days": 0}
    for dt, price_row in prices.iterrows():
        gross = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(regimes.loc[dt])
        date_str = str(dt.date())
        if regime == "golden1":
            coverage["golden1_days"] += 1
            model_w = model_weights.get(date_str)
            if model_w is not None:
                coverage["golden1_days_with_model_weight"] += 1
                raw = {t: float(model_w.get(t, 0.0)) for t in TICKERS}
                weights = raw  # already sums to <=1 across TICKERS; remainder is implicit cash
            else:
                weights = {t: shares[t] * float(price_row[t]) / gross if gross > 0 else 0.0 for t in TICKERS}
        else:
            coverage["defensive_days"] += 1
            weights = {t: w for t, w in _normalize(DEFENSIVE).items() if t in TICKERS}
        target_values = {t: gross * weights.get(t, 0.0) for t in TICKERS}
        current_values = {t: shares[t] * float(price_row[t]) for t in TICKERS}
        net_value = gross
        cost = 0.0
        for _ in range(3):
            cost, _turnover = _trade_cost(current_values, target_values, COMMISSION, SLIPPAGE, SELL_TAX)
            net_value = max(gross - cost, 0.0)
            scale = net_value / gross if gross > 0 else 0.0
            target_values = {t: v * scale for t, v in target_values.items()}
        shares = {t: target_values[t] / max(float(price_row[t]), 1e-12) for t in TICKERS}
        cash = max(net_value - sum(target_values.values()), 0.0)
        values.append(net_value + cash - cash)  # net_value already includes cash portion via scale; keep explicit
        values[-1] = net_value
    return pd.Series(values, index=prices.index, dtype=float), coverage


def main() -> None:
    model_weights = load_model_daily_weights(MODEL_RESULT_FILES)
    results = {}
    for label, start, end in WINDOWS:
        load_start = (pd.Timestamp(start) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
        prices = _load_prices(DB_PATH, TICKERS, load_start, end)
        chip_features = _load_chip_features(DB_PATH, prices.index, load_start, end)
        events, frame = _switch_returns(prices, chip_features, RULE, **PRODUCTION_KW)
        regimes = frame["regime"].astype(str)

        curve, coverage = simulate_new_model(prices, regimes, model_weights)
        curve_w = curve.loc[start:end]
        new_model_metrics = _metrics(curve_w / curve_w.iloc[0] * INITIAL_VALUE, INITIAL_VALUE)

        report, _ = run_a2118(start, end, INITIAL_VALUE, DB_PATH)
        prod_metrics = report["metrics"]

        results[label] = {
            MODEL_LABEL: new_model_metrics,
            "production_golden1_0531": {
                "final_value": prod_metrics["final_value"],
                "sharpe_ratio": prod_metrics["sharpe_ratio"],
                "max_drawdown": prod_metrics["max_drawdown"],
            },
            "coverage": coverage,
        }
        print(f"=== {label} ({start}..{end}) ===")
        print(
            f"  {MODEL_LABEL}:            final={new_model_metrics['final_value']:>12,.0f}  "
            f"sharpe={new_model_metrics['sharpe_ratio']:7.4f}  mdd={new_model_metrics['max_drawdown']*100:7.2f}%"
        )
        print(
            f"  production_golden1_0531:  final={prod_metrics['final_value']:>12,.0f}  "
            f"sharpe={prod_metrics['sharpe_ratio']:7.4f}  mdd={prod_metrics['max_drawdown']*100:7.2f}%"
        )
        print(f"  coverage: {coverage}")
        print()

    out_path = PROJECT_ROOT / "results" / f"a2118_independent_ppo_v1_80k_integration_{MODEL_LABEL}_20260908.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
