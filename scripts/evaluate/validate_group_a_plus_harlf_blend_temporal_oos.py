#!/usr/bin/env python3
"""Temporal OOS validation for the HARLF/latest blend.

The 8% HARLF sleeve was selected on the aligned monthly comparison window.
This validator repeats the blend-selection rule on an earlier training segment
and evaluates only the later holdout segment. It is intentionally conservative:
if the training segment cannot select a viable HARLF sleeve under the original
drawdown constraint, OOS validation fails.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_blend_temporal_oos_validation.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_blend_temporal_oos_validation/history"


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
    return frame.dropna(subset=["harlf_compound", "latest_strategy", "golden01_0531"]).set_index("month").sort_index()


def _sweep_train(frame: pd.DataFrame, *, step: float, max_drawdown_tolerance: float) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    latest_metrics = _metrics(frame["latest_strategy"])
    golden_metrics = _metrics(frame["golden01_0531"])
    drawdown_floor = min(latest_metrics["max_drawdown"], golden_metrics["max_drawdown"]) - max_drawdown_tolerance
    latest_return = latest_metrics["total_return"]
    rows: list[dict[str, Any]] = []
    for idx in range(int(round(1.0 / step)) + 1):
        harlf_weight = round(idx * step, 10)
        returns = harlf_weight * frame["harlf_compound"] + (1.0 - harlf_weight) * frame["latest_strategy"]
        metrics = _metrics(returns)
        row = {
            "harlf_weight": harlf_weight,
            "latest_weight": 1.0 - harlf_weight,
            "metrics": metrics,
            "beats_latest_total_return": metrics["total_return"] > latest_return,
            "not_worse_than_latest_golden_drawdown": metrics["max_drawdown"] >= drawdown_floor,
        }
        rows.append(row)
    viable = [row for row in rows if row["beats_latest_total_return"] and row["not_worse_than_latest_golden_drawdown"]]
    best = max(viable, key=lambda row: (row["harlf_weight"], row["metrics"]["total_return"])) if viable else None
    return rows, best


def build_temporal_oos_validation(
    *,
    comparison: dict[str, Any],
    holdout_months: int = 3,
    step: float = 0.01,
    max_drawdown_tolerance: float = 1e-6,
) -> dict[str, Any]:
    blockers: list[str] = []
    frame = _returns_frame(comparison)
    if frame.empty:
        blockers.append("missing_comparison_monthly_returns")
    if len(frame) <= holdout_months:
        blockers.append("insufficient_months_for_temporal_oos")
    if blockers:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_blend_temporal_oos_validation",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "blocking_reasons": sorted(set(blockers)),
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "oos_window_available": False,
                "temporal_oos_passed": False,
                "promotion_ready": False,
            },
        }

    train = frame.iloc[:-holdout_months]
    holdout = frame.iloc[-holdout_months:]
    sweep_rows, best = _sweep_train(train, step=step, max_drawdown_tolerance=max_drawdown_tolerance)
    if best is None:
        blockers.append("no_train_viable_harlf_blend_under_drawdown_constraint")
        selected_weight = None
        holdout_metrics = {}
        holdout_decision = {
            "beats_latest_total_return": False,
            "not_worse_than_latest_golden_drawdown": False,
        }
    else:
        selected_weight = float(best["harlf_weight"])
        blend_returns = selected_weight * holdout["harlf_compound"] + (1.0 - selected_weight) * holdout["latest_strategy"]
        holdout_metrics = {
            "selected_blend": _metrics(blend_returns),
            "latest_strategy": _metrics(holdout["latest_strategy"]),
            "golden01_0531": _metrics(holdout["golden01_0531"]),
            "harlf_compound": _metrics(holdout["harlf_compound"]),
        }
        latest_m = holdout_metrics["latest_strategy"]
        golden_m = holdout_metrics["golden01_0531"]
        blend_m = holdout_metrics["selected_blend"]
        drawdown_floor = min(latest_m["max_drawdown"], golden_m["max_drawdown"]) - max_drawdown_tolerance
        holdout_decision = {
            "beats_latest_total_return": blend_m["total_return"] > latest_m["total_return"],
            "not_worse_than_latest_golden_drawdown": blend_m["max_drawdown"] >= drawdown_floor,
        }
        if not all(holdout_decision.values()):
            blockers.append("selected_blend_failed_holdout_performance_gate")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_blend_temporal_oos_validation",
        "status": "available" if not blockers else "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_temporal_oos_no_weight_change",
        "parameters": {
            "holdout_months": holdout_months,
            "step": step,
            "max_drawdown_tolerance": max_drawdown_tolerance,
        },
        "train_window": {"months": list(train.index), "n": int(len(train))},
        "holdout_window": {"months": list(holdout.index), "n": int(len(holdout))},
        "train_best_viable_blend": best,
        "train_sweep_rows": sweep_rows,
        "holdout_metrics": holdout_metrics,
        "holdout_decision": holdout_decision,
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "oos_window_available": True,
            "selected_harlf_weight": selected_weight,
            "temporal_oos_passed": not blockers,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_blend_temporal_oos_validation_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--holdout-months", type=int, default=3)
    parser.add_argument("--step", type=float, default=0.01)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_temporal_oos_validation(
        comparison=_load_json(_resolve(args.comparison)),
        holdout_months=args.holdout_months,
        step=args.step,
    )
    report["inputs"] = {"comparison": str(_resolve(args.comparison))}
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report.get("blocking_reasons"),
                "train_best_viable_blend": report.get("train_best_viable_blend"),
                "holdout_window": report.get("holdout_window"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
