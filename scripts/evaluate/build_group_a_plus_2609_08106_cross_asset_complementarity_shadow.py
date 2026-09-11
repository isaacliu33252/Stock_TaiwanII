#!/usr/bin/env python3
"""Build a 2609.08106-inspired cross-asset complementarity shadow."""

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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_cross_asset_complementarity_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_cross_asset_complementarity_shadow.md"
DEFAULT_TICKERS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "00679B.TWO",
    "00713.TW",
    "00751B.TWO",
    "00878.TW",
    "2330.TW",
    "TSM",
    "QQQ",
    "SOXX",
    "^TWII",
    "^GSPC",
    "^IXIC",
    "^VIX",
    "^TNX",
    "GC=F",
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_close_panel(db_path: Path, tickers: tuple[str, ...], as_of: str) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        frames: list[pd.DataFrame] = []
        placeholders = ",".join(["?"] * len(tickers))
        params: list[Any] = [*tickers, as_of]
        if "ohlcv" in tables:
            frames.append(
                con.execute(
                    f"""
                    SELECT ticker, dt, close, 'ohlcv' AS source_table
                    FROM ohlcv
                    WHERE ticker IN ({placeholders}) AND dt <= ?
                    """,
                    params,
                ).fetchdf()
            )
        if "external_market_ohlcv" in tables:
            frames.append(
                con.execute(
                    f"""
                    SELECT ticker, dt, close, 'external_market_ohlcv' AS source_table
                    FROM external_market_ohlcv
                    WHERE ticker IN ({placeholders}) AND dt <= ?
                    """,
                    params,
                ).fetchdf()
            )
    if not frames:
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True).dropna(subset=["ticker", "dt", "close"])
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    rows["_priority"] = rows["source_table"].map({"ohlcv": 0, "external_market_ohlcv": 1}).fillna(9)
    rows = rows.sort_values(["ticker", "dt", "_priority"]).drop_duplicates(["ticker", "dt"], keep="first")
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index()


def _safe_corr(a: pd.Series, b: pd.Series) -> float | None:
    paired = pd.concat([a, b], axis=1).dropna()
    if len(paired) < 20:
        return None
    value = float(paired.iloc[:, 0].corr(paired.iloc[:, 1]))
    if not np.isfinite(value):
        return None
    return value


