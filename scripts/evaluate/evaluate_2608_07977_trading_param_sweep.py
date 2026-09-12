#!/usr/bin/env python3
"""Parameter sweep for the 2608.07977 released trading-test checkpoints."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from reproduce_2608_07977_author_trading_test import DEFAULT_SOURCE_ROOT, run_dbdp2, run_deepbsde


def _parse_floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_windows(value: str) -> list[tuple[str, str]]:
    windows: list[tuple[str, str]] = []
    for item in value.split(","):
        if not item.strip():
            continue
        start, end = item.split(":", 1)
        windows.append((start.strip(), end.strip()))
    return windows


def _affine_row(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run["metrics"]["Affine_6.0%"]
    return {"method": run["method"], **metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--methods", default="deepbsde,dbdp2")
    parser.add_argument("--windows", default="2020-01-01:2020-12-31,2025-01-01:2025-12-31")
    parser.add_argument("--rf-values", default="0.02,0.04")
    parser.add_argument("--target-returns", default="0.04,0.06,0.08,0.10")
    parser.add_argument("--strategy-windows", default="20,60")
    parser.add_argument("--rebalance-period", type=int, default=5)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--include-leverage", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()

    methods = [item.strip().lower() for item in args.methods.split(",") if item.strip()]
    windows = _parse_windows(args.windows)
    rf_values = _parse_floats(args.rf_values)
    target_returns = _parse_floats(args.target_returns)
    strategy_windows = _parse_ints(args.strategy_windows)
    leverage_values = [False, True] if args.include_leverage else [False]

    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for start_date, end_date in windows:
        window_label = start_date[:4]
        for rf in rf_values:
            for target_return in target_returns:
                for strategy_window in strategy_windows:
                    for allow_leverage in leverage_values:
                        for method in methods:
                            kwargs = {
                                "source_root": args.source_root,
                                "device": args.device,
                                "model_path": None,
                                "start_date": start_date,
                                "end_date": end_date,
                                "rf": rf,
                                "target_return": target_return,
                                "rebalance_period": args.rebalance_period,
                                "strategy_window": strategy_window,
                                "allow_leverage": allow_leverage,
                            }
                            run = run_deepbsde(**kwargs) if method == "deepbsde" else run_dbdp2(**kwargs)
                            runs.append(
                                {
                                    "window": window_label,
                                    "start_date": start_date,
                                    "end_date": end_date,
                                    "rf": rf,
                                    "target_return": target_return,
                                    "strategy_window": strategy_window,
                                    "allow_leverage": allow_leverage,
                                    "run": run,
                                }
                            )
                            affine_key = f"Affine_{target_return:.1%}"
                            metrics = run["metrics"].get(affine_key)
                            if metrics is None:
                                metrics = run["metrics"]["Affine_6.0%"]
                            rows.append(
                                {
                                    "window": window_label,
                                    "start_date": start_date,
                                    "end_date": end_date,
                                    "method": run["method"],
                                    "rf": rf,
                                    "target_return": target_return,
                                    "strategy_window": strategy_window,
                                    "allow_leverage": allow_leverage,
                                    **metrics,
                                }
                            )

    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_trading_parameter_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(args.source_root),
        "methods": methods,
        "windows": windows,
        "rf_values": rf_values,
        "target_returns": target_returns,
        "strategy_windows": strategy_windows,
        "leverage_values": leverage_values,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with args.csv_output.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Output: {args.output.resolve()}")
    print(f"CSV: {args.csv_output.resolve()}")
    for row in sorted(rows, key=lambda r: (r["window"], r["method"], -r["sharpe_ratio"]))[:10]:
        print(
            f"{row['window']} {row['method']} rf={row['rf']:.2%} target={row['target_return']:.2%} "
            f"win={row['strategy_window']} lev={row['allow_leverage']}: "
            f"ret={row['annual_return']:.2%} vol={row['volatility']:.2%} "
            f"sharpe={row['sharpe_ratio']:.2f} mdd={row['max_drawdown']:.2%}"
        )


if __name__ == "__main__":
    main()
