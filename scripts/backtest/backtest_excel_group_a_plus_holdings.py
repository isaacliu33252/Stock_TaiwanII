#!/usr/bin/env python3
"""Backtest an Excel-listed Group A+ holdings allocation.

The workbook is treated as a current holdings snapshot. We infer current
weights from the latest requested close and total assets, then replay those
weights over the requested backtest window.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--total-assets", type=float, required=True)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-06-05")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output-prefix", default=None)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _normalize_ticker(code: str) -> str:
    code = code.upper().strip()
    if code in {"00679B", "00751B"}:
        return f"{code}.TWO"
    return f"{code}.TW"


def _extract_code(value: object) -> str | None:
    text = "" if pd.isna(value) else str(value)
    matches = re.findall(r"\b\d{4,5}[A-Z]?\b", text.upper())
    return matches[-1] if matches else None


def load_holdings_from_xlsx(path: Path) -> dict[str, int]:
    frame = pd.read_excel(path, sheet_name=0, header=None)
    if frame.shape[0] < 2:
        raise ValueError(f"Workbook has no holdings row: {path}")
    holdings: dict[str, int] = {}
    for col_idx in range(1, frame.shape[1]):
        code = _extract_code(frame.iloc[0, col_idx])
        if code is None:
            continue
        ticker = _normalize_ticker(code)
        value = frame.iloc[1, col_idx]
        shares = 0 if pd.isna(value) else int(round(float(value)))
        holdings[ticker] = shares
    if not holdings:
        raise ValueError(f"No holdings parsed from workbook: {path}")
    return holdings


def load_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(subset=tickers)


def _metrics(values: pd.Series, initial_value: float) -> dict[str, Any]:
    returns = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / initial_value - 1.0)
    annual_return = float((values.iloc[-1] / initial_value) ** (1.0 / years) - 1.0)
    volatility = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    downside = returns[returns < 0]
    sortino = (
        float((returns.mean() / downside.std()) * math.sqrt(252))
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )
    max_drawdown = float((values / values.cummax() - 1.0).min())
    return {
        "initial_value": float(initial_value),
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": volatility,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
    }


def _curve_from_weights(prices: pd.DataFrame, weights: dict[str, float], cash_weight: float, total_assets: float) -> pd.Series:
    first_prices = prices.iloc[0]
    shares = {
        ticker: (float(total_assets) * float(weight) / float(first_prices[ticker]))
        for ticker, weight in weights.items()
        if float(weight) > 0.0
    }
    cash = float(total_assets) * float(cash_weight)
    values = pd.Series(cash, index=prices.index, dtype=float)
    for ticker, share_count in shares.items():
        values = values + prices[ticker].astype(float) * float(share_count)
    return values


def main() -> None:
    args = _parse_args()
    xlsx_path = _resolve(args.xlsx)
    db_path = _resolve(args.db)
    holdings = load_holdings_from_xlsx(xlsx_path)
    tickers = sorted(holdings)
    prices = load_prices(db_path, tickers, args.start, args.end)
    actual_start = str(prices.index[0].date())
    actual_end = str(prices.index[-1].date())
    latest_prices = prices.iloc[-1].to_dict()

    holding_values = {ticker: int(holdings[ticker]) * float(latest_prices[ticker]) for ticker in tickers}
    holdings_market_value = float(sum(holding_values.values()))
    cash_value = float(args.total_assets - holdings_market_value)
    weights = {ticker: value / float(args.total_assets) for ticker, value in holding_values.items()}
    cash_weight = cash_value / float(args.total_assets)

    curves = pd.DataFrame(index=prices.index)
    curves["excel_holdings_with_cash"] = _curve_from_weights(prices, weights, cash_weight, args.total_assets)
    normalized_total = max(sum(weights.values()), 1e-12)
    normalized_weights = {ticker: weight / normalized_total for ticker, weight in weights.items()}
    curves["excel_holdings_no_cash_normalized"] = _curve_from_weights(prices, normalized_weights, 0.0, args.total_assets)
    if "0050.TW" in tickers:
        curves["benchmark_0050_only"] = _curve_from_weights(prices, {"0050.TW": 1.0}, 0.0, args.total_assets)
    if "00679B.TWO" in tickers:
        curves["benchmark_00679b_only"] = _curve_from_weights(prices, {"00679B.TWO": 1.0}, 0.0, args.total_assets)

    summary = {
        name: _metrics(curves[name], float(args.total_assets))
        for name in curves.columns
    }
    report = {
        "experiment": "excel_group_a_plus_holdings_backtest",
        "method_note": (
            "Workbook shares are treated as a current holdings snapshot. We infer weights "
            "from the latest close inside the backtest window and total assets, then replay "
            "those weights from the first available backtest date. Cash is held constant."
        ),
        "workbook": str(xlsx_path),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": actual_start, "end": actual_end, "rows": int(len(prices))},
        "total_assets": float(args.total_assets),
        "holdings": holdings,
        "latest_prices": {ticker: float(value) for ticker, value in latest_prices.items()},
        "holding_values_at_latest_close": holding_values,
        "holdings_market_value_at_latest_close": holdings_market_value,
        "cash_value_assumed": cash_value,
        "weights_inferred_at_latest_close": weights,
        "cash_weight_assumed": cash_weight,
        "summary": summary,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_a_plus_holdings_backtest_{timestamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"variant": name, **metrics} for name, metrics in summary.items()]).to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )
    curves.to_csv(curve_path, encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Window: {actual_start} ~ {actual_end} ({len(prices)} rows)")
    print(f"Holdings market value at {actual_end}: {holdings_market_value:,.0f}")
    print(f"Assumed cash: {cash_value:,.0f} ({cash_weight:.2%})")
    for name, metrics in summary.items():
        print(
            f"{name}: final={metrics['final_value']:,.0f}, "
            f"return={metrics['total_return']:.2%}, sharpe={metrics['sharpe_ratio']:.3f}, "
            f"mdd={metrics['max_drawdown']:.2%}"
        )


if __name__ == "__main__":
    main()
