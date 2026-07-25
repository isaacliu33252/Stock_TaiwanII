#!/usr/bin/env python3
"""Build a compact machine-readable summary of the latest GroupA+ deployment state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_DEPLOYMENT = PROJECT_ROOT / "report/group_a_plus/latest/deployment_consistency_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/deployment_summary.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/deployment_summary.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/deployment_summary/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if payload.get("success") is True and isinstance(data, dict) else payload


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _consistency_review(summary: dict[str, Any], deployment: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    summary_decision = _dict(summary, "decision")
    deployment_decision = _dict(deployment, "decision")

    required_summary_flags = {
        "summary_only": True,
        "creates_orders": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
        "keep_golden1_0531_unchanged": True,
    }
    for key, expected in required_summary_flags.items():
        if summary_decision.get(key) is not expected:
            errors.append(f"summary_decision_{key}_unexpected")

    comparable_decision_flags = (
        "target_weight_change_allowed",
        "auto_rebalance_allowed",
        "allow_00631l_add",
        "keep_golden1_0531_unchanged",
    )
    for key in comparable_decision_flags:
        if key in deployment_decision and summary_decision.get(key) is not deployment_decision.get(key):
            errors.append(f"deployment_decision_{key}_mismatch")

    if summary.get("status") != deployment.get("status"):
        errors.append("deployment_status_mismatch")
    if summary.get("broker_actionable") is not deployment_decision.get("broker_actionable"):
        errors.append("broker_actionable_mismatch")
    if bool(summary.get("blocking_reasons") or []) != bool(deployment.get("blocking_reasons") or []):
        errors.append("blocking_reason_presence_mismatch")
    if summary.get("warning_reasons") != (deployment.get("warning_reasons") or []):
        warnings.append("warning_reasons_changed_or_reordered")

    return {
        "status": "error" if errors else ("warning" if warnings else "ok"),
        "errors": errors,
        "warnings": warnings,
        "checked": {
            "summary_decision_flags": sorted(required_summary_flags),
            "deployment_decision_flags": sorted(comparable_decision_flags),
            "status": True,
            "broker_actionable": True,
            "blocking_reason_presence": True,
            "warning_reasons": True,
        },
    }


def build_summary(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    execution_plan_path: Path = DEFAULT_EXECUTION_PLAN,
    deployment_path: Path = DEFAULT_DEPLOYMENT,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    plan = _unwrap(_load(execution_plan_path))
    deployment = _unwrap(_load(deployment_path))
    computed = _dict(deployment, "computed")
    decision = _dict(deployment, "decision")
    guard_summary = _dict(plan, "guard_impact_summary") or _dict(computed, "guard_summary")
    planned_trades = _list(plan, "trades")
    nonzero_trade_count = sum(
        1 for row in planned_trades if isinstance(row, dict) and int(row.get("delta_shares") or 0) != 0
    )
    execution_plan_cash = {
        "current_cash_input": plan.get("current_cash_input", computed.get("cash_balance")),
        "cash_assumption": plan.get("cash_assumption"),
        "nonzero_trade_count": nonzero_trade_count,
        "cash_source_explicit": computed.get("cash_source_explicit"),
        "execution_plan_allowed": plan.get("execution_allowed", computed.get("execution_plan_allowed")),
        "manual_confirmation_required": plan.get(
            "manual_confirmation_required", computed.get("manual_confirmation_required")
        ),
    }

    summary = {
        "schema_version": 1,
        "report_type": "group_a_plus_deployment_summary",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "summary_only_no_order_no_strategy_change_no_weight_change",
        "as_of": deployment.get("as_of") or live.get("requested_as_of_date") or plan.get("requested_as_of_date"),
        "actual_data_date": live.get("actual_data_date") or computed.get("live_actual_data_date"),
        "strategy_id": live.get("strategy_id") or computed.get("live_strategy_id"),
        "status": deployment.get("status"),
        "broker_actionable": decision.get("broker_actionable"),
        "blocking_reasons": deployment.get("blocking_reasons") or [],
        "warning_reasons": deployment.get("warning_reasons") or [],
        "target_weights": live.get("target_weights") or computed.get("target_weights") or {},
        "final_target_shares": plan.get("target_shares") or computed.get("execution_target_shares") or {},
        "execution_plan_cash": execution_plan_cash,
        "planned_trades": planned_trades,
        "pre_trade_guards": _list(plan, "pre_trade_guards"),
        "blocked_buys": guard_summary.get("combined_blocked_buys") or [],
        "source_freshness": computed.get("source_freshness") or {},
        "securities_lending_0050_source_status": computed.get("securities_lending_0050_source_status") or {},
        "decision": {
            "summary_only": True,
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path),
            "deployment_consistency_review": str(deployment_path),
        },
    }
    summary["consistency_review"] = _consistency_review(summary, deployment)
    return summary


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Deployment Summary",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Broker actionable: `{summary.get('broker_actionable')}`",
        f"- As of: `{summary.get('as_of')}`",
        f"- Actual data date: `{summary.get('actual_data_date')}`",
        f"- Strategy: `{summary.get('strategy_id')}`",
        f"- Cash input: `{(summary.get('execution_plan_cash') or {}).get('current_cash_input')}`",
        f"- Nonzero trades: `{(summary.get('execution_plan_cash') or {}).get('nonzero_trade_count')}`",
        f"- Golden1_0531 unchanged: `{summary['decision']['keep_golden1_0531_unchanged']}`",
        f"- Consistency review: `{(summary.get('consistency_review') or {}).get('status')}`",
        "",
        "## Target Weights",
        "",
    ]
    for ticker, weight in (summary.get("target_weights") or {}).items():
        lines.append(f"- `{ticker}`: `{weight}`")
    lines.extend(["", "## Final Target Shares", ""])
    for ticker, shares in (summary.get("final_target_shares") or {}).items():
        lines.append(f"- `{ticker}`: `{shares}`")
    lines.extend(["", "## Planned Trades", ""])
    trades = summary.get("planned_trades") or []
    if not trades:
        lines.append("- None")
    for trade in trades:
        lines.append(
            f"- `{trade.get('side')}` `{trade.get('ticker')}` "
            f"`{trade.get('delta_shares')}` shares @ `{trade.get('price')}`"
        )
    lines.extend(["", "## Blocked Buys", ""])
    blocked = summary.get("blocked_buys") or []
    if not blocked:
        lines.append("- None")
    for row in blocked:
        lines.append(
            f"- `{row.get('ticker')}` staged `{row.get('staged_target_shares')}` "
            f"final `{row.get('final_target_shares')}` blocked `{row.get('blocked_delta_shares')}`"
        )
    lines.extend(["", "## Warnings", ""])
    warnings = summary.get("warning_reasons") or []
    if not warnings:
        lines.append("- None")
    for warning in warnings:
        lines.append(f"- `{warning}`")
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"deployment_summary_{stamp}.json"


def write_outputs(
    summary: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(summary), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, summary.get("as_of")).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--deployment", default=str(DEFAULT_DEPLOYMENT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    summary = build_summary(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        deployment_path=_resolve(args.deployment),
    )
    write_outputs(
        summary,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Deployment summary: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "broker_actionable": summary["broker_actionable"],
                "planned_trade_count": len(summary["planned_trades"]),
                "blocked_buy_count": len(summary["blocked_buys"]),
                "keep_golden1_0531_unchanged": summary["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
