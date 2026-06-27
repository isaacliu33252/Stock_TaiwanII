#!/usr/bin/env python3
"""Simple 00631L + cash 50/50 rebalance baseline for quick comparisons."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
FINRL_DATA_ROOT = PROJECT_ROOT / "FinRL" / "data"
PORTFOLIO_CACHE_DIR = FINRL_DATA_ROOT / "portfolio_cache"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FINRL_DATA_ROOT))

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE
from stock_db import query_ohlcv
from data_utils import read_parquet_safe


DEFAULT_ASSET_TICKER = "00631L.TW"
DEFAULT_BENCHMARK_TICKER = "0050.TW"
DEFAULT_INITIAL_CASH = 1_000_000.0
DEFAULT_TARGET_WEIGHT = 0.50
DEFAULT_BACKTEST_START = "2024-01-01"
DEFAULT_BACKTEST_END = "2026-05-15"
DEFAULT_REBALANCE_FREQUENCY = "monthly"


def calculate_backtest_metrics(
    equity_curve: list[float],
    initial_value: float = DEFAULT_INITIAL_CASH,
    risk_free_rate: float = 0.02,
) -> dict:
    equity = np.asarray(equity_curve, dtype=float)
    equity = equity[np.isfinite(equity)]
    if len(equity) < 2 or initial_value <= 0:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
        }

    returns = np.diff(equity) / equity[:-1]
    returns = returns[np.isfinite(returns)]
    total_return = float(equity[-1] / initial_value - 1.0)
    years = max((len(equity) - 1) / 252.0, 1 / 252.0)
    annual_return = float((1.0 + total_return) ** (1.0 / years) - 1.0) if total_return > -1.0 else -1.0

    if len(returns) > 1:
        daily_rf = risk_free_rate / 252.0
        excess = returns - daily_rf
        std = float(np.std(excess, ddof=1))
        sharpe = float(np.mean(excess) / std * np.sqrt(252.0)) if std > 0 else 0.0
        volatility = float(np.std(returns, ddof=1) * np.sqrt(252.0))
    else:
        sharpe = 0.0
        volatility = 0.0

    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) else 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
    }


def _find_covering_portfolio_cache(
    ticker: str,
    start: str,
    end: str,
    *,
    require_full_coverage: bool = True,
) -> Path | None:
    safe_ticker = ticker.replace(".", "_")
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    pattern = re.compile(rf"^{re.escape(safe_ticker)}_(\d{{8}})_(\d{{8}})_1d_raw_v1\.parquet$")
    candidates: list[tuple[int, int, int, Path]] = []

    for path in PORTFOLIO_CACHE_DIR.glob(f"{safe_ticker}_*_1d_raw_v1.parquet"):
        match = pattern.match(path.name)
        if not match:
            continue
        cache_start = pd.Timestamp(match.group(1)).normalize()
        cache_end = pd.Timestamp(match.group(2)).normalize()
        if require_full_coverage:
            if cache_start <= start_ts and cache_end >= end_ts:
                span_days = int((cache_end - cache_start).days)
                candidates.append((span_days, -cache_end.value, 0, path))
        else:
            overlap_start = max(cache_start, start_ts)
            overlap_end = min(cache_end, end_ts)
            if overlap_end < overlap_start:
                continue
            overlap_days = int((overlap_end - overlap_start).days)
            span_days = int((cache_end - cache_start).days)
            candidates.append((-overlap_days, span_days, -cache_end.value, path))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _load_portfolio_cache_ohlcv(
    ticker: str,
    start: str,
    end: str,
    *,
    allow_partial: bool = False,
) -> pd.DataFrame:
    cache_path = _find_covering_portfolio_cache(
        ticker,
        start,
        end,
        require_full_coverage=not allow_partial,
    )
    if cache_path is None:
        return pd.DataFrame()

    df = read_parquet_safe(cache_path)
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
    if "date" not in df.columns:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))].copy()
    if "stock_splits" not in df.columns:
        if "stocksplits" in df.columns:
            df = df.rename(columns={"stocksplits": "stock_splits"})
        else:
            df["stock_splits"] = 0.0
    if "dividends" not in df.columns:
        df["dividends"] = 0.0

    keep_cols = ["date", "open", "high", "low", "close", "volume", "dividends", "stock_splits"]
    return df[keep_cols].sort_values("date").reset_index(drop=True)


def load_ohlcv_db_first(ticker: str, start: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    try:
        db_df = query_ohlcv(ticker, start, end)
    except Exception:
        # Another process can briefly hold a DuckDB file lock; keep the
        # baseline usable by falling back to the parquet cache.
        db_df = pd.DataFrame()
    if not db_df.empty:
        db_df = db_df.rename(columns={"dt": "date"}).copy()
        db_df["date"] = pd.to_datetime(db_df["date"]).dt.tz_localize(None)
        frames.append(db_df[["date", "open", "high", "low", "close", "volume", "dividends", "stock_splits"]])

    db_covers = False
    if not db_df.empty:
        db_start = pd.Timestamp(db_df["date"].min()).normalize()
        db_end = pd.Timestamp(db_df["date"].max()).normalize()
        db_covers = db_start <= pd.Timestamp(start).normalize() and db_end >= pd.Timestamp(end).normalize()

    if not db_covers:
        cache_df = _load_portfolio_cache_ohlcv(ticker, start, end, allow_partial=True)
        if not cache_df.empty:
            frames.append(cache_df)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    return merged


def align_price_panel(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        df = load_ohlcv_db_first(ticker, start, end)
        if df.empty:
            raise RuntimeError(f"No OHLCV data for {ticker}")
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))].copy()
        df = df.dropna(subset=["date", "open", "close"])
        part = df[["date", "open", "close"]].rename(
            columns={
                "open": f"{ticker}_open",
                "close": f"{ticker}_close",
            }
        )
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")

    price_cols = [col for col in panel.columns if col != "date"]
    panel = panel.dropna(subset=price_cols).sort_values("date").reset_index(drop=True)
    if panel.empty:
        raise RuntimeError("No aligned rows available after merging tickers")
    return panel


def build_rebalance_mask(
    dates: pd.Series,
    frequency: str,
    every_n_trading_days: int | None,
) -> list[bool]:
    mask: list[bool] = []
    for idx, current in enumerate(pd.to_datetime(dates)):
        if idx == 0:
            mask.append(True)
            continue
        previous = pd.Timestamp(dates.iloc[idx - 1])
        current = pd.Timestamp(current)

        if every_n_trading_days is not None and every_n_trading_days > 0:
            mask.append(idx % every_n_trading_days == 0)
            continue

        if frequency == "daily":
            mask.append(True)
        elif frequency == "weekly":
            prev_iso = previous.isocalendar()
            curr_iso = current.isocalendar()
            mask.append((prev_iso.year, prev_iso.week) != (curr_iso.year, curr_iso.week))
        elif frequency == "monthly":
            mask.append((previous.year, previous.month) != (current.year, current.month))
        elif frequency == "quarterly":
            mask.append(previous.to_period("Q") != current.to_period("Q"))
        elif frequency == "yearly":
            mask.append(previous.year != current.year)
        elif frequency == "none":
            mask.append(False)
        else:
            raise ValueError(f"Unsupported rebalance frequency: {frequency}")
    return mask


def run_static_benchmark(
    panel: pd.DataFrame,
    weights: dict[str, float],
    *,
    initial_cash: float,
    commission_rate: float,
) -> dict:
    normalized = {ticker: max(float(weight), 0.0) for ticker, weight in weights.items()}
    total_weight = sum(normalized.values())
    if total_weight > 1.0 + 1e-9:
        raise ValueError(f"Benchmark weights exceed 100%: {weights}")

    first_row = panel.iloc[0]
    cash = float(initial_cash)
    shares: dict[str, float] = {}
    entry_fees = 0.0

    for ticker, target_weight in normalized.items():
        if target_weight <= 0.0:
            continue
        open_price = float(first_row[f"{ticker}_open"])
        budget = initial_cash * target_weight
        cost = budget / (1.0 + commission_rate)
        fee = cost * commission_rate
        shares[ticker] = cost / open_price if open_price > 0 else 0.0
        cash -= cost + fee
        entry_fees += fee

    equity_curve: list[float] = []
    for _, row in panel.iterrows():
        equity = cash
        for ticker, share_count in shares.items():
            equity += share_count * float(row[f"{ticker}_close"])
        equity_curve.append(float(equity))

    final_equity = float(equity_curve[-1])
    final_weights = {}
    if final_equity > 0:
        for ticker, share_count in shares.items():
            final_weights[ticker] = float(share_count * float(panel.iloc[-1][f"{ticker}_close"]) / final_equity)
    final_weights["cash"] = float(max(0.0, cash) / final_equity) if final_equity > 0 else 0.0

    return {
        "final_value": final_equity,
        "metrics": calculate_backtest_metrics(equity_curve, initial_value=initial_cash),
        "entry_fees_paid": float(entry_fees),
        "final_weights": final_weights,
        "equity_curve": equity_curve,
    }


def run_rebalance_strategy(
    panel: pd.DataFrame,
    *,
    asset_ticker: str,
    target_weight: float,
    initial_cash: float,
    commission_rate: float,
    etf_tax_rate: float,
    rebalance_frequency: str,
    every_n_trading_days: int | None,
    drift_threshold: float,
) -> dict:
    rebalance_mask = build_rebalance_mask(panel["date"], rebalance_frequency, every_n_trading_days)

    cash = float(initial_cash)
    shares = 0.0
    fees_paid = 0.0
    trade_count = 0
    rebalance_checks = 0
    rebalance_trades = 0
    trade_log: list[dict] = []
    daily_trace: list[dict] = []
    equity_curve: list[float] = []

    open_col = f"{asset_ticker}_open"
    close_col = f"{asset_ticker}_close"

    for idx, row in panel.iterrows():
        date = pd.Timestamp(row["date"])
        open_price = float(row[open_col])
        close_price = float(row[close_col])

        executed_trade = False
        desired_asset_weight = float(target_weight)
        current_weight_before_trade = 0.0
        drift_before_trade = 0.0
        trade_note = "skip"

        if rebalance_mask[idx]:
            rebalance_checks += 1
            equity_open = cash + shares * open_price
            current_asset_value = shares * open_price
            current_weight_before_trade = (
                float(current_asset_value / equity_open) if equity_open > 0 else 0.0
            )
            drift_before_trade = abs(current_weight_before_trade - desired_asset_weight)
            should_trade = idx == 0 or drift_before_trade >= drift_threshold

            if should_trade and equity_open > 0.0:
                target_asset_value = equity_open * desired_asset_weight
                delta_value = target_asset_value - current_asset_value

                if delta_value < -1e-8:
                    sell_shares = min(shares, abs(delta_value) / open_price)
                    if sell_shares > 0.0:
                        proceeds = sell_shares * open_price
                        fee = proceeds * commission_rate
                        tax = proceeds * etf_tax_rate
                        cash += proceeds - fee - tax
                        shares -= sell_shares
                        fees_paid += fee + tax
                        trade_count += 1
                        rebalance_trades += 1
                        executed_trade = True
                        trade_note = "sell"
                        trade_log.append(
                            {
                                "date": str(date.date()),
                                "type": "SELL",
                                "shares": float(sell_shares),
                                "price": open_price,
                                "gross_amount": float(proceeds),
                                "fee": float(fee),
                                "tax": float(tax),
                                "weight_before_trade": float(current_weight_before_trade),
                                "target_weight": float(desired_asset_weight),
                            }
                        )
                elif delta_value > 1e-8:
                    max_affordable_value = cash / (1.0 + commission_rate)
                    buy_value = min(delta_value, max_affordable_value)
                    buy_shares = buy_value / open_price if open_price > 0 else 0.0
                    if buy_shares > 0.0:
                        cost = buy_shares * open_price
                        fee = cost * commission_rate
                        cash -= cost + fee
                        shares += buy_shares
                        fees_paid += fee
                        trade_count += 1
                        rebalance_trades += 1
                        executed_trade = True
                        trade_note = "buy"
                        trade_log.append(
                            {
                                "date": str(date.date()),
                                "type": "BUY",
                                "shares": float(buy_shares),
                                "price": open_price,
                                "gross_amount": float(cost),
                                "fee": float(fee),
                                "tax": 0.0,
                                "weight_before_trade": float(current_weight_before_trade),
                                "target_weight": float(desired_asset_weight),
                            }
                        )
                else:
                    trade_note = "already_on_target"
            else:
                trade_note = "within_drift_band"

        equity_close = cash + shares * close_price
        current_asset_value_close = shares * close_price
        current_weight_close = float(current_asset_value_close / equity_close) if equity_close > 0 else 0.0
        cash_weight_close = float(max(equity_close - current_asset_value_close, 0.0) / equity_close) if equity_close > 0 else 0.0

        equity_curve.append(float(equity_close))
        daily_trace.append(
            {
                "date": str(date.date()),
                "close_equity": float(equity_close),
                "close_price": float(close_price),
                "asset_shares": float(shares),
                "asset_weight": current_weight_close,
                "cash_weight": cash_weight_close,
                "rebalance_check": bool(rebalance_mask[idx]),
                "executed_trade": bool(executed_trade),
                "drift_before_trade": float(drift_before_trade),
                "trade_note": trade_note,
            }
        )

    final_value = float(equity_curve[-1])
    final_asset_value = float(shares * float(panel.iloc[-1][close_col]))
    final_weights = {
        asset_ticker: float(final_asset_value / final_value) if final_value > 0 else 0.0,
        "cash": float(max(final_value - final_asset_value, 0.0) / final_value) if final_value > 0 else 0.0,
    }

    return {
        "final_value": final_value,
        "strategy_metrics": calculate_backtest_metrics(equity_curve, initial_value=initial_cash),
        "num_trades": int(trade_count),
        "rebalance_checks": int(rebalance_checks),
        "rebalance_trades": int(rebalance_trades),
        "fees_paid_estimate": float(fees_paid),
        "final_cash": float(cash),
        "final_shares": {asset_ticker: float(shares)},
        "final_weights": final_weights,
        "equity_curve": equity_curve,
        "trade_log": trade_log,
        "daily_trace": daily_trace,
    }


def resolve_group_a_result_json(path: str | None) -> Path | None:
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Group A result JSON not found: {candidate}")
        return candidate

    candidates = sorted(
        (PROJECT_ROOT / "results").glob("group_a_backtest_*.json"),
        key=lambda item: item.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def load_group_a_summary(result_json: Path | None) -> dict | None:
    if result_json is None:
        return None
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    result = payload.get("group_a", {}).get("result", {})
    metrics = result.get("rl_metrics")
    if not result or not metrics:
        return None
    return {
        "result_json": str(result_json),
        "model_name": payload.get("group_a", {}).get("model_name"),
        "final_value": float(result.get("final_value", 0.0)),
        "metrics": metrics,
    }


def build_comparison(strategy_result: dict, group_a_summary: dict | None) -> dict | None:
    if group_a_summary is None:
        return None

    strategy_metrics = strategy_result["strategy_metrics"]
    group_metrics = group_a_summary["metrics"]
    return {
        "group_a_result_json": group_a_summary["result_json"],
        "group_a_model_name": group_a_summary["model_name"],
        "strategy_minus_group_a_final_value": float(strategy_result["final_value"] - group_a_summary["final_value"]),
        "strategy_minus_group_a_total_return": float(
            strategy_metrics["total_return"] - float(group_metrics.get("total_return", 0.0))
        ),
        "strategy_minus_group_a_sharpe": float(
            strategy_metrics["sharpe"] - float(group_metrics.get("sharpe", 0.0))
        ),
        "strategy_minus_group_a_max_drawdown": float(
            strategy_metrics["max_drawdown"] - float(group_metrics.get("max_drawdown", 0.0))
        ),
        "strategy_minus_group_a_volatility": float(
            strategy_metrics["volatility"] - float(group_metrics.get("volatility", 0.0))
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest a simple 00631L + cash 50/50 rebalance baseline.")
    parser.add_argument("--asset-ticker", default=DEFAULT_ASSET_TICKER)
    parser.add_argument("--benchmark-ticker", default=DEFAULT_BENCHMARK_TICKER)
    parser.add_argument("--initial-cash", type=float, default=DEFAULT_INITIAL_CASH)
    parser.add_argument("--target-weight", type=float, default=DEFAULT_TARGET_WEIGHT)
    parser.add_argument("--backtest-start", default=DEFAULT_BACKTEST_START)
    parser.add_argument("--backtest-end", default=DEFAULT_BACKTEST_END)
    parser.add_argument(
        "--rebalance-frequency",
        choices=["none", "daily", "weekly", "monthly", "quarterly", "yearly"],
        default=DEFAULT_REBALANCE_FREQUENCY,
    )
    parser.add_argument(
        "--rebalance-every-n-trading-days",
        type=int,
        default=None,
        help="Override calendar frequency and rebalance every N aligned trading days",
    )
    parser.add_argument(
        "--drift-threshold",
        type=float,
        default=0.0,
        help="Only trade when |current_weight - target_weight| >= threshold",
    )
    parser.add_argument("--commission-rate", type=float, default=COMMISSION_RATE)
    parser.add_argument("--etf-tax-rate", type=float, default=ETF_TAX_RATE)
    parser.add_argument(
        "--compare-group-a-json",
        default=None,
        help="Optional Group A result JSON; defaults to the latest group_a_backtest_*.json",
    )
    args = parser.parse_args()

    if not 0.0 <= args.target_weight <= 1.0:
        raise ValueError("target-weight must be between 0 and 1")
    if args.drift_threshold < 0.0:
        raise ValueError("drift-threshold must be non-negative")

    tickers = [args.asset_ticker, args.benchmark_ticker]
    panel = align_price_panel(tickers, args.backtest_start, args.backtest_end)

    strategy_result = run_rebalance_strategy(
        panel,
        asset_ticker=args.asset_ticker,
        target_weight=args.target_weight,
        initial_cash=args.initial_cash,
        commission_rate=args.commission_rate,
        etf_tax_rate=args.etf_tax_rate,
        rebalance_frequency=args.rebalance_frequency,
        every_n_trading_days=args.rebalance_every_n_trading_days,
        drift_threshold=args.drift_threshold,
    )

    benchmarks = {
        "buy_and_hold_00631l_50_cash_50": run_static_benchmark(
            panel,
            {args.asset_ticker: args.target_weight},
            initial_cash=args.initial_cash,
            commission_rate=args.commission_rate,
        ),
        "buy_and_hold_00631l_100": run_static_benchmark(
            panel,
            {args.asset_ticker: 1.0},
            initial_cash=args.initial_cash,
            commission_rate=args.commission_rate,
        ),
        "buy_and_hold_0050_100": run_static_benchmark(
            panel,
            {args.benchmark_ticker: 1.0},
            initial_cash=args.initial_cash,
            commission_rate=args.commission_rate,
        ),
        "buy_and_hold_0050_50_00631l_50": run_static_benchmark(
            panel,
            {args.asset_ticker: 0.5, args.benchmark_ticker: 0.5},
            initial_cash=args.initial_cash,
            commission_rate=args.commission_rate,
        ),
    }

    group_a_summary = load_group_a_summary(resolve_group_a_result_json(args.compare_group_a_json))
    comparison_to_group_a = build_comparison(strategy_result, group_a_summary)

    payload = {
        "strategy": "00631l_cash_50_50_rebalance",
        "asset_ticker": args.asset_ticker,
        "benchmark_ticker": args.benchmark_ticker,
        "tickers": tickers,
        "backtest_start": args.backtest_start,
        "backtest_end": args.backtest_end,
        "actual_backtest_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_backtest_end": str(pd.Timestamp(panel["date"].max()).date()),
        "backtest_rows": int(len(panel)),
        "initial_cash": float(args.initial_cash),
        "target_weight": float(args.target_weight),
        "cash_weight": float(1.0 - args.target_weight),
        "rebalance_frequency": args.rebalance_frequency,
        "rebalance_every_n_trading_days": args.rebalance_every_n_trading_days,
        "drift_threshold": float(args.drift_threshold),
        "execution_timing": {
            "rebalance_price": "same_day_open",
            "mark_to_market_price": "same_day_close",
        },
        "transaction_costs": {
            "commission_rate": float(args.commission_rate),
            "etf_tax_rate": float(args.etf_tax_rate),
        },
        **strategy_result,
        "benchmarks": benchmarks,
        "comparison_to_group_a": comparison_to_group_a,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    output_file = (
        PROJECT_ROOT
        / "results"
        / f"backtest_00631l_cash_5050_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    metrics = strategy_result["strategy_metrics"]
    print("=" * 72)
    print("00631L 50/50 cash rebalance baseline")
    print(f"Output:            {output_file}")
    print(f"Backtest:          {payload['actual_backtest_start']} ~ {payload['actual_backtest_end']} ({payload['backtest_rows']} rows)")
    print(f"Target allocation: {args.asset_ticker} {args.target_weight:.0%} / cash {1.0 - args.target_weight:.0%}")
    print(f"Rebalance:         {args.rebalance_frequency}")
    if args.rebalance_every_n_trading_days:
        print(f"Every N days:      {args.rebalance_every_n_trading_days}")
    print(f"Drift threshold:   {args.drift_threshold:.2%}")
    print("-" * 72)
    print(f"Final value:       {strategy_result['final_value']:,.0f}")
    print(f"Total return:      {metrics['total_return'] * 100:.2f}%")
    print(f"Annual return:     {metrics['annual_return'] * 100:.2f}%")
    print(f"Sharpe:            {metrics['sharpe']:.3f}")
    print(f"Max drawdown:      {metrics['max_drawdown'] * 100:.2f}%")
    print(f"Volatility:        {metrics['volatility'] * 100:.2f}%")
    print(f"Trades / fees:     {strategy_result['num_trades']} / {strategy_result['fees_paid_estimate']:,.0f}")
    if comparison_to_group_a:
        print("-" * 72)
        print(f"Vs latest Group A: {comparison_to_group_a['group_a_model_name']}")
        print(f"Delta final value: {comparison_to_group_a['strategy_minus_group_a_final_value']:,.0f}")
        print(f"Delta return:      {comparison_to_group_a['strategy_minus_group_a_total_return'] * 100:.2f} pct")
        print(f"Delta Sharpe:      {comparison_to_group_a['strategy_minus_group_a_sharpe']:.3f}")
        print(f"Delta Max DD:      {comparison_to_group_a['strategy_minus_group_a_max_drawdown'] * 100:.2f} pct")


if __name__ == "__main__":
    main()
