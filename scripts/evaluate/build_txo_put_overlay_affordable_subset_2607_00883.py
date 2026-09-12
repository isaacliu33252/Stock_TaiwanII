#!/usr/bin/env python3
"""Follow-up to arXiv:2607.00883's TXO put overlay (see
GROUP_A_PLUS_20260819_2607_00883_TXO_PUT_OVERLAY_HANDOFF.md Section 12).

The original 5-layer validation used a *fractional* premium-budget
convention (ret_per_premium * q) that implicitly assumes the overlay can
buy any fractional slice of a TXO contract. Rechecking all 77 historical
rolls (2020-01-02 to 2026-08-18) against Group A+'s real NAV ($1,478,056)
and the real NT$50/point TXO multiplier found that 50/77 (65%) round to 0
theoretical contracts -- the fractional convention silently assumes
coverage that was never actually purchasable.

This script asks the honest question: if you can only hold the overlay on
the rolls you can actually afford >=1 contract for (skip the hedge, hold
switch-only otherwise), does the overlay still help, given Group A+'s real
current NAV? It also checks whether a cheaper (further-OTM) strike raises
the affordable-roll fraction enough to matter.

Research-only diagnostic. Reuses build_txo_put_return_per_premium() from
evaluate_2607_00883_txo_put_overlay_shadow.py unmodified. No production
code touched.
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

from scripts.evaluate.evaluate_2607_00883_txo_put_overlay_shadow import (  # noqa: E402
    ANNUAL_PREMIUM_BUDGET,
    DB_PATH,
    ROLL_EVERY,
    build_txo_put_return_per_premium,
    perf_stats,
    scale_to_premium_budget,
)

REAL_NAV = 1_478_056.0
TXO_MULTIPLIER = 50.0  # NT$ per index point per contract
SWITCH_CURVE = PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_curve.csv"
SWITCH_COL = "switch_risk_ma80_dd11_total6_hold5_eg015_xg015"
START, END = pd.Timestamp("2020-01-02"), pd.Timestamp("2026-08-18")


def build_price_df_with_roll_dt(
    con: duckdb.DuckDBPyConnection, start: pd.Timestamp, end: pd.Timestamp, otm_frac: float = 0.90,
) -> pd.DataFrame:
    """Local re-derivation of build_txo_put_return_per_premium's internal
    price_df, but keeping the 'price'/'bid'/'ask' columns (the upstream
    function only returns the roll_dt column) and parameterizing the OTM
    fraction so the same code path can test a cheaper (further-OTM) strike."""
    twii = con.execute(
        "select dt, close from external_market_ohlcv where ticker='^TWII' order by dt"
    ).fetchdf()
    twii["dt"] = pd.to_datetime(twii["dt"])
    twii = twii.set_index("dt").sort_index()
    trading_dates = twii.loc[start:end].index

    opt = con.execute(
        """
        select dt, contract_month, strike_price, close, settlement_price, best_bid, best_ask
        from taifex_options_daily
        where call_put='賣權' and trading_session='一般'
        order by dt
        """
    ).fetchdf()
    opt["dt"] = pd.to_datetime(opt["dt"])

    roll_idx = list(range(0, len(trading_dates), ROLL_EVERY))
    roll_dates = [trading_dates[i] for i in roll_idx]

    records = []
    for k, roll_dt in enumerate(roll_dates):
        next_roll_dt = roll_dates[k + 1] if k + 1 < len(roll_dates) else (trading_dates[-1] + pd.Timedelta(days=1))
        spot = twii.loc[roll_dt, "close"]
        target_strike = round(spot * otm_frac / 100) * 100

        next_month = (roll_dt.month % 12) + 1
        next_year = roll_dt.year + (1 if roll_dt.month == 12 else 0)
        contract_month = f"{next_year:04d}{next_month:02d}"

        window = opt[(opt["dt"] >= roll_dt) & (opt["dt"] < next_roll_dt) & (opt["contract_month"] == contract_month)]
        if window.empty:
            continue
        available_strikes = window["strike_price"].unique()
        nearest_strike = available_strikes[np.argmin(np.abs(available_strikes - target_strike))]
        leg = window[window["strike_price"] == nearest_strike].sort_values("dt").drop_duplicates(subset="dt", keep="last")
        for _, row in leg.iterrows():
            price = row["settlement_price"] if row["settlement_price"] > 0 else row["close"]
            bid = row["best_bid"] if row["best_bid"] > 0 else price
            ask = row["best_ask"] if row["best_ask"] > 0 else price
            records.append((row["dt"], price, bid, ask, roll_dt))

    price_df = pd.DataFrame(records, columns=["dt", "price", "bid", "ask", "roll_dt"]).sort_values("dt")
    price_df = price_df.drop_duplicates(subset="dt", keep="last").set_index("dt")
    price_df = price_df.reindex(trading_dates)
    price_df["price"] = price_df["price"].replace(0.0, np.nan)
    price_df = price_df.ffill().dropna(subset=["price"])
    return price_df


def per_roll_contract_counts(price_df: pd.DataFrame, annual_premium_budget: float) -> pd.DataFrame:
    n_rolls_per_year = 252 / ROLL_EVERY
    per_roll_budget_dollars = REAL_NAV * annual_premium_budget / n_rolls_per_year
    p0 = price_df.groupby("roll_dt")["price"].first().rename("P0")
    dollars_per_contract = p0 * TXO_MULTIPLIER
    theoretical_contracts_exact = per_roll_budget_dollars / dollars_per_contract
    contracts = np.floor(theoretical_contracts_exact).astype(int)
    return pd.DataFrame({
        "P0": p0,
        "dollars_per_contract": dollars_per_contract,
        "theoretical_contracts_exact": theoretical_contracts_exact,
        "contracts": contracts,
        "affordable": contracts >= 1,
    })


def build_realistic_hybrid_ret(
    price_df: pd.DataFrame, roll_info: pd.DataFrame, roundtrip_cost_by_window: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Integer-contract dollar P&L / NAV per day; 0 on unaffordable rolls.
    Returns (gross, cost-adjusted) daily return series."""
    df = price_df.join(roll_info[["contracts", "affordable"]], on="roll_dt")
    df["dprice"] = df.groupby("roll_dt")["price"].diff()
    df["ret_gross"] = df["contracts"] * TXO_MULTIPLIER * df["dprice"] / REAL_NAV
    df["ret_gross"] = df["ret_gross"].fillna(0.0)

    cost_by_roll = roundtrip_cost_by_window.reindex(roll_info.index).fillna(0.0)
    p0 = roll_info["P0"]
    cost_dollars_per_contract = cost_by_roll * p0 * TXO_MULTIPLIER
    total_cost_dollars = cost_dollars_per_contract * roll_info["contracts"]
    last_day_per_roll = df.reset_index().groupby("roll_dt")["dt"].max()

    ret_costed = df["ret_gross"].copy()
    for roll_dt, cost in total_cost_dollars.items():
        last_dt = last_day_per_roll.get(roll_dt)
        if last_dt is not None and last_dt in ret_costed.index and cost != 0:
            ret_costed.loc[last_dt] -= cost / REAL_NAV

    return df["ret_gross"], ret_costed


