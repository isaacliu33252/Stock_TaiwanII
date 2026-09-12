#!/usr/bin/env python3
"""Four-axis hedge diagnostic + TXO put-overlay shadow test for Group A+
(arXiv:2607.00883, Noguer i Alonso & Al-Fallouji, "Tail Risk Management with
Puts and Trend Following: A CVaR Framework for Crashes and Drawdowns").

The paper's core mechanism claim: convex put insurance reprices immediately
on a jump/crash (contractual, instant), while trend-following is structurally
LATE on a sudden shock because its signal must first cross zero -- but trend
becomes progressively more defensive over a PERSISTENT drawdown without
needing fresh premium. The two are complementary, not substitutes, and the
paper's own Section 3.1 four-axis diagnostic (conditional convexity,
tail-event reliability, non-stress carry, drawdown persistence) is the tool
it proposes for separating which mechanism is providing protection.

This script does two things for Group A+'s real regime-switch strategy
(0050/00631L/00632R, golden1<->defensive):

  1. Four-axis diagnostic on the real switch backtest (2020-01-02 to
     2026-08-18), isolating the defensive-switch overlay's own contribution
     from golden1's pure offense leg, against a 0050 buy-and-hold market
     baseline. Confirms/refutes: does Group A+'s regime-switching behave
     like the paper's "trend" archetype (high reliability/persistence, weak
     convexity), and does the combined strategy have a net conditional-
     convexity gap that a genuinely convex sleeve could fill?

  2. A real TXO (TAIEX index option) rolled 10%-OTM put overlay, built from
     actual TAIFEX settlement data (2020-2026, not a Black-Scholes proxy
     like the paper's own stylized experiment), sized at a realistic ~1.5%
     of NAV annual premium budget, layered on top of the real switch
     strategy. Reports whether the hybrid improves Sharpe/vol/MDD/CVaR over
     the switch strategy alone, and whether the improvement concentrates in
     sudden-shock episodes (as the paper predicts) versus slow-drawdown
     episodes.

Research-only. Does not modify any production runner, signal, or execution
plan. Requires a pre-existing switch-policy backtest curve CSV (see
--switch-curve) with 2020-01-02+ coverage; generate one with e.g.:
  python3 backtest_group_a_plus_switch_policy.py --start 2020-01-02 \
      --end <today> --output-prefix results/whatif_<name>
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"

ROLL_EVERY = 21  # trading days per roll, matching the paper's Delta=21
ANNUAL_PREMIUM_BUDGET = 0.015  # 1.5% of NAV/year, typical institutional tail-hedge sizing
ALPHA = 0.95
PERS_H, PERS_D = 10, 0.05  # persistence window: 10 trading days, >=5% drawdown


# ------------------------------------------------------------- TXO overlay
def build_txo_put_return_per_premium(con: duckdb.DuckDBPyConnection, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Unscaled overlay return: (P_t - P_{t-1}) / P_0 per roll window, i.e.
    the option's own P&L as a fraction of its initial premium. Multiply by a
    chosen per-roll premium-budget q to get the overlay's contribution to
    portfolio return -- kept separate from q so a sensitivity grid over q
    does not require re-querying TAIFEX data for every grid point."""
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
        target_strike = round(spot * 0.90 / 100) * 100

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

    price_df["P0"] = price_df.groupby("roll_dt")["price"].transform("first")
    ret_per_premium = price_df.groupby("roll_dt")["price"].diff() / price_df["P0"]

    # Round-trip transaction cost: buy at the entry-day ASK, sell the
    # incumbent contract at the exit-day (last day of window) BID, both
    # expressed relative to P0 (the mid/settlement price used as the return
    # denominator) so this is directly comparable to / subtractable from
    # ret_per_premium.
    first_rows = price_df.groupby("roll_dt").head(1)
    last_rows = price_df.groupby("roll_dt").tail(1)
    entry_cost = ((first_rows["ask"] - first_rows["price"]) / first_rows["P0"]).rename("entry_cost")
    exit_cost = ((last_rows["price"] - last_rows["bid"]) / last_rows["P0"]).rename("exit_cost")
    roundtrip_cost_by_window = (entry_cost.set_axis(first_rows["roll_dt"]) +
                                 exit_cost.set_axis(last_rows["roll_dt"])).rename("roundtrip_cost")

    return ret_per_premium.dropna().rename("ret_per_premium"), roundtrip_cost_by_window, price_df[["roll_dt"]]


