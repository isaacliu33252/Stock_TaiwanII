#!/usr/bin/env python3
"""Sweep HARLF/latest monthly blend weights.

This is research-only. It blends monthly outcome returns from the compound
HARLF comparison report and asks whether a small HARLF sleeve can improve total
return without exceeding latest/golden max drawdown.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPARISON = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_vs_latest_strategy_comparison.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_latest_blend_sweep/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _metrics(returns: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {"n": 0}
    equity = (1.0 + clean).cumprod()
    peak = equity.cummax()
    std = float(clean.std(ddof=0))
    return {
        "n": int(len(clean)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "mean_monthly_return": float(clean.mean()),
        "monthly_volatility": std,
        "annualized_sharpe": float(clean.mean() / std * math.sqrt(12)) if std > 1e-12 else float(clean.mean() * 12),
        "max_drawdown": float((equity / peak - 1.0).min()),
        "positive_month_rate": float((clean > 0.0).mean()),
        "worst_month": float(clean.min()),
        "best_month": float(clean.max()),
    }


def _returns_frame(comparison: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(comparison.get("monthly_returns") or [])
    required = {"month", "harlf_compound", "latest_strategy", "golden01_0531"}
    if frame.empty or required - set(frame.columns):
        return pd.DataFrame(columns=sorted(required))
    frame["month"] = frame["month"].astype(str)
    for column in ["harlf_compound", "latest_strategy", "golden01_0531"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["harlf_compound", "latest_strategy", "golden01_0531"]).set_index("month")


def build_blend_sweep(
    *,
    comparison: dict[str, Any],
    step: float = 0.01,
    max_drawdown_tolerance: float = 1e-6,
) -> dict[str, Any]:
    frame = _returns_frame(comparison)
    if frame.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_latest_blend_sweep",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "policy": "research_only_harlf_latest_blend_no_weight_change",
            "blocking_reasons": ["missing_comparison_monthly_returns"],
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "promotion_ready": False,
            },
        }

    latest_metrics = _metrics(frame["latest_strategy"])
    golden_metrics = _metrics(frame["golden01_0531"])
    drawdown_floor = min(latest_metrics["max_drawdown"], golden_metrics["max_drawdown"]) - max_drawdown_tolerance
    latest_return = latest_metrics["total_return"]
    rows: list[dict[str, Any]] = []
    count = int(round(1.0 / step))
    for idx in range(count + 1):
        harlf_weight = round(idx * step, 10)
        latest_weight = 1.0 - harlf_weight
        returns = harlf_weight * frame["harlf_compound"] + latest_weight * frame["latest_strategy"]
        metrics = _metrics(returns)
        rows.append(
            {
                "harlf_weight": harlf_weight,
                "latest_weight": latest_weight,
                "metrics": metrics,
                "beats_latest_total_return": metrics["total_return"] > latest_return,
                "not_worse_than_latest_golden_drawdown": metrics["max_drawdown"] >= drawdown_floor,
            }
        )

    viable = [
        row
        for row in rows
        if row["beats_latest_total_return"] and row["not_worse_than_latest_golden_drawdown"]
    ]
    best = max(viable, key=lambda row: (row["harlf_weight"], row["metrics"]["total_return"])) if viable else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_latest_blend_sweep",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_harlf_latest_blend_no_weight_change",
        "parameters": {
            "step": step,
            "max_drawdown_tolerance": max_drawdown_tolerance,
            "drawdown_floor": drawdown_floor,
        },
        "baseline_metrics": {
            "latest_strategy": latest_metrics,
            "golden01_0531": golden_metrics,
            "harlf_compound": _metrics(frame["harlf_compound"]),
        },
        "rows": rows,
        "best_viable_blend": best,
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "found_blend_ready_for_latest_strategy_review": best is not None,
            "candidate_harlf_weight": None if best is None else best["harlf_weight"],
            "candidate_latest_weight": None if best is None else best["latest_weight"],
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_latest_blend_sweep_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--step", type=float, default=0.01)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_blend_sweep(comparison=_load_json(_resolve(args.comparison)), step=args.step)
    report["inputs"] = {"comparison": str(_resolve(args.comparison))}
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "best_viable_blend": report.get("best_viable_blend"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