def summarize(name: str, r: pd.Series) -> dict:
    stats = perf_stats(r.values)
    return {"name": name, **stats}


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    ret_per_premium, roundtrip_cost_by_window, _ = build_txo_put_return_per_premium(con, START, END)
    price_df = build_price_df_with_roll_dt(con, START, END, otm_frac=0.90)
    roll_info = per_roll_contract_counts(price_df, ANNUAL_PREMIUM_BUDGET)

    n_total = len(roll_info)
    n_affordable = int(roll_info["affordable"].sum())
    print(f"\n=== Roll affordability (real NAV ${REAL_NAV:,.0f}, {ANNUAL_PREMIUM_BUDGET*100:.1f}%/yr budget) ===")
    print(f"total rolls={n_total}  affordable(>=1 contract)={n_affordable} "
          f"({n_affordable/n_total*100:.1f}%)  unaffordable={n_total - n_affordable} "
          f"({(n_total-n_affordable)/n_total*100:.1f}%)")

    fractional_ret = scale_to_premium_budget(ret_per_premium, ANNUAL_PREMIUM_BUDGET)
    realistic_gross, realistic_costed = build_realistic_hybrid_ret(price_df, roll_info, roundtrip_cost_by_window)

    curve = pd.read_csv(SWITCH_CURVE)
    curve["dt"] = pd.to_datetime(curve["dt"])
    curve = curve.set_index("dt").sort_index()
    switch_ret = curve[SWITCH_COL].pct_change().rename("switch_ret")

    df = pd.concat(
        [switch_ret, fractional_ret.rename("fractional_put_ret"),
         realistic_gross.rename("realistic_put_ret_gross"), realistic_costed.rename("realistic_put_ret_costed")],
        axis=1, sort=True,
    ).dropna()
    df["hybrid_fractional"] = df["switch_ret"] + df["fractional_put_ret"]
    df["hybrid_realistic_gross"] = df["switch_ret"] + df["realistic_put_ret_gross"]
    df["hybrid_realistic_costed"] = df["switch_ret"] + df["realistic_put_ret_costed"]

    print("\n=== Full-window performance: switch alone vs fractional (unrealistic) hybrid vs realistic (integer-contract) hybrid ===")
    rows = [
        summarize("switch_alone", df["switch_ret"]),
        summarize("hybrid_fractional_unrealistic", df["hybrid_fractional"]),
        summarize("hybrid_realistic_gross", df["hybrid_realistic_gross"]),
        summarize("hybrid_realistic_costed", df["hybrid_realistic_costed"]),
    ]
    for r in rows:
        print(f"{r['name']:32s} ann_ret={r['ann_ret']*100:7.3f}%  ann_vol={r['ann_vol']*100:6.3f}%  "
              f"sharpe={r['sharpe']:6.3f}  mdd={r['mdd']*100:7.3f}%  CVaR95={r['cvar95_daily_loss']*100:6.4f}%")

    print("\n=== Contribution lost to granularity (fractional dollars vs realistic integer-contract dollars) ===")
    n_rolls_per_year = 252 / ROLL_EVERY
    per_roll_budget = REAL_NAV * ANNUAL_PREMIUM_BUDGET / n_rolls_per_year
    fractional_dollars_at_entry = per_roll_budget
    realistic_dollars_at_entry = roll_info["contracts"] * roll_info["dollars_per_contract"]
    coverage_ratio = (realistic_dollars_at_entry / fractional_dollars_at_entry)
    print(f"mean premium-dollar coverage ratio (realistic/fractional) across all rolls: {coverage_ratio.mean()*100:.1f}%")
    print(f"mean coverage ratio, affordable rolls only: {coverage_ratio[roll_info['affordable']].mean()*100:.1f}%")

    print("\n=== Per-year affordable-roll breakdown ===")
    roll_info_yr = roll_info.copy()
    roll_info_yr["year"] = roll_info_yr.index.year
    yearly = roll_info_yr.groupby("year")["affordable"].agg(["sum", "count"])
    yearly["pct"] = yearly["sum"] / yearly["count"] * 100
    print(yearly.to_string())

    out_path = PROJECT_ROOT / "results" / "txo_put_overlay_affordable_subset_2607_00883.csv"
    roll_info.to_csv(out_path, encoding="utf-8-sig")
    print(f"\nSaved per-roll affordability detail: {out_path}")

    # ---- second angle: does a cheaper (further-OTM) strike raise the
    # affordable-roll fraction enough to matter? Try 85% and 80% of spot
    # (vs the original 90%) -- cheaper premium per point, but weaker/later
    # protection (deeper OTM, further from triggering).
    print("\n=== Cheaper-strike sensitivity: affordable-roll % vs OTM depth ===")
    for otm_frac in (0.90, 0.85, 0.80, 0.75):
        pdf = build_price_df_with_roll_dt(con, START, END, otm_frac=otm_frac)
        ri = per_roll_contract_counts(pdf, ANNUAL_PREMIUM_BUDGET)
        n_afford = int(ri["affordable"].sum())
        mean_p0 = ri["P0"].mean()
        print(f"  strike={otm_frac*100:.0f}% of spot: mean P0={mean_p0:7.1f}pts  "
              f"affordable={n_afford}/{len(ri)} ({n_afford/len(ri)*100:5.1f}%)")


if __name__ == "__main__":
    main()
