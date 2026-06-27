#!/usr/bin/env python3
"""Replay GroupA+ policy signal weights for a quick decision-layer backtest."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_DECISION_POINTER = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "decision.json"
DEFAULT_ORIGINAL_SIGNAL = PROJECT_ROOT / "results" / "group_a_plus_final_signal_20260613_6p12data.json"
DEFAULT_GOLDEN_SIGNAL = PROJECT_ROOT / "results" / "signal_group_a_golden1_0531_predict_20260615_from_all_20260613_total1000000.json"
DEFAULT_LATEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "decision_backtest.json"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _load_policy_signal(pointer_path: Path) -> tuple[dict[str, Any], Path]:
    pointer = _load(pointer_path)
    signal_path = _resolve(pointer["signal_json"])
    return _load(signal_path), signal_path


def _weights_from_group_a_plus(payload: dict[str, Any]) -> dict[str, float]:
    if payload.get("policy_adjusted_weights"):
        weights = dict(payload.get("policy_adjusted_weights") or {})
        return {ticker: float(weights.get(ticker, 0.0) or 0.0) for ticker in (*TICKERS, "cash")}
    total_assets = float(payload.get("total_assets") or payload.get("current_total_portfolio_value") or 0.0)
    prices = dict(payload.get("latest_prices") or {})
    shares = dict(payload.get("target_shares") or {})
    weights = {
        ticker: float(shares.get(ticker, 0) or 0) * float(prices.get(ticker, 0.0) or 0.0) / max(total_assets, 1.0)
        for ticker in TICKERS
    }
    weights["cash"] = float((payload.get("execution_summary") or {}).get("cash_after_cost", 0.0) or 0.0) / max(total_assets, 1.0)
    return weights


def _weights_from_group_a(payload: dict[str, Any]) -> dict[str, float]:
    weights = dict(payload.get("target_weights") or payload.get("planned_target_weights") or {})
    out = {ticker: float(weights.get(ticker, 0.0) or 0.0) for ticker in TICKERS}
    out["cash"] = float(weights.get("cash", payload.get("target_cash_weight", 0.0)) or 0.0)
    return out


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    risky = {ticker: max(float(weights.get(ticker, 0.0) or 0.0), 0.0) for ticker in TICKERS}
    cash = max(float(weights.get("cash", 0.0) or 0.0), 0.0)
    total = sum(risky.values()) + cash
    if total <= 0.0:
        return {**{ticker: 0.0 for ticker in TICKERS}, "cash": 1.0}
    return {**{ticker: value / total for ticker, value in risky.items()}, "cash": cash / total}


def _load_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
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


def _curve_from_weights(prices: pd.DataFrame, weights: dict[str, float], initial_value: float) -> pd.Series:
    weights = _normalize(weights)
    first_prices = prices.iloc[0]
    values = pd.Series(initial_value * weights.get("cash", 0.0), index=prices.index, dtype=float)
    for ticker in TICKERS:
        weight = float(weights.get(ticker, 0.0) or 0.0)
        if weight <= 0.0:
            continue
        shares = initial_value * weight / float(first_prices[ticker])
        values = values + prices[ticker].astype(float) * shares
    return values


def _metrics(values: pd.Series, initial_value: float) -> dict[str, Any]:
    returns = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / initial_value - 1.0)
    annual_return = float((values.iloc[-1] / initial_value) ** (1.0 / years) - 1.0)
    volatility = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    max_drawdown = float((values / values.cummax() - 1.0).min())
    return {
        "initial_value": float(initial_value),
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": volatility,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--original-signal", default=str(DEFAULT_ORIGINAL_SIGNAL))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-06-17")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LATEST))
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    original_signal_path = _resolve(args.original_signal)
    golden_signal_path = _resolve(args.golden_signal)
    original_signal = _load(original_signal_path)
    golden_signal = _load(golden_signal_path)

    variants = {
        "group_a_plus_original": _weights_from_group_a_plus(original_signal),
        "group_a_plus_policy_adjusted": _weights_from_group_a_plus(policy_signal),
        "golden1_0531_1m": _weights_from_group_a(golden_signal),
    }
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    actual_start = str(prices.index[0].date())
    actual_end = str(prices.index[-1].date())
    curves = pd.DataFrame(index=prices.index)
    for name, weights in variants.items():
        curves[name] = _curve_from_weights(prices, weights, args.initial_value)
    summary = {name: _metrics(curves[name], args.initial_value) for name in curves.columns}

    report = {
        "experiment": "group_a_plus_policy_signal_weight_replay",
        "method_note": "Static target weights are replayed over the requested window. This tests the decision-layer allocation effect, not the full dynamic PPO/overlay path.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": actual_start, "end": actual_end, "rows": int(len(prices))},
        "initial_value": float(args.initial_value),
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "original_signal": str(original_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {name: _normalize(weights) for name, weights in variants.items()},
        "summary": summary,
    }

    stamp = report["generated_at"].replace("-", "").replace(":", "").replace("T", "_")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_a_plus_policy_signal_backtest_{stamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"variant": name, **metrics} for name, metrics in summary.items()]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_path, encoding="utf-8-sig")
    latest_path = _resolve(args.latest_pointer)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "report_type": "decision_backtest",
                "generated_at": report["generated_at"],
                "json": str(json_path.relative_to(PROJECT_ROOT)),
                "csv": str(csv_path.relative_to(PROJECT_ROOT)),
                "curve_csv": str(curve_path.relative_to(PROJECT_ROOT)),
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Latest: {latest_path}")
    print(f"Window: {actual_start} ~ {actual_end} ({len(prices)} rows)")
    for name, metrics in summary.items():
        print(
            f"{name}: final={metrics['final_value']:,.0f}, return={metrics['total_return']:.2%}, "
            f"sharpe={metrics['sharpe_ratio']:.3f}, mdd={metrics['max_drawdown']:.2%}"
        )


if __name__ == "__main__":
    main()
