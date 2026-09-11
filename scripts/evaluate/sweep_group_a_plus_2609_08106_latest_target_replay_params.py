#!/usr/bin/env python3
"""Parameter sweep for the 2609.08106 latest-target-weight replay.

Research-only: this script never changes live target weights, execution plans,
orders, or strategy manifests.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate import replay_group_a_plus_2609_08106_latest_target_weights as replay


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_latest_target_weight_replay_param_sweep.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_latest_target_weight_replay_param_sweep.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_float_list(raw: str) -> list[float]:
    values = [float(part.strip()) for part in str(raw).split(",") if part.strip()]
    if not values:
        raise ValueError(f"empty float list: {raw}")
    return values


def _run_one(
    args: argparse.Namespace,
    *,
    prices,
    scores,
    weights,
    baseline_by_cost_bps: dict[float, tuple[Any, dict[str, Any]]],
    threshold: float,
    shift_weight: float,
    cost_bps: float,
) -> dict[str, Any]:
    base_returns, base_turnover = baseline_by_cost_bps[float(cost_bps)]
    adjusted, events = replay._apply_sleeve(
        weights,
        scores,
        shift_weight=shift_weight,
        threshold=threshold,
        momentum_5d_max=args.momentum_5d_max,
        drawdown_max=args.drawdown_max,
        ann_vol_min=args.ann_vol_min,
    )
    sleeve_returns, sleeve_turnover = replay._simulate(prices, adjusted, cost_bps=cost_bps)
    baseline_metrics = replay._metrics(base_returns, args.initial_value) | base_turnover
    sleeve_metrics = replay._metrics(sleeve_returns, args.initial_value) | sleeve_turnover
    delta = replay._delta(sleeve_metrics, baseline_metrics)
    return {
        "threshold": float(threshold),
        "shift_weight": float(shift_weight),
        "cost_bps": float(cost_bps),
        "event_count": int(len(events)),
        "days_with_00631l_weight": int((weights["00631L.TW"] > 1e-12).sum()),
        "delta_total_return": delta.get("total_return"),
        "delta_annual_return": delta.get("annual_return"),
        "delta_sharpe": delta.get("sharpe_ratio"),
        "delta_max_drawdown": delta.get("max_drawdown"),
        "delta_total_turnover": delta.get("total_turnover"),
        "positive_core_metrics": bool(
            int(len(events)) > 0
            and (delta.get("total_return") or 0.0) > 0.0
            and (delta.get("sharpe_ratio") or 0.0) > 0.0
            and (delta.get("max_drawdown") or -1.0) >= 0.0
        ),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    thresholds = _parse_float_list(args.thresholds)
    shift_weights = _parse_float_list(args.shift_weights)
    cost_bps_values = _parse_float_list(args.cost_bps_values)
    weights = replay._load_target_weights(_resolve(args.target_weights))
    if weights.empty:
        raise RuntimeError("No latest target weights to sweep")
    start = args.start or str(weights.index.min().date())
    end = args.end or str(weights.index.max().date())
    weights = weights.loc[(weights.index >= replay.pd.Timestamp(start)) & (weights.index <= replay.pd.Timestamp(end))]
    prices = replay._load_prices(_resolve(args.db), start, end, args.window + 30)
    scores = replay.sleeve._score_frame(prices, args.window)
    baseline_by_cost_bps = {
        float(cost_bps): replay._simulate(prices, weights, cost_bps=cost_bps)
        for cost_bps in cost_bps_values
    }
    rows = [
        _run_one(
            args,
            prices=prices,
            scores=scores,
            weights=weights,
            baseline_by_cost_bps=baseline_by_cost_bps,
            threshold=threshold,
            shift_weight=shift_weight,
            cost_bps=cost_bps,
        )
        for threshold, shift_weight, cost_bps in itertools.product(thresholds, shift_weights, cost_bps_values)
    ]
    rows_sorted = sorted(
        rows,
        key=lambda row: (
            row["delta_sharpe"] is not None,
            row["delta_sharpe"] if row["delta_sharpe"] is not None else float("-inf"),
            row["delta_total_return"] if row["delta_total_return"] is not None else float("-inf"),
        ),
        reverse=True,
    )
    positive_rows = [row for row in rows if row["positive_core_metrics"]]
    best = rows_sorted[0] if rows_sorted else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_latest_target_weight_replay_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_orders_no_live_weight_change",
        "inputs": {
            "db": str(_resolve(args.db)),
            "target_weights": str(_resolve(args.target_weights)),
            "start": start,
            "end": end,
            "window": int(args.window),
            "thresholds": thresholds,
            "shift_weights": shift_weights,
            "cost_bps_values": cost_bps_values,
            "momentum_5d_max": float(args.momentum_5d_max),
            "drawdown_max": float(args.drawdown_max),
            "ann_vol_min": float(args.ann_vol_min),
            "initial_value": float(args.initial_value),
        },
        "summary": {
            "grid_count": int(len(rows)),
            "positive_core_metric_count": int(len(positive_rows)),
            "positive_core_metric_rate": None if not rows else float(len(positive_rows) / len(rows)),
            "best_by_delta_sharpe": best,
        },
        "rows": rows_sorted,
        "decision": {
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "advisory_import_allowed": True,
            "reason": "Parameter robustness is validation evidence only; live use still requires forward triggered and realized after-cost evidence.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 2609.08106 Latest Target-Weight Replay Param Sweep",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- grid_count: `{summary['grid_count']}`",
        f"- positive_core_metric_count: `{summary['positive_core_metric_count']}`",
        f"- positive_core_metric_rate: `{summary['positive_core_metric_rate']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| threshold | shift_weight | cost_bps | events | d_return | d_sharpe | d_max_dd | d_turnover | positive |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {threshold} | {shift_weight} | {cost_bps} | {event_count} | {delta_total_return} | {delta_sharpe} | {delta_max_drawdown} | {delta_total_turnover} | `{positive_core_metrics}` |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Use this as parameter-robustness evidence only.",
            "- Keep 2609.08106 in advisory/reporting and forward shadow.",
            "- Do not change latest GroupA++ target weights, execution plans, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(replay.DEFAULT_DB))
    parser.add_argument("--target-weights", default=str(replay.DEFAULT_TARGET_WEIGHTS))
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--thresholds", default="1.5,1.75,2.0,2.25,2.5")
    parser.add_argument("--shift-weights", default="0.01,0.02,0.03,0.04,0.05")
    parser.add_argument("--cost-bps-values", default="5,10,20,40")
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
    parser.add_argument("--drawdown-max", type=float, default=-0.03)
    parser.add_argument("--ann-vol-min", type=float, default=0.35)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Sweep JSON: {output}")
    print(f"Sweep Markdown: {markdown}")


if __name__ == "__main__":
    main()
