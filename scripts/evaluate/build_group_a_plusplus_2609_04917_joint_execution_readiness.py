#!/usr/bin/env python3
"""Build a joint signal-portfolio-execution readiness report.

arXiv 2609.04917 warns that a forecast is not a portfolio, and a portfolio is
not net alpha until execution costs and fills are evaluated. This report joins
the current signal, execution plan, market-impact review, and promotion
readiness without changing live weights or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_EXECUTION_PLAN_PROMOTION = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_promotion_readiness.json"
DEFAULT_PROFIT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/profit_deployment_readiness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2609_04917_joint_execution_readiness/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _date(payload: dict[str, Any]) -> str | None:
    for key in ("actual_data_date", "as_of", "date", "signal_asof"):
        if payload.get(key):
            return str(payload[key])
    return None


def _weights(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("target_weights") if isinstance(payload.get("target_weights"), dict) else {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            pass
    return out


def build_report(
    *,
    live_signal_path: Path,
    execution_plan_path: Path,
    market_impact_path: Path,
    execution_plan_promotion_path: Path,
    profit_readiness_path: Path,
    as_of: str | None = None,
) -> dict[str, Any]:
    live = _load_optional(live_signal_path)
    plan = _load_optional(execution_plan_path)
    impact = _load_optional(market_impact_path)
    exec_promo = _load_optional(execution_plan_promotion_path)
    profit = _load_optional(profit_readiness_path)
    live_date = _date(live)
    plan_date = _date(plan)
    weights = _weights(live)
    blockers: list[str] = []
    warnings: list[str] = []
    if not weights:
        blockers.append("live_signal_target_weights_missing")
    if live_date and plan_date and live_date != plan_date:
        blockers.append("signal_execution_plan_date_mismatch")
    if not plan:
        blockers.append("execution_plan_missing")
    elif plan.get("execution_allowed") is False:
        blockers.append("execution_plan_disallows_execution")
    impact_status = str(impact.get("status") or "missing")
    if impact_status == "missing":
        blockers.append("market_impact_review_missing")
    elif impact_status.lower() in {"blocked", "error"}:
        blockers.append(f"market_impact_status={impact_status}")
    else:
        warnings.extend(f"market_impact_warning:{item}" for item in _as_list(impact.get("warning_reasons")))
    promo_status = str(exec_promo.get("status") or "missing")
    if promo_status.lower() in {"blocked", "error"}:
        blockers.append(f"execution_plan_promotion_status={promo_status}")
    elif promo_status == "missing":
        warnings.append("execution_plan_promotion_missing")
    cost_review = profit.get("turnover_cost_robustness_review") if isinstance(profit.get("turnover_cost_robustness_review"), dict) else {}
    if str(cost_review.get("status") or "").startswith("blocked"):
        blockers.append(f"turnover_cost_robustness_status={cost_review.get('status')}")
    status = "blocked" if blockers else ("warning" if warnings else "available_for_manual_review")
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_joint_execution_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "shadow_only_joint_signal_portfolio_execution_no_weight_change",
        "live_execution_effect": "none",
        "source_paper": {"arxiv": "2609.04917", "concept": "joint_signal_portfolio_execution_evaluation"},
        "status": status,
        "signal": {"date": live_date, "target_weights": weights},
        "portfolio_mapping": {
            "execution_plan_date": plan_date,
            "execution_allowed": plan.get("execution_allowed"),
            "planning_status": plan.get("planning_status") or plan.get("status"),
            "manual_confirmation_required": plan.get("manual_confirmation_required"),
        },
        "execution_realism": {
            "market_impact_status": impact_status,
            "execution_plan_promotion_status": promo_status,
            "turnover_cost_robustness_status": cost_review.get("status"),
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "creates_orders": False,
            "latest_strategy_change_allowed": False,
            "joint_execution_gate_required_before_live": True,
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 2609.04917 Joint Execution Readiness",
            "",
            f"- status: {report['status']}",
            f"- signal_date: {report['signal']['date']}",
            f"- execution_plan_date: {report['portfolio_mapping']['execution_plan_date']}",
            f"- execution_allowed: {report['portfolio_mapping']['execution_allowed']}",
            f"- market_impact_status: {report['execution_realism']['market_impact_status']}",
            f"- blocking_reasons: {', '.join(report['blocking_reasons']) or 'none'}",
            "",
        ]
    )


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = as_of or datetime.now().strftime("%Y%m%d")
    return history_dir / f"2609_04917_joint_execution_readiness_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--execution-plan-promotion", default=str(DEFAULT_EXECUTION_PLAN_PROMOTION))
    parser.add_argument("--profit-readiness", default=str(DEFAULT_PROFIT_READINESS))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()
    report = build_report(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        market_impact_path=_resolve(args.market_impact),
        execution_plan_promotion_path=_resolve(args.execution_plan_promotion),
        profit_readiness_path=_resolve(args.profit_readiness),
        as_of=args.as_of,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    history = _history_path(_resolve(args.history_dir), args.as_of)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    history.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
