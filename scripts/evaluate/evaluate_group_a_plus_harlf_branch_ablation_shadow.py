#!/usr/bin/env python3
"""Evaluate HARLF-style market/sentiment branch ablation for Group A+.

This is a lightweight OOS shadow check inspired by arXiv:2507.18560. It does
not train an RL super-agent. It asks whether existing monthly market metrics and
monthly asset sentiment contain usable next-month allocation signal.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_SENTIMENT_PANEL = PROJECT_ROOT / "FinRL/data/sentiment/monthly_asset_sentiment_panel.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_branch_ablation_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_branch_ablation_shadow/history"
DEFAULT_TICKERS = ("0050", "00631L", "00632R", "00679B", "2330")
COMMISSION_RATE = 0.001425
SELL_TAX_RATE = 0.001
TICKER_MAP = {
    "0050": ("ohlcv", "0050.TW"),
    "00631L": ("ohlcv", "00631L.TW"),
    "00632R": ("ohlcv", "00632R.TW"),
    "00679B": ("ohlcv", "00679B.TWO"),
    "2330": ("external_market_ohlcv", "2330.TW"),
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_close(db_path: Path, tickers: tuple[str, ...]) -> pd.DataFrame:
    panels: list[pd.DataFrame] = []
    with duckdb.connect(str(db_path), read_only=True) as conn:
        for short in tickers:
            table, full = TICKER_MAP[short]
            df = conn.execute(
                f"SELECT dt, close FROM {table} WHERE ticker = ? ORDER BY dt",
                [full],
            ).fetchdf()
            if df.empty:
                continue
            df["dt"] = pd.to_datetime(df["dt"]).dt.normalize()
            panels.append(df.set_index("dt")["close"].astype(float).rename(short).to_frame())
    if not panels:
        return pd.DataFrame()
    return pd.concat(panels, axis=1).sort_index()


def _monthly_market_features(close: pd.DataFrame) -> pd.DataFrame:
    monthly_close = close.resample("ME").last()
    monthly_return = monthly_close.pct_change(fill_method=None)
    daily_return = close.pct_change(fill_method=None)
    monthly_vol = daily_return.resample("ME").std()
    rows: list[dict[str, Any]] = []
    for dt in monthly_return.index:
        month = dt.to_period("M").strftime("%Y-%m")
        for ticker in monthly_return.columns:
            rows.append(
                {
                    "month": month,
                    "ticker": ticker,
                    "market_return_1m": monthly_return.at[dt, ticker],
                    "market_volatility_1m": monthly_vol.at[dt, ticker] if ticker in monthly_vol.columns else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _load_sentiment(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["month", "ticker", "sentiment_score", "news_intensity"])
    frame = pd.read_csv(path)
    required = {"month", "ticker", "sentiment_score", "news_intensity"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"sentiment panel missing columns: {sorted(missing)}")
    frame["ticker"] = frame["ticker"].astype(str)
    frame["month"] = frame["month"].astype(str)
    return frame


def _zscore_cross_section(values: pd.Series) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    mean = clean.mean()
    std = clean.std(ddof=0)
    if not std or pd.isna(std):
        return pd.Series(0.0, index=values.index)
    return (clean - mean) / std


def _weights_from_scores(scores: pd.Series) -> pd.Series:
    clean = pd.to_numeric(scores, errors="coerce").fillna(0.0)
    shifted = clean - clean.min()
    if float(shifted.sum()) <= 0.0:
        return pd.Series(1.0 / len(clean), index=clean.index) if len(clean) else clean
    return shifted / shifted.sum()


def _portfolio_turnover_cost(prev: pd.Series | None, current: pd.Series) -> float:
    if prev is None:
        return 0.0
    aligned_prev = prev.reindex(current.index).fillna(0.0)
    delta = current - aligned_prev
    buys = float(delta.clip(lower=0.0).sum())
    sells = float((-delta.clip(upper=0.0)).sum())
    return buys * COMMISSION_RATE + sells * (COMMISSION_RATE + SELL_TAX_RATE)


def _metrics(returns: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {"n": 0}
    equity = (1.0 + clean).cumprod()
    std = float(clean.std(ddof=0))
    sharpe = float(clean.mean() / std * math.sqrt(12)) if std > 0 else 0.0
    peak = equity.cummax()
    return {
        "n": int(len(clean)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "mean_monthly_return": float(clean.mean()),
        "monthly_volatility": std,
        "annualized_sharpe": sharpe,
        "max_drawdown": float((equity / peak - 1.0).min()),
        "positive_month_rate": float((clean > 0.0).mean()),
        "worst_month": float(clean.min()),
        "best_month": float(clean.max()),
    }


def build_ablation(
    *,
    close: pd.DataFrame,
    sentiment: pd.DataFrame,
    start_month: str = "2025-01",
    end_month: str = "2026-07",
) -> dict[str, Any]:
    market = _monthly_market_features(close)
    monthly_close = close.resample("ME").last()
    next_return = monthly_close.pct_change(fill_method=None).shift(-1)
    rows: list[dict[str, Any]] = []
    merged = market.merge(sentiment, on=["month", "ticker"], how="left")
    merged["sentiment_score"] = pd.to_numeric(merged["sentiment_score"], errors="coerce").fillna(0.0)
    merged["news_intensity"] = pd.to_numeric(merged["news_intensity"], errors="coerce").fillna(0.0)
    merged = merged[(merged["month"] >= start_month) & (merged["month"] <= end_month)]

    prev_weights: dict[str, pd.Series | None] = {
        "equal_weight": None,
        "market_only": None,
        "sentiment_only": None,
        "combined": None,
    }
    for month, group in merged.groupby("month"):
        dt = pd.Period(month, freq="M").to_timestamp("M")
        available = [ticker for ticker in group["ticker"].astype(str).tolist() if ticker in next_return.columns]
        if not available or dt not in next_return.index:
            continue
        outcome = next_return.loc[dt, available].dropna()
        if outcome.empty:
            continue
        group = group.set_index("ticker").reindex(outcome.index)
        market_score = _zscore_cross_section(group["market_return_1m"]) - 0.25 * _zscore_cross_section(group["market_volatility_1m"])
        sentiment_score = _zscore_cross_section(group["sentiment_score"]) * (group["news_intensity"].fillna(0.0).clip(lower=0.0).pow(0.25))
        score_map = {
            "equal_weight": pd.Series(1.0, index=outcome.index),
            "market_only": market_score,
            "sentiment_only": sentiment_score,
            "combined": 0.5 * market_score + 0.5 * sentiment_score,
        }
        for branch, score in score_map.items():
            weights = _weights_from_scores(score.reindex(outcome.index))
            gross = float((weights * outcome).sum())
            cost = _portfolio_turnover_cost(prev_weights[branch], weights)
            prev_weights[branch] = weights
            rows.append(
                {
                    "month": month,
                    "branch": branch,
                    "gross_return": gross,
                    "turnover_cost": cost,
                    "net_return": gross - cost,
                    "assets": list(outcome.index),
                    "weights": {ticker: float(weight) for ticker, weight in weights.items()},
                }
            )

    frame = pd.DataFrame(rows)
    branch_metrics: dict[str, Any] = {}
    if not frame.empty:
        for branch, group in frame.groupby("branch"):
            branch_metrics[branch] = {
                "gross": _metrics(group["gross_return"]),
                "net": _metrics(group["net_return"]),
                "mean_turnover_cost": float(group["turnover_cost"].mean()),
                "evaluated_months": int(len(group)),
            }
    equal_net = (branch_metrics.get("equal_weight") or {}).get("net", {}).get("total_return")
    ranked = sorted(
        [
            {
                "branch": branch,
                "net_total_return": metrics["net"].get("total_return"),
                "net_sharpe": metrics["net"].get("annualized_sharpe"),
                "net_max_drawdown": metrics["net"].get("max_drawdown"),
                "beats_equal_weight_total_return": (
                    None
                    if equal_net is None or metrics["net"].get("total_return") is None
                    else metrics["net"].get("total_return") > equal_net
                ),
            }
            for branch, metrics in branch_metrics.items()
        ],
        key=lambda item: (item["net_total_return"] is not None, item["net_total_return"] or -999.0),
        reverse=True,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_branch_ablation_shadow",
        "status": "available" if branch_metrics else "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_harlf_branch_ablation_no_weight_change",
        "input_window": {"start_month": start_month, "end_month": end_month},
        "branch_metrics": branch_metrics,
        "ranked_branches": ranked,
        "branch_returns": rows,
        "rows_preview": rows[:20],
        "decision": {
            "creates_orders": False,
            "changes_target_weights": False,
            "live_harlf_super_agent_allowed": False,
            "market_only_base_agent_oos_backtest_available": "market_only" in branch_metrics,
            "sentiment_only_base_agent_oos_backtest_available": "sentiment_only" in branch_metrics,
            "combined_ablation_available": "combined" in branch_metrics,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_branch_ablation_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--sentiment-panel", default=str(DEFAULT_SENTIMENT_PANEL))
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start-month", default="2025-01")
    parser.add_argument("--end-month", default="2026-07")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = tuple(part.strip() for part in str(args.tickers).split(",") if part.strip())
    close = _load_close(_resolve(args.db), tickers)
    sentiment = _load_sentiment(_resolve(args.sentiment_panel))
    report = build_ablation(close=close, sentiment=sentiment, start_month=args.start_month, end_month=args.end_month)
    report["inputs"] = {
        "db": str(_resolve(args.db)),
        "sentiment_panel": str(_resolve(args.sentiment_panel)),
        "tickers": list(tickers),
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(json.dumps({"status": report["status"], "ranked_branches": report.get("ranked_branches"), "output": str(_resolve(args.output))}))


if __name__ == "__main__":
    main()
