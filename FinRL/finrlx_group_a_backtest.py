#!/usr/bin/env python3
"""
Run Group A through the FinRL-X adapter + weight-centric backtest engine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from FinRL.backtesting import GroupABridgeConfig, run_group_a_finrlx_backtest

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "group_a_finrlx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Group A through FinRL-X backtesting.")
    parser.add_argument("--payload", required=True, help="Canonical Group A payload JSON")
    parser.add_argument("--name", default="GroupAFinRLX")
    parser.add_argument("--target-date", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--initial-capital", type=float, default=None)
    parser.add_argument("--benchmark", action="append", default=None, help="Repeatable benchmark ticker")
    parser.add_argument("--price-dir", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def _write_optional_frame(path: Path, frame: pd.DataFrame) -> None:
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        frame.to_csv(path)


def _json_default(value):
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (pd.Series,)):
        return value.astype(float).to_dict()
    if isinstance(value, (pd.DataFrame,)):
        return value.reset_index().to_dict(orient="records")
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bridge_result = run_group_a_finrlx_backtest(
        GroupABridgeConfig(
            payload_path=args.payload,
            name=args.name,
            target_date=args.target_date,
            start_date=args.start_date,
            end_date=args.end_date,
            model_path=args.model_path,
            download_end=args.download_end,
            initial_capital=args.initial_capital,
            benchmark_tickers=args.benchmark or ["0050.TW"],
            price_dir=args.price_dir,
        )
    )

    print(bridge_result.backtest_result.summary())
    comparison = bridge_result.summary["comparison"]
    print(
        "Env vs FinRL-X final value drift: "
        f"{comparison['final_value_diff']:+,.2f} "
        f"({comparison['final_value_diff_pct_of_initial']:+.4%} of initial)"
    )

    strategy_result = bridge_result.strategy_result
    metadata = strategy_result.metadata or {}
    _write_optional_frame(output_dir / "weights_full.csv", metadata.get("weights_full"))
    _write_optional_frame(output_dir / "weights_rebalance.csv", metadata.get("weights_rebalance"))
    _write_optional_frame(output_dir / "close_prices.csv", metadata.get("prices"))
    _write_optional_frame(output_dir / "finrlx_equity.csv", bridge_result.backtest_result.portfolio_values.to_frame("portfolio_value"))
    if bridge_result.backtest_result.benchmark_values is not None:
        _write_optional_frame(
            output_dir / "benchmark_equity.csv",
            bridge_result.backtest_result.benchmark_values.to_frame("benchmark_value"),
        )
    if not bridge_result.backtest_result.trades.empty:
        bridge_result.backtest_result.trades.to_csv(output_dir / "finrlx_trades.csv")

    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(bridge_result.summary, f, indent=2, ensure_ascii=False, default=_json_default)


if __name__ == "__main__":
    main()
