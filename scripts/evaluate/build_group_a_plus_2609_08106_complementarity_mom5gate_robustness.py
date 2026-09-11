#!/usr/bin/env python3
"""Parameter robustness for the 2609.08106 mom5-gated complementarity sleeve."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate import backtest_group_a_plus_2609_08106_complementarity_sleeve_shadow as sleeve

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_mom5gate_robustness.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_mom5gate_robustness.md"
WINDOWS = (
    ("2018", "2018-01-02", "2018-12-28"),
    ("2020_covid", "2020-01-02", "2020-12-31"),
    ("2022_rate", "2022-01-03", "2022-10-31"),
    ("2024", "2024-01-02", "2024-12-31"),
    ("2025_2026", "2025-01-02", "2026-09-09"),
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    thresholds = _parse_floats(args.thresholds)
    shifts = _parse_floats(args.shift_weights)
    costs = _parse_floats(args.cost_bps_values)
    for label, start, end in WINDOWS:
        prices = sleeve._load_prices(_resolve(args.db), start, end, args.window + 30)
        scores = sleeve._score_frame(prices, args.window)
        for threshold in thresholds:
            for shift_weight in shifts:
                for cost_bps in costs:
                    sim = sleeve._simulate(
                        prices,
                        scores,
                        start=start,
                        end=end,
                        shift_weight=shift_weight,
                        threshold=threshold,
                        cost_bps=cost_bps,
                        risk_gate="momentum5_weak",
                        momentum_5d_max=args.momentum_5d_max,
                        drawdown_max=args.drawdown_max,
                        ann_vol_min=args.ann_vol_min,
                    )
                    delta = sim["delta_shadow_minus_baseline"]
                    rows.append(
                        {
                            "window": label,
                            "start": start,
                            "end": end,
                            "threshold": threshold,
                            "shift_weight": shift_weight,
                            "cost_bps": cost_bps,
                            "event_count": sim["event_count"],
                            "delta_total_return": delta["total_return"],
                            "delta_sharpe": delta["sharpe_ratio"],
                            "delta_max_drawdown": delta["max_drawdown"],
                            "total_turnover": sim["total_turnover"],
                            "pass": bool(
                                (delta.get("total_return") or 0.0) > 0
                                and (delta.get("sharpe_ratio") or 0.0) > 0
                                and (delta.get("max_drawdown") or 0.0) >= 0
                            ),
                        }
                    )
    combo_rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        for shift_weight in shifts:
            for cost_bps in costs:
                subset = [
                    row
                    for row in rows
                    if row["threshold"] == threshold and row["shift_weight"] == shift_weight and row["cost_bps"] == cost_bps
                ]
                combo_rows.append(
                    {
                        "threshold": threshold,
                        "shift_weight": shift_weight,
                        "cost_bps": cost_bps,
                        "window_count": len(subset),
                        "pass_count": sum(1 for row in subset if row["pass"]),
                        "positive_return_count": sum(1 for row in subset if float(row["delta_total_return"] or 0.0) > 0),
                        "positive_sharpe_count": sum(1 for row in subset if float(row["delta_sharpe"] or 0.0) > 0),
                        "non_worse_drawdown_count": sum(1 for row in subset if float(row["delta_max_drawdown"] or 0.0) >= 0),
                        "avg_delta_total_return": sum(float(row["delta_total_return"] or 0.0) for row in subset) / len(subset),
                        "avg_delta_sharpe": sum(float(row["delta_sharpe"] or 0.0) for row in subset) / len(subset),
                        "avg_delta_max_drawdown": sum(float(row["delta_max_drawdown"] or 0.0) for row in subset) / len(subset),
                        "avg_total_turnover": sum(float(row["total_turnover"] or 0.0) for row in subset) / len(subset),
                    }
                )
    robust = [
        row
        for row in combo_rows
        if row["pass_count"] == row["window_count"]
        and row["positive_return_count"] == row["window_count"]
        and row["positive_sharpe_count"] == row["window_count"]
        and row["non_worse_drawdown_count"] == row["window_count"]
    ]
    best = sorted(robust, key=lambda row: (row["avg_delta_sharpe"], row["avg_delta_total_return"]), reverse=True)[:5]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_complementarity_mom5gate_robustness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_orders_no_live_weight_change",
        "inputs": {
            "db": str(_resolve(args.db)),
            "window": args.window,
            "thresholds": thresholds,
            "shift_weights": shifts,
            "cost_bps_values": costs,
            "risk_gate": "momentum5_weak",
            "momentum_5d_max": args.momentum_5d_max,
        },
        "combos": combo_rows,
        "windows": rows,
        "robust_combo_count": len(robust),
        "top_robust_combos": best,
        "decision": {
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "Parameter screen is positive, but this remains research-only until enough forward daily logging with realized after-cost attribution is accumulated.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.08106 Mom5 Gate Robustness",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- robust_combo_count: `{report['robust_combo_count']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| threshold | shift | cost_bps | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["top_robust_combos"]:
        lines.append(
            "| {threshold:.2f} | {shift:.2%} | {cost:.1f} | {passed}/{count} | {ret:.4%} | {sharpe:.4f} | {mdd:.4%} | {turn:.3f} |".format(
                threshold=row["threshold"],
                shift=row["shift_weight"],
                cost=row["cost_bps"],
                passed=row["pass_count"],
                count=row["window_count"],
                ret=row["avg_delta_total_return"],
                sharpe=row["avg_delta_sharpe"],
                mdd=row["avg_delta_max_drawdown"],
                turn=row["avg_total_turnover"],
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Keep as shadow-only candidate.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.",
            "- No GroupA++ live target-weight changes.",
            "- Next gate: daily forward shadow log with realized after-cost attribution.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(sleeve.DEFAULT_DB))
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--thresholds", default="1.8,2.0,2.2")
    parser.add_argument("--shift-weights", default="0.02,0.03,0.04")
    parser.add_argument("--cost-bps-values", default="10,20")
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
    parser.add_argument("--drawdown-max", type=float, default=-0.03)
    parser.add_argument("--ann-vol-min", type=float, default=0.35)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Robustness JSON: {output}")
    print(f"Robustness Markdown: {markdown}")


if __name__ == "__main__":
    main()
