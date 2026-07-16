#!/usr/bin/env python3
"""Build the daily/weekly TSMC checklist used alongside ncf_2330.

The report is diagnostic-only: it summarizes the table of fundamental,
valuation, technical, ADR, global semiconductor, FX, chip-flow, and 0050
relationship checks without changing GroupA+ weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from group_a_plus.utils.tsmc_0050_weight import TSMC_0050_WEIGHT_ASSUMPTION  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
RESULTS_DIR = PROJECT_ROOT / "results"
DEFAULT_OUTPUT = RESULTS_DIR / f"ncf_2330_checklist_{datetime.now().strftime('%Y%m%d')}.json"

TSMC_ADR_RATIO = 5.0
# Fable audit (2026-07-08, #9): this had drifted to a third, independently
# hardcoded value (0.50) while daily_signal.py and ncf_2330.py both used
# 0.55 -- the manual-review checklist a human reads was silently computing
# its ex-TSMC proxy with a different weight than the one actually driving
# the tsmc_weak_manual_review alert. Now sourced from the same single
# constant as everywhere else.
SIGNAL_SCORE = {"bullish": 1, "neutral": 0, "bearish": -1}


def _round(value: Any, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _status(status: str, signal: str, values: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "signal": signal,
        "values": values,
        "reason": reason,
    }


def _read_ohlcv(
    db_path: Path,
    ticker: str,
    *,
    table: str,
    provider: str | None = None,
    as_of: str | None = None,
) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    where = ["ticker = ?"]
    params: list[Any] = [ticker]
    if provider is not None:
        where.append("provider = ?")
        params.append(provider)
    if as_of is not None:
        where.append("dt <= ?")
        params.append(as_of)
    sql = (
        f"SELECT dt, open, high, low, close, volume FROM {table} "
        f"WHERE {' AND '.join(where)} AND close IS NOT NULL ORDER BY dt"
    )
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(sql, params).fetchdf()
    finally:
        con.close()
    if df.empty:
        return df
    df["dt"] = pd.to_datetime(df["dt"])
    return df.set_index("dt").sort_index()


def _close_series(
    db_path: Path,
    ticker: str,
    *,
    table: str = "external_market_ohlcv",
    provider: str | None = "yfinance",
    as_of: str | None = None,
) -> pd.Series:
    df = _read_ohlcv(db_path, ticker, table=table, provider=provider, as_of=as_of)
    if df.empty:
        return pd.Series(dtype=float, name=ticker)
    return df["close"].astype(float).rename(ticker)


def _first_close_series(
    db_path: Path,
    tickers: list[str],
    *,
    table: str = "external_market_ohlcv",
    provider: str | None = "yfinance",
    as_of: str | None = None,
) -> tuple[str | None, pd.Series]:
    for ticker in tickers:
        close = _close_series(db_path, ticker, table=table, provider=provider, as_of=as_of)
        if not close.empty:
            return ticker, close
    return None, pd.Series(dtype=float)


def _pct_change_at(series: pd.Series, periods: int) -> float | None:
    s = series.dropna()
    if len(s) <= periods:
        return None
    prev = float(s.iloc[-1 - periods])
    if prev == 0:
        return None
    return float(s.iloc[-1] / prev - 1.0)


def _latest_date(series: pd.Series) -> str | None:
    s = series.dropna()
    return str(s.index[-1].date()) if not s.empty else None


def _load_latest_ncf_2330(project_root: Path = PROJECT_ROOT) -> dict[str, Any] | None:
    candidates = sorted((project_root / "results").glob("ncf_2330*.json"), key=lambda p: p.stat().st_mtime)
    for path in reversed(candidates):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("ticker") == "2330.TW":
            payload["_path"] = str(path)
            return payload
    return None


def _fundamental_layer(results_dir: Path, as_of: str | None) -> dict[str, Any]:
    path = results_dir / "finmind_2330_monthly_revenue_cache.csv"
    if not path.exists():
        return _status(
            "missing_source",
            "neutral",
            {"missing": ["monthly_revenue", "gross_margin", "eps"]},
            "monthly revenue cache is missing; gross margin and EPS sources are not configured",
        )
    rev = pd.read_csv(path, parse_dates=["date"])
    if as_of is not None:
        rev = rev[rev["date"] <= pd.Timestamp(as_of)]
    rev = rev.sort_values("date")
    if rev.empty or "revenue" not in rev:
        return _status("missing_source", "neutral", {}, "monthly revenue cache has no usable rows")
    rev["revenue_yoy"] = rev["revenue"].pct_change(12)
    rev["revenue_qoq_proxy"] = rev["revenue"].pct_change(3)
    rev["revenue_yoy_accel"] = rev["revenue_yoy"].diff()
    latest = rev.iloc[-1]
    yoy = _round(latest.get("revenue_yoy"))
    qoq = _round(latest.get("revenue_qoq_proxy"))
    accel = _round(latest.get("revenue_yoy_accel"))
    if yoy is not None and yoy > 0.10 and (accel is None or accel >= -0.03):
        signal = "bullish"
        reason = "monthly revenue YoY remains above 10% and growth is not materially decelerating"
    elif yoy is not None and yoy < 0:
        signal = "bearish"
        reason = "monthly revenue YoY is negative"
    else:
        signal = "neutral"
        reason = "monthly revenue growth is positive but not strong enough for a clear growth-continuation signal"
    return _status(
        "available_partial",
        signal,
        {
            "latest_revenue_month": str(latest["date"].date()),
            "revenue": _round(latest["revenue"], 0),
            "revenue_yoy": yoy,
            "revenue_qoq_proxy_3m": qoq,
            "revenue_yoy_accel": accel,
            "gross_margin": None,
            "eps": None,
            "missing": ["gross_margin", "eps"],
        },
        reason,
    )


def _valuation_layer(db_path: Path, as_of: str | None) -> dict[str, Any]:
    if not db_path.exists():
        return _status(
            "missing_source",
            "neutral",
            {"pe": None, "forward_pe": None, "pb": None, "missing": ["pe", "forward_pe", "pb"]},
            "valuation database is missing",
        )
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = {row[0] for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
            if "stock_per_data" not in tables:
                raise RuntimeError("missing stock_per_data")
            where = ["ticker = '2330.TW'"]
            params: list[Any] = []
            if as_of is not None:
                where.append("dt <= ?")
                params.append(as_of)
            frame = con.execute(
                f"""
                SELECT dt, dividend_yield, per, pbr
                FROM stock_per_data
                WHERE {' AND '.join(where)}
                ORDER BY dt
                """,
                params,
            ).fetchdf()
        finally:
            con.close()
    except Exception:
        return _status(
            "missing_source",
            "neutral",
            {"pe": None, "forward_pe": None, "pb": None, "missing": ["pe", "forward_pe", "pb"]},
            "stock_per_data is not available; run FinMind TaiwanStockPER refresh first",
        )
    if frame.empty:
        return _status(
            "missing_source",
            "neutral",
            {"pe": None, "forward_pe": None, "pb": None, "missing": ["pe", "forward_pe", "pb"]},
            "stock_per_data has no 2330.TW rows",
        )
    frame["dt"] = pd.to_datetime(frame["dt"])
    latest = frame.iloc[-1]
    pe = _round(latest.get("per"), 4)
    pbr = _round(latest.get("pbr"), 4)
    dividend_yield = _round(latest.get("dividend_yield"), 4)
    if pe is not None and pbr is not None and pe >= 35 and pbr >= 8:
        signal = "bearish"
        reason = "PE and PBR are both elevated; valuation is overheated"
    elif pe is not None and pe <= 20 and pbr is not None and pbr <= 5:
        signal = "bullish"
        reason = "PE and PBR are not stretched"
    else:
        signal = "neutral"
        reason = "valuation is not cheap, but not extreme enough for an overheating veto"
    return _status(
        "available_partial",
        signal,
        {
            "date": str(latest["dt"].date()),
            "pe": pe,
            "forward_pe": None,
            "pb": pbr,
            "dividend_yield": dividend_yield,
            "missing": ["forward_pe"],
        },
        reason,
    )


def _technical_layer(db_path: Path, as_of: str | None) -> dict[str, Any]:
    close = _close_series(db_path, "2330.TW", as_of=as_of)
    if close.empty:
        return _status("missing_source", "neutral", {}, "2330.TW OHLCV is missing")
    last = float(close.iloc[-1])
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    ma120 = close.rolling(120).mean().iloc[-1]
    prior_high_60 = close.iloc[:-1].tail(60).max() if len(close) > 60 else None
    above_all = last > ma20 > ma60 > ma120
    below_60 = last < ma60
    if above_all and prior_high_60 is not None and last >= float(prior_high_60) * 0.98:
        signal = "bullish"
        reason = "price is above 20/60/120MA and remains near the recent high"
    elif below_60:
        signal = "bearish"
        reason = "price has broken below 60MA"
    else:
        signal = "neutral"
        reason = "trend is intact but not a clean leadership breakout"
    return _status(
        "available",
        signal,
        {
            "date": _latest_date(close),
            "close": _round(last, 4),
            "ma20": _round(ma20, 4),
            "ma60": _round(ma60, 4),
            "ma120": _round(ma120, 4),
            "prior_60d_high": _round(prior_high_60, 4),
            "close_vs_ma20": _round(last / ma20 - 1.0) if ma20 else None,
            "close_vs_ma60": _round(last / ma60 - 1.0) if ma60 else None,
            "close_vs_ma120": _round(last / ma120 - 1.0) if ma120 else None,
        },
        reason,
    )


def _adr_layer(db_path: Path, as_of: str | None) -> dict[str, Any]:
    tsm = _close_series(db_path, "TSM", as_of=as_of)
    fx = _close_series(db_path, "TWD=X", as_of=as_of)
    tsmc = _close_series(db_path, "2330.TW", as_of=as_of)
    if tsm.empty or fx.empty or tsmc.empty:
        return _status("missing_source", "neutral", {}, "TSM ADR, USD/TWD, or 2330.TW price cache is missing")
    latest_date = min(tsm.index[-1], fx.index[-1], tsmc.index[-1])
    tsm_latest = float(tsm.loc[:latest_date].iloc[-1])
    fx_latest = float(fx.loc[:latest_date].iloc[-1])
    tsmc_latest = float(tsmc.loc[:latest_date].iloc[-1])
    implied_twd_per_share = tsm_latest * fx_latest / TSMC_ADR_RATIO
    premium = implied_twd_per_share / tsmc_latest - 1.0
    adr_1d = _pct_change_at(tsm, 1)
    fx_1d = _pct_change_at(fx, 1)
    fx_adjusted_adr_1d = (adr_1d or 0.0) + (fx_1d or 0.0)
    if fx_adjusted_adr_1d >= 0.015 and premium >= -0.02:
        signal = "bullish"
        reason = "ADR FX-adjusted return implies positive next-session pressure"
    elif fx_adjusted_adr_1d <= -0.015 or premium <= -0.05:
        signal = "bearish"
        reason = "ADR FX-adjusted return or discount implies next-session pressure"
    else:
        signal = "neutral"
        reason = "ADR signal is not large enough to imply clear opening pressure"
    return _status(
        "available",
        signal,
        {
            "date": str(pd.Timestamp(latest_date).date()),
            "tsm_adr_close_usd": _round(tsm_latest, 4),
            "usdtwd": _round(fx_latest, 4),
            "tsmc_close_twd": _round(tsmc_latest, 4),
            "implied_twd_per_share": _round(implied_twd_per_share, 4),
            "adr_premium_discount": _round(premium),
            "adr_1d_return": _round(adr_1d),
            "usdtwd_1d_change": _round(fx_1d),
            "fx_adjusted_adr_1d_return": _round(fx_adjusted_adr_1d),
        },
        reason,
    )


def _global_semiconductor_layer(db_path: Path, as_of: str | None) -> dict[str, Any]:
    tickers = {"SOXX": "SOX/SOXX proxy", "NVDA": "NVDA", "AMD": "AMD", "ASML": "ASML"}
    values: dict[str, Any] = {}
    missing: list[str] = []
    available_returns: list[float] = []
    for ticker, label in tickers.items():
        close = _close_series(db_path, ticker, as_of=as_of)
        ret_5d = _pct_change_at(close, 5) if not close.empty else None
        values[label] = {"date": _latest_date(close), "return_5d": _round(ret_5d)}
        if ret_5d is None:
            missing.append(ticker)
        else:
            available_returns.append(ret_5d)
    if not available_returns:
        return _status("missing_source", "neutral", {**values, "missing": missing}, "global semiconductor price caches are missing")
    avg_5d = sum(available_returns) / len(available_returns)
    if avg_5d >= 0.03:
        signal = "bullish"
        reason = "available global semiconductor proxies have positive 5d momentum"
    elif avg_5d <= -0.03:
        signal = "bearish"
        reason = "available global semiconductor proxies have negative 5d momentum"
    else:
        signal = "neutral"
        reason = "global semiconductor proxy momentum is mixed or flat"
    return _status(
        "available_partial" if missing else "available",
        signal,
        {**values, "average_available_5d_return": _round(avg_5d), "missing": missing},
        reason,
    )


def _fx_layer(db_path: Path, as_of: str | None) -> dict[str, Any]:
    usdtwd = _close_series(db_path, "TWD=X", as_of=as_of)
    dxy_ticker, dxy = _first_close_series(db_path, ["DX-Y.NYB", "DX=F", "DXY"], as_of=as_of)
    if usdtwd.empty:
        return _status("missing_source", "neutral", {"missing": ["TWD=X", "DXY"]}, "USD/TWD cache is missing")
    change_5d = _pct_change_at(usdtwd, 5)
    change_20d = _pct_change_at(usdtwd, 20)
    dxy_change_5d = _pct_change_at(dxy, 5) if not dxy.empty else None
    # TWD=X rises when USD strengthens vs TWD, usually pressure for Taiwan equity flows.
    if (change_5d is not None and change_5d >= 0.01) or (dxy_change_5d is not None and dxy_change_5d >= 0.015):
        signal = "bearish"
        reason = "USD/TWD or DXY rose enough to imply FX pressure"
    elif (change_5d is not None and change_5d <= -0.01) and (dxy_change_5d is None or dxy_change_5d <= 0.0):
        signal = "bullish"
        reason = "TWD strengthened and DXY is not rising, easing FX pressure"
    else:
        signal = "neutral"
        reason = "USD/TWD and DXY moves are not large enough for a clear FX pressure signal"
    missing = [] if dxy_ticker else ["DXY"]
    return _status(
        "available" if dxy_ticker else "available_partial",
        signal,
        {
            "date": _latest_date(usdtwd),
            "usdtwd": _round(usdtwd.dropna().iloc[-1], 4),
            "usdtwd_5d_change": _round(change_5d),
            "usdtwd_20d_change": _round(change_20d),
            "dxy_ticker": dxy_ticker,
            "dxy_date": _latest_date(dxy),
            "dxy": _round(dxy.dropna().iloc[-1], 4) if not dxy.empty else None,
            "dxy_5d_change": _round(dxy_change_5d),
            "missing": missing,
        },
        reason,
    )


def _chip_layer(results_dir: Path, as_of: str | None) -> dict[str, Any]:
    inst_path = results_dir / "finmind_2330_institutional_buysell_cache.csv"
    share_path = results_dir / "finmind_2330_shareholding_cache.csv"
    if not inst_path.exists():
        return _status("missing_source", "neutral", {}, "institutional buy/sell cache is missing")
    inst = pd.read_csv(inst_path, parse_dates=["date"])
    if as_of is not None:
        inst = inst[inst["date"] <= pd.Timestamp(as_of)]
    if inst.empty:
        return _status("missing_source", "neutral", {}, "institutional buy/sell cache has no usable rows")
    inst["net"] = pd.to_numeric(inst["buy"], errors="coerce") - pd.to_numeric(inst["sell"], errors="coerce")
    piv = inst.pivot_table(index="date", columns="name", values="net", aggfunc="sum").sort_index()
    foreign = piv.get("Foreign_Investor", pd.Series(0.0, index=piv.index)) + piv.get(
        "Foreign_Dealer_Self",
        pd.Series(0.0, index=piv.index),
    )
    trust = piv.get("Investment_Trust", pd.Series(0.0, index=piv.index))
    dealer = piv.get("Dealer", pd.Series(0.0, index=piv.index))
    total = foreign + trust + dealer
    latest_date = foreign.index[-1]
    foreign_5d = float(foreign.tail(5).sum())
    trust_5d = float(trust.tail(5).sum())
    dealer_5d = float(dealer.tail(5).sum())
    total_5d = float(total.tail(5).sum())
    foreign_holding_ratio = None
    if share_path.exists():
        share = pd.read_csv(share_path, parse_dates=["date"])
        if as_of is not None:
            share = share[share["date"] <= pd.Timestamp(as_of)]
        if not share.empty and "ForeignInvestmentSharesRatio" in share:
            foreign_holding_ratio = float(share.sort_values("date")["ForeignInvestmentSharesRatio"].iloc[-1])
    if total_5d > 0 and foreign_5d > 0:
        signal = "bullish"
        reason = "foreign investors and total institutions are net buyers over 5 sessions"
    elif total_5d < 0 and foreign_5d < 0:
        signal = "bearish"
        reason = "foreign investors and total institutions are net sellers over 5 sessions"
    else:
        signal = "neutral"
        reason = "institutional flows are mixed"
    return _status(
        "available",
        signal,
        {
            "date": str(latest_date.date()),
            "foreign_net_1d_shares": _round(foreign.iloc[-1], 0),
            "foreign_net_5d_shares": _round(foreign_5d, 0),
            "investment_trust_net_5d_shares": _round(trust_5d, 0),
            "dealer_net_5d_shares": _round(dealer_5d, 0),
            "institutional_total_net_5d_shares": _round(total_5d, 0),
            "foreign_holding_ratio": _round(foreign_holding_ratio, 4),
        },
        reason,
    )


def _relation_0050_layer(db_path: Path, as_of: str | None) -> dict[str, Any]:
    tsmc = _close_series(db_path, "2330.TW", as_of=as_of)
    etf50 = _close_series(db_path, "0050.TW", table="ohlcv", provider=None, as_of=as_of)
    if tsmc.empty or etf50.empty:
        return _status("missing_source", "neutral", {}, "2330.TW or 0050.TW price history is missing")
    ret_2330_5d = _pct_change_at(tsmc, 5)
    ret_0050_5d = _pct_change_at(etf50, 5)
    ret_2330_20d = _pct_change_at(tsmc, 20)
    ret_0050_20d = _pct_change_at(etf50, 20)
    ex_5d = None
    ex_20d = None
    if ret_2330_5d is not None and ret_0050_5d is not None:
        ex_5d = (ret_0050_5d - TSMC_0050_WEIGHT_ASSUMPTION * ret_2330_5d) / (1.0 - TSMC_0050_WEIGHT_ASSUMPTION)
    if ret_2330_20d is not None and ret_0050_20d is not None:
        ex_20d = (ret_0050_20d - TSMC_0050_WEIGHT_ASSUMPTION * ret_2330_20d) / (1.0 - TSMC_0050_WEIGHT_ASSUMPTION)
    if ret_2330_5d is not None and ret_0050_5d is not None and ex_5d is not None and min(ret_2330_5d, ret_0050_5d, ex_5d) > 0:
        signal = "bullish"
        reason = "TSMC, 0050, and 0050 ex-TSMC proxy are all positive over 5 sessions"
    elif ret_2330_5d is not None and ex_5d is not None and ret_2330_5d > 0 and ex_5d <= 0:
        signal = "neutral"
        reason = "TSMC is leading narrowly while 0050 ex-TSMC proxy is weak"
    elif ret_2330_5d is not None and ret_2330_5d < -0.02 and ex_5d is not None and ex_5d <= 0:
        signal = "bearish"
        reason = "TSMC and 0050 ex-TSMC proxy are both weak"
    else:
        signal = "neutral"
        reason = "TSMC and 0050 breadth relationship is mixed"
    return _status(
        "available",
        signal,
        {
            "date_2330": _latest_date(tsmc),
            "date_0050": _latest_date(etf50),
            "tsmc_weight_assumption": TSMC_0050_WEIGHT_ASSUMPTION,
            "ret_2330_5d": _round(ret_2330_5d),
            "ret_0050_5d": _round(ret_0050_5d),
            "ret_0050_ex_tsmc_proxy_5d": _round(ex_5d),
            "ret_2330_20d": _round(ret_2330_20d),
            "ret_0050_20d": _round(ret_0050_20d),
            "ret_0050_ex_tsmc_proxy_20d": _round(ex_20d),
        },
        reason,
    )


def _ncf_layer(project_root: Path) -> dict[str, Any]:
    payload = _load_latest_ncf_2330(project_root)
    if payload is None:
        return _status("missing_source", "neutral", {}, "latest ncf_2330 JSON is missing")
    state = payload.get("tsmc_market_state") or {}
    h20 = ((payload.get("horizons") or {}).get("20") or {}).get("classification") or {}
    severe = payload.get("forward_severe_drawdown_risk") or {}
    return _status(
        "available",
        "bullish" if state.get("state") == 1 else "bearish" if state.get("state") == 5 else "neutral",
        {
            "source": payload.get("_path"),
            "date": payload.get("last_close_date"),
            "state": state,
            "h20_probability_up": _round(h20.get("probability_up")),
            "prob_fwd_mdd_gt8_h20": _round(severe.get("probability")) if severe.get("available") else None,
        },
        f"ncf_2330 market state is {state.get('label_zh', 'unavailable')}",
    )


def _num(values: dict[str, Any], key: str) -> float | None:
    value = values.get(key)
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _factor_quality_overlay(layers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Research overlay from the highest-IC checklist factors.

    This is intentionally rule-based and conservative. The factor-quality
    evaluator ranks which fields have historical explanatory power, while this
    overlay only turns the stable, interpretable fields into diagnostics.
    """
    components: dict[str, dict[str, Any]] = {}
    risk_score = 0.0
    opportunity_score = 0.0

    technical = (layers.get("technical") or {}).get("values") or {}
    close_vs_ma60 = _num(technical, "close_vs_ma60")
    close_vs_ma120 = _num(technical, "close_vs_ma120")
    tech_points = 0.0
    tech_reason = "technical extension is not extreme"
    if close_vs_ma60 is not None and close_vs_ma60 < 0:
        tech_points += 2.0
        tech_reason = "price is below 60MA"
    elif close_vs_ma60 is not None and close_vs_ma60 >= 0.12:
        tech_points += 2.0
        tech_reason = "price is extended more than 12% above 60MA"
    elif close_vs_ma60 is not None and close_vs_ma60 >= 0.08:
        tech_points += 1.0
        tech_reason = "price is extended more than 8% above 60MA"
    if close_vs_ma120 is not None and close_vs_ma120 >= 0.18:
        tech_points += 1.0
        tech_reason += "; price is extended versus 120MA"
    if (
        close_vs_ma60 is not None
        and close_vs_ma120 is not None
        and 0.0 <= close_vs_ma60 <= 0.04
        and close_vs_ma120 > 0
    ):
        opportunity_score += 1.0
    risk_score += tech_points
    components["technical_extension"] = {
        "risk_points": _round(tech_points, 2),
        "opportunity_points": 1.0 if close_vs_ma60 is not None and close_vs_ma120 is not None and 0.0 <= close_vs_ma60 <= 0.04 and close_vs_ma120 > 0 else 0.0,
        "close_vs_ma60": _round(close_vs_ma60),
        "close_vs_ma120": _round(close_vs_ma120),
        "reason": tech_reason,
    }

    valuation = (layers.get("valuation") or {}).get("values") or {}
    pe = _num(valuation, "pe")
    pb = _num(valuation, "pb")
    valuation_points = 0.0
    valuation_opp = 0.0
    valuation_reason = "valuation is not at an overlay threshold"
    if pe is not None and pe >= 35:
        valuation_points += 1.0
    elif pe is not None and pe <= 20:
        valuation_opp += 1.0
    if pb is not None and pb >= 8:
        valuation_points += 1.0
    elif pb is not None and pb <= 5:
        valuation_opp += 1.0
    if valuation_points:
        valuation_reason = "PE/PB are in historically riskier zones"
    elif valuation_opp:
        valuation_reason = "PE/PB are not stretched"
    risk_score += valuation_points
    opportunity_score += valuation_opp
    components["valuation_heat"] = {
        "risk_points": _round(valuation_points, 2),
        "opportunity_points": _round(valuation_opp, 2),
        "pe": _round(pe, 4),
        "pb": _round(pb, 4),
        "reason": valuation_reason,
    }

    fx = (layers.get("fx") or {}).get("values") or {}
    usdtwd_5d = _num(fx, "usdtwd_5d_change")
    dxy_5d = _num(fx, "dxy_5d_change")
    fx_points = 0.0
    fx_opp = 0.0
    fx_reason = "FX pressure is not at an overlay threshold"
    if dxy_5d is not None and dxy_5d >= 0.01:
        fx_points += 1.0
    if usdtwd_5d is not None and usdtwd_5d >= 0.005:
        fx_points += 1.0
    if dxy_5d is not None and dxy_5d <= -0.005 and (usdtwd_5d is None or usdtwd_5d <= 0):
        fx_opp += 1.0
    if fx_points:
        fx_reason = "USD/TWD or DXY is rising enough to add tail-risk pressure"
    elif fx_opp:
        fx_reason = "DXY is easing and USD/TWD is not rising"
    risk_score += fx_points
    opportunity_score += fx_opp
    components["fx_tail_pressure"] = {
        "risk_points": _round(fx_points, 2),
        "opportunity_points": _round(fx_opp, 2),
        "usdtwd_5d_change": _round(usdtwd_5d),
        "dxy_5d_change": _round(dxy_5d),
        "reason": fx_reason,
    }

    chip = (layers.get("chip") or {}).get("values") or {}
    trust_5d = _num(chip, "investment_trust_net_5d_shares")
    foreign_5d = _num(chip, "foreign_net_5d_shares")
    chip_points = 0.0
    chip_opp = 0.0
    chip_reason = "chip flow is not at an overlay threshold"
    if trust_5d is not None and trust_5d > 0:
        chip_points += 1.0
        chip_reason = "investment trust 5d net buying is treated as possible crowding, not a pure bullish input"
    if foreign_5d is not None and foreign_5d < 0:
        chip_points += 1.0
        chip_reason = "foreign investors are net sellers"
    elif foreign_5d is not None and foreign_5d > 0 and (trust_5d is None or trust_5d <= 0):
        chip_opp += 1.0
        chip_reason = "foreign investors are net buyers without investment-trust crowding"
    risk_score += chip_points
    opportunity_score += chip_opp
    components["chip_crowding"] = {
        "risk_points": _round(chip_points, 2),
        "opportunity_points": _round(chip_opp, 2),
        "foreign_net_5d_shares": _round(foreign_5d, 0),
        "investment_trust_net_5d_shares": _round(trust_5d, 0),
        "reason": chip_reason,
    }

    fundamental = (layers.get("fundamental") or {}).get("values") or {}
    revenue_yoy = _num(fundamental, "revenue_yoy")
    revenue_accel = _num(fundamental, "revenue_yoy_accel")
    fundamental_points = 0.0
    fundamental_opp = 0.0
    fundamental_reason = "fundamental growth is not at an overlay threshold"
    if revenue_yoy is not None and revenue_yoy < 0:
        fundamental_points += 1.0
        fundamental_reason = "monthly revenue YoY is negative"
    elif revenue_yoy is not None and revenue_yoy >= 0.10 and (revenue_accel is None or revenue_accel >= -0.03):
        fundamental_opp += 1.0
        fundamental_reason = "monthly revenue growth remains strong without material deceleration"
    risk_score += fundamental_points
    opportunity_score += fundamental_opp
    components["fundamental_growth"] = {
        "risk_points": _round(fundamental_points, 2),
        "opportunity_points": _round(fundamental_opp, 2),
        "revenue_yoy": _round(revenue_yoy),
        "revenue_yoy_accel": _round(revenue_accel),
        "reason": fundamental_reason,
    }

    net_score = opportunity_score - risk_score
    if risk_score >= 4 and net_score <= -3:
        signal = "bearish"
        label = "risk_off"
        reason = "factor-quality overlay has clustered risk from high-IC checklist fields"
    elif opportunity_score >= 3 and risk_score <= 2:
        signal = "bullish"
        label = "constructive"
        reason = "factor-quality overlay has enough constructive fields without clustered risk"
    else:
        signal = "neutral"
        label = "mixed"
        reason = "factor-quality overlay is mixed; keep it diagnostic"
    return {
        "status": "research_only",
        "signal": signal,
        "label": label,
        "risk_score": _round(risk_score, 2),
        "opportunity_score": _round(opportunity_score, 2),
        "net_score": _round(net_score, 2),
        "components": components,
        "source": "evaluate_ncf_2330_checklist_factor_quality.py",
        "reason": reason,
    }


