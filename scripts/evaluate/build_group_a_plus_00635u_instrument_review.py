#!/usr/bin/env python3
"""Review 00635U.TW readiness for GroupA++ research/import decisions.

This is an instrument-readiness artifact only. It does not add 00635U.TW to the
live watchlist, tradable core, target weights, execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_WATCHLIST = PROJECT_ROOT / "config/group_a_plus_watchlist.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/00635u_instrument_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/00635u_instrument_review.md"
TICKERS = ("0050.TW", "00631L.TW", "00635U.TW", "00679B.TWO", "00751B.TWO", "00713.TW")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_ohlcv(db_path: Path, start: str | None, end: str | None) -> pd.DataFrame:
    clauses = ["ticker IN (SELECT * FROM UNNEST(?))"]
    params: list[Any] = [list(TICKERS)]
    if start:
        clauses.append("dt >= ?")
        params.append(start)
    if end:
        clauses.append("dt <= ?")
        params.append(end)
    query = f"""
        SELECT dt, ticker, open, high, low, close, volume
        FROM ohlcv
        WHERE {' AND '.join(clauses)}
        ORDER BY dt, ticker
    """
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(query, params).fetchdf()
    if rows.empty:
        raise RuntimeError("No OHLCV rows for 00635U instrument review")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows


def _watchlist_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "contains_00635u": False, "gold_keywords_present": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    symbols = data.get("symbols") if isinstance(data.get("symbols"), list) else []
    contains = any(row.get("symbol") == "00635U.TW" for row in symbols if isinstance(row, dict))
    text = json.dumps(data, ensure_ascii=False)
    return {
        "path": str(path),
        "exists": True,
        "contains_00635u": contains,
        "gold_keywords_present": any(key in text for key in ("黃金", "金價", "COMEX", "GSCI")),
    }


def _ticker_summary(rows: pd.DataFrame, ticker: str) -> dict[str, Any]:
    part = rows.loc[rows["ticker"] == ticker].sort_values("dt").copy()
    if part.empty:
        return {"ticker": ticker, "available": False}
    part["traded_value"] = part["close"] * part["volume"]
    part["daily_return"] = part["close"].pct_change(fill_method=None)
    latest = part.iloc[-1]
    return {
        "ticker": ticker,
        "available": True,
        "min_dt": str(part["dt"].min().date()),
        "max_dt": str(part["dt"].max().date()),
        "row_count": int(len(part)),
        "latest_close": float(latest["close"]),
        "latest_volume": int(latest["volume"]),
        "avg_volume_20": float(part["volume"].tail(20).mean()),
        "avg_volume_60": float(part["volume"].tail(60).mean()),
        "avg_traded_value_20": float(part["traded_value"].tail(20).mean()),
        "avg_traded_value_60": float(part["traded_value"].tail(60).mean()),
        "ann_vol_20": float(part["daily_return"].tail(20).std(ddof=1) * np.sqrt(252)),
        "ann_vol_60": float(part["daily_return"].tail(60).std(ddof=1) * np.sqrt(252)),
        "return_20d": float(part["close"].pct_change(20, fill_method=None).iloc[-1]),
        "return_60d": float(part["close"].pct_change(60, fill_method=None).iloc[-1]),
    }


def _correlations(rows: pd.DataFrame, window: int) -> dict[str, Any]:
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index().ffill(limit=3)
    returns = panel.pct_change(fill_method=None).tail(window)
    target = "00635U.TW"
    out: dict[str, Any] = {"window": window}
    for ticker in TICKERS:
        if ticker == target:
            continue
        pair = returns[[target, ticker]].dropna()
        out[ticker] = None if len(pair) < int(window * 0.5) else float(pair[target].corr(pair[ticker]))
    return out


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    rows = _load_ohlcv(db_path, args.start, args.end)
    summaries = {ticker: _ticker_summary(rows, ticker) for ticker in TICKERS}
    watchlist = _watchlist_state(_resolve(args.watchlist))
    target = summaries["00635U.TW"]
    liquidity_pass = bool(
        target.get("available")
        and target.get("avg_volume_20", 0.0) >= args.min_avg_volume_20
        and target.get("avg_traded_value_20", 0.0) >= args.min_avg_traded_value_20
    )
    data_pass = bool(target.get("available") and pd.Timestamp(target["max_dt"]) >= pd.Timestamp(args.required_latest_date))
    watchlist_pass = bool(watchlist["contains_00635u"] and watchlist["gold_keywords_present"])
    correlations_252 = _correlations(rows, 252)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_00635u_instrument_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_no_watchlist_change_no_orders",
        "instrument": {
            "ticker": "00635U.TW",
            "name": "元大標普高盛黃金ER指數股票型期貨信託基金",
            "twse_category": "期貨ETF",
            "benchmark": "S&P GSCI Gold Excess Return Index",
            "source_note": "Official TWSE/Yuanta pages classify 00635U as a gold futures ETF tracking S&P GSCI Gold ER.",
        },
        "inputs": {
            "db": str(db_path),
            "start": args.start,
            "end": args.end,
            "required_latest_date": args.required_latest_date,
            "min_avg_volume_20": args.min_avg_volume_20,
            "min_avg_traded_value_20": args.min_avg_traded_value_20,
        },
        "summaries": summaries,
        "correlations_252d": correlations_252,
        "watchlist_state": watchlist,
        "checks": {
            "data_latest_pass": data_pass,
            "liquidity_pass": liquidity_pass,
            "watchlist_monitoring_pass": watchlist_pass,
        },
        "decision": {
            "instrument_ready_for_live_core": False,
            "instrument_ready_for_forward_shadow": bool(data_pass and liquidity_pass),
            "allow_watchlist_add_without_user_approval": False,
            "allow_target_weight_change": False,
            "allow_order_generation": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "00635U has enough local price/liquidity data for forward shadow, but it is a futures ETF outside the current GroupA++ watchlist/tradable core; live use needs explicit instrument approval, news/monitoring coverage, and execution rules.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    inst = report["instrument"]
    target = report["summaries"]["00635U.TW"]
    checks = report["checks"]
    corr = report["correlations_252d"]
    lines = [
        "# 00635U Instrument Review",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- ticker: `{inst['ticker']}`",
        f"- name: `{inst['name']}`",
        f"- category: `{inst['twse_category']}`",
        f"- benchmark: `{inst['benchmark']}`",
        "",
        "## Local Data",
        "",
        f"- min_dt: `{target.get('min_dt')}`",
        f"- max_dt: `{target.get('max_dt')}`",
        f"- rows: `{target.get('row_count')}`",
        f"- latest_close: `{target.get('latest_close'):.4f}`",
        f"- latest_volume: `{target.get('latest_volume'):,}`",
        f"- avg_volume_20: `{target.get('avg_volume_20'):,.1f}`",
        f"- avg_traded_value_20: `{target.get('avg_traded_value_20'):,.0f}`",
        f"- ann_vol_20: `{target.get('ann_vol_20'):.2%}`",
        f"- return_20d: `{target.get('return_20d'):.2%}`",
        "",
        "## 252D Correlation",
        "",
        "| peer | corr_to_00635U |",
        "|---|---:|",
    ]
    for ticker in ("0050.TW", "00631L.TW", "00679B.TWO", "00751B.TWO", "00713.TW"):
        value = corr.get(ticker)
        lines.append(f"| {ticker} | {'' if value is None else f'{value:.4f}'} |")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            f"- data_latest_pass: `{checks['data_latest_pass']}`",
            f"- liquidity_pass: `{checks['liquidity_pass']}`",
            f"- watchlist_monitoring_pass: `{checks['watchlist_monitoring_pass']}`",
            "",
            "## Decision",
            "",
            "- Ready for forward shadow only.",
            "- Do not add to live watchlist/tradable core without explicit approval.",
            "- Do not change latest GroupA++ target weights, execution plans, or orders.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--required-latest-date", default="2026-09-10")
    parser.add_argument("--min-avg-volume-20", type=float, default=300_000.0)
    parser.add_argument("--min-avg-traded-value-20", type=float, default=10_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"00635U instrument review JSON: {output}")
    print(f"00635U instrument review Markdown: {markdown}")
    print("Decision:", json.dumps(report["decision"], ensure_ascii=False))


if __name__ == "__main__":
    main()
