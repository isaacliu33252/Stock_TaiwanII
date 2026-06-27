#!/usr/bin/env python3
"""Backtest a simple regime-based Group A / Group B allocator."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CURVE = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_regime_allocator_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curve-csv", default=str(DEFAULT_CURVE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--normal-a-weight", type=float, default=0.70)
    parser.add_argument("--caution-a-weight", type=float, default=0.60)
    parser.add_argument("--risk-off-a-weight", type=float, default=0.40)
    parser.add_argument("--caution-drawdown", type=float, default=-0.06)
    parser.add_argument("--risk-off-drawdown", type=float, default=-0.12)
    parser.add_argument("--caution-momentum21", type=float, default=-0.03)
    parser.add_argument("--risk-off-momentum21", type=float, default=-0.08)
    parser.add_argument("--calendar-rebalance", choices=["quarterly", "monthly", "none"], default="quarterly")
    parser.add_argument("--drift-threshold", type=float, default=0.05)
    parser.add_argument("--transfer-cost-rate", type=float, default=0.001425)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _metrics(values: pd.Series, *, rebalances: int, total_cost: float) -> dict[str, Any]:
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


def _target_for_state(row: pd.Series, args: argparse.Namespace) -> tuple[float, str]:
    drawdown = float(row["group_a_drawdown_lag1"])
    momentum21 = float(row["group_a_momentum21_lag1"])
    if drawdown <= float(args.risk_off_drawdown) or momentum21 <= float(args.risk_off_momentum21):
        return float(args.risk_off_a_weight), "risk_off"
    if drawdown <= float(args.caution_drawdown) or momentum21 <= float(args.caution_momentum21):
        return float(args.caution_a_weight), "caution"
    return float(args.normal_a_weight), "normal"


def _simulate(frame: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.Series, list[dict[str, Any]], pd.DataFrame]:
    a_returns = frame["group_a_value"].pct_change().fillna(0.0)
    b_returns = frame["group_b_value"].pct_change().fillna(0.0)
    group_a_peak = frame["group_a_value"].cummax()
    frame = frame.copy()
    frame["group_a_drawdown_lag1"] = (frame["group_a_value"] / group_a_peak - 1.0).shift(1).fillna(0.0)
    frame["group_a_momentum21_lag1"] = frame["group_a_value"].pct_change(21).shift(1).fillna(0.0)
    targets = frame.apply(lambda row: _target_for_state(row, args), axis=1)
    frame["target_group_a_weight"] = [float(item[0]) for item in targets]
    frame["regime"] = [str(item[1]) for item in targets]

    first_target = float(frame["target_group_a_weight"].iloc[0])
    a_value = 2_000_000.0 * first_target
    b_value = 2_000_000.0 * (1.0 - first_target)
    last_target = first_target
    previous_date: pd.Timestamp | None = None
    curve = []
    events: list[dict[str, Any]] = []

    for date, row in frame.iterrows():
        a_value *= 1.0 + float(a_returns.loc[date])
        b_value *= 1.0 + float(b_returns.loc[date])
        total = a_value + b_value
        current_a_weight = a_value / total if total > 0 else 0.0
        target_a = float(row["target_group_a_weight"])
        target_changed = abs(target_a - last_target) > 1e-12
        calendar_triggered = _calendar_due(date, previous_date, str(args.calendar_rebalance))
        drift_triggered = abs(current_a_weight - target_a) >= float(args.drift_threshold)
        if target_changed or calendar_triggered or drift_triggered:
            target_a_value = total * target_a
            transfer_notional = abs(target_a_value - a_value)
            cost = transfer_notional * float(args.transfer_cost_rate)
            total_after_cost = total - cost
            a_value = total_after_cost * target_a
            b_value = total_after_cost * (1.0 - target_a)
            total = total_after_cost
            reason = "target_change" if target_changed else ("calendar" if calendar_triggered else "drift")
            events.append(
                {
                    "date": str(date.date()),
                    "reason": reason,
                    "regime": str(row["regime"]),
                    "pre_group_a_weight": float(current_a_weight),
                    "target_group_a_weight": float(target_a),
                    "transfer_notional": float(transfer_notional),
                    "cost": float(cost),
                }
            )
            last_target = target_a
        curve.append((date, total))
        previous_date = date

    values = pd.Series([value for _, value in curve], index=[date for date, _ in curve], dtype=float)
    return values, events, frame


def main() -> None:
    args = _parse_args()
    curve_path = _resolve(args.curve_csv)
    frame = pd.read_csv(curve_path, encoding="utf-8-sig")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    curve, events, diagnostic = _simulate(frame, args)
    total_cost = sum(float(event["cost"]) for event in events)
    metrics = _metrics(curve, rebalances=len(events), total_cost=total_cost)

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path_out = output.with_name(output.stem + "_curve.csv")
    report = {
        "experiment": "group_ab_regime_allocator",
        "method_note": (
            "Uses previous-day Group A drawdown and 21-day momentum to set top-level A/B allocation. "
            "No model retraining. Rebalances on target changes, calendar schedule, or drift."
        ),
        "source_curve_csv": str(curve_path.resolve()),
        "window": {
            "start": str(curve.index[0].date()),
            "end": str(curve.index[-1].date()),
            "rows": int(len(curve)),
        },
        "settings": {
            "normal_a_weight": float(args.normal_a_weight),
            "caution_a_weight": float(args.caution_a_weight),
            "risk_off_a_weight": float(args.risk_off_a_weight),
            "caution_drawdown": float(args.caution_drawdown),
            "risk_off_drawdown": float(args.risk_off_drawdown),
            "caution_momentum21": float(args.caution_momentum21),
            "risk_off_momentum21": float(args.risk_off_momentum21),
            "calendar_rebalance": str(args.calendar_rebalance),
            "drift_threshold": float(args.drift_threshold),
            "transfer_cost_rate": float(args.transfer_cost_rate),
        },
        "metrics": metrics,
        "regime_counts": {str(k): int(v) for k, v in diagnostic["regime"].value_counts().to_dict().items()},
        "rebalance_events": events,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path_out)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"strategy": "regime_allocator", **metrics}]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        {
            "date": curve.index.date.astype(str),
            "value": curve.values,
            "target_group_a_weight": diagnostic["target_group_a_weight"].values,
            "regime": diagnostic["regime"].values,
        }
    ).to_csv(curve_path_out, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path_out}")
    print(
        f"Regime allocator: final={metrics['final_value']:.2f}, annual={metrics['annual_return']:.4%}, "
        f"sharpe={metrics['sharpe_ratio']:.4f}, mdd={metrics['max_drawdown']:.4%}, "
        f"rebalances={metrics['num_rebalances']}, cost={metrics['total_cost']:.2f}"
    )
    print(f"Regime counts: {report['regime_counts']}")


if __name__ == "__main__":
    main()
