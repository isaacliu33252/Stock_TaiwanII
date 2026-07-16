#!/usr/bin/env python3
"""Weighted-rank factor baseline for Taiwan stock/ETF universes.

This is a research-only benchmark inspired by the book examples, adapted to
the local DuckDB data store.  It builds simple cross-sectional ranks from
price/volume and optional institutional flow data, then backtests a top-N
equal-weight portfolio with next-day execution.
"""

from __future__ import annotations

import argparse
import json
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

from FinRL.data.stock_db import DB_PATH
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_TICKERS = "0050.TW,0056.TW,00646.TW,00679B.TWO,00713.TW,00751B.TWO,00878.TW,2884.TW"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "weighted_rank_baseline_latest.json"
DEFAULT_WEIGHTS = {
    "momentum_20d": 0.30,
    "momentum_60d": 0.25,
    "volume_trend_5_20d": 0.15,
    "institutional_flow_20d": 0.30,
}


def parse_tickers(value: str) -> list[str]:
    tickers = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not tickers:
        raise ValueError("At least one ticker is required")
    return tickers


def parse_weights(value: str | None) -> dict[str, float]:
    if not value:
        return dict(DEFAULT_WEIGHTS)
    weights = json.loads(value)
    if not isinstance(weights, dict) or not weights:
        raise ValueError("--weights must be a non-empty JSON object")
    return {str(key): float(val) for key, val in weights.items()}


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    rows = con.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_name = ?
        """,
        [table_name],
    ).fetchone()
    return bool(rows and rows[0] > 0)


def load_ohlcv(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    placeholders = ",".join(["?"] * len(tickers))
    with duckdb.connect(str(db_path), read_only=True) as con:
        frame = con.execute(
            f"""
            SELECT ticker, dt AS date, open, high, low, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders})
              AND dt BETWEEN ? AND ?
            ORDER BY date, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    if frame.empty:
        raise ValueError(f"No OHLCV rows for {tickers} between {start} and {end}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values(["date", "ticker"])
    return frame.reset_index(drop=True)


def load_institutional(
    db_path: Path,
    tickers: list[str],
    start: str,
    end: str,
) -> pd.DataFrame | None:
    placeholders = ",".join(["?"] * len(tickers))
    with duckdb.connect(str(db_path), read_only=True) as con:
        if not _table_exists(con, "institutional_data"):
            return None
        frame = con.execute(
            f"""
            SELECT ticker, dt AS date, institutional_total_net_buy
            FROM institutional_data
            WHERE ticker IN ({placeholders})
              AND dt BETWEEN ? AND ?
            ORDER BY date, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    if frame.empty:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    return frame.dropna(subset=["date"]).sort_values(["date", "ticker"]).reset_index(drop=True)


def _wide(frame: pd.DataFrame, value: str) -> pd.DataFrame:
    return frame.pivot(index="date", columns="ticker", values=value).sort_index()


def build_factor_frames(
    ohlcv: pd.DataFrame,
    institutional: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    close = _wide(ohlcv, "close").ffill()
    volume = _wide(ohlcv, "volume").ffill()
    factors: dict[str, pd.DataFrame] = {
        "momentum_20d": close.pct_change(20),
        "momentum_60d": close.pct_change(60),
        "volume_trend_5_20d": volume.rolling(5, min_periods=3).mean()
        / volume.rolling(20, min_periods=10).mean()
        - 1.0,
    }
    if institutional is not None and not institutional.empty:
        inst = _wide(institutional, "institutional_total_net_buy").reindex(close.index).fillna(0.0)
        vol20 = volume.rolling(20, min_periods=5).sum().replace(0.0, np.nan)
        factors["institutional_flow_20d"] = inst.rolling(20, min_periods=5).sum() / vol20
    return factors


def weighted_rank_score(
    factors: dict[str, pd.DataFrame],
    weights: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, float]]:
    available = {name: weight for name, weight in weights.items() if name in factors and weight != 0}
    if not available:
        raise ValueError(f"No requested factors are available. Requested={sorted(weights)}")
    score: pd.DataFrame | None = None
    weight_sum = float(sum(abs(weight) for weight in available.values()))
    for name, weight in available.items():
        ranked = factors[name].rank(axis=1, pct=True, method="average").fillna(0.5)
        component = ranked * float(weight)
        score = component if score is None else score.add(component, fill_value=0.0)
    assert score is not None
    return score / weight_sum, available


def target_weights_from_score(
    score: pd.DataFrame,
    *,
    top_n: int,
    rebalance_days: int,
    min_score_count: int = 2,
) -> pd.DataFrame:
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    if rebalance_days < 1:
        raise ValueError("rebalance_days must be >= 1")

    weights = pd.DataFrame(np.nan, index=score.index, columns=score.columns, dtype=float)
    usable_dates = [idx for idx, row in score.iterrows() if row.notna().sum() >= min_score_count]
    for idx in usable_dates[::rebalance_days]:
        row = score.loc[idx].dropna().sort_values(ascending=False)
        selected = row.head(min(top_n, len(row))).index
        weights.loc[idx, :] = 0.0
        if len(selected) > 0:
            weights.loc[idx, selected] = 1.0 / len(selected)
    return weights.ffill().fillna(0.0)


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    return float(drawdown.min())


def summarize_returns(returns: pd.Series, *, initial_cash: float = 1_000_000.0) -> dict[str, Any]:
    returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    equity = initial_cash * (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] / initial_cash - 1.0) if len(equity) else 0.0
    years = max(len(returns) / 252.0, 1.0 / 252.0)
    annual_return = float((1.0 + total_return) ** (1.0 / years) - 1.0)
    volatility = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 and returns.std(ddof=1) > 0 else 0.0
    return {
        "final_value": float(equity.iloc[-1]) if len(equity) else initial_cash,
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": _max_drawdown(equity),
        "rows": int(len(returns)),
    }


def backtest_rank_strategy(
    close: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    cost_bps: float,
    benchmark: str | None = "0050.TW",
    initial_cash: float = 1_000_000.0,
) -> dict[str, Any]:
    close = close.ffill()
    asset_returns = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    target_weights = target_weights.reindex(asset_returns.index).fillna(0.0)

    effective_weights = target_weights.shift(1).fillna(0.0)
    gross_returns = (effective_weights * asset_returns).sum(axis=1)
    turnover = target_weights.diff().abs().sum(axis=1).fillna(target_weights.abs().sum(axis=1))
    effective_turnover = turnover.shift(1).fillna(0.0)
    net_returns = gross_returns - effective_turnover * (float(cost_bps) / 10_000.0)

    strategy = summarize_returns(net_returns, initial_cash=initial_cash)
    strategy["average_turnover"] = float(effective_turnover.mean())
    strategy["total_turnover"] = float(effective_turnover.sum())
    strategy["estimated_cost"] = float((effective_turnover * (float(cost_bps) / 10_000.0)).sum() * initial_cash)

    out: dict[str, Any] = {
        "strategy": strategy,
        "rebalance_count": int((turnover > 0).sum()),
        "last_weights": {
            str(k): float(v)
            for k, v in target_weights.iloc[-1].items()
            if float(v) > 1e-9
        },
    }
    if benchmark and benchmark in asset_returns.columns:
        out["benchmark"] = {
            "ticker": benchmark,
            **summarize_returns(asset_returns[benchmark], initial_cash=initial_cash),
        }
    out["equal_weight_universe"] = summarize_returns(asset_returns.mean(axis=1), initial_cash=initial_cash)
    return out


def build_report(
    *,
    db_path: Path,
    tickers: list[str],
    start: str,
    end: str,
    top_n: int,
    rebalance_days: int,
    cost_bps: float,
    benchmark: str | None,
    weights: dict[str, float],
) -> dict[str, Any]:
    ohlcv = load_ohlcv(db_path, tickers, start, end)
    available_tickers = sorted(str(ticker) for ticker in ohlcv["ticker"].unique())
    missing_tickers = sorted(set(tickers) - set(available_tickers))
    if len(available_tickers) < 2:
        raise ValueError(f"Need at least 2 OHLCV tickers for cross-sectional ranking, got {available_tickers}")
    institutional = load_institutional(db_path, available_tickers, start, end)
    factors = build_factor_frames(ohlcv, institutional)
    score, used_weights = weighted_rank_score(factors, weights)
    targets = target_weights_from_score(score, top_n=top_n, rebalance_days=rebalance_days)
    close = _wide(ohlcv, "close")
    result = backtest_rank_strategy(
        close,
        targets,
        cost_bps=cost_bps,
        benchmark=benchmark,
    )
    return {
        "schema_version": 1,
        "report_type": "weighted_rank_factor_baseline",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "db": str(db_path),
            "requested_tickers": tickers,
            "available_tickers": available_tickers,
            "missing_tickers": missing_tickers,
            "start": start,
            "end": end,
            "institutional_data_used": institutional is not None and not institutional.empty,
        },
        "method": {
            "top_n": top_n,
            "rebalance_days": rebalance_days,
            "cost_bps": cost_bps,
            "benchmark": benchmark,
            "requested_weights": weights,
            "used_weights": used_weights,
            "execution_lag": "signals formed on date t are applied to returns on t+1",
        },
        "factor_coverage": {
            name: {
                "rows": int(frame.shape[0]),
                "columns": int(frame.shape[1]),
                "non_null_ratio": float(frame.notna().sum().sum() / max(frame.size, 1)),
            }
            for name, frame in factors.items()
        },
        "backtest": result,
        "active_allocation_impact": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tickers", default=DEFAULT_TICKERS)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--rebalance-days", type=int, default=20)
    parser.add_argument("--cost-bps", type=float, default=14.25)
    parser.add_argument("--benchmark", default="0050.TW")
    parser.add_argument("--weights", default=None, help="JSON object mapping factor name to weight")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_weighted_rank_baseline")
    try:
        report = build_report(
            db_path=Path(args.db),
            tickers=parse_tickers(args.tickers),
            start=args.start,
            end=args.end,
            top_n=args.top_n,
            rebalance_days=args.rebalance_days,
            cost_bps=args.cost_bps,
            benchmark=args.benchmark or None,
            weights=parse_weights(args.weights),
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Weighted-rank baseline report: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