def scale_to_premium_budget(ret_per_premium: pd.Series, annual_premium_budget: float) -> pd.Series:
    n_rolls_per_year = 252 / ROLL_EVERY
    q = annual_premium_budget / n_rolls_per_year
    return (ret_per_premium * q).rename("put_overlay_ret")


# --------------------------------------------------------- four-axis diag
def four_axis_diagnostic(sleeves: dict[str, np.ndarray], R_M: np.ndarray) -> pd.DataFrame:
    q_alpha = np.quantile(R_M, 1 - ALPHA)
    tail_mask = R_M <= q_alpha
    normal_mask = ~tail_mask

    def beta_cond(Ri, mask):
        r_i, r_m = Ri[mask], R_M[mask]
        v = np.var(r_m)
        return np.cov(r_i, r_m)[0, 1] / v if v > 0 else np.nan

    def persistence(Ri):
        n = len(R_M)
        cum_m = np.cumsum(np.log1p(R_M))
        hits, total = 0, 0
        for t in range(n - PERS_H):
            window_dd = cum_m[t + PERS_H] - cum_m[t : t + PERS_H + 1].max()
            if window_dd <= -PERS_D:
                total += 1
                if np.sum(np.log1p(Ri[t : t + PERS_H])) > 0:
                    hits += 1
        return (hits / total if total > 0 else np.nan), total

    rows = []
    for name, Ri in sleeves.items():
        b_minus, b_zero = beta_cond(Ri, tail_mask), beta_cond(Ri, normal_mask)
        pers, n_dd = persistence(Ri)
        rows.append({
            "sleeve": name, "beta_tail": b_minus, "beta_normal": b_zero,
            "Conv": -(b_minus - b_zero), "Hit": float(np.mean(Ri[tail_mask] > 0)),
            "Carry": float(-np.mean(Ri[normal_mask])), "Pers": pers, "n_drawdown_episodes": n_dd,
        })
    return pd.DataFrame(rows)


