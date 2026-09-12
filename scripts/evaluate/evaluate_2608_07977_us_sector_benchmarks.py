#!/usr/bin/env python3
"""Approximate benchmark replication for arXiv:2608.07977.

This script covers only price-data benchmarks that can be reproduced from
locally cached yfinance-adjusted closes: equal weight, inverse volatility, and
global minimum variance. It does not implement the paper's stochastic Riccati,
Deep-BSDE, DBDP, Heston/CIR calibration, or Black-Scholes baseline.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402


DEFAULT_TICKERS = ("SPY", "XLK", "XLF", "XLE", "XLV")
DEFAULT_WINDOWS = (
    ("table5_2020", "2015-01-02", "2019-12-31", "2020-01-02", "2020-12-31"),
    ("table6_2025", "2020-01-02", "2024-12-31", "2025-01-02", "2025-12-31"),
)


def load_external_closes(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM external_market_ohlcv
            WHERE ticker IN ({placeholders})
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No external_market_ohlcv rows for {tickers}")
    frame["dt"] = pd.to_datetime(frame["dt"])
    panel = frame.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.dropna(subset=list(tickers))


def _max_drawdown(values: pd.Series) -> tuple[float, int]:
    peak = values.cummax()
    drawdown = values / peak - 1.0
    max_dd = float(drawdown.min())
    duration = 0
    current = 0
    for value in drawdown:
        if value < 0:
            current += 1
            duration = max(duration, current)
        else:
            current = 0
    return max_dd, duration


def metrics(values: pd.Series, daily_returns: pd.Series) -> dict[str, float]:
    returns = daily_returns.dropna()
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    years = max(len(returns) / 252.0, 1e-12)
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    vol = float(returns.std(ddof=0) * math.sqrt(252.0))
    downside = returns[returns < 0.0]
    downside_dev = float(downside.std(ddof=0) * math.sqrt(252.0)) if len(downside) else 0.0
    max_dd, max_dd_duration = _max_drawdown(values)
    tail = returns.nsmallest(max(1, int(math.ceil(len(returns) * 0.05))))
    return {
        "initial_value": float(values.iloc[0]),
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": vol,
        "sharpe_ratio": annual_return / vol if vol > 0 else 0.0,
        "sortino_ratio": annual_return / downside_dev if downside_dev > 0 else 0.0,
        "calmar_ratio": annual_return / abs(max_dd) if max_dd < 0 else 0.0,
        "max_drawdown": max_dd,
        "max_drawdown_duration": int(max_dd_duration),
        "mean_expected_shortfall_5pct": float(tail.mean()) if len(tail) else 0.0,
        "worst_daily_return": float(returns.min()) if len(returns) else 0.0,
    }


def gmv_weights(cov: pd.DataFrame) -> pd.Series:
    tickers = list(cov.columns)
    inv = np.linalg.pinv(cov.to_numpy(dtype=float))
    ones = np.ones(len(tickers))
    raw = inv @ ones
    denom = float(ones @ raw)
    if abs(denom) < 1e-12:
        return pd.Series(1.0 / len(tickers), index=tickers)
    weights = pd.Series(raw / denom, index=tickers)
    weights = weights.clip(lower=0.0)
    total = float(weights.sum())
    if total <= 0.0:
        return pd.Series(1.0 / len(tickers), index=tickers)
    return weights / total


def fixed_weight_backtest(prices: pd.DataFrame, weights: pd.Series, *, initial_value: float) -> tuple[pd.Series, pd.Series]:
    weights = weights.reindex(prices.columns).fillna(0.0)
    weights = weights / weights.sum()
    returns = prices.pct_change().dropna()
    portfolio_returns = returns.dot(weights)
    values = initial_value * (1.0 + portfolio_returns).cumprod()
    values = pd.concat([pd.Series([initial_value], index=[prices.index[0]]), values])
    return values, portfolio_returns


def evaluate_window(
    prices: pd.DataFrame,
    *,
    label: str,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    initial_value: float,
) -> dict[str, Any]:
    train_prices = prices.loc[train_start:train_end]
    test_prices = prices.loc[test_start:test_end]
    if len(train_prices) < 252 or len(test_prices) < 20:
        raise RuntimeError(f"Insufficient rows for {label}")
    train_returns = train_prices.pct_change().dropna()
    vol = train_returns.std(ddof=0).replace(0.0, np.nan)
    weights = {
        "EW": pd.Series(1.0 / len(DEFAULT_TICKERS), index=DEFAULT_TICKERS),
        "IV": (1.0 / vol).dropna(),
        "GMV": gmv_weights(train_returns.cov()),
    }
    weights["IV"] = weights["IV"].reindex(DEFAULT_TICKERS).fillna(0.0)
    weights["IV"] = weights["IV"] / weights["IV"].sum()

    strategies: dict[str, Any] = {}
    for name, strategy_weights in weights.items():
        values, returns = fixed_weight_backtest(test_prices, strategy_weights, initial_value=initial_value)
        strategies[name] = {
            "weights": {ticker: float(value) for ticker, value in strategy_weights.items()},
            "metrics": metrics(values, returns),
        }
    return {
        "label": label,
        "train_window": {"start": train_start, "end": train_end, "rows": int(len(train_prices))},
        "test_window": {"start": test_start, "end": test_end, "rows": int(len(test_prices))},
        "strategies": strategies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--initial-value", type=float, default=100.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results/2608_07977_us_sector_benchmarks.json"))
    parser.add_argument("--csv-output", default=str(PROJECT_ROOT / "results/2608_07977_us_sector_benchmarks.csv"))
    args = parser.parse_args()

    tickers = tuple(item.strip() for item in args.tickers.split(",") if item.strip())
    if tickers != DEFAULT_TICKERS:
        raise ValueError(f"Only the paper benchmark ticker set is supported: {DEFAULT_TICKERS}")
    start = min(window[1] for window in DEFAULT_WINDOWS)
    end = max(window[4] for window in DEFAULT_WINDOWS)
    prices = load_external_closes(Path(args.db), tickers, start, end)
    windows = [
        evaluate_window(
            prices,
            label=label,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            initial_value=args.initial_value,
        )
        for label, train_start, train_end, test_start, test_end in DEFAULT_WINDOWS
    ]
    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_us_sector_benchmark_approximation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2608.07977",
        "coverage": {
            "reproduced": ["EW", "IV", "GMV"],
            "not_reproduced": ["MV_Deep_BSDE", "MV_DBDP", "Black_Scholes_baseline", "Heston_CIR_calibration"],
            "data_note": "Uses yfinance auto_adjust=True ETF closes cached in external_market_ohlcv; SPY proxies the S&P 500 index.",
        },
        "tickers": list(tickers),
        "windows": windows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = []
    for window in windows:
        for name, strategy in window["strategies"].items():
            row = {
                "window": window["label"],
                "strategy": name,
                **strategy["metrics"],
            }
            rows.append(row)
    csv_output = Path(args.csv_output)
    pd.DataFrame(rows).to_csv(csv_output, index=False, encoding="utf-8-sig")
    print(f"Output: {output.resolve()}")
    print(f"CSV: {csv_output.resolve()}")
    for window in windows:
        print(window["label"])
        for name, strategy in window["strategies"].items():
            m = strategy["metrics"]
            print(
                f"  {name}: return={m['total_return']:.2%} vol={m['volatility']:.2%} "
                f"sharpe={m['sharpe_ratio']:.2f} mdd={m['max_drawdown']:.2%}"
            )


if __name__ == "__main__":
    main()
