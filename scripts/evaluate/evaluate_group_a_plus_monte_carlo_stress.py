#!/usr/bin/env python3
"""Monte Carlo stress report for the latest Group A+ target weights.

This is a reporting-only tool.  It does not change live allocation logic.
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

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_monte_carlo_stress_latest.json"


def _unwrap_standard_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def load_live_signal(path: Path) -> dict[str, Any]:
    return _unwrap_standard_payload(json.loads(path.read_text(encoding="utf-8")))


def target_weights_from_signal(signal: dict[str, Any]) -> dict[str, float]:
    weights = signal.get("target_weights")
    if not isinstance(weights, dict):
        raise ValueError("Live signal is missing target_weights")
    parsed = {str(k): float(v or 0.0) for k, v in weights.items()}
    for ticker in TICKERS:
        parsed.setdefault(ticker, 0.0)
    parsed.setdefault("cash", max(0.0, 1.0 - sum(parsed.get(ticker, 0.0) for ticker in TICKERS)))
    return parsed


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


def portfolio_daily_returns(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    returns = prices.astype(float).pct_change().dropna(how="any")
    if returns.empty:
        raise ValueError("Need at least two price rows to compute portfolio returns")
    weighted = pd.Series(0.0, index=returns.index, dtype=float)
    for ticker in TICKERS:
        if ticker in returns.columns:
            weighted = weighted + returns[ticker].astype(float) * float(weights.get(ticker, 0.0) or 0.0)
    return weighted.dropna()


def _max_drawdown_from_path(values: np.ndarray) -> np.ndarray:
    peaks = np.maximum.accumulate(values, axis=1)
    drawdowns = values / peaks - 1.0
    return np.min(drawdowns, axis=1)


def simulate_monte_carlo(
    daily_returns: pd.Series,
    *,
    initial_value: float,
    horizon_days: int,
    n_paths: int,
    seed: int,
) -> dict[str, Any]:
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    if n_paths <= 0:
        raise ValueError("n_paths must be positive")
    values = daily_returns.astype(float).to_numpy()
    if len(values) == 0:
        raise ValueError("daily_returns is empty")

    rng = np.random.default_rng(seed)
    sampled = rng.choice(values, size=(n_paths, horizon_days), replace=True)
    path_values = initial_value * np.cumprod(1.0 + sampled, axis=1)
    terminal = path_values[:, -1]
    path_returns = terminal / initial_value - 1.0
    path_mdd = _max_drawdown_from_path(path_values)

    quantiles = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    terminal_quantiles = {f"p{int(q * 100):02d}": float(np.quantile(terminal, q)) for q in quantiles}
    return_quantiles = {f"p{int(q * 100):02d}": float(np.quantile(path_returns, q)) for q in quantiles}
    mdd_quantiles = {f"p{int(q * 100):02d}": float(np.quantile(path_mdd, q)) for q in quantiles}

    return {
        "initial_value": float(initial_value),
        "horizon_days": int(horizon_days),
        "n_paths": int(n_paths),
        "seed": int(seed),
        "terminal_value": {
            "mean": float(np.mean(terminal)),
            "median": float(np.median(terminal)),
            "quantiles": terminal_quantiles,
        },
        "path_return": {
            "mean": float(np.mean(path_returns)),
            "median": float(np.median(path_returns)),
            "quantiles": return_quantiles,
            "prob_loss": float(np.mean(path_returns < 0.0)),
            "prob_loss_gt_5pct": float(np.mean(path_returns <= -0.05)),
            "prob_gain_gt_5pct": float(np.mean(path_returns >= 0.05)),
        },
        "max_drawdown": {
            "mean": float(np.mean(path_mdd)),
            "median": float(np.median(path_mdd)),
            "quantiles": mdd_quantiles,
            "prob_drawdown_gt_5pct": float(np.mean(path_mdd <= -0.05)),
            "prob_drawdown_gt_10pct": float(np.mean(path_mdd <= -0.10)),
        },
    }


def build_report(
    *,
    signal_path: Path,
    db_path: Path,
    start: str,
    end: str,
    horizon_days: int,
    n_paths: int,
    seed: int,
    initial_value: float | None = None,
) -> dict[str, Any]:
    signal = load_live_signal(signal_path)
    weights = target_weights_from_signal(signal)
    value = float(initial_value if initial_value is not None else signal.get("portfolio_value_input", 1_000_000.0))
    prices = load_prices(db_path, list(TICKERS), start, end)
    returns = portfolio_daily_returns(prices, weights)
    simulation = simulate_monte_carlo(
        returns,
        initial_value=value,
        horizon_days=horizon_days,
        n_paths=n_paths,
        seed=seed,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_monte_carlo_stress",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "live_signal": str(signal_path),
            "db_path": str(db_path),
            "historical_window": {
                "requested_start": start,
                "requested_end": end,
                "actual_start": str(prices.index[0].date()),
                "actual_end": str(prices.index[-1].date()),
                "price_rows": int(len(prices)),
                "return_rows": int(len(returns)),
            },
        },
        "strategy": {
            "strategy_id": signal.get("strategy_id"),
            "signal_date": signal.get("actual_data_date"),
            "execution_regime": signal.get("execution_regime"),
            "execution_allowed": bool(signal.get("execution_allowed")),
            "target_weights": weights,
        },
        "historical_daily_return": {
            "mean": float(returns.mean()),
            "volatility": float(returns.std(ddof=1)),
            "min": float(returns.min()),
            "p05": float(returns.quantile(0.05)),
            "median": float(returns.median()),
            "p95": float(returns.quantile(0.95)),
            "max": float(returns.max()),
        },
        "simulation": simulation,
        "method_note": (
            "Reporting-only bootstrap Monte Carlo. Daily portfolio returns are sampled from the "
            "historical return distribution implied by the latest target weights. Cash yield is "
            "assumed to be zero; transaction costs and regime changes are not simulated."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--horizon-days", type=int, default=20)
    parser.add_argument("--n-paths", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=2118)
    parser.add_argument("--initial-value", type=float, default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_group_a_plus_monte_carlo_stress")
    try:
        report = build_report(
            signal_path=Path(args.signal),
            db_path=Path(args.db),
            start=args.start,
            end=args.end,
            horizon_days=args.horizon_days,
            n_paths=args.n_paths,
            seed=args.seed,
            initial_value=args.initial_value,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Monte Carlo stress report: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
