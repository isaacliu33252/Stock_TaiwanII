#!/usr/bin/env python3
"""Evaluate a train-only conditional HARLF sleeve for latest strategy.

golden01_0531 is fixed as a benchmark and is never modified. This script tests
whether an editable latest-strategy shadow candidate can enable HARLF only when
prior monthly data can select a drawdown-neutral sleeve. It creates no orders.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_conditional_sleeve_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_conditional_sleeve_shadow/history"


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


def _select_weight(train: pd.DataFrame, *, max_harlf_weight: float, step: float, tolerance: float) -> dict[str, Any]:
    latest_metrics = _metrics(train["latest_strategy"])
    golden_metrics = _metrics(train["golden01_0531"])
    drawdown_floor = min(latest_metrics["max_drawdown"], golden_metrics["max_drawdown"]) - tolerance
    rows: list[dict[str, Any]] = []
    for idx in range(int(round(max_harlf_weight / step)) + 1):
        weight = round(idx * step, 10)
        returns = weight * train["harlf_compound"] + (1.0 - weight) * train["latest_strategy"]
        metrics = _metrics(returns)
        row = {
            "harlf_weight": weight,
            "latest_weight": 1.0 - weight,
            "metrics": metrics,
            "beats_latest_total_return": metrics["total_return"] > latest_metrics["total_return"],
            "not_worse_than_latest_golden_drawdown": metrics["max_drawdown"] >= drawdown_floor,
        }
        rows.append(row)
    viable = [row for row in rows if row["harlf_weight"] > 0 and row["beats_latest_total_return"] and row["not_worse_than_latest_golden_drawdown"]]
    best = max(viable, key=lambda row: (row["harlf_weight"], row["metrics"]["total_return"])) if viable else None
    return {"selected": best, "sweep_rows": rows}


def build_conditional_sleeve_shadow(
    *,
    comparison: dict[str, Any],
    warmup_months: int = 4,
    max_harlf_weight: float = 0.10,
    step: float = 0.01,
    max_drawdown_tolerance: float = 1e-6,
) -> dict[str, Any]:
    blockers: list[str] = []
    frame = _returns_frame(comparison)
    if frame.empty:
        blockers.append("missing_comparison_monthly_returns")
    if len(frame) <= warmup_months:
        blockers.append("insufficient_months_for_conditional_sleeve")
    if blockers:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_conditional_sleeve_shadow",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "blocking_reasons": blockers,
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "candidate_ready_for_latest_strategy_review": False,
                "promotion_ready": False,
            },
        }

    decisions: list[dict[str, Any]] = []
    realized: list[float] = []
    for idx, (month, row) in enumerate(frame.iterrows()):
        if idx < warmup_months:
            selected_weight = 0.0
            reason = "warmup"
            train_result = None
        else:
            train = frame.iloc[:idx]
            train_result = _select_weight(
                train,
                max_harlf_weight=max_harlf_weight,
                step=step,
                tolerance=max_drawdown_tolerance,
            )
            selected = train_result["selected"]
            selected_weight = 0.0 if selected is None else float(selected["harlf_weight"])
            reason = "no_train_viable_drawdown_neutral_sleeve" if selected is None else "train_viable_sleeve_selected"
        ret = selected_weight * float(row["harlf_compound"]) + (1.0 - selected_weight) * float(row["latest_strategy"])
        realized.append(ret)
        decisions.append(
            {
                "month": month,
                "harlf_weight": selected_weight,
                "latest_weight": 1.0 - selected_weight,
                "realized_return": ret,
                "latest_return": float(row["latest_strategy"]),
                "harlf_return": float(row["harlf_compound"]),
                "reason": reason,
                "train_selected": None if train_result is None else train_result["selected"],
            }
        )

    candidate_returns = pd.Series(realized, index=frame.index)
    metrics = {
        "conditional_sleeve": _metrics(candidate_returns),
        "latest_strategy": _metrics(frame["latest_strategy"]),
        "golden01_0531": _metrics(frame["golden01_0531"]),
        "harlf_compound": _metrics(frame["harlf_compound"]),
    }
    candidate = metrics["conditional_sleeve"]
    latest = metrics["latest_strategy"]
    golden = metrics["golden01_0531"]
    beats_latest = candidate["total_return"] > latest["total_return"]
    drawdown_ok = candidate["max_drawdown"] >= min(latest["max_drawdown"], golden["max_drawdown"]) - max_drawdown_tolerance
    nonzero_months = sum(1 for row in decisions if row["harlf_weight"] > 0)
    ready = bool(beats_latest and drawdown_ok and nonzero_months > 0)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_conditional_sleeve_shadow",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_latest_strategy_shadow_no_weight_change",
        "parameters": {
            "warmup_months": warmup_months,
            "max_harlf_weight": max_harlf_weight,
            "step": step,
            "max_drawdown_tolerance": max_drawdown_tolerance,
        },
        "metrics": metrics,
        "monthly_decisions": decisions,
        "nonzero_harlf_months": nonzero_months,
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "beats_latest_total_return": beats_latest,
            "not_worse_than_latest_golden_drawdown": drawdown_ok,
            "candidate_ready_for_latest_strategy_review": ready,
            "promotion_ready": False,
        },
        "recommendation": (
            "Do not promote this conditional HARLF sleeve; train-only drawdown gating disables HARLF "
            "for all evaluated months, so it adds no latest-strategy edge."
            if nonzero_months == 0
            else "Review only if it beats latest without worsening drawdown."
        ),
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_conditional_sleeve_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--warmup-months", type=int, default=4)
    parser.add_argument("--max-harlf-weight", type=float, default=0.10)
    parser.add_argument("--step", type=float, default=0.01)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_conditional_sleeve_shadow(
        comparison=_load_json(_resolve(args.comparison)),
        warmup_months=args.warmup_months,
        max_harlf_weight=args.max_harlf_weight,
        step=args.step,
    )
    report["inputs"] = {"comparison": str(_resolve(args.comparison))}
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "nonzero_harlf_months": report.get("nonzero_harlf_months"),
                "metrics": report.get("metrics"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
