#!/usr/bin/env python3
"""Multi-candidate Bonferroni-corrected significance test: does any cap20-lineage
independent PPO variant tested this week (2026-09-08/09) beat production
(golden1_0531-driven a2118) on the one genuinely fair (both-sides-OOS) window,
active_2025_2026?

Uses group_a_plus.governance.significance's jobson_korkie_memmel_test (paired
Sharpe-difference test on daily returns) per candidate, then
bonferroni_grid_significance across the full grid of 9 distinct configs
actually tested this week against production on this window (not narrowed to
survivors -- the whole set that was tried).

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _switch_returns
from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _trade_cost
from group_a_plus.runners.a2111 import _build_switch_rule
from group_a_plus.runners.a2118 import run_a2118
from backtest_group_a_plus_policy_signal import TICKERS as ALL_TICKERS, _normalize
from group_a_plus.governance.significance import jobson_korkie_memmel_test, bonferroni_grid_significance

RULE = _build_switch_rule()
TICKERS = list(ALL_TICKERS)
DEFENSIVE = dict(DEFENSIVE_BASKETS["bond0_cash60"])
INITIAL_VALUE = 1_000_000.0
COMMISSION = 0.001425
SLIPPAGE = 0.0005
SELL_TAX = 0.001
PRODUCTION_KW = dict(risk_score_lookback_days=5, momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.08)

START, END = "2025-01-02", "2026-09-04"

# The full grid of 9 distinct candidate configs tested this week against
# production on this window (2026-09-08/09) -- not narrowed to survivors.
CANDIDATES = {
    "seed42_cap30": ["results/group_a_backtest_20240101_20260904_20260908_180917.json"],
    "seed42_cap30_100k": ["results/group_a_backtest_20240101_20260904_20260908_175510.json"],
    "seed7_cap30": ["results/group_a_backtest_20240101_20260904_20260908_222057.json"],
    "seed123_cap30": ["results/group_a_backtest_20240101_20260904_20260908_222118.json"],
    "tripletv4_cap30": ["results/group_a_backtest_20240101_20260904_20260908_223126.json"],
    "seed42_cap20": ["results/group_a_backtest_20240101_20260904_20260908_223625.json"],
    "seed7_cap20": ["results/group_a_backtest_20240101_20260904_20260908_224431.json"],
    "seed123_cap20": ["results/group_a_backtest_20240101_20260904_20260908_224921.json"],
    "cap20_institutional_2020window": ["results/group_a_backtest_20240601_20260904_20260908_234013.json"],
    "cap20_auxvol": ["results/group_a_backtest_auxvol_live_2024_2026_20260909.json"],
}


def load_model_daily_weights(paths: list[str]) -> dict[str, dict[str, float]]:
    weights_by_date: dict[str, dict[str, float]] = {}
    for rel in paths:
        payload = json.loads((PROJECT_ROOT / rel).read_text(encoding="utf-8"))
        history = payload["group_a"]["result"]["daily_target_weight_history"]
        for row in history:
            weights_by_date[row["execution_date"]] = dict(row["final_target_weights"])
    return weights_by_date


def simulate_new_model(prices, regimes, model_weights) -> pd.Series:
    shares = {t: 0.0 for t in TICKERS}
    cash = INITIAL_VALUE
    values = []
    dates = []
    for dt, price_row in prices.iterrows():
        gross = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(regimes.loc[dt])
        date_str = str(dt.date())
        if regime == "golden1":
            model_w = model_weights.get(date_str)
            if model_w is not None:
                weights = {t: float(model_w.get(t, 0.0)) for t in TICKERS}
            else:
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
        values.append(net_value)
        dates.append(dt)
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float)


def main() -> None:
    load_start = (pd.Timestamp(START) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    prices = _load_prices(DB_PATH, TICKERS, load_start, END)
    chip_features = _load_chip_features(DB_PATH, prices.index, load_start, END)
    events, frame = _switch_returns(prices, chip_features, RULE, **PRODUCTION_KW)
    regimes = frame["regime"].astype(str)

    report, prod_frame = run_a2118(START, END, INITIAL_VALUE, DB_PATH)
    prod_curve = prod_frame.loc[START:END, "portfolio_value"].astype(float)
    prod_returns = prod_curve.pct_change().dropna()

    jkm_results = {}
    summary_rows = []
    for label, paths in CANDIDATES.items():
        model_weights = load_model_daily_weights(paths)
        curve = simulate_new_model(prices, regimes, model_weights)
        curve_w = curve.loc[START:END]
        cand_returns = curve_w.pct_change().dropna()

        jkm = jobson_korkie_memmel_test(cand_returns, prod_returns)
        jkm_results[label] = jkm
        summary_rows.append(
            {
                "label": label,
                "n": jkm.get("n"),
                "status": jkm.get("status"),
                "sharpe_a": jkm.get("sharpe_a"),
                "sharpe_b": jkm.get("sharpe_b"),
                "sharpe_diff": jkm.get("sharpe_diff"),
                "p_value": jkm.get("p_value"),
            }
        )
        print(f"{label:35s} n={jkm.get('n')}  sharpe_cand={jkm.get('sharpe_a')}  sharpe_prod={jkm.get('sharpe_b')}  "
              f"diff={jkm.get('sharpe_diff')}  p={jkm.get('p_value')}  status={jkm.get('status')}")

    bonf = bonferroni_grid_significance(jkm_results, candidate_grid_size=len(CANDIDATES), alpha=0.05)
    print("\n=== Bonferroni-corrected result (grid size = %d, alpha = 0.05) ===" % len(CANDIDATES))
    print(f"corrected_alpha = {bonf['corrected_alpha']:.6f}")
    print(f"any_significant = {bonf['any_significant']}")
    print(f"any_significant_improvement = {bonf['any_significant_improvement']}")
    for cid, c in bonf["candidates"].items():
        print(f"  {cid:35s} {c}")

    out = {
        "window": {"start": START, "end": END},
        "summary_rows": summary_rows,
        "jkm_results": jkm_results,
        "bonferroni": bonf,
    }
    out_path = PROJECT_ROOT / "results" / "significance_check_cap20_vs_production_20260909.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
