#!/usr/bin/env python3
"""Sweep Group A / Group B meta-allocation weights.

This script consumes already-generated Group A and Group B daily equity curves.
It does not retrain either model. Practical mode rebalances on quarter starts or
when allocation drift crosses a threshold, with a simple transfer-cost estimate.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CURVE = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_allocation_sweep_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curve-csv", default=str(DEFAULT_CURVE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--group-a-weights",
        default="0.30,0.40,0.50,0.60,0.70,0.80",
        help="Comma-separated Group A target weights.",
    )
    parser.add_argument("--calendar-rebalance", choices=["quarterly", "monthly", "none"], default="quarterly")
    parser.add_argument("--drift-threshold", type=float, default=0.05)
    parser.add_argument("--transfer-cost-rate", type=float, default=0.001425)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _parse_weights(raw: str) -> list[float]:
    values = sorted({float(item.strip()) for item in raw.split(",") if item.strip()})
    for value in values:
        if not 0.0 <= value <= 1.0:
            raise ValueError("--group-a-weights entries must be between 0 and 1")
    return values


def _metrics(values: pd.Series, *, rebalances: int = 0, total_cost: float = 0.0) -> dict[str, Any]:
    daily = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "annual_return": float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0),
        "sharpe_ratio": (
            float((daily.mean() / daily.std()) * math.sqrt(252))
            if len(daily) > 1 and daily.std() > 0
            else 0.0
        ),
        "max_drawdown": float((values / values.cummax() - 1.0).min()),
        "volatility": float(daily.std() * math.sqrt(252)) if len(daily) > 1 else 0.0,
        "num_rebalances": int(rebalances),
        "total_cost": float(total_cost),
    }


def _calendar_due(date: pd.Timestamp, previous_date: pd.Timestamp | None, mode: str) -> bool:
    if previous_date is None:
        return True
    if mode == "none":
        return False
    if mode == "monthly":
        return date.year != previous_date.year or date.month != previous_date.month
    if mode == "quarterly":
        return date.year != previous_date.year or (date.month - 1) // 3 != (previous_date.month - 1) // 3
    raise ValueError(f"Unsupported calendar mode: {mode}")


def _daily_rebalanced(a_returns: pd.Series, b_returns: pd.Series, a_weight: float) -> pd.Series:
    returns = a_weight * a_returns + (1.0 - a_weight) * b_returns
    return 2_000_000.0 * (1.0 + returns).cumprod()


def _practical_curve(
    a_returns: pd.Series,
    b_returns: pd.Series,
    *,
    a_weight: float,
    calendar_rebalance: str,
    drift_threshold: float,
    transfer_cost_rate: float,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    target_a = float(a_weight)
    target_b = 1.0 - target_a
    a_value = 2_000_000.0 * target_a
    b_value = 2_000_000.0 * target_b
    previous_date: pd.Timestamp | None = None
    curve: list[tuple[pd.Timestamp, float]] = []
    events: list[dict[str, Any]] = []

    for date in a_returns.index:
        a_value *= 1.0 + float(a_returns.loc[date])
        b_value *= 1.0 + float(b_returns.loc[date])
        total = a_value + b_value
        current_a_weight = a_value / total if total > 0 else 0.0
        calendar_triggered = _calendar_due(date, previous_date, calendar_rebalance)
        drift_triggered = abs(current_a_weight - target_a) >= drift_threshold
        if calendar_triggered or drift_triggered:
            target_a_value = total * target_a
            transfer_notional = abs(target_a_value - a_value)
            cost = transfer_notional * transfer_cost_rate
            total_after_cost = total - cost
            a_value = total_after_cost * target_a
            b_value = total_after_cost * target_b
            total = total_after_cost
            events.append(
                {
                    "date": str(date.date()),
                    "reason": "calendar" if calendar_triggered else "drift",
                    "pre_group_a_weight": float(current_a_weight),
                    "target_group_a_weight": float(target_a),
                    "transfer_notional": float(transfer_notional),
                    "cost": float(cost),
                }
            )
        curve.append((date, total))
        previous_date = date

    return pd.Series([value for _, value in curve], index=[date for date, _ in curve], dtype=float), events


def main() -> None:
    args = _parse_args()
    curve_path = _resolve(args.curve_csv)
    frame = pd.read_csv(curve_path, encoding="utf-8-sig")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    a_curve = frame["group_a_value"].astype(float)
    b_curve = frame["group_b_value"].astype(float)
    a_returns = a_curve.pct_change().fillna(0.0)
    b_returns = b_curve.pct_change().fillna(0.0)

    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    events_by_variant: dict[str, list[dict[str, Any]]] = {}
    curves = pd.DataFrame(index=frame.index)
    curves["group_a_value"] = a_curve
    curves["group_b_value"] = b_curve

    for a_weight in _parse_weights(args.group_a_weights):
        label = f"{int(round(a_weight * 100)):02d}A_{int(round((1.0 - a_weight) * 100)):02d}B"
        daily_name = f"{label}_daily_rebalanced"
        daily_curve = _daily_rebalanced(a_returns, b_returns, a_weight)
        daily_metrics = _metrics(daily_curve)
        summary[daily_name] = daily_metrics
        rows.append({"variant": daily_name, "mode": "daily_rebalanced", "group_a_weight": a_weight, **daily_metrics})
        curves[f"value_{daily_name}"] = daily_curve

        practical_name = f"{label}_{args.calendar_rebalance}_or_drift_fee"
        practical_curve, events = _practical_curve(
            a_returns,
            b_returns,
            a_weight=a_weight,
            calendar_rebalance=str(args.calendar_rebalance),
            drift_threshold=float(args.drift_threshold),
            transfer_cost_rate=float(args.transfer_cost_rate),
        )
        practical_metrics = _metrics(
            practical_curve,
            rebalances=len(events),
            total_cost=sum(float(event["cost"]) for event in events),
        )
        summary[practical_name] = practical_metrics
        events_by_variant[practical_name] = events
        rows.append(
            {
                "variant": practical_name,
                "mode": f"{args.calendar_rebalance}_or_drift_fee",
                "group_a_weight": a_weight,
                **practical_metrics,
            }
        )
        curves[f"value_{practical_name}"] = practical_curve

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_csv_path = output.with_name(output.stem + "_curve.csv")
    report = {
        "experiment": "group_ab_allocation_sweep",
        "method_note": (
            "Uses existing Group A and Group B daily equity curves. Practical mode "
            "rebalances on calendar schedule or group-weight drift and estimates top-level transfer cost."
        ),
        "source_curve_csv": str(curve_path.resolve()),
        "window": {
            "start": str(frame.index[0].date()),
            "end": str(frame.index[-1].date()),
            "rows": int(len(frame)),
        },
        "settings": {
            "group_a_weights": _parse_weights(args.group_a_weights),
            "calendar_rebalance": str(args.calendar_rebalance),
            "drift_threshold": float(args.drift_threshold),
            "transfer_cost_rate": float(args.transfer_cost_rate),
        },
        "summary": summary,
        "rebalance_events": events_by_variant,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_csv_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_csv_path, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_csv_path}")
    print(f"Window: {frame.index[0].date()} ~ {frame.index[-1].date()} ({len(frame)} rows)")
    for row in rows:
        if str(row["mode"]).endswith("_or_drift_fee"):
            print(
                f"{row['variant']}: final={row['final_value']:.2f}, "
                f"annual={row['annual_return']:.4%}, sharpe={row['sharpe_ratio']:.4f}, "
                f"mdd={row['max_drawdown']:.4%}, rebalances={row['num_rebalances']}, "
                f"cost={row['total_cost']:.2f}"
            )


if __name__ == "__main__":
    main()
