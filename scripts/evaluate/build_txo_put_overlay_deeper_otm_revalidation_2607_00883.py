#!/usr/bin/env python3
"""Follow-up to 2607.00883's put-overlay affordability line of work
(build_txo_put_overlay_affordable_subset_2607_00883.py). That script showed
the validated 10%-OTM design's granularity problem is real, and that moving
to 15%-OTM (85% of spot) roughly doubles the affordable-roll fraction
(35.1% -> 62.3%). It explicitly flagged that only AFFORDABILITY was checked
there -- the deeper strike's own hedge-quality / risk-return properties
were never re-validated. This script does that re-validation, using the
REALISTIC integer-contract sizing (not the original fractional-budget
convention) since that is what the affordable-subset work established as
the honest deployment-relevant construction.

Tests, at 85%-of-spot (15% OTM) and 80%-of-spot (20% OTM) strikes, against
the original validated 90%-of-spot (10% OTM) design, all under identical
real-NAV integer-contract sizing:
  1. full-window Sharpe/vol/MDD vs switch_alone
  2. per-year (7-year) independent breakdown
  3. episode-level (COVID 2020, bear 2022, tariff shock 2025) cumulative return / MDD
  4. round-trip transaction-cost impact (already embedded in the realistic-costed series)
  5. basis-risk note: TXO trades the TAIEX index (^TWII), not 0050/00631L
     directly; this basis-risk source is a property of using TXO at all,
     not of strike depth, so it is not re-derived here -- see
     GROUP_A_PLUS_20260819_2607_00883_TXO_PUT_OVERLAY_HANDOFF.md Section on
     basis-risk quantification for the original figure.

Research-only. Reuses build_price_df_with_roll_dt / per_roll_contract_counts
/ build_realistic_hybrid_ret from build_txo_put_overlay_affordable_subset_
2607_00883.py unmodified. No production code touched.
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
    ANNUAL_PREMIUM_BUDGET,
    DB_PATH,
    REAL_NAV,
    START,
    END,
    SWITCH_CURVE,
    SWITCH_COL,
    build_price_df_with_roll_dt,
    per_roll_contract_counts,
    build_realistic_hybrid_ret,
    perf_stats,
)
from scripts.evaluate.evaluate_2607_00883_txo_put_overlay_shadow import (  # noqa: E402
    ROLL_EVERY,
    build_txo_put_return_per_premium,
)

STRIKE_DEPTHS = {"90pct_10otm_validated": 0.90, "85pct_15otm": 0.85, "80pct_20otm": 0.80}


def run_one_depth(con: duckdb.DuckDBPyConnection, otm_frac: float, switch_ret: pd.Series) -> dict:
    price_df = build_price_df_with_roll_dt(con, START, END, otm_frac=otm_frac)
    roll_info = per_roll_contract_counts(price_df, ANNUAL_PREMIUM_BUDGET)

    _, roundtrip_cost_by_window, _ = build_txo_put_return_per_premium(con, START, END)
    _, realistic_costed = build_realistic_hybrid_ret(price_df, roll_info, roundtrip_cost_by_window)

    df = pd.concat([switch_ret.rename("switch_ret"), realistic_costed.rename("put_ret")], axis=1, sort=True).dropna()
    df["hybrid_ret"] = df["switch_ret"] + df["put_ret"]

    n_total = len(roll_info)
    n_afford = int(roll_info["affordable"].sum())

    full = {
        "switch_alone": perf_stats(df["switch_ret"].values),
        "hybrid_realistic": perf_stats(df["hybrid_ret"].values),
    }

    roll_info_yr = roll_info.copy()
    roll_info_yr["year"] = roll_info_yr.index.year
    df_yr = df.copy()
    df_yr["year"] = df_yr.index.year
    per_year = {}
    for yr, grp in df_yr.groupby("year"):
        p_switch = perf_stats(grp["switch_ret"].values)
        p_hybrid = perf_stats(grp["hybrid_ret"].values)
        n_afford_yr = int(roll_info_yr[roll_info_yr["year"] == yr]["affordable"].sum())
        n_total_yr = int((roll_info_yr["year"] == yr).sum())
        per_year[int(yr)] = {
            "switch_sharpe": p_switch["sharpe"], "hybrid_sharpe": p_hybrid["sharpe"],
            "switch_mdd": p_switch["mdd"], "hybrid_mdd": p_hybrid["mdd"],
            "affordable_rolls": f"{n_afford_yr}/{n_total_yr}",
        }

    episodes = {
        "covid_crash_2020": ("2020-01-20", "2020-03-23"),
        "bear_2022_full_year": ("2022-01-01", "2022-12-31"),
        "tariff_shock_2025_04": ("2025-04-01", "2025-04-15"),
    }
    episode_results = {}
    for name, (s, e) in episodes.items():
        sub = df.loc[s:e]
        if sub.empty:
            continue
        cs = (1 + sub["switch_ret"]).cumprod()
        ch = (1 + sub["hybrid_ret"]).cumprod()
        episode_results[name] = {
            "switch_cum": float(cs.iloc[-1] - 1), "hybrid_cum": float(ch.iloc[-1] - 1),
            "switch_mdd": float((cs / cs.cummax() - 1).min()), "hybrid_mdd": float((ch / ch.cummax() - 1).min()),
        }

    return {
        "otm_frac": otm_frac, "n_total_rolls": n_total, "n_affordable_rolls": n_afford,
        "affordable_pct": n_afford / n_total * 100,
        "full_window": full, "per_year": per_year, "episodes": episode_results,
    }


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    curve = pd.read_csv(SWITCH_CURVE)
    curve["dt"] = pd.to_datetime(curve["dt"])
    curve = curve.set_index("dt").sort_index()
    switch_ret = curve[SWITCH_COL].pct_change()

    results = {}
    for label, otm_frac in STRIKE_DEPTHS.items():
        print(f"\n{'='*70}\n{label} (otm_frac={otm_frac})\n{'='*70}")
        r = run_one_depth(con, otm_frac, switch_ret)
        results[label] = r

        print(f"affordable rolls: {r['n_affordable_rolls']}/{r['n_total_rolls']} ({r['affordable_pct']:.1f}%)")
        fw = r["full_window"]
        for name in ["switch_alone", "hybrid_realistic"]:
            p = fw[name]
            print(f"  {name:20s} ann_ret={p['ann_ret']*100:7.2f}%  ann_vol={p['ann_vol']*100:6.2f}%  "
                  f"sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%")

        print("  --- per-year (hybrid vs switch sharpe/mdd, affordable-roll count) ---")
        for yr, y in sorted(r["per_year"].items()):
            print(f"  {yr}: switch_sharpe={y['switch_sharpe']:6.3f} hybrid_sharpe={y['hybrid_sharpe']:6.3f}  "
                  f"switch_mdd={y['switch_mdd']*100:7.2f}% hybrid_mdd={y['hybrid_mdd']*100:7.2f}%  "
                  f"affordable={y['affordable_rolls']}")

        print("  --- episodes (cum return, switch vs hybrid) ---")
        for name, e in r["episodes"].items():
            print(f"  {name:24s} switch={e['switch_cum']*100:+7.2f}%  hybrid={e['hybrid_cum']*100:+7.2f}%  "
                  f"switch_mdd={e['switch_mdd']*100:7.2f}%  hybrid_mdd={e['hybrid_mdd']*100:7.2f}%")

    print(f"\n{'='*70}\nSummary: full-window Sharpe/MDD improvement (hybrid - switch_alone) by strike depth\n{'='*70}")
    for label, r in results.items():
        fw = r["full_window"]
        d_sharpe = fw["hybrid_realistic"]["sharpe"] - fw["switch_alone"]["sharpe"]
        d_mdd = fw["hybrid_realistic"]["mdd"] - fw["switch_alone"]["mdd"]
        print(f"  {label:24s} affordable={r['affordable_pct']:5.1f}%  d_sharpe={d_sharpe:+.4f}  "
              f"d_mdd_pp={d_mdd*100:+.3f}pp")


if __name__ == "__main__":
    main()
