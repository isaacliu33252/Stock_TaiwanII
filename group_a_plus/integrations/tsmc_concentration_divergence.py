"""TSMC concentration-divergence diagnostics: is 0050's move TSMC-led or broad?

User-proposed research line, 2026-08-09. Formalizes and extends the existing
`0050_ex_tsmc_proxy` / `narrow_lead` machinery already live in
`group_a_plus/operations/daily_signal.py` (advisory-only there) with:

- an explicit TSMC_contribution_to_0050 metric (previously only implicit in
  the ex-TSMC formula's residual);
- a "top-5" concentration/breadth proxy using the 5 largest 0050 constituents
  this project already has price history for (TSMC/2330, Hon Hai/2317,
  MediaTek/2454, Delta/2308, Quanta/2382 -- ~58-71% of 0050's weight
  depending on source, see WEIGHT CAVEAT below).

Deliberately price-only (no NCF dependency), so it is fully backtestable over
history without reconstructing historical model probabilities and without
lookahead -- matches daily_signal.py's `narrow_lead` boolean exactly, but
factored out so it can run standalone in a shadow backtest.

WEIGHT CAVEAT: `TSMC_0050_WEIGHT_ASSUMPTION` (0.5831, from
group_a_plus/utils/tsmc_0050_weight.py) is the single, officially-calibrated
source of truth for TSMC's own weight (Yuanta's disclosed holdings page,
2026-07-10). The other 4 tickers' weights below come from
`scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`'s
`PARTIAL_0050_PROXY_WEIGHTS`, itself labelled "research-only proxy" there --
not independently re-verified here. Treat TOP5_WEIGHTS as an estimate.

BREADTH CAVEAT: this project's DB only has individual-stock price history for
these 5 large-cap constituents. A literal full-0050-universe breadth metric
(~50 constituents: % above 20MA, % advancing, equal-weight vs cap-weight
proxy) would need a new constituent-list + OHLCV-fetch pipeline for the
other ~45 stocks -- not built here. Everything below is a top-5 mega-cap
proxy, not full-universe breadth. It still captures a meaningful slice
(~67-71% of 0050's weight) but systematically cannot detect breadth
divergence confined to the remaining ~45 mid-cap constituents.

DATA SOURCE (2026-08-09): all 5 tickers, including TSMC, are read from
`external_market_ohlcv` (provider='yfinance'). 2317/2454/2308/2382 were
originally in `ohlcv` (populated once by an unrelated research backtest,
found stuck at 2026-07-15 -- ~3.5 weeks stale) and have now been backfilled
into `external_market_ohlcv` via `scripts/fetch/fetch_cross_market_ohlcv.py`
(added to its DEFAULT_TICKERS so they refresh unconditionally every daily
pipeline run going forward, same mechanism as 2330.TW). The old `ohlcv` rows
for these 4 tickers are left in place but are no longer read here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from group_a_plus.utils.tsmc_0050_weight import TSMC_0050_WEIGHT_ASSUMPTION

TSMC_TICKER = "2330.TW"
TOP5_TICKERS = ("2330.TW", "2317.TW", "2454.TW", "2308.TW", "2382.TW")
# Research-only proxy weights (2317/2454/2308/2382 from
# evaluate_stockmixer_atfnet_shadow.py's PARTIAL_0050_PROXY_WEIGHTS; TSMC
# overridden to the officially-calibrated TSMC_0050_WEIGHT_ASSUMPTION).
TOP5_WEIGHTS = {
    "2330.TW": TSMC_0050_WEIGHT_ASSUMPTION,
    "2317.TW": 0.04834110,
    "2454.TW": 0.03959831,
    "2308.TW": 0.02607424,
    "2382.TW": 0.01352036,
}
NARROW_LEAD_MIN_2330_RET_5D = 0.0
NARROW_LEAD_MAX_EX_TSMC_RET_5D = 0.0
NARROW_LEAD_MIN_LEAD_GAP_5D = 0.01


def ex_tsmc_return(ret_0050: float, ret_2330: float, tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION) -> float | None:
    """Same formula as daily_signal.py's `0050_ex_tsmc_proxy`."""

    if tsmc_weight >= 1.0:
        return None
    return (ret_0050 - tsmc_weight * ret_2330) / (1.0 - tsmc_weight)


def tsmc_contribution_to_0050(ret_2330: float, tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION) -> float:
    """Percentage-point contribution of TSMC's own move to 0050's return."""

    return tsmc_weight * ret_2330


def concentration_divergence(ret_2330: float, ret_0050: float, tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION) -> float | None:
    ex_ret = ex_tsmc_return(ret_0050, ret_2330, tsmc_weight)
    if ex_ret is None:
        return None
    return ret_2330 - ex_ret


def classify_narrow_lead(
    ret_2330_5d: float | None,
    ret_0050_5d: float | None,
    ret_ex_tsmc_5d: float | None,
) -> bool:
    """Reproduces daily_signal.py's `narrow_lead` boolean exactly (price-only)."""

    if ret_2330_5d is None or ret_0050_5d is None or ret_ex_tsmc_5d is None:
        return False
    return (
        float(ret_2330_5d) > NARROW_LEAD_MIN_2330_RET_5D
        and float(ret_ex_tsmc_5d) <= NARROW_LEAD_MAX_EX_TSMC_RET_5D
        and float(ret_2330_5d) - float(ret_0050_5d) > NARROW_LEAD_MIN_LEAD_GAP_5D
    )


