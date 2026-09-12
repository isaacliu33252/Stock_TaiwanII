#!/usr/bin/env python3
"""Sweep all AEGIS-lite shadow variants for GroupA+.

Runs research-only combinations of VAM gate and Sortino reference allocation.
The paper's minimax-correlation basket construction is intentionally excluded
because GroupA+ does not have a sufficiently large, diverse candidate universe.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import _metrics
from group_a_plus.runners.latest import run_latest
from scripts.evaluate.backtest_group_a_plus_aegis_lite_shadow import (
    DEFAULT_DB,
    _load_prices,
    _weights_from_latest_frame,
    build_shadow_weights,
    simulate_weight_curve,
)


DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/group_a_plus_aegis_lite_shadow_sweep_latest.json"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "results/group_a_plus_aegis_lite_shadow_sweep_latest.csv"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/aegis_lite_shadow_sweep.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _variant_grid() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = [
        {
            "name": "vam_only_63d",
            "enable_vam": True,
            "enable_sortino": False,
            "vam_lookback_days": 63,
            "sortino_lookback_days": 63,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "vam_only_126d",
            "enable_vam": True,
            "enable_sortino": False,
            "vam_lookback_days": 126,
            "sortino_lookback_days": 63,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "sortino_only_63d_monthly",
            "enable_vam": False,
            "enable_sortino": True,
            "vam_lookback_days": 126,
            "sortino_lookback_days": 63,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "sortino_only_126d_monthly",
            "enable_vam": False,
            "enable_sortino": True,
            "vam_lookback_days": 126,
            "sortino_lookback_days": 126,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "vam126_sortino63_monthly",
            "enable_vam": True,
            "enable_sortino": True,
            "vam_lookback_days": 126,
            "sortino_lookback_days": 63,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "vam63_sortino63_monthly",
            "enable_vam": True,
            "enable_sortino": True,
            "vam_lookback_days": 63,
            "sortino_lookback_days": 63,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "vam126_sortino126_monthly",
            "enable_vam": True,
            "enable_sortino": True,
            "vam_lookback_days": 126,
            "sortino_lookback_days": 126,
            "sortino_reopt_frequency": "monthly",
        },
        {
            "name": "vam126_sortino63_daily",
            "enable_vam": True,
            "enable_sortino": True,
            "vam_lookback_days": 126,
            "sortino_lookback_days": 63,
            "sortino_reopt_frequency": "daily",
        },
    ]
    return variants


def _score(row: dict[str, Any]) -> float:
    return float(
        row["delta_sortino_ratio"]
        + 0.50 * row["delta_sharpe_ratio"]
        + 2.00 * row["delta_max_drawdown"]
        + 0.25 * (row["delta_final_value"] / max(row["baseline_final_value"], 1e-12))
    )


def run_sweep(
    *,
    start: str,
    end: str,
    initial_value: float,
    db_path: Path,
    max_00631l_to_0050_vol_ratio: float,
    max_abs_deviation: float,
    max_single_asset_weight: float,
    turnover_penalty: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    latest_report, latest_frame = run_latest(start, end, initial_value, db_path)
    prices = _load_prices(db_path, start, end)
    baseline_weights = _weights_from_latest_frame(latest_frame, latest_report).reindex(prices.index).ffill()
    baseline_curve, baseline_exec = simulate_weight_curve(prices, baseline_weights, initial_value=initial_value)
    baseline_metrics = _metrics(baseline_curve, initial_value)
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for variant in _variant_grid():
        shadow_weights, metadata = build_shadow_weights(
            prices,
            baseline_weights,
            enable_vam=bool(variant["enable_vam"]),
            enable_sortino=bool(variant["enable_sortino"]),
            vam_lookback_days=int(variant["vam_lookback_days"]),
            sortino_lookback_days=int(variant["sortino_lookback_days"]),
            max_00631l_to_0050_vol_ratio=max_00631l_to_0050_vol_ratio,
            max_abs_deviation=max_abs_deviation,
            max_single_asset_weight=max_single_asset_weight,
            turnover_penalty=turnover_penalty,
            sortino_reopt_frequency=str(variant["sortino_reopt_frequency"]),
        )
        curve, execution = simulate_weight_curve(prices, shadow_weights, initial_value=initial_value)
        metrics = _metrics(curve, initial_value)
        row = {
            "name": variant["name"],
            **variant,
            "baseline_final_value": float(baseline_metrics["final_value"]),
            "final_value": float(metrics["final_value"]),
            "delta_final_value": float(metrics["final_value"] - baseline_metrics["final_value"]),
            "annual_return": float(metrics["annual_return"]),
            "delta_annual_return": float(metrics["annual_return"] - baseline_metrics["annual_return"]),
            "sharpe_ratio": float(metrics["sharpe_ratio"]),
            "delta_sharpe_ratio": float(metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "sortino_ratio": float(metrics["sortino_ratio"]),
            "delta_sortino_ratio": float(metrics["sortino_ratio"] - baseline_metrics["sortino_ratio"]),
            "max_drawdown": float(metrics["max_drawdown"]),
            "delta_max_drawdown": float(metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
            "rebalance_count": int(execution["rebalance_count"]),
            "transaction_cost": float(execution["transaction_cost"]),
            "turnover_value": float(execution["turnover_value"]),
            "vam_block_days": int(metadata["vam_block_days"]),
            "sortino_updates": int(metadata["sortino_updates"]),
        }
        row["score"] = _score(row)
        row["promotion_ready"] = bool(
            row["delta_final_value"] > 0.0
            and row["delta_sortino_ratio"] > 0.0
            and row["delta_max_drawdown"] >= -0.01
        )
        rows.append(row)
        details[variant["name"]] = {"metrics": metrics, "execution": execution, "metadata": metadata}
    frame = pd.DataFrame(rows).sort_values(["promotion_ready", "score"], ascending=[False, False]).reset_index(drop=True)
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_aegis_lite_shadow_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_weight_change",
        "codex_note": "Codex 2026-08-13: all AEGIS-lite variants swept; active latest strategy is unchanged.",
        "inputs": {
            "db": str(db_path),
            "window": {"start": start, "end": end, "rows": int(len(prices))},
            "initial_value": float(initial_value),
            "active_strategy_id": latest_report.get("active_strategy_id") or latest_report.get("strategy"),
            "common_params": {
                "max_00631l_to_0050_vol_ratio": float(max_00631l_to_0050_vol_ratio),
                "max_abs_deviation": float(max_abs_deviation),
                "max_single_asset_weight": float(max_single_asset_weight),
                "turnover_penalty": float(turnover_penalty),
            },
        },
        "baseline": {"metrics": baseline_metrics, "execution": baseline_exec},
        "ranked_variants": frame.to_dict(orient="records"),
        "details": details,
        "decision": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "promotion_ready": bool(frame["promotion_ready"].any()),
            "recommended_use": "promotion_gate_input_only" if bool(frame["promotion_ready"].any()) else "keep_research_only",
        },
    }
    return report, frame


def _write_markdown(report: dict[str, Any], frame: pd.DataFrame, path: Path) -> None:
    lines = [
        "# GroupA+ AEGIS-lite Shadow Sweep",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Window: `{report['inputs']['window']['start']}` ~ `{report['inputs']['window']['end']}`",
        f"- Policy: `{report['policy']}`",
        f"- Any promotion ready: `{report['decision']['promotion_ready']}`",
        "",
        "## Ranked Variants",
        "",
        "| Rank | Variant | Final Delta | Sortino Delta | Sharpe Delta | MaxDD Delta | Promotion |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for idx, row in frame.iterrows():
        lines.append(
            f"| {idx + 1} | `{row['name']}` | {row['delta_final_value']:.2f} | "
            f"{row['delta_sortino_ratio']:.6f} | {row['delta_sharpe_ratio']:.6f} | "
            f"{row['delta_max_drawdown']:.6f} | `{bool(row['promotion_ready'])}` |"
        )
    lines.extend(
        [
            "",
            "Codex 2026-08-13: research-only sweep; no active strategy or golden1_0531 artifact is changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], frame: pd.DataFrame, *, output_json: Path, output_csv: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    frame.to_csv(output_csv, index=False, encoding="utf-8-sig")
    _write_markdown(report, frame, output_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-00631l-to-0050-vol-ratio", type=float, default=2.25)
    parser.add_argument("--max-abs-deviation", type=float, default=0.15)
    parser.add_argument("--max-single-asset-weight", type=float, default=0.85)
    parser.add_argument("--turnover-penalty", type=float, default=0.02)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, frame = run_sweep(
        start=args.start,
        end=args.end,
        initial_value=float(args.initial_value),
        db_path=_resolve(args.db),
        max_00631l_to_0050_vol_ratio=float(args.max_00631l_to_0050_vol_ratio),
        max_abs_deviation=float(args.max_abs_deviation),
        max_single_asset_weight=float(args.max_single_asset_weight),
        turnover_penalty=float(args.turnover_penalty),
    )
    write_outputs(
        report,
        frame,
        output_json=_resolve(args.output_json),
        output_csv=_resolve(args.output_csv),
        output_md=_resolve(args.output_md),
    )
    best = frame.iloc[0].to_dict()
    print(
        json.dumps(
            {
                "promotion_ready": report["decision"]["promotion_ready"],
                "best_variant": best["name"],
                "best_delta_final_value": best["delta_final_value"],
                "best_delta_sortino": best["delta_sortino_ratio"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
