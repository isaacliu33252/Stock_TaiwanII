"""Standardized runner for the research-only A21.4 candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a213 import _run_recovery_strategy
from tw_output_standard import OutputStandardizer, write_standard_output


A214_ID = "a214_bond30c30_mw60"


def run_a214(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    """Run A21.4 without changing the active A21.3 implementation."""
    return _run_recovery_strategy(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db,
        warmup_days=warmup_days,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        basket_name="bond30_cash30",
        ma_window=60,
        strategy_id=A214_ID,
        experiment="group_a_plus_a214_standard_runner",
        status="candidate",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default="results/group_a_plus_runner_a214.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a214_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a214")
    try:
        report, frame = run_a214(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Runner JSON: {Path(args.output).resolve()}")
    print(f"Runner frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