def _load_close_prices(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    """All top-5-proxy tickers (including TSMC) come from external_market_ohlcv.

    2026-08-09: consolidated onto this single source -- see module docstring
    DATA SOURCE note. 0050.TW itself (the ETF being decomposed, not one of
    the 5 proxy constituents) still comes from `ohlcv`, which is refreshed
    daily via the main Group A pipeline and was never stale.
    """

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        external_tickers = [t for t in tickers if t in TOP5_TICKERS]
        ohlcv_tickers = [t for t in tickers if t not in TOP5_TICKERS]
        frames = []
        if ohlcv_tickers:
            placeholders = ", ".join(["?"] * len(ohlcv_tickers))
            rows = con.execute(
                f"SELECT dt, ticker, close FROM ohlcv WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?",
                [*ohlcv_tickers, start, end],
            ).fetchdf()
            frames.append(rows)
        if external_tickers:
            placeholders = ", ".join(["?"] * len(external_tickers))
            rows = con.execute(
                f"SELECT dt, ticker, close FROM external_market_ohlcv "
                f"WHERE provider = 'yfinance' AND ticker IN ({placeholders}) AND dt BETWEEN ? AND ?",
                [*external_tickers, start, end],
            ).fetchdf()
            frames.append(rows)
    finally:
        con.close()
    combined = pd.concat(frames, ignore_index=True)
    combined["dt"] = pd.to_datetime(combined["dt"])
    return combined.pivot(index="dt", columns="ticker", values="close").sort_index()


def top5_breadth_snapshot(db_path: Path, as_of: str, *, lookback_days: int = 60) -> dict[str, Any]:
    """Top-5 concentration + breadth proxy as of a given date.

    Returns None-status fields (not a raised exception) when data is
    insufficient -- callers decide how to treat unavailability.
    """

    as_of_ts = pd.Timestamp(as_of)
    start = (as_of_ts - pd.Timedelta(days=lookback_days + 40)).strftime("%Y-%m-%d")
    prices = _load_close_prices(db_path, (*TOP5_TICKERS, "0050.TW"), start, as_of)
    prices = prices.loc[prices.index <= as_of_ts]
    if prices.empty or any(t not in prices.columns for t in (*TOP5_TICKERS, "0050.TW")):
        return {"status": "unavailable", "reason": "missing_price_history"}

    prices = prices.dropna(subset=["0050.TW", *TOP5_TICKERS], how="any")
    if len(prices) < 21:
        return {"status": "unavailable", "reason": "insufficient_history"}

    latest = prices.iloc[-1]
    ma20 = prices[list(TOP5_TICKERS)].rolling(20).mean().iloc[-1]
    above_ma20 = {t: bool(latest[t] > ma20[t]) for t in TOP5_TICKERS}
    ret_5d = (prices / prices.shift(5) - 1.0).iloc[-1]
    advancing_5d = {t: bool(ret_5d[t] > 0.0) for t in TOP5_TICKERS}

    ret_2330_5d = float(ret_5d[TSMC_TICKER])
    ret_0050_5d = float(ret_5d["0050.TW"])
    ex_ret_5d = ex_tsmc_return(ret_0050_5d, ret_2330_5d)
    divergence_5d = concentration_divergence(ret_2330_5d, ret_0050_5d)
    narrow_lead = classify_narrow_lead(ret_2330_5d, ret_0050_5d, ex_ret_5d)

    top5_weight_sum = sum(TOP5_WEIGHTS.values())
    weighted_top5_ret_5d = sum(float(ret_5d[t]) * TOP5_WEIGHTS[t] for t in TOP5_TICKERS)
    top5_contribution_ratio = (
        weighted_top5_ret_5d / (ret_0050_5d * top5_weight_sum)
        if ret_0050_5d != 0.0
        else None
    )

    return {
        "status": "ok",
        "date": str(prices.index[-1].date()),
        "tsmc_weight_assumption": TSMC_0050_WEIGHT_ASSUMPTION,
        "top5_weight_sum_estimate": round(top5_weight_sum, 4),
        "ret_5d": {t: round(float(ret_5d[t]), 6) for t in (*TOP5_TICKERS, "0050.TW")},
        "ex_tsmc_return_5d": round(ex_ret_5d, 6) if ex_ret_5d is not None else None,
        "concentration_divergence_5d": round(divergence_5d, 6) if divergence_5d is not None else None,
        "tsmc_contribution_to_0050_5d": round(tsmc_contribution_to_0050(ret_2330_5d), 6),
        "narrow_lead": narrow_lead,
        "top5_above_ma20": above_ma20,
        "top5_above_ma20_pct": round(sum(above_ma20.values()) / len(above_ma20), 4),
        "top5_advancing_5d": advancing_5d,
        "top5_advancing_5d_pct": round(sum(advancing_5d.values()) / len(advancing_5d), 4),
        "top5_weighted_contribution_ratio_5d": (
            round(top5_contribution_ratio, 4) if top5_contribution_ratio is not None else None
        ),
        "caveat": (
            "top-5 mega-cap proxy only (~"
            f"{round(top5_weight_sum * 100, 1)}% of 0050's weight estimated), "
            "not full ~50-constituent breadth -- see module docstring"
        ),
    }