def perf_stats(r: np.ndarray) -> dict:
    ann_ret = r.mean() * 252
    ann_vol = r.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    cum = np.exp(np.cumsum(np.log1p(r)))
    mdd = (cum / np.maximum.accumulate(cum) - 1).min()
    L = -np.log1p(r)
    var95 = np.quantile(L, ALPHA)
    cvar95 = L[L >= var95].mean()
    return {"ann_ret": float(ann_ret), "ann_vol": float(ann_vol), "sharpe": float(sharpe),
            "mdd": float(mdd), "cvar95_daily_loss": float(cvar95)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--switch-curve", default=str(
        PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_curve.csv"))
    parser.add_argument("--switch-col", default="switch_risk_ma80_dd11_total6_hold5_eg015_xg015")
    parser.add_argument("--golden-col", default="golden1_0531_1m")
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-08-18")
    parser.add_argument("--output", default=str(
        PROJECT_ROOT / "results" / "2607_00883_txo_put_overlay_shadow.json"))
    args = parser.parse_args()

    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    con = duckdb.connect(str(DB_PATH), read_only=True)

    curve = pd.read_csv(args.switch_curve)
    curve["dt"] = pd.to_datetime(curve["dt"])
    curve = curve.set_index("dt").sort_index()
    switch_ret = curve[args.switch_col].pct_change().rename("switch_ret")
    golden_ret = curve[args.golden_col].pct_change().rename("golden1_offense")

    ohlcv = con.execute("select dt, close from ohlcv where ticker='0050.TW' order by dt").fetchdf()
    ohlcv["dt"] = pd.to_datetime(ohlcv["dt"])
    ohlcv = ohlcv.set_index("dt").sort_index()
    mkt_ret = ohlcv["close"].pct_change().rename("mkt_ret")

    ret_per_premium, roundtrip_cost_by_window, _win = build_txo_put_return_per_premium(con, start, end)
    put_ret = scale_to_premium_budget(ret_per_premium, ANNUAL_PREMIUM_BUDGET)

    # Cost-adjusted variant: subtract the round-trip bid-ask cost once at the
    # end of each roll window (the day the incumbent contract is sold to
    # fund the next roll), scaled by the same premium budget q.
    ret_per_premium_costed = ret_per_premium.copy()
    last_day_per_window = _win.reset_index().groupby("roll_dt")["dt"].max()
    for rdt, cost in roundtrip_cost_by_window.items():
        last_dt = last_day_per_window.get(rdt)
        if last_dt is not None and last_dt in ret_per_premium_costed.index:
            ret_per_premium_costed.loc[last_dt] -= cost
    put_ret_costed = scale_to_premium_budget(ret_per_premium_costed, ANNUAL_PREMIUM_BUDGET)

    df = pd.concat([switch_ret, golden_ret, mkt_ret, put_ret], axis=1, sort=True).dropna()
    df["defensive_overlay"] = df["switch_ret"] - df["golden1_offense"]
    df["hybrid_ret"] = df["switch_ret"] + df["put_overlay_ret"]

    diag = four_axis_diagnostic(
        {name: df[name].values for name in
         ["mkt_ret", "golden1_offense", "switch_ret", "defensive_overlay", "put_overlay_ret", "hybrid_ret"]},
        df["mkt_ret"].values,
    )
    print("\n=== Four-axis diagnostic ===")
    print(diag.to_string(index=False))

    perf = {name: perf_stats(df[name].values) for name in ["switch_ret", "hybrid_ret", "mkt_ret"]}
    print("\n=== Full-window performance (switch alone vs switch+put hybrid) ===")
    for name, p in perf.items():
        print(f"{name:16s} ann_ret={p['ann_ret']*100:7.2f}%  ann_vol={p['ann_vol']*100:7.2f}%  "
              f"sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%  CVaR95={p['cvar95_daily_loss']*100:6.3f}%")

    episodes = {
        "covid_crash_2020": ("2020-01-20", "2020-03-23"),
        "tariff_shock_2025_04": ("2025-04-01", "2025-04-15"),
        "bear_2022_full_year": ("2022-01-01", "2022-12-31"),
    }
    episode_results = {}
    for name, (s, e) in episodes.items():
        sub = df.loc[s:e]
        if sub.empty:
            continue
        cs = (1 + sub["switch_ret"]).cumprod()
        ch = (1 + sub["hybrid_ret"]).cumprod()
        episode_results[name] = {
            "switch_cum_ret": float(cs.iloc[-1] - 1), "hybrid_cum_ret": float(ch.iloc[-1] - 1),
            "switch_mdd": float((cs / cs.cummax() - 1).min()), "hybrid_mdd": float((ch / ch.cummax() - 1).min()),
        }
    print("\n=== Episode breakdown (switch vs hybrid MDD) ===")
    for name, r in episode_results.items():
        print(f"{name:22s} switch_mdd={r['switch_mdd']*100:7.2f}%  hybrid_mdd={r['hybrid_mdd']*100:7.2f}%  "
              f"delta={100*(r['hybrid_mdd']-r['switch_mdd']):+.2f}pp")

    # Independent-year split: the full-window aggregate can be dominated by a
    # single episode (e.g. the 2025-04 tariff shock). Split into calendar
    # years -- the project's standard robustness check before any promotion
    # discussion -- to see whether the hybrid's improvement holds up as
    # independent year-by-year evidence rather than one continuous sample.
    year_results = {}
    for year, sub in df.groupby(df.index.year):
        if len(sub) < 20:
            continue
        p_switch = perf_stats(sub["switch_ret"].values)
        p_hybrid = perf_stats(sub["hybrid_ret"].values)
        year_results[str(year)] = {
            "n_days": int(len(sub)),
            "switch": p_switch, "hybrid": p_hybrid,
            "sharpe_delta": float(p_hybrid["sharpe"] - p_switch["sharpe"]),
            "mdd_delta_pp": float(100 * (p_hybrid["mdd"] - p_switch["mdd"])),
            "cvar95_delta_pp": float(100 * (p_hybrid["cvar95_daily_loss"] - p_switch["cvar95_daily_loss"])),
        }
    print("\n=== Independent calendar-year breakdown (switch vs hybrid) ===")
    n_years_hybrid_wins_sharpe = 0
    n_years_hybrid_wins_mdd = 0
    for year, r in year_results.items():
        sharpe_win = r["sharpe_delta"] > 0
        mdd_win = r["mdd_delta_pp"] > 0
        n_years_hybrid_wins_sharpe += int(sharpe_win)
        n_years_hybrid_wins_mdd += int(mdd_win)
        print(f"{year} (n={r['n_days']:4d})  sharpe: {r['switch']['sharpe']:6.3f} -> {r['hybrid']['sharpe']:6.3f} "
              f"({r['sharpe_delta']:+.3f}{'  WIN' if sharpe_win else ''})   "
              f"mdd: {r['switch']['mdd']*100:7.2f}% -> {r['hybrid']['mdd']*100:7.2f}% "
              f"({r['mdd_delta_pp']:+.2f}pp{'  WIN' if mdd_win else ''})")
    n_years = len(year_results)
    print(f"\nhybrid wins on Sharpe in {n_years_hybrid_wins_sharpe}/{n_years} years, "
          f"on MDD in {n_years_hybrid_wins_mdd}/{n_years} years")

    # Premium-budget sensitivity grid: q=1.5%/year was a single point. Check
    # whether the full-window improvement and the year-win-rate are stable
    # across a reasonable range, or whether 1.5% happened to sit at a lucky
    # sweet spot (the earlier q=2%/roll blowup already showed this parameter
    # is NOT robust to careless sizing -- see handoff doc Section 4.1).
    grid = [0.005, 0.010, 0.015, 0.020, 0.030]
    grid_results = {}
    print("\n=== Premium-budget sensitivity grid (annual %, full-window + year win-rate) ===")
    for budget in grid:
        put_ret_g = scale_to_premium_budget(ret_per_premium, budget)
        df_g = pd.concat([switch_ret, put_ret_g], axis=1, sort=True).dropna()
        df_g["hybrid_ret"] = df_g["switch_ret"] + df_g["put_overlay_ret"]
        p_switch_g = perf_stats(df_g["switch_ret"].values)
        p_hybrid_g = perf_stats(df_g["hybrid_ret"].values)

        wins_sharpe, wins_mdd, n_yrs_g = 0, 0, 0
        for _, sub in df_g.groupby(df_g.index.year):
            if len(sub) < 20:
                continue
            n_yrs_g += 1
            ps = perf_stats(sub["switch_ret"].values)
            ph = perf_stats(sub["hybrid_ret"].values)
            wins_sharpe += int(ph["sharpe"] > ps["sharpe"])
            wins_mdd += int(ph["mdd"] > ps["mdd"])

        grid_results[f"{budget:.3f}"] = {
            "annual_premium_budget": budget,
            "full_window_sharpe": p_hybrid_g["sharpe"], "full_window_sharpe_delta": p_hybrid_g["sharpe"] - p_switch_g["sharpe"],
            "full_window_mdd": p_hybrid_g["mdd"], "full_window_mdd_delta_pp": 100 * (p_hybrid_g["mdd"] - p_switch_g["mdd"]),
            "full_window_ann_ret_delta_pp": 100 * (p_hybrid_g["ann_ret"] - p_switch_g["ann_ret"]),
            "years_win_sharpe": wins_sharpe, "years_win_mdd": wins_mdd, "years_total": n_yrs_g,
        }
        print(f"q={budget*100:4.1f}%/yr  sharpe {p_switch_g['sharpe']:6.3f}->{p_hybrid_g['sharpe']:6.3f} "
              f"({p_hybrid_g['sharpe']-p_switch_g['sharpe']:+.3f})   "
              f"mdd {p_switch_g['mdd']*100:7.2f}%->{p_hybrid_g['mdd']*100:7.2f}% "
              f"({100*(p_hybrid_g['mdd']-p_switch_g['mdd']):+.2f}pp)   "
              f"ann_ret_delta={100*(p_hybrid_g['ann_ret']-p_switch_g['ann_ret']):+.2f}pp   "
              f"year_wins: sharpe {wins_sharpe}/{n_yrs_g}, mdd {wins_mdd}/{n_yrs_g}")

    # Transaction-cost-adjusted comparison: enter at ASK, exit (roll out) at
    # BID, using the actual quoted TXO spreads for the exact strikes traded.
    df_costed = pd.concat([switch_ret, put_ret_costed.rename("put_overlay_ret")], axis=1, sort=True).dropna()
    df_costed["hybrid_ret"] = df_costed["switch_ret"] + df_costed["put_overlay_ret"]
    p_hybrid_costed = perf_stats(df_costed["hybrid_ret"].values)
    p_hybrid_nocost = perf["hybrid_ret"]
    print("\n=== Transaction-cost impact (real TXO bid-ask spreads, entry@ask/exit@bid) ===")
    print(f"{'no transaction cost':22s} sharpe={p_hybrid_nocost['sharpe']:6.3f}  mdd={p_hybrid_nocost['mdd']*100:7.2f}%  "
          f"ann_ret={p_hybrid_nocost['ann_ret']*100:7.2f}%")
    print(f"{'with transaction cost':22s} sharpe={p_hybrid_costed['sharpe']:6.3f}  mdd={p_hybrid_costed['mdd']*100:7.2f}%  "
          f"ann_ret={p_hybrid_costed['ann_ret']*100:7.2f}%")
    avg_roundtrip_cost_pct = float(roundtrip_cost_by_window.mean() * 100)
    print(f"average round-trip spread cost per roll: {avg_roundtrip_cost_pct:.1f}% of that window's initial premium "
          f"({len(roundtrip_cost_by_window)} rolls)")

    # Basis risk: the overlay hedges TAIEX (^TWII) via TXO, but Group A+'s
    # actual exposure is 0050 (and 00631L/00632R). Quantify the gap directly
    # rather than asserting it away -- especially conditional on the same
    # market-tail days the put overlay is meant to protect.
    twii_close = con.execute("select dt, close from external_market_ohlcv where ticker='^TWII' order by dt").fetchdf()
    twii_close["dt"] = pd.to_datetime(twii_close["dt"])
    twii_close = twii_close.set_index("dt").sort_index()
    twii_ret = twii_close["close"].pct_change().rename("twii_ret")
    basis_df = pd.concat([df["mkt_ret"], twii_ret], axis=1, sort=True).dropna()
    full_corr = float(basis_df["mkt_ret"].corr(basis_df["twii_ret"]))
    q_tail = np.quantile(basis_df["mkt_ret"].values, 1 - ALPHA)
    tail_sub = basis_df[basis_df["mkt_ret"] <= q_tail]
    tail_corr = float(tail_sub["mkt_ret"].corr(tail_sub["twii_ret"]))
    beta_0050_on_twii_tail = float(np.cov(tail_sub["mkt_ret"], tail_sub["twii_ret"])[0, 1] / np.var(tail_sub["twii_ret"]))
    print("\n=== Basis risk: 0050 vs TAIEX (^TWII), the TXO underlying ===")
    print(f"full-sample correlation: {full_corr:.4f}")
    print(f"market-tail-day correlation (n={len(tail_sub)}): {tail_corr:.4f}, "
          f"beta(0050 on TWII) in tail: {beta_0050_on_twii_tail:.3f}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"start": str(df.index.min().date()), "end": str(df.index.max().date()), "n_days": int(len(df))},
        "annual_premium_budget": ANNUAL_PREMIUM_BUDGET,
        "roll_every_trading_days": ROLL_EVERY,
        "four_axis_diagnostic": diag.to_dict(orient="records"),
        "performance": perf,
        "episode_breakdown": episode_results,
        "independent_year_breakdown": year_results,
        "n_years_hybrid_wins_sharpe": n_years_hybrid_wins_sharpe,
        "n_years_hybrid_wins_mdd": n_years_hybrid_wins_mdd,
        "n_years_total": n_years,
        "premium_budget_sensitivity_grid": grid_results,
        "transaction_cost_impact": {
            "no_cost": p_hybrid_nocost, "with_cost": p_hybrid_costed,
            "avg_roundtrip_cost_pct_of_premium": avg_roundtrip_cost_pct, "n_rolls": int(len(roundtrip_cost_by_window)),
        },
        "basis_risk_0050_vs_twii": {
            "full_sample_corr": full_corr, "tail_day_corr": tail_corr,
            "tail_beta_0050_on_twii": beta_0050_on_twii_tail, "n_tail_days": int(len(tail_sub)),
        },
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
