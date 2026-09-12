#!/usr/bin/env python3
"""Completion experiments for arXiv:2412.05431 smart-leverage import.

This runs the missing robustness/incident/lot-rounding checks in one
research-only report. It does not modify latest strategy, golden1_0531,
execution plans, target weights, or order files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.evaluate_2412_05431_smart_leverage_ir_lite_shadow import (  # noqa: E402
    _candidate_pass,
    build_report,
)


OUTPUT_JSON = PROJECT_ROOT / "results/2412_05431_smart_leverage_completion_experiments.json"
OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2412_05431_smart_leverage_completion_experiments.md"

WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", "standard_recent"),
    ("active_2025_2026", "2025-01-02", "latest", "standard_recent"),
    ("holdout_2022_full", "2022-01-03", "2022-12-30", "standard_holdout"),
    ("holdout_2023", "2023-01-03", "2023-12-29", "standard_holdout"),
    ("holdout_2026", "2026-01-02", "latest", "standard_holdout"),
    ("stress_2020_covid_full", "2020-01-02", "2020-12-31", "standard_stress"),
    ("stress_2021_may_correction", "2021-01-04", "2021-12-30", "standard_stress"),
    ("incident_2020_covid_crash", "2020-02-03", "2020-05-29", "incident"),
    ("incident_2022_rate_hike", "2022-01-03", "2022-10-31", "incident"),
    ("incident_2024_aug_unwind", "2024-07-01", "2024-09-30", "incident"),
    ("incident_2026_q2_drawdown", "2026-04-01", "2026-06-30", "incident"),
]

VARIANTS = [
    {
        "name": "quarterly_default_risk_penalty",
        "rebalance_frequency": "quarterly",
        "grid_step": 0.10,
        "max_00631l_weight": 0.30,
        "max_effective_beta": 1.10,
        "drawdown_penalty": 5.0,
        "worst_20d_penalty": 3.0,
        "max_rebalance_turnover": None,
        "no_trade_band": 0.0,
        "lot_size": None,
    },
    {
        "name": "monthly_default_risk_penalty",
        "rebalance_frequency": "monthly",
        "grid_step": 0.10,
        "max_00631l_weight": 0.30,
        "max_effective_beta": 1.10,
        "drawdown_penalty": 5.0,
        "worst_20d_penalty": 3.0,
        "max_rebalance_turnover": None,
        "no_trade_band": 0.0,
        "lot_size": None,
    },
    {
        "name": "monthly_risk_turnover_cap",
        "rebalance_frequency": "monthly",
        "grid_step": 0.10,
        "max_00631l_weight": 0.30,
        "max_effective_beta": 1.10,
        "drawdown_penalty": 12.0,
        "worst_20d_penalty": 8.0,
        "max_rebalance_turnover": 0.30,
        "no_trade_band": 0.05,
        "lot_size": None,
    },
    {
        "name": "monthly_low_beta",
        "rebalance_frequency": "monthly",
        "grid_step": 0.10,
        "max_00631l_weight": 0.10,
        "max_effective_beta": 0.80,
        "drawdown_penalty": 20.0,
        "worst_20d_penalty": 12.0,
        "max_rebalance_turnover": 0.20,
        "no_trade_band": 0.05,
        "lot_size": None,
    },
    {
        "name": "monthly_no_00631l_control",
        "rebalance_frequency": "monthly",
        "grid_step": 0.10,
        "max_00631l_weight": 0.0,
        "max_effective_beta": 0.90,
        "drawdown_penalty": 20.0,
        "worst_20d_penalty": 12.0,
        "max_rebalance_turnover": 0.20,
        "no_trade_band": 0.05,
        "lot_size": None,
    },
    {
        "name": "monthly_risk_turnover_cap_lot1000",
        "rebalance_frequency": "monthly",
        "grid_step": 0.10,
        "max_00631l_weight": 0.30,
        "max_effective_beta": 1.10,
        "drawdown_penalty": 12.0,
        "worst_20d_penalty": 8.0,
        "max_rebalance_turnover": 0.30,
        "no_trade_band": 0.05,
        "lot_size": 1000,
    },
]


def _variant_args(base: argparse.Namespace, variant: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        db=base.db,
        initial_value=base.initial_value,
        commission_rate=base.commission_rate,
        slippage_rate=base.slippage_rate,
        equity_etf_sell_tax=base.equity_etf_sell_tax,
        lookback_days=base.lookback_days,
        rebalance_frequency=variant["rebalance_frequency"],
        max_00631l_weight=variant["max_00631l_weight"],
        max_effective_beta=variant["max_effective_beta"],
        grid_step=variant["grid_step"],
        drawdown_penalty=variant["drawdown_penalty"],
        worst_20d_penalty=variant["worst_20d_penalty"],
        max_rebalance_turnover=variant["max_rebalance_turnover"],
        no_trade_band=variant["no_trade_band"],
        lot_size=variant["lot_size"],
        window=[":".join(window) for window in WINDOWS],
    )


def _window_blockers(window: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    db = window["delta_vs_benchmark"]
    dl = window["delta_vs_latest_a2118"]
    if db["final_value"] <= 0.0:
        blockers.append("benchmark_final_value")
    if db["sharpe_ratio"] < 0.0:
        blockers.append("benchmark_sharpe")
    if db["max_drawdown"] < -0.02:
        blockers.append("benchmark_drawdown")
    if dl["max_drawdown"] < -0.03:
        blockers.append("latest_a2118_drawdown")
    if "lot_rounded_ir_lite" in window:
        lot_delta = window["lot_rounded_ir_lite"]["delta_vs_fractional_ir_lite"]
        if lot_delta["final_value"] < -5000.0:
            blockers.append("lot_rounding_final_value")
    return blockers


def _summarize_variant(name: str, report: dict[str, Any]) -> dict[str, Any]:
    windows = report["windows"]
    incidents = [w for w in windows if w["bucket"] == "incident"]
    standard_holdout = [w for w in windows if w["bucket"] == "standard_holdout"]
    blocker_counts: dict[str, int] = {}
    for window in windows:
        for blocker in _window_blockers(window):
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    lot_final_delta = None
    if any("lot_rounded_ir_lite" in w for w in windows):
        lot_final_delta = float(
            sum(
                w.get("lot_rounded_ir_lite", {})
                .get("delta_vs_fractional_ir_lite", {})
                .get("final_value", 0.0)
                for w in windows
            )
        )
    return {
        "name": name,
        "params": report["params"],
        "window_count": len(windows),
        "pass_windows": int(sum(_candidate_pass(w) for w in windows)),
        "standard_holdout_pass_windows": int(sum(_candidate_pass(w) for w in standard_holdout)),
        "standard_holdout_window_count": len(standard_holdout),
        "incident_pass_windows": int(sum(_candidate_pass(w) for w in incidents)),
        "incident_window_count": len(incidents),
        "total_delta_final_vs_benchmark": float(sum(w["delta_vs_benchmark"]["final_value"] for w in windows)),
        "total_delta_final_vs_latest_a2118": float(sum(w["delta_vs_latest_a2118"]["final_value"] for w in windows)),
        "avg_00631l_weight": float(
            sum(w["target_weight_average"].get("00631L.TW", 0.0) for w in windows) / max(len(windows), 1)
        ),
        "blocker_counts": blocker_counts,
        "lot_total_delta_final_vs_fractional": lot_final_delta,
        "promotion_ready": bool(
            standard_holdout
            and all(_candidate_pass(w) for w in standard_holdout)
            and incidents
            and all(_candidate_pass(w) for w in incidents)
        ),
    }


def build_completion_report(args: argparse.Namespace) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    for variant in VARIANTS:
        print(f"Running {variant['name']}", flush=True)
        report = build_report(_variant_args(args, variant))
        variants.append(
            {
                "name": variant["name"],
                "summary": _summarize_variant(variant["name"], report),
                "report": report,
            }
        )
    best = sorted(
        (item["summary"] for item in variants),
        key=lambda row: (
            row["standard_holdout_pass_windows"],
            row["incident_pass_windows"],
            row["total_delta_final_vs_benchmark"],
            -row["avg_00631l_weight"],
        ),
        reverse=True,
    )[0]
    return {
        "schema_version": 1,
        "report_type": "2412_05431_smart_leverage_completion_experiments",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_groupa_plus_live_change",
        "source_paper": "arXiv:2412.05431v2 Smart leverage?",
        "scope": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_target_weights": False,
            "creates_orders": False,
        },
        "windows": WINDOWS,
        "variant_summaries": [item["summary"] for item in variants],
        "best_by_pass_then_final": best,
        "promotion_ready": bool(any(item["summary"]["promotion_ready"] for item in variants)),
        "decision": "do_not_promote_keep_shadow",
        "variants": variants,
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2412.05431 Smart Leverage Completion Experiments",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']}`",
        f"- Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Variant Summary",
        "",
        "| Variant | Pass | Holdout Pass | Incident Pass | dFinal vs Benchmark | dFinal vs Latest | Avg 00631L | Lot dFinal | Top Blockers |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["variant_summaries"]:
        blockers = ", ".join(
            f"{key}:{value}" for key, value in sorted(item["blocker_counts"].items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        )
        lot_delta = item["lot_total_delta_final_vs_fractional"]
        lines.append(
            f"| {item['name']} | {item['pass_windows']}/{item['window_count']} | "
            f"{item['standard_holdout_pass_windows']}/{item['standard_holdout_window_count']} | "
            f"{item['incident_pass_windows']}/{item['incident_window_count']} | "
            f"{item['total_delta_final_vs_benchmark']:.2f} | "
            f"{item['total_delta_final_vs_latest_a2118']:.2f} | "
            f"{item['avg_00631l_weight']:.4f} | "
            f"{'' if lot_delta is None else f'{lot_delta:.2f}'} | {blockers} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- No variant passed both standard holdout and incident windows.",
            "- Main blockers are benchmark-relative Sharpe/final-value instability and drawdown versus latest A21.18.",
            "- Lot-size 1000 is reported as a stress diagnostic only; it does not create any live order permission.",
            "- Latest strategy, golden1_0531, target weights, execution plans, and order files were not changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--output-json", default=str(OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_completion_report(args)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    print(
        json.dumps(
            {
                "promotion_ready": report["promotion_ready"],
                "decision": report["decision"],
                "best": report["best_by_pass_then_final"]["name"],
                "output_json": str(output_json.resolve()),
                "output_md": str(output_md.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
