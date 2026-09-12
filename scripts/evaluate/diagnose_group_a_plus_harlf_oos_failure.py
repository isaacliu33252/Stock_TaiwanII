#!/usr/bin/env python3
"""Diagnose why the HARLF/latest sleeve failed temporal OOS.

This diagnostic is research-only. It explains the temporal OOS rejection and
checks whether a future latest-strategy candidate could be redesigned. It does
not change golden01_0531 or latest strategy weights.
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
DEFAULT_MAPPED = PROJECT_ROOT / "report/group_a_plus/latest/harlf_etf_mapped_shadow.json"
DEFAULT_TEMPORAL_OOS = PROJECT_ROOT / "report/group_a_plus/latest/harlf_blend_temporal_oos_validation.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_oos_failure_diagnosis.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_oos_failure_diagnosis/history"


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


def _drawdown_by_month(returns: pd.Series) -> pd.DataFrame:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    equity = (1.0 + clean).cumprod()
    peak = equity.cummax()
    return pd.DataFrame({"return": clean, "equity": equity, "drawdown": equity / peak - 1.0})


def _branch_frame(mapped_shadow: dict[str, Any], mode: str) -> pd.DataFrame:
    rows = ((mapped_shadow.get("variants") or {}).get(mode) or {}).get("branch_returns") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame()
    frame["month"] = frame["month"].astype(str)
    frame["branch"] = frame["branch"].astype(str)
    frame["net_return"] = pd.to_numeric(frame["net_return"], errors="coerce")
    return frame.dropna(subset=["net_return"])


def build_diagnosis(
    *,
    comparison: dict[str, Any],
    mapped_shadow: dict[str, Any],
    temporal_oos: dict[str, Any],
    mapping_mode: str = "drop_2330_renormalize",
) -> dict[str, Any]:
    blockers: list[str] = []
    frame = _returns_frame(comparison)
    if frame.empty:
        blockers.append("missing_comparison_monthly_returns")
    holdout_months = list((temporal_oos.get("holdout_window") or {}).get("months") or [])
    if not holdout_months:
        blockers.append("missing_temporal_oos_holdout_window")
    if blockers:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_oos_failure_diagnosis",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "blocking_reasons": blockers,
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "promotion_ready": False,
            },
        }

    train = frame.loc[[month for month in frame.index if month not in set(holdout_months)]]
    holdout = frame.loc[[month for month in frame.index if month in set(holdout_months)]]
    latest_metrics = _metrics(train["latest_strategy"])
    drawdown_floor = min(latest_metrics["max_drawdown"], _metrics(train["golden01_0531"])["max_drawdown"])
    sleeve_rows: list[dict[str, Any]] = []
    for weight in [0.0, 0.01, 0.02, 0.05, 0.08, 0.10]:
        returns = weight * train["harlf_compound"] + (1.0 - weight) * train["latest_strategy"]
        metrics = _metrics(returns)
        dd = _drawdown_by_month(returns)
        worst_month = str(dd["drawdown"].idxmin()) if not dd.empty else None
        sleeve_rows.append(
            {
                "harlf_weight": weight,
                "metrics": metrics,
                "beats_latest_total_return": metrics["total_return"] > latest_metrics["total_return"],
                "not_worse_than_latest_golden_drawdown": metrics["max_drawdown"] >= drawdown_floor - 1e-6,
                "worst_drawdown_month": worst_month,
                "worst_drawdown": None if worst_month is None else float(dd.loc[worst_month, "drawdown"]),
            }
        )

    monthly_rows = []
    for month, row in train.iterrows():
        monthly_rows.append(
            {
                "month": month,
                "latest_strategy": float(row["latest_strategy"]),
                "harlf_compound": float(row["harlf_compound"]),
                "harlf_minus_latest": float(row["harlf_compound"] - row["latest_strategy"]),
                "is_harlf_drawdown_worse_month": bool(row["harlf_compound"] < row["latest_strategy"] and row["latest_strategy"] < 0),
            }
        )
    branch = _branch_frame(mapped_shadow, mapping_mode)
    branch_pivot: dict[str, Any] = {}
    if not branch.empty:
        pivot = branch.pivot_table(index="month", columns="branch", values="net_return", aggfunc="last")
        selected_months = [month for month in train.index if month in pivot.index]
        for branch_name in ["market_only", "sentiment_only", "combined", "equal_weight"]:
            if branch_name in pivot.columns:
                branch_pivot[branch_name] = _metrics(pivot.loc[selected_months, branch_name])
    blocker_months = [
        row["month"]
        for row in monthly_rows
        if row["is_harlf_drawdown_worse_month"]
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_oos_failure_diagnosis",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_diagnosis_no_weight_change",
        "mapping_mode": mapping_mode,
        "train_window": {"months": list(train.index), "n": int(len(train))},
        "holdout_window": {"months": list(holdout.index), "n": int(len(holdout))},
        "temporal_oos_blocking_reasons": temporal_oos.get("blocking_reasons") or [],
        "train_drawdown_floor": drawdown_floor,
        "sleeve_sensitivity": sleeve_rows,
        "train_monthly_deltas": monthly_rows,
        "branch_metrics_on_train_window": branch_pivot,
        "primary_failure": {
            "reason": "positive_harlf_sleeve_improves_return_but_immediately_worsens_drawdown_gate",
            "drawdown_gate_blocker_months": blocker_months,
            "minimum_positive_weight_tested": 0.01,
            "minimum_positive_weight_passed_drawdown_gate": any(
                row["harlf_weight"] > 0 and row["not_worse_than_latest_golden_drawdown"]
                for row in sleeve_rows
            ),
        },
        "latest_strategy_candidate_implication": {
            "fixed_harlf_sleeve_recommended": False,
            "conditional_harlf_sleeve_research_allowed": True,
            "candidate_rules_to_test_next": [
                "block HARLF sleeve in months where prior HARLF branch or latest strategy drawdown gate is already stressed",
                "cap HARLF sleeve below 1% unless drawdown-neutral proof exists",
                "use HARLF only after a separate train-only gate confirms drawdown does not worsen",
            ],
        },
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "current_8pct_sleeve_rejected": True,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_oos_failure_diagnosis_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--mapped-shadow", default=str(DEFAULT_MAPPED))
    parser.add_argument("--temporal-oos", default=str(DEFAULT_TEMPORAL_OOS))
    parser.add_argument("--mapping-mode", default="drop_2330_renormalize")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_diagnosis(
        comparison=_load_json(_resolve(args.comparison)),
        mapped_shadow=_load_json(_resolve(args.mapped_shadow)),
        temporal_oos=_load_json(_resolve(args.temporal_oos)),
        mapping_mode=args.mapping_mode,
    )
    report["inputs"] = {
        "comparison": str(_resolve(args.comparison)),
        "mapped_shadow": str(_resolve(args.mapped_shadow)),
        "temporal_oos": str(_resolve(args.temporal_oos)),
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "primary_failure": report.get("primary_failure"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
