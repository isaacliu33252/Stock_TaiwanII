#!/usr/bin/env python3
"""Evaluate a HARLF-style hierarchical meta-agent shadow router.

The router consumes the market-only, sentiment-only, and combined branch
returns from the HARLF branch ablation report. It uses only trailing branch
performance available before each month. It does not create orders and does not
modify golden01_0531.
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
DEFAULT_BRANCH_ABLATION = PROJECT_ROOT / "report/group_a_plus/latest/harlf_branch_ablation_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_meta_agent_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_meta_agent_shadow/history"
ROUTABLE_BRANCHES = ("market_only", "sentiment_only", "combined")


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
        "annualized_sharpe": float(clean.mean() / std * math.sqrt(12)) if std > 0 else 0.0,
        "max_drawdown": float((equity / peak - 1.0).min()),
        "positive_month_rate": float((clean > 0.0).mean()),
        "worst_month": float(clean.min()),
        "best_month": float(clean.max()),
    }


def _branch_frame(branch_report: dict[str, Any]) -> pd.DataFrame:
    rows = branch_report.get("branch_returns") or branch_report.get("rows_preview") or []
    frame = pd.DataFrame(rows)
    required = {"month", "branch", "net_return", "turnover_cost"}
    missing = required - set(frame.columns)
    if frame.empty or missing:
        return pd.DataFrame(columns=["month", "branch", "net_return", "turnover_cost"])
    frame["month"] = frame["month"].astype(str)
    frame["branch"] = frame["branch"].astype(str)
    frame["net_return"] = pd.to_numeric(frame["net_return"], errors="coerce")
    frame["turnover_cost"] = pd.to_numeric(frame["turnover_cost"], errors="coerce").fillna(0.0)
    return frame.dropna(subset=["net_return"]).sort_values(["month", "branch"]).reset_index(drop=True)


def _trailing_score(history: pd.Series, drawdown_penalty: float) -> float:
    clean = pd.to_numeric(history, errors="coerce").dropna()
    if clean.empty:
        return -999.0
    std = float(clean.std(ddof=0))
    sharpe = float(clean.mean() / std * math.sqrt(12)) if std > 1e-12 else float(clean.mean() * 12)
    equity = (1.0 + clean).cumprod()
    drawdown = float((equity / equity.cummax() - 1.0).min())
    return sharpe + drawdown_penalty * drawdown


def build_meta_agent_shadow(
    *,
    branch_report: dict[str, Any],
    warmup_months: int = 6,
    lookback_months: int = 6,
    drawdown_penalty: float = 1.0,
    defensive_sentiment_score_threshold: float | None = None,
    defensive_sentiment_overheat_threshold: float | None = None,
    defensive_sentiment_soft_threshold: float | None = None,
    defensive_prev_equal_weight_return_max: float | None = None,
) -> dict[str, Any]:
    frame = _branch_frame(branch_report)
    if frame.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_meta_agent_shadow",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "policy": "research_only_harlf_meta_agent_no_weight_change",
            "blocking_reasons": ["missing_branch_return_series"],
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "hierarchical_meta_agent_oos_backtest_available": False,
                "promotion_ready": False,
            },
        }

    pivot = frame.pivot_table(index="month", columns="branch", values="net_return", aggfunc="last").sort_index()
    rows: list[dict[str, Any]] = []
    months = list(pivot.index)
    for idx, month in enumerate(months):
        if idx < warmup_months:
            continue
        history = pivot.iloc[max(0, idx - lookback_months) : idx]
        scores = {
            branch: _trailing_score(history[branch], drawdown_penalty)
            for branch in ROUTABLE_BRANCHES
            if branch in history.columns and branch in pivot.columns and pd.notna(pivot.at[month, branch])
        }
        if not scores:
            continue
        selected = max(scores, key=lambda branch: (scores[branch], branch))
        raw_selected = selected
        defensive_fallback = False
        defensive_fallback_reason = None
        prev_equal_weight_return = None
        if idx > 0 and "equal_weight" in pivot.columns and pd.notna(pivot.iloc[idx - 1]["equal_weight"]):
            prev_equal_weight_return = float(pivot.iloc[idx - 1]["equal_weight"])
        if (
            defensive_sentiment_score_threshold is not None
            and selected == "sentiment_only"
            and scores.get("sentiment_only", -999.0) >= defensive_sentiment_score_threshold
            and "equal_weight" in pivot.columns
            and pd.notna(pivot.at[month, "equal_weight"])
        ):
            selected = "equal_weight"
            defensive_fallback = True
            defensive_fallback_reason = "sentiment_score_threshold"
        if (
            selected == "sentiment_only"
            and defensive_sentiment_overheat_threshold is not None
            and scores.get("sentiment_only", -999.0) >= defensive_sentiment_overheat_threshold
            and "equal_weight" in pivot.columns
            and pd.notna(pivot.at[month, "equal_weight"])
        ):
            selected = "equal_weight"
            defensive_fallback = True
            defensive_fallback_reason = "sentiment_overheat_threshold"
        if (
            selected == "sentiment_only"
            and defensive_sentiment_soft_threshold is not None
            and defensive_prev_equal_weight_return_max is not None
            and prev_equal_weight_return is not None
            and scores.get("sentiment_only", -999.0) >= defensive_sentiment_soft_threshold
            and prev_equal_weight_return <= defensive_prev_equal_weight_return_max
            and "equal_weight" in pivot.columns
            and pd.notna(pivot.at[month, "equal_weight"])
        ):
            selected = "equal_weight"
            defensive_fallback = True
            defensive_fallback_reason = "sentiment_soft_threshold_after_weak_equal_weight"
        rows.append(
            {
                "month": month,
                "selected_branch": selected,
                "raw_selected_branch": raw_selected,
                "defensive_fallback_applied": defensive_fallback,
                "defensive_fallback_reason": defensive_fallback_reason,
                "prev_equal_weight_return": prev_equal_weight_return,
                "net_return": float(pivot.at[month, selected]),
                "branch_scores": {branch: float(score) for branch, score in scores.items()},
            }
        )

    meta_returns = pd.DataFrame(rows)
    benchmark_metrics: dict[str, Any] = {}
    for branch in ["equal_weight", *ROUTABLE_BRANCHES]:
        if branch in pivot.columns:
            aligned = pivot.loc[[row["month"] for row in rows], branch] if rows else pd.Series(dtype=float)
            benchmark_metrics[branch] = _metrics(aligned)
    meta_metrics = _metrics(meta_returns["net_return"]) if not meta_returns.empty else {"n": 0}
    combined_total = benchmark_metrics.get("combined", {}).get("total_return")
    equal_total = benchmark_metrics.get("equal_weight", {}).get("total_return")
    meta_total = meta_metrics.get("total_return")
    selected_counts = (
        meta_returns["selected_branch"].value_counts().sort_index().to_dict() if not meta_returns.empty else {}
    )

    beats_combined = meta_total is not None and combined_total is not None and meta_total > combined_total
    beats_equal = meta_total is not None and equal_total is not None and meta_total > equal_total
    candidate_ready_for_stress = bool(
        meta_metrics.get("n", 0) >= 12
        and beats_combined
        and beats_equal
        and meta_metrics.get("max_drawdown", 0.0) >= benchmark_metrics.get("combined", {}).get("max_drawdown", -1.0)
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_meta_agent_shadow",
        "status": "available" if rows else "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_harlf_meta_agent_no_weight_change",
        "parameters": {
            "warmup_months": warmup_months,
            "lookback_months": lookback_months,
            "drawdown_penalty": drawdown_penalty,
            "routable_branches": list(ROUTABLE_BRANCHES),
            "defensive_sentiment_score_threshold": defensive_sentiment_score_threshold,
            "defensive_sentiment_overheat_threshold": defensive_sentiment_overheat_threshold,
            "defensive_sentiment_soft_threshold": defensive_sentiment_soft_threshold,
            "defensive_prev_equal_weight_return_max": defensive_prev_equal_weight_return_max,
        },
        "source_branch_report": {
            "report_type": branch_report.get("report_type"),
            "input_window": branch_report.get("input_window"),
        },
        "meta_agent_metrics": meta_metrics,
        "benchmark_metrics": benchmark_metrics,
        "selected_branch_counts": selected_counts,
        "monthly_decisions": rows,
        "blocking_reasons": [] if rows else ["missing_meta_agent_monthly_decisions"],
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "hierarchical_meta_agent_oos_backtest_available": bool(rows),
            "beats_equal_weight_total_return": beats_equal,
            "beats_static_combined_total_return": beats_combined,
            "candidate_ready_for_stress_test": candidate_ready_for_stress,
            "defensive_equal_weight_fallback_enabled": any(
                value is not None
                for value in [
                    defensive_sentiment_score_threshold,
                    defensive_sentiment_overheat_threshold,
                    defensive_sentiment_soft_threshold,
                    defensive_prev_equal_weight_return_max,
                ]
            ),
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_meta_agent_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch-ablation", default=str(DEFAULT_BRANCH_ABLATION))
    parser.add_argument("--warmup-months", type=int, default=6)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--drawdown-penalty", type=float, default=1.0)
    parser.add_argument("--defensive-sentiment-score-threshold", type=float)
    parser.add_argument("--defensive-sentiment-overheat-threshold", type=float)
    parser.add_argument("--defensive-sentiment-soft-threshold", type=float)
    parser.add_argument("--defensive-prev-equal-weight-return-max", type=float)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    branch_report = _load_json(_resolve(args.branch_ablation))
    report = build_meta_agent_shadow(
        branch_report=branch_report,
        warmup_months=args.warmup_months,
        lookback_months=args.lookback_months,
        drawdown_penalty=args.drawdown_penalty,
        defensive_sentiment_score_threshold=args.defensive_sentiment_score_threshold,
        defensive_sentiment_overheat_threshold=args.defensive_sentiment_overheat_threshold,
        defensive_sentiment_soft_threshold=args.defensive_sentiment_soft_threshold,
        defensive_prev_equal_weight_return_max=args.defensive_prev_equal_weight_return_max,
    )
    report["inputs"] = {"branch_ablation": str(_resolve(args.branch_ablation))}
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "meta_agent_metrics": report.get("meta_agent_metrics"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