def _zscore(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce")
    std = values.std(ddof=1)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return ((values - values.mean()) / std).fillna(0.0)


def build_shadow(
    *,
    db_path: Path,
    as_of: str,
    window: int,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = ["shadow_only_no_live_weight_change", "not_paper_equivalent_no_trained_attention"]
    close = _load_close_panel(db_path, tickers, as_of) if db_path.exists() else pd.DataFrame()
    if close.empty:
        blockers.append("close_panel_missing")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).tail(window).replace([np.inf, -np.inf], np.nan)
    usable = [ticker for ticker in returns.columns if int(returns[ticker].notna().sum()) >= max(20, int(window * 0.6))]
    returns = returns[usable] if usable else pd.DataFrame()
    if len(usable) < 6:
        blockers.append("insufficient_cross_asset_breadth")

    latest_dt = str(close.index.max().date()) if not close.empty else None
    candidates: list[dict[str, Any]] = []
    focus = ["00631L.TW", "00713.TW", "00632R.TW", "00679B.TWO", "00751B.TWO", "00878.TW"]
    if not blockers:
        ret_0050 = returns.get("0050.TW")
        ret_631 = returns.get("00631L.TW")
        vols = returns.std(ddof=1) * np.sqrt(252)
        mom_5 = close[usable].pct_change(5, fill_method=None).iloc[-1]
        mom_20 = close[usable].pct_change(20, fill_method=None).iloc[-1]
        corr_to_0050 = pd.Series({ticker: _safe_corr(returns[ticker], ret_0050) for ticker in usable}, dtype=float)
        corr_to_631 = pd.Series({ticker: _safe_corr(returns[ticker], ret_631) for ticker in usable}, dtype=float)

        # Proxy for the paper's complementarity-seeking deviation: favor lower co-movement
        # with 0050/00631L while penalizing unstable volatility and strongly negative momentum.
        score = (
            -0.45 * _zscore(corr_to_0050.abs())
            -0.30 * _zscore(corr_to_631.abs())
            -0.15 * _zscore(vols)
            +0.05 * _zscore(mom_5)
            +0.05 * _zscore(mom_20)
        )
        for ticker in focus:
            if ticker not in usable:
                continue
            candidates.append(
                {
                    "ticker": ticker,
                    "close": round(float(close[ticker].dropna().iloc[-1]), 4),
                    "corr_to_0050": round(float(corr_to_0050.get(ticker)), 6),
                    "corr_to_00631l": round(float(corr_to_631.get(ticker)), 6),
                    "ann_vol": round(float(vols.get(ticker)), 6),
                    "momentum_5d": round(float(mom_5.get(ticker)), 6),
                    "momentum_20d": round(float(mom_20.get(ticker)), 6),
                    "complementarity_score": round(float(score.get(ticker)), 6),
                }
            )
        candidates = sorted(candidates, key=lambda item: item["complementarity_score"], reverse=True)

    best = candidates[0] if candidates else None
    sleeve_reference = "neutral"
    if best:
        if best["ticker"] in {"00713.TW", "00679B.TWO", "00751B.TWO", "00878.TW"} and best["complementarity_score"] > 0:
            sleeve_reference = "defensive_complement_available"
        elif best["ticker"] == "00631L.TW":
            sleeve_reference = "risk_on_self_dominant"
        elif best["ticker"] == "00632R.TW":
            sleeve_reference = "inverse_hedge_complement_available_manual_review"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_cross_asset_complementarity_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": latest_dt,
        "policy": "shadow_only_no_orders_no_weight_change",
        "method": {
            "source_paper": "2609.08106",
            "paper_equivalent": False,
            "window_trading_days": window,
            "interpretation": "Proxy for dynamic complementarity, not a trained Nyström/Master attention model.",
            "sparse_graph_masks_allowed": False,
        },
        "coverage": {
            "requested_tickers": list(tickers),
            "usable_tickers": usable,
            "usable_ticker_count": len(usable),
            "return_observations": int(len(returns)),
        },
        "candidates": candidates,
        "latest": {
            "best_complement": best,
            "sleeve_reference": sleeve_reference,
            "allow_live_change": False,
            "allow_00631l_add_change": False,
            "allow_00713_weight_change": False,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "shadow_available": not blockers,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "keep_golden1_0531_unchanged": True,
            "keep_golden2_0830_unchanged": True,
            "next_step": "Backtest this complementarity score as a no-add/resize diagnostic before any live integration.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.08106 Cross-Asset Complementarity Shadow",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- actual_data_end: `{report['actual_data_end']}`",
        f"- policy: `{report['policy']}`",
        f"- shadow_available: `{report['decision']['shadow_available']}`",
        "",
        "| ticker | close | corr0050 | corr00631L | ann_vol | mom5 | mom20 | score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["candidates"]:
        lines.append(
            "| {ticker} | {close:.4f} | {c0050:.4f} | {c631:.4f} | {vol:.4f} | {m5:.4f} | {m20:.4f} | {score:.4f} |".format(
                ticker=item["ticker"],
                close=item["close"],
                c0050=item["corr_to_0050"],
                c631=item["corr_to_00631l"],
                vol=item["ann_vol"],
                m5=item["momentum_5d"],
                m20=item["momentum_20d"],
                score=item["complementarity_score"],
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- sleeve_reference: `{report['latest']['sleeve_reference']}`",
            "- No live weight change. No order generation.",
            "- Do not add graph/top-K sparse masks from this paper.",
            f"- Next step: {report['decision']['next_step']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-09-09")
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_shadow(db_path=_resolve(args.db), as_of=args.as_of, window=args.window)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Shadow JSON: {output}")
    print(f"Shadow Markdown: {markdown}")


if __name__ == "__main__":
    main()
