#!/usr/bin/env python3
"""Stress-test the HARLF meta-agent shadow candidate.

This consumes the HARLF branch ablation and meta-agent reports. It tests the
candidate under extra transaction costs, sentiment branch dropout, and weak
market months. It does not create orders, does not modify golden01_0531, and
does not modify the latest strategy.
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
DEFAULT_META_AGENT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_meta_agent_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_stress_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_stress_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _metrics(values: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
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


def _branch_frame(branch_report: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(branch_report.get("branch_returns") or [])
    required = {"month", "branch", "net_return", "turnover_cost"}
    if frame.empty or required - set(frame.columns):
        return pd.DataFrame(columns=["month", "branch", "net_return", "turnover_cost"])
    frame["month"] = frame["month"].astype(str)
    frame["branch"] = frame["branch"].astype(str)
    frame["net_return"] = pd.to_numeric(frame["net_return"], errors="coerce")
    frame["turnover_cost"] = pd.to_numeric(frame["turnover_cost"], errors="coerce").fillna(0.0)
    return frame.dropna(subset=["net_return"]).sort_values(["month", "branch"]).reset_index(drop=True)


def _meta_frame(meta_report: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(meta_report.get("monthly_decisions") or [])
    required = {"month", "selected_branch", "net_return"}
    if frame.empty or required - set(frame.columns):
        return pd.DataFrame(columns=["month", "selected_branch", "net_return"])
    frame["month"] = frame["month"].astype(str)
    frame["selected_branch"] = frame["selected_branch"].astype(str)
    frame["net_return"] = pd.to_numeric(frame["net_return"], errors="coerce")
    return frame.dropna(subset=["net_return"]).sort_values("month").reset_index(drop=True)


def _aligned_inputs(branch_report: dict[str, Any], meta_report: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    branch = _branch_frame(branch_report)
    meta = _meta_frame(meta_report)
    if branch.empty or meta.empty:
        return branch, meta
    months = set(meta["month"])
    return branch[branch["month"].isin(months)].copy(), meta


def build_stress_report(
    *,
    branch_report: dict[str, Any],
    meta_report: dict[str, Any],
    cost_multipliers: tuple[float, ...] = (2.0, 3.0),
    high_turnover_penalty: float = 0.005,
) -> dict[str, Any]:
    branch, meta = _aligned_inputs(branch_report, meta_report)
    if branch.empty or meta.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_stress_shadow",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "policy": "research_only_harlf_stress_no_weight_change",
            "blocking_reasons": ["missing_branch_or_meta_monthly_returns"],
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "stress_test_available": False,
                "promotion_ready": False,
            },
        }

    pivot_return = branch.pivot_table(index="month", columns="branch", values="net_return", aggfunc="last").sort_index()
    pivot_cost = branch.pivot_table(index="month", columns="branch", values="turnover_cost", aggfunc="last").sort_index()
    meta = meta.set_index("month").sort_index()
    common_months = [month for month in meta.index if month in pivot_return.index]
    selected_returns = pd.Series(
        [float(pivot_return.at[month, meta.at[month, "selected_branch"]]) for month in common_months],
        index=common_months,
        dtype=float,
    )
    selected_costs = pd.Series(
        [float(pivot_cost.at[month, meta.at[month, "selected_branch"]]) for month in common_months],
        index=common_months,
        dtype=float,
    )
    equal_returns = pivot_return.reindex(common_months)["equal_weight"] if "equal_weight" in pivot_return else pd.Series(dtype=float)
    combined_returns = pivot_return.reindex(common_months)["combined"] if "combined" in pivot_return else pd.Series(dtype=float)

    scenario_returns: dict[str, pd.Series] = {
        "base_meta_agent": selected_returns,
        "high_turnover_penalty_50bps": selected_returns - high_turnover_penalty,
    }
    for multiplier in cost_multipliers:
        label = str(multiplier).replace(".", "_")
        scenario_returns[f"transaction_cost_multiplier_{label}x"] = selected_returns - selected_costs * (multiplier - 1.0)

    dropout_combined = selected_returns.copy()
    dropout_market = selected_returns.copy()
    selected_branch = meta.reindex(common_months)["selected_branch"]
    sentiment_months = selected_branch[selected_branch == "sentiment_only"].index
    if "combined" in pivot_return:
        dropout_combined.loc[sentiment_months] = pivot_return.reindex(sentiment_months)["combined"]
    if "market_only" in pivot_return:
        dropout_market.loc[sentiment_months] = pivot_return.reindex(sentiment_months)["market_only"]
    scenario_returns["sentiment_dropout_to_combined"] = dropout_combined
    scenario_returns["sentiment_dropout_to_market_only"] = dropout_market

    weak_market_months = equal_returns[equal_returns < 0.0].index if not equal_returns.empty else []
    if len(weak_market_months) > 0:
        scenario_returns["weak_equal_weight_months_only"] = selected_returns.reindex(weak_market_months)

    scenario_metrics = {name: _metrics(values) for name, values in scenario_returns.items()}
    equal_metrics = _metrics(equal_returns)
    combined_metrics = _metrics(combined_returns)
    cost_3x = scenario_metrics.get("transaction_cost_multiplier_3_0x") or {}
    dropout_combined_metrics = scenario_metrics.get("sentiment_dropout_to_combined") or {}
    weak_metrics = scenario_metrics.get("weak_equal_weight_months_only") or {}
    weak_equal_metrics = _metrics(equal_returns.reindex(weak_market_months))
    weak_not_worse = weak_metrics.get("total_return", -1.0) >= weak_equal_metrics.get("total_return", 999.0) - 1e-12
    stress_pass = bool(
        cost_3x.get("total_return", -1.0) > equal_metrics.get("total_return", 999.0)
        and dropout_combined_metrics.get("total_return", -1.0) > 0.0
        and weak_metrics.get("n", 0) > 0
        and weak_not_worse
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_stress_shadow",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_harlf_stress_no_weight_change",
        "parameters": {
            "cost_multipliers": list(cost_multipliers),
            "high_turnover_penalty": high_turnover_penalty,
        },
        "source_reports": {
            "branch_report_type": branch_report.get("report_type"),
            "meta_report_type": meta_report.get("report_type"),
            "months": common_months,
        },
        "baseline_metrics": {
            "equal_weight": equal_metrics,
            "static_combined": combined_metrics,
        },
        "scenario_metrics": scenario_metrics,
        "selected_branch_counts": meta["selected_branch"].value_counts().sort_index().to_dict(),
        "blocking_reasons": [],
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "stress_test_available": True,
            "beats_equal_weight_under_3x_cost": cost_3x.get("total_return", -1.0) > equal_metrics.get("total_return", 999.0),
            "sentiment_dropout_to_combined_positive": dropout_combined_metrics.get("total_return", -1.0) > 0.0,
            "weak_market_months_not_worse_than_equal_weight": weak_not_worse,
            "latest_strategy_candidate_ready_for_comparison": stress_pass,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_stress_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch-ablation", default=str(DEFAULT_BRANCH_ABLATION))
    parser.add_argument("--meta-agent", default=str(DEFAULT_META_AGENT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_stress_report(
        branch_report=_load_json(_resolve(args.branch_ablation)),
        meta_report=_load_json(_resolve(args.meta_agent)),
    )
    report["inputs"] = {
        "branch_ablation": str(_resolve(args.branch_ablation)),
        "meta_agent": str(_resolve(args.meta_agent)),
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
