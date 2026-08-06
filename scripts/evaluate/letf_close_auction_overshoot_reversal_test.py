#!/usr/bin/env python3
"""Test whether 00631L/00632R rebalancing pressure produces a Korea-style
close-auction overshoot/next-day-reversal signature in TSMC (2330).

Research/advisory-readiness artifact only. Motivated by arXiv:2608.03703
("Preying on Leveraged ETFs", Zhao 2026), which shows that when a leveraged
ETF's daily rebalancing order is large relative to the closing auction that
prices it, the close over-weights public news and the overweight reverses
the next cycle. 00631L/00632R are index-level (not single-stock) LETFs, but
TSMC (2330) dominates the Taiwan 50 index weight, so the rebalancing flow
concentrates disproportionately on 2330's own closing print.

We do not have LETF AUM/NAV or closing-auction-specific volume data (Taiwan
tick/order-book data is not stored in this project's DB), so this is a
reduced-form replication using what is available:
  - overnight U.S. tech/semiconductor return as the public-news instrument
    (matches the paper's identification strategy)
  - same-day and next-day close-to-close returns for 2330 and index-weight
    control stocks (2317, 2454, 2412 -- lower Taiwan 50 weight, so less
    exposed to 00631L/00632R rebalancing flow per unit of own liquidity)
  - 00631L+00632R combined daily traded value as a rebalancing-capital
    "dose" proxy (AUM is unobserved; traded value is the closest available
    proxy and grows with fund size)

This script never writes to the production DB and never changes live target
weights. Output is a markdown report under research/shadow/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402

CACHE_DIR = PROJECT_ROOT / "research" / "shadow" / "_cache"
OUTPUT_MD = PROJECT_ROOT / "research" / "shadow" / "LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md"

CONTROL_TICKERS = {
    "2317.TW": "Hon Hai (low Taiwan50 weight)",
    "2454.TW": "MediaTek (low Taiwan50 weight)",
    "2412.TW": "Chunghwa Telecom (low-beta control)",
}
INSTRUMENTS = ["SOXX", "QQQ", "^IXIC"]
HAC_LAGS = 5


def _fetch_control(ticker: str) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{ticker.replace('^', '').replace('=', '_')}.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["dt"])
        return df
    raw = yf.download(ticker, start="2014-01-01", progress=False, auto_adjust=False)
    if raw.empty:
        raise RuntimeError(f"yfinance returned no data for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.reset_index()[["Date", "Close"]].rename(columns={"Date": "dt", "Close": "close"})
    df["dt"] = pd.to_datetime(df["dt"])
    df.to_csv(cache_path, index=False)
    return df


def _load_db_series(con: duckdb.DuckDBPyConnection, table: str, ticker: str, ticker_col: str = "ticker") -> pd.DataFrame:
    q = f"SELECT dt, close, volume FROM {table} WHERE {ticker_col} = ? ORDER BY dt"
    df = con.execute(q, [ticker]).fetchdf()
    df["dt"] = pd.to_datetime(df["dt"])
    return df


def _ret(df: pd.DataFrame, col: str = "close") -> pd.Series:
    return df.set_index("dt")[col].pct_change()


def _align_overnight_instrument(tw_dates: pd.DatetimeIndex, us_ret: pd.Series) -> pd.Series:
    """For each Taiwan trading date T, return the U.S. instrument's return on
    the most recent U.S. trading date strictly before T's local morning, i.e.
    the most recent U.S. close <= T - 1 calendar day (12-13h timezone gap
    means the U.S. session for calendar date T has not opened yet when
    Taiwan's date-T session starts)."""
    us_ret = us_ret.dropna().sort_index()
    tw = pd.DataFrame({"dt": tw_dates}).sort_values("dt")
    tw["cutoff"] = tw["dt"] - pd.Timedelta(days=1)
    us = pd.DataFrame({"us_dt": us_ret.index, "us_ret": us_ret.values}).sort_values("us_dt")
    merged = pd.merge_asof(tw, us, left_on="cutoff", right_on="us_dt", direction="backward")
    return pd.Series(merged["us_ret"].values, index=merged["dt"].values)


def _hac_reg(y: pd.Series, x: pd.Series, label: str) -> dict:
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(df) < 30:
        return {"label": label, "n": len(df), "beta": np.nan, "t": np.nan, "p": np.nan}
    X = sm.add_constant(df["x"])
    model = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return {
        "label": label,
        "n": int(len(df)),
        "beta": float(model.params["x"]),
        "t": float(model.tvalues["x"]),
        "p": float(model.pvalues["x"]),
    }


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)

    letf_l = _load_db_series(con, "ohlcv", "00631L.TW")
    letf_r = _load_db_series(con, "ohlcv", "00632R.TW")
    tsmc = con.execute(
        "SELECT dt, close, volume FROM external_market_ohlcv WHERE ticker = '2330.TW' ORDER BY dt"
    ).fetchdf()
    tsmc["dt"] = pd.to_datetime(tsmc["dt"])
    tw50 = _load_db_series(con, "ohlcv", "0050.TW")
    con.close()

    controls = {name: _fetch_control(t) for t, name in CONTROL_TICKERS.items()}
    instruments = {t: _fetch_control(t) for t in INSTRUMENTS}

    tsmc_ret = _ret(tsmc)
    control_rets = {name: _ret(df) for name, df in controls.items()}
    instr_rets = {t: _ret(df) for t, df in instruments.items()}

    tw_dates = pd.DatetimeIndex(sorted(tsmc["dt"].unique()))

    # dose proxy: 00631L + 00632R combined daily traded value (TWD)
    dv_l = (letf_l.set_index("dt")["close"] * letf_l.set_index("dt")["volume"]).rename("dv_l")
    dv_r = (letf_r.set_index("dt")["close"] * letf_r.set_index("dt")["volume"]).rename("dv_r")
    dose = (dv_l.reindex(tw_dates).fillna(0) + dv_r.reindex(tw_dates).fillna(0)).rename("dose")
    dose_by_year = dose.groupby(dose.index.year).mean() / 1e8  # 億元 TWD

    tsmc_dv = (tsmc.set_index("dt")["close"] * tsmc.set_index("dt")["volume"]).rename("tsmc_dv")
    tsmc_dv_by_year = tsmc_dv.reindex(tw_dates).groupby(tw_dates.year).mean() / 1e8
    ratio_by_year = (dose_by_year / tsmc_dv_by_year).round(3)

    tw50_ret = _ret(tw50)
    targets = {"2330 (TSMC)": tsmc_ret, "0050 (Taiwan50, LETF's own underlying)": tw50_ret, **control_rets}

    results_full = []
    results_split = []
    for instr_name, instr_ret in instr_rets.items():
        overnight = _align_overnight_instrument(tw_dates, instr_ret)
        for tgt_name, tgt_ret in targets.items():
            tgt_aligned = tgt_ret.reindex(overnight.index)
            tgt_next = tgt_ret.reindex(overnight.index).shift(-1)

            r_same = _hac_reg(tgt_aligned, overnight, f"{tgt_name} | t | {instr_name}")
            r_next = _hac_reg(tgt_next, overnight, f"{tgt_name} | t+1 | {instr_name}")
            results_full.append({"channel": "same-day (t)", **r_same})
            results_full.append({"channel": "next-day (t+1, reversal test)", **r_next})

            # dose split: below/above median of trailing 60d dose, evaluated only for 2330 and SOXX
            if tgt_name == "2330 (TSMC)" and instr_name == "SOXX":
                dose_roll = dose.rolling(60, min_periods=30).median()
                dose_aligned = dose_roll.reindex(overnight.index)
                lo_mask = dose_aligned <= dose_aligned.median()
                hi_mask = dose_aligned > dose_aligned.median()
                for label, mask in [("low-dose (00631L+00632R turnover below median)", lo_mask),
                                     ("high-dose (00631L+00632R turnover above median)", hi_mask)]:
                    r = _hac_reg(tgt_next[mask], overnight[mask], f"{tgt_name} | t+1 | {label}")
                    results_split.append(r | {"regime": label})

                # also split by calendar period (00631L AUM grew sharply from ~2020)
                for label, period_mask in [
                    ("pre-2020-01 (smaller 00631L)", overnight.index.year < 2020),
                    ("2020-01 onward (larger 00631L)", overnight.index.year >= 2020),
                ]:
                    m = pd.Series(period_mask, index=overnight.index)
                    r = _hac_reg(tgt_next[m], overnight[m], f"{tgt_name} | t+1 | {label}")
                    results_split.append(r | {"regime": label})

    full_df = pd.DataFrame(results_full)
    split_df = pd.DataFrame(results_split)

    lines = []
    lines.append("# LETF Close-Auction Overshoot/Reversal Test — 2330 vs 00631L/00632R")
    lines.append("")
    lines.append("**Status: research/shadow only. Not wired to any production signal or gate.**")
    lines.append("")
    lines.append("Motivated by arXiv:2608.03703 (\"Preying on Leveraged ETFs\", Zhao 2026-08-04).")
    lines.append("Tests whether TSMC's close over-weights overnight U.S. tech/semiconductor news")
    lines.append("and reverses the next session -- the paper's headline signature for Korean")
    lines.append("single-stock LETFs -- given that TSMC dominates the Taiwan 50 index weight that")
    lines.append("00631L/00632R rebalance against. No LETF AUM or closing-auction-specific volume")
    lines.append("data exists in this project's DB, so K and the saturation ratio from the paper")
    lines.append("cannot be replicated directly; this is a reduced-form proxy test only.")
    lines.append("")
    lines.append("## Dose proxy: 00631L+00632R combined daily traded value (億元 TWD, yearly mean)")
    lines.append("")
    lines.append(dose_by_year.round(1).to_string())
    lines.append("")
    lines.append("## Context: TSMC's own daily traded value (億元 TWD, yearly mean)")
    lines.append("")
    lines.append(tsmc_dv_by_year.round(1).to_string())
    lines.append("")
    lines.append("## Ratio: (00631L+00632R turnover) / (TSMC's own full-day turnover)")
    lines.append("")
    lines.append("Ceiling on any same-day loop gain from this channel -- 00631L/00632R's")
    lines.append("*entire* day's flow, not just the closing-auction slice of it, relative to")
    lines.append("TSMC's own full-day liquidity. Korea's SK Hynix analogue (order vs. auction")
    lines.append("alone, not full-day volume) reached a median of 1.02.")
    lines.append("")
    lines.append(ratio_by_year.to_string())
    lines.append("")
    lines.append("## Full-sample regressions (HAC/Newey-West, 5 lags)")
    lines.append("")
    lines.append(full_df.to_string(index=False))
    lines.append("")
    lines.append("## Dose-split and period-split regressions (2330, next-day reversal, SOXX instrument)")
    lines.append("")
    lines.append(split_df.to_string(index=False))
    lines.append("")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