def build_checklist(
    *,
    db_path: Path = DEFAULT_DB,
    results_dir: Path = RESULTS_DIR,
    project_root: Path = PROJECT_ROOT,
    mode: str = "daily",
    as_of: str | None = None,
) -> dict[str, Any]:
    layers = {
        "fundamental": _fundamental_layer(results_dir, as_of),
        "valuation": _valuation_layer(db_path, as_of),
        "technical": _technical_layer(db_path, as_of),
        "adr": _adr_layer(db_path, as_of),
        "global_semiconductor": _global_semiconductor_layer(db_path, as_of),
        "fx": _fx_layer(db_path, as_of),
        "chip": _chip_layer(results_dir, as_of),
        "relation_0050": _relation_0050_layer(db_path, as_of),
        "ncf_2330": _ncf_layer(project_root),
    }
    scored = [
        SIGNAL_SCORE[layer["signal"]]
        for layer in layers.values()
        if layer["status"] != "missing_source" and layer["signal"] in SIGNAL_SCORE
    ]
    total_score = sum(scored)
    if total_score >= 3:
        overall = "bullish"
    elif total_score <= -2:
        overall = "bearish"
    else:
        overall = "neutral"
    factor_quality_overlay = _factor_quality_overlay(layers)
    return {
        "schema_version": 1,
        "report": "ncf_2330_checklist",
        "mode": mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "diagnostic_only_no_weight_change",
        "overall_signal": overall,
        "available_layer_score": total_score,
        "available_layer_count": len(scored),
        "factor_quality_overlay": factor_quality_overlay,
        "layers": layers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD cutoff date")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = build_checklist(
        db_path=args.db_path,
        results_dir=args.results_dir,
        project_root=PROJECT_ROOT,
        mode=args.mode,
        as_of=args.as_of,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {args.output}")
    print(
        f"overall={report['overall_signal']} "
        f"score={report['available_layer_score']} "
        f"available_layers={report['available_layer_count']}"
    )


if __name__ == "__main__":
    main()
