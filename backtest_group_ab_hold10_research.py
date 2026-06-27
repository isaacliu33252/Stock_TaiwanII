#!/usr/bin/env python3
"""Re-run Group A + Group B using the Group A 00632R hold-10 overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_ab_allocation import _metrics as _allocation_metrics
from backtest_group_ab_allocation import _practical_curve
from research_group_ab_group_a_improvements import _metrics, _run_ab_dynamic_and_execution, _segment_rows


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GROUP_A_SWEEP = PROJECT_ROOT / "results" / "group_a_00632r_dca_sweep_20240102_20260604_curve.csv"
DEFAULT_BASE_AB = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_hold10_no2884_research_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-a-sweep-csv", default=str(DEFAULT_GROUP_A_SWEEP))
    parser.add_argument("--base-ab-curve-csv", default=str(DEFAULT_BASE_AB))
    parser.add_argument("--group-a-variant", default="hold_limit_00632r_10d_to_0050")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--transfer-cost-rate", type=float, default=0.001425)
    parser.add_argument(
        "--fixed-weights",
        default="0.00,0.25,0.40,0.50,0.55,0.60,0.625,0.65,0.675,0.70,0.725,0.75,0.80,0.85,0.90,0.95,1.00",
    )
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _parse_weights(raw: str) -> list[float]:
    return sorted({float(item.strip()) for item in raw.split(",") if item.strip()})


def _load_hold10_ab(group_a_path: Path, base_ab_path: Path, group_a_variant: str) -> pd.DataFrame:
    group_a = pd.read_csv(group_a_path, encoding="utf-8-sig")
    base_ab = pd.read_csv(base_ab_path, encoding="utf-8-sig")
    group_a["date"] = pd.to_datetime(group_a["date"])
    base_ab["date"] = pd.to_datetime(base_ab["date"])
    if group_a_variant not in group_a.columns:
        raise ValueError(f"Missing Group A variant column: {group_a_variant}")

    merged = (
        group_a[["date", group_a_variant]]
        .rename(columns={group_a_variant: "group_a_value"})
        .merge(base_ab[["date", "group_b_value"]], on="date", how="inner")
        .sort_values("date")
    )
    merged["combined_value"] = merged["group_a_value"].astype(float) + merged["group_b_value"].astype(float)
    return merged.set_index("date")


def _fixed_rows_and_curves(
    ab: pd.DataFrame,
    weights: list[float],
    *,
    transfer_cost_rate: float,
) -> tuple[list[dict[str, Any]], dict[str, pd.Series], dict[str, list[dict[str, Any]]]]:
    a_returns = ab["group_a_value"].pct_change().fillna(0.0)
    b_returns = ab["group_b_value"].pct_change().fillna(0.0)
    rows: list[dict[str, Any]] = []
    curves: dict[str, pd.Series] = {}
    events_by_variant: dict[str, list[dict[str, Any]]] = {}

    for weight in weights:
        label = f"fixed_{str(weight).replace('.', '_')}"
        curve, events = _practical_curve(
            a_returns,
            b_returns,
            a_weight=weight,
            calendar_rebalance="quarterly",
            drift_threshold=0.05,
            transfer_cost_rate=transfer_cost_rate,
        )
        curves[label] = curve
        events_by_variant[label] = events
        rows.append(
            {
                "family": "fixed_ab",
                "variant": label,
                "group_a_weight": float(weight),
                **_allocation_metrics(
                    curve,
                    rebalances=len(events),
                    total_cost=sum(float(event["cost"]) for event in events),
                ),
            }
        )

    return rows, curves, events_by_variant


def main() -> None:
    args = _parse_args()
    group_a_path = _resolve(args.group_a_sweep_csv)
    base_ab_path = _resolve(args.base_ab_curve_csv)
    output = _resolve(args.output)
    weights = _parse_weights(args.fixed_weights)

    ab = _load_hold10_ab(group_a_path, base_ab_path, str(args.group_a_variant))
    fixed_rows, fixed_curves, fixed_events = _fixed_rows_and_curves(
        ab,
        weights,
        transfer_cost_rate=float(args.transfer_cost_rate),
    )
    dynamic_rows, dynamic_curves = _run_ab_dynamic_and_execution(ab, float(args.transfer_cost_rate))

    all_curves = {
        "group_a_hold10": ab["group_a_value"],
        "group_b_no2884": ab["group_b_value"],
        "ab_raw_100_100": ab["combined_value"],
        **fixed_curves,
        **dynamic_curves,
    }
    segment_rows = _segment_rows(
        {
            "group_a_hold10": ab["group_a_value"],
            "group_b_no2884": ab["group_b_value"],
            "best_fixed_ab": fixed_curves[max(fixed_rows, key=lambda row: (row["sharpe_ratio"], row["final_value"]))["variant"]],
            "best_dynamic_ab": dynamic_curves[
                max(
                    (row for row in dynamic_rows if row["family"] == "dynamic_ab"),
                    key=lambda row: (row["sharpe_ratio"], row["final_value"]),
                )["variant"]
            ],
        }
    )
    rows = fixed_rows + dynamic_rows + segment_rows
    best_fixed = max(fixed_rows, key=lambda row: (row["sharpe_ratio"], row["final_value"]))
    best_dynamic = max((row for row in dynamic_rows if row["family"] == "dynamic_ab"), key=lambda row: (row["sharpe_ratio"], row["final_value"]))
    best_execution = max((row for row in dynamic_rows if row["family"] == "execution_threshold"), key=lambda row: (row["sharpe_ratio"], row["final_value"]))

    output.parent.mkdir(parents=True, exist_ok=True)
    combined_curve_path = output.with_name("group_ab_hold10_no2884_backtest_20240102_20260604_curve.csv")
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    ab.reset_index().to_csv(combined_curve_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(all_curves).to_csv(curve_path, encoding="utf-8-sig")

    report = {
        "experiment": "group_ab_hold10_no2884_research",
        "method_note": (
            "Group A uses hold_limit_00632r_10d_to_0050 from the 00632R overlay sweep. "
            "Group B uses the latest no-2884 curve. No retraining."
        ),
        "sources": {
            "group_a_sweep_csv": str(group_a_path.resolve()),
            "base_ab_curve_csv": str(base_ab_path.resolve()),
            "group_a_variant": str(args.group_a_variant),
        },
        "window": {"start": str(ab.index[0].date()), "end": str(ab.index[-1].date()), "rows": int(len(ab))},
        "settings": {"fixed_weights": weights, "transfer_cost_rate": float(args.transfer_cost_rate)},
        "best": {"fixed_ab": best_fixed, "dynamic_ab": best_dynamic, "execution_threshold": best_execution},
        "fixed_rebalance_events": fixed_events,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path), "combined_curve_csv": str(combined_curve_path)},
        "rows": rows,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Combined curve CSV: {combined_curve_path}")
    print(f"Window: {ab.index[0].date()} ~ {ab.index[-1].date()} ({len(ab)} rows)")
    for label, row in [("Best fixed", best_fixed), ("Best dynamic", best_dynamic), ("Best execution", best_execution)]:
        print(
            f"{label}: {row['variant']} final={row['final_value']:.2f}, "
            f"annual={row['annual_return']:.4%}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, events={row.get('num_events', row.get('num_rebalances', 0))}, "
            f"cost={row['total_cost']:.2f}"
        )


if __name__ == "__main__":
    main()
