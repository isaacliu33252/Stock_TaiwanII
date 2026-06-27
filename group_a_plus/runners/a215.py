"""Standardized runner for the train-selected A21.5 risk-adjusted candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a213 import _run_recovery_strategy
from tw_output_standard import OutputStandardizer, write_standard_output


A215_ID = "a215_cash40_mw80"


def run_a215(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    return _run_recovery_strategy(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db,
        warmup_days=warmup_days,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        basket_name="cash40",
        ma_window=80,
        strategy_id=A215_ID,
        experiment="group_a_plus_a215_standard_runner",
        status="research_candidate",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default="results/group_a_plus_runner_a215.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a215_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a215")
    try:
        report, frame = run_a215(args.start, args.end, args.initial_value, Path(args.db))
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)


if __name__ == "__main__":
    main()
