#!/usr/bin/env python3
"""Narrow Taiwan-ETF sensitivity for arXiv:2605.20636/A21.19.

Research-only. This compares continuous defensive-tilt endpoints inside the
GroupA+ Taiwan ETF universe; it does not alter live weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_a2119_continuous_defensive_tilt_shadow import evaluate

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_20636_taiwan_etf_sensitivity.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2605_20636_taiwan_etf_sensitivity.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_20636_taiwan_etf_sensitivity/history"

ENDPOINTS: dict[str, dict[str, float]] = {
    "0050_cash": {"0050.TW": 0.40, "cash": 0.60},
    "0050_00679b_cash": {"0050.TW": 0.40, "00679B.TWO": 0.30, "cash": 0.30},
    "0050_00631l_cash": {"0050.TW": 0.50, "00631L.TW": 0.10, "cash": 0.40},
}

WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("full_available", "2017-01-03", "2026-08-28"),
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("rate_hike_2022", "2022-01-03", "2022-12-30"),
    ("recent_2024_2026", "2024-01-02", "2026-08-28"),
)


def _score_row(row: dict[str, Any]) -> dict[str, Any]:
    deltas = row["metric_deltas"]
    cont_exec = row["continuous_execution"]
    base_exec = row["baseline_execution"]
    initial_value = float(row.get("parameters", {}).get("initial_value", 1_000_000.0))
    continuous_turnover = float(cont_exec.get("turnover", cont_exec.get("turnover_value", 0.0) / initial_value))
    baseline_turnover = float(base_exec.get("turnover", base_exec.get("turnover_value", 0.0) / initial_value))
    return {
        "label": row["label"],
        "endpoint": row["endpoint"],
        "delta_final_value": float(deltas["final_value"]),
        "delta_annual_return": float(deltas["annual_return"]),
        "delta_sharpe_ratio": float(deltas["sharpe_ratio"]),
        "delta_max_drawdown": float(deltas["max_drawdown"]),
        "continuous_turnover": continuous_turnover,
        "baseline_turnover": baseline_turnover,
        "turnover_delta": continuous_turnover - baseline_turnover,
        "rebalance_count_delta": int(cont_exec.get("rebalance_count", 0)) - int(base_exec.get("rebalance_count", 0)),
        "triple_pass": (
            float(deltas["final_value"]) > 0.0
            and float(deltas["sharpe_ratio"]) > 0.0
            and float(deltas["max_drawdown"]) >= 0.0
        ),
    }


def build_sensitivity(
    *,
    db_path: Path = DB_PATH,
    initial_value: float = 1_000_000.0,
    no_trade_band: float = 0.005,
    warmup_days: int = 756,
    cost_multiplier: float = 1.0,
    windows: tuple[tuple[str, str, str], ...] = WINDOWS,
    endpoints: dict[str, dict[str, float]] = ENDPOINTS,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []
    for label, start, end in windows:
        for endpoint_name, endpoint_weights in endpoints.items():
            result = evaluate(
                start=start,
                end=end,
                initial_value=initial_value,
                db_path=db_path,
                no_trade_band=no_trade_band,
                cost_multiplier=cost_multiplier,
                warmup_days=warmup_days,
                defensive_endpoint=endpoint_weights,
                defensive_endpoint_name=endpoint_name,
            )
            result["label"] = label
            result["endpoint"] = endpoint_name
            rows.append(result)
            scored.append(_score_row(result))

    endpoint_summary: dict[str, dict[str, Any]] = {}
    for endpoint_name in endpoints:
        subset = [row for row in scored if row["endpoint"] == endpoint_name]
        endpoint_summary[endpoint_name] = {
            "windows": len(subset),
            "triple_pass_windows": sum(1 for row in subset if row["triple_pass"]),
            "avg_delta_final_value": sum(row["delta_final_value"] for row in subset) / len(subset),
            "avg_delta_sharpe_ratio": sum(row["delta_sharpe_ratio"] for row in subset) / len(subset),
            "min_delta_max_drawdown": min(row["delta_max_drawdown"] for row in subset),
            "avg_turnover_delta": sum(row["turnover_delta"] for row in subset) / len(subset),
        }

    best_endpoint = max(
        endpoint_summary,
        key=lambda name: (
            endpoint_summary[name]["triple_pass_windows"],
            endpoint_summary[name]["avg_delta_final_value"],
            endpoint_summary[name]["avg_delta_sharpe_ratio"],
        ),
    )
    promote = (
        endpoint_summary[best_endpoint]["triple_pass_windows"] == len(windows)
        and endpoint_summary[best_endpoint]["min_delta_max_drawdown"] >= 0.0
        and endpoint_summary[best_endpoint]["avg_turnover_delta"] <= 0.0
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_20636_taiwan_etf_sensitivity",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "promotable" if promote else "blocked_for_live_promotion",
        "research_only": True,
        "production_effect": "none",
        "source_paper": "2605.20636v2",
        "method": "A21.19 continuous defensive tilt with custom Taiwan ETF defensive endpoints",
        "parameters": {
            "initial_value": initial_value,
            "no_trade_band": no_trade_band,
            "warmup_days": warmup_days,
            "cost_multiplier": cost_multiplier,
        },
        "endpoints": endpoints,
        "windows": [{"label": label, "start": start, "end": end} for label, start, end in windows],
        "scored_rows": scored,
        "endpoint_summary": endpoint_summary,
        "best_endpoint": best_endpoint,
        "decision": {
            "taiwan_etf_backtest_useful": True,
            "groupa_plus_importability_tested": True,
            "promote_to_live": promote,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "raw_rows": rows,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 2605.20636 Taiwan ETF Sensitivity",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Decision",
        "",
        f"- Taiwan ETF backtest useful: `{payload['decision']['taiwan_etf_backtest_useful']}`",
        f"- Promote to live: `{payload['decision']['promote_to_live']}`",
        "- Production effect: `none`",
        "- Do not change latest strategy target weights.",
        "",
        "## Endpoint Summary",
        "",
        "| Endpoint | Triple-pass windows | Avg final value delta | Avg Sharpe delta | Min MaxDD delta | Avg turnover delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for endpoint, summary in payload["endpoint_summary"].items():
        lines.append(
            "| {endpoint} | {tp}/{windows} | {dfv:.2f} | {dsh:.6f} | {dmdd:.6f} | {dto:.6f} |".format(
                endpoint=endpoint,
                tp=summary["triple_pass_windows"],
                windows=summary["windows"],
                dfv=summary["avg_delta_final_value"],
                dsh=summary["avg_delta_sharpe_ratio"],
                dmdd=summary["min_delta_max_drawdown"],
                dto=summary["avg_turnover_delta"],
            )
        )
    lines.extend(
        [
            "",
            "## Window Rows",
            "",
            "| Window | Endpoint | Final value delta | Annual return delta | Sharpe delta | MaxDD delta | Turnover delta | Triple pass |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["scored_rows"]:
        lines.append(
            "| {label} | {endpoint} | {dfv:.2f} | {dar:.6f} | {dsh:.6f} | {dmdd:.6f} | {dto:.6f} | `{tp}` |".format(
                label=row["label"],
                endpoint=row["endpoint"],
                dfv=row["delta_final_value"],
                dar=row["delta_annual_return"],
                dsh=row["delta_sharpe_ratio"],
                dmdd=row["delta_max_drawdown"],
                dto=row["turnover_delta"],
                tp=row["triple_pass"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (history_dir / f"2605_20636_taiwan_etf_sensitivity_{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--no-trade-band", type=float, default=0.005)
    parser.add_argument("--warmup-days", type=int, default=756)
    parser.add_argument("--cost-multiplier", type=float, default=1.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_sensitivity(
        db_path=Path(args.db),
        initial_value=args.initial_value,
        no_trade_band=args.no_trade_band,
        warmup_days=args.warmup_days,
        cost_multiplier=args.cost_multiplier,
    )
    write_outputs(
        payload,
        Path(args.output),
        Path(args.output_md),
        None if args.no_history else Path(args.history_dir),
    )
    print(f"Output: {Path(args.output).resolve()}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "best_endpoint": payload["best_endpoint"],
                "endpoint_summary": payload["endpoint_summary"],
                "promote_to_live": payload["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
