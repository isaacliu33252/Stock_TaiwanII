#!/usr/bin/env python3
"""Follow-up to the TXO put overlay deeper-OTM revalidation
(build_txo_put_overlay_deeper_otm_revalidation_2607_00883.py), which found
that 85%/80%-of-spot strikes restore real crisis-specific protection
(especially the 2025 tariff shock) but leave full-window Sharpe at
noise-level versus switch_alone, because calm-year carry drag roughly
cancels the crisis-window gain in the full-sample average. That handoff's
explicitly flagged next step: grid search over strike-depth x
premium-budget combinations to look for a combination where full-window
Sharpe genuinely improves, not just crisis-window MDD.

Grids: OTM strike depth in {90%, 87.5%, 85%, 82.5%, 80%, 77.5%, 75%} of
spot (10% to 25% OTM); annual premium budget in {1.0%, 1.5%, 2.0%, 2.5%,
3.0%} of NAV. All under the same realistic integer-contract sizing
established in the affordable-subset work (real NAV, NT$50/point TXO
multiplier, round-trip transaction cost only on rolls actually traded).

Research-only. Reuses build_price_df_with_roll_dt / per_roll_contract_
counts / build_realistic_hybrid_ret from build_txo_put_overlay_affordable_
subset_2607_00883.py unmodified. No production code touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_txo_put_overlay_affordable_subset_2607_00883 import (  # noqa: E402
    DB_PATH, START, END, SWITCH_CURVE, SWITCH_COL,
    build_price_df_with_roll_dt, per_roll_contract_counts, build_realistic_hybrid_ret, perf_stats,
)
from scripts.evaluate.evaluate_2607_00883_txo_put_overlay_shadow import (  # noqa: E402
    build_txo_put_return_per_premium,
)

DEPTHS = (0.90, 0.875, 0.85, 0.825, 0.80, 0.775, 0.75)
BUDGETS = (0.010, 0.015, 0.020, 0.025, 0.030)


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    curve = pd.read_csv(SWITCH_CURVE)
    curve["dt"] = pd.to_datetime(curve["dt"])
    curve = curve.set_index("dt").sort_index()
    switch_ret = curve[SWITCH_COL].pct_change()
    switch_perf = perf_stats(switch_ret.dropna().values)
    print(f"switch_alone: sharpe={switch_perf['sharpe']:.3f}  mdd={switch_perf['mdd']*100:.2f}%\n")

    _, roundtrip_cost_by_window, _ = build_txo_put_return_per_premium(con, START, END)

    price_df_cache = {}
    rows = []
    for depth in DEPTHS:
        price_df_cache[depth] = build_price_df_with_roll_dt(con, START, END, otm_frac=depth)

    for depth in DEPTHS:
        price_df = price_df_cache[depth]
        for budget in BUDGETS:
            roll_info = per_roll_contract_counts(price_df, budget)
            _, realistic_costed = build_realistic_hybrid_ret(price_df, roll_info, roundtrip_cost_by_window)
            df = pd.concat([switch_ret.rename("switch_ret"), realistic_costed.rename("put_ret")],
                            axis=1, sort=True).dropna()
            df["hybrid_ret"] = df["switch_ret"] + df["put_ret"]
            hybrid_perf = perf_stats(df["hybrid_ret"].values)
            n_afford = int(roll_info["affordable"].sum())
            n_total = len(roll_info)
            rows.append({
                "depth_pct": depth * 100, "budget_pct": budget * 100,
                "affordable_pct": n_afford / n_total * 100,
                "sharpe": hybrid_perf["sharpe"], "mdd": hybrid_perf["mdd"],
                "d_sharpe": hybrid_perf["sharpe"] - switch_perf["sharpe"],
                "d_mdd_pp": (hybrid_perf["mdd"] - switch_perf["mdd"]) * 100,
            })

    grid = pd.DataFrame(rows)
    print("=== Full grid: d_sharpe (hybrid - switch_alone) ===")
    pivot_sharpe = grid.pivot(index="depth_pct", columns="budget_pct", values="d_sharpe")
    print(pivot_sharpe.round(4).to_string())
    print("\n=== Full grid: d_mdd_pp (positive = improvement) ===")
    pivot_mdd = grid.pivot(index="depth_pct", columns="budget_pct", values="d_mdd_pp")
    print(pivot_mdd.round(3).to_string())
    print("\n=== Full grid: affordable roll % ===")
    pivot_afford = grid.pivot(index="depth_pct", columns="budget_pct", values="affordable_pct")
    print(pivot_afford.round(1).to_string())

    best = grid.sort_values("d_sharpe", ascending=False).head(5)
    print("\n=== Top 5 combos by d_sharpe ===")
    print(best.to_string(index=False))

    n_positive_both = int(((grid["d_sharpe"] > 0.02) & (grid["d_mdd_pp"] > 0)).sum())
    print(f"\ncombos with d_sharpe > 0.02 AND d_mdd_pp > 0: {n_positive_both}/{len(grid)}")

    out_path = PROJECT_ROOT / "results" / "txo_put_overlay_depth_budget_grid_2607_00883.csv"
    grid.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
