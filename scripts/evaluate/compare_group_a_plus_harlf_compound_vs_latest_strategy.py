#!/usr/bin/env python3
"""Compare compound defensive HARLF against editable latest strategy.

HARLF monthly decision rows are labelled by signal month: a row for 2025-07
means "decide at July month-end, realize the next month". This script aligns
latest/golden daily backtest values to the same month-end-to-next-month
outcome convention.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.runners.a2111 import run_a2111
from group_a_plus.runners.latest import run_latest


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_HARLF = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_defensive_meta_agent_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_vs_latest_strategy_comparison.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_compound_vs_latest_strategy_comparison/history"


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


def _harlf_returns(report: dict[str, Any]) -> pd.Series:
    rows = report.get("monthly_decisions") or []
    frame = pd.DataFrame(rows)
    if frame.empty or {"month", "net_return"} - set(frame.columns):
        return pd.Series(dtype=float)
    frame["month"] = frame["month"].astype(str)
    frame["net_return"] = pd.to_numeric(frame["net_return"], errors="coerce")
    return frame.dropna(subset=["net_return"]).set_index("month")["net_return"].sort_index()


def _next_month_returns_from_daily_frame(frame: pd.DataFrame, months: list[str]) -> pd.Series:
    if frame.empty or "portfolio_value" not in frame.columns:
        return pd.Series(dtype=float)
    values = frame.copy()
    values.index = pd.to_datetime(values.index)
    month_end = values["portfolio_value"].astype(float).resample("ME").last()
    monthly_return = month_end.pct_change(fill_method=None)
    signal_month_return = monthly_return.copy()
    signal_month_return.index = [(idx.to_period("M") - 1).strftime("%Y-%m") for idx in monthly_return.index]
    return signal_month_return.reindex(months).dropna()


def build_comparison(
    *,
    harlf_report: dict[str, Any],
    latest_frame: pd.DataFrame,
    golden_frame: pd.DataFrame,
    latest_report: dict[str, Any] | None = None,
    golden_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    harlf = _harlf_returns(harlf_report)
    if harlf.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_compound_vs_latest_strategy_comparison",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "policy": "research_only_comparison_no_weight_change",
            "blocking_reasons": ["missing_harlf_monthly_decisions"],
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "promotion_ready": False,
            },
        }
    months = list(harlf.index)
    latest = _next_month_returns_from_daily_frame(latest_frame, months)
    golden = _next_month_returns_from_daily_frame(golden_frame, months)
    common = sorted(set(harlf.index) & set(latest.index) & set(golden.index))
    if not common:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_compound_vs_latest_strategy_comparison",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "policy": "research_only_comparison_no_weight_change",
            "blocking_reasons": ["no_common_monthly_outcomes"],
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "promotion_ready": False,
            },
        }

    aligned = pd.DataFrame(
        {
            "harlf_compound": harlf.reindex(common),
            "latest_strategy": latest.reindex(common),
            "golden01_0531": golden.reindex(common),
        },
        index=common,
    )
    metrics = {column: _metrics(aligned[column]) for column in aligned.columns}
    h = metrics["harlf_compound"]
    latest_m = metrics["latest_strategy"]
    golden_m = metrics["golden01_0531"]
    beats_latest_return = h.get("total_return", -999.0) > latest_m.get("total_return", 999.0)
    beats_latest_drawdown = h.get("max_drawdown", -999.0) >= latest_m.get("max_drawdown", 999.0)
    beats_golden_return = h.get("total_return", -999.0) > golden_m.get("total_return", 999.0)
    candidate_ready = bool(beats_latest_return and beats_latest_drawdown and beats_golden_return and h.get("n", 0) >= 12)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_compound_vs_latest_strategy_comparison",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_comparison_no_weight_change",
        "alignment_method": "month_end_to_next_month_outcomes_labelled_by_signal_month",
        "months": common,
        "monthly_returns": [
            {"month": month, **{column: float(aligned.at[month, column]) for column in aligned.columns}}
            for month in common
        ],
        "metrics": metrics,
        "source_reports": {
            "harlf_report_type": harlf_report.get("report_type"),
            "latest_strategy_id": (latest_report or {}).get("active_strategy_id"),
            "latest_candidate_status": (latest_report or {}).get("candidate_status"),
            "golden_report_strategy": (golden_report or {}).get("strategy"),
        },
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "beats_latest_total_return": beats_latest_return,
            "not_worse_than_latest_max_drawdown": beats_latest_drawdown,
            "beats_golden01_total_return": beats_golden_return,
            "candidate_ready_for_latest_strategy_review": candidate_ready,
            "promotion_ready": False,
        },
        "caveats": [
            "HARLF is monthly and latest/golden runners are daily dynamic strategies.",
            "This is a research comparison; it does not modify latest strategy or golden01_0531.",
            "golden01_0531 is fixed benchmark only.",
        ],
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_compound_vs_latest_strategy_comparison_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harlf", default=str(DEFAULT_HARLF))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2025-07-01")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    latest_report, latest_frame = run_latest(args.start, args.end, args.initial_value, _resolve(args.db))
    golden_report, golden_frame = run_a2111(args.start, args.end, args.initial_value, _resolve(args.db))
    report = build_comparison(
        harlf_report=_load_json(_resolve(args.harlf)),
        latest_frame=latest_frame,
        golden_frame=golden_frame,
        latest_report=latest_report,
        golden_report=golden_report,
    )
    report["inputs"] = {
        "harlf": str(_resolve(args.harlf)),
        "db": str(_resolve(args.db)),
        "start": args.start,
        "end": args.end,
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "metrics": report.get("metrics"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
