"""Audit report writer for GroupA+ broker-neutral rebalance plans."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from group_a_plus.core.signal_contract import from_daily_signal
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.portfolio.rebalance_plan import RebalancePlan
from group_a_plus.portfolio.rebalance_validation import RebalanceValidation


DEFAULT_LATEST_REBALANCE_AUDIT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "rebalance_plan.json"
DEFAULT_REBALANCE_AUDIT_DIR = PROJECT_ROOT / "results"


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _manual_approval_template(*, required: bool = True) -> dict[str, Any]:
    return {
        "required": required,
        "approved": False,
        "approved_by": None,
        "approved_at": None,
        "notes": "",
    }


def build_rebalance_audit_report(
    *,
    daily_signal: dict[str, Any],
    plan: RebalancePlan,
    validation: RebalanceValidation,
    current_shares: dict[str, float],
    cash: float,
    generated_at: str | None = None,
    manual_approval_required: bool = True,
) -> dict[str, Any]:
    """Build an immutable-by-default audit payload for a rebalance plan.

    `validation.approved` means the pre-trade checks passed. It is deliberately
    separate from `manual_approval.approved`, which defaults to False and should
    only be changed by a human-controlled workflow outside this builder.
    """
    signal_contract = from_daily_signal(daily_signal)
    generated = generated_at or datetime.now().isoformat(timespec="seconds")
    report: dict[str, Any] = {
        "schema_version": 1,
        "report_type": "group_a_plus_rebalance_plan_audit",
        "generated_at": generated,
        "strategy_id": plan.strategy_id,
        "signal_asof": plan.signal_asof,
        "signal": {
            "strategy_id": signal_contract.strategy_id,
            "signal_asof": str(signal_contract.signal_asof.date()),
            "generated_at": signal_contract.generated_at.isoformat(),
            "execution_date": str(signal_contract.execution_date.date()),
            "model_version": signal_contract.model_version,
            "feature_version": signal_contract.feature_version,
            "data_snapshot_hash": signal_contract.data_snapshot_hash,
            "target_weights": dict(signal_contract.weights),
            "execution_allowed": bool(daily_signal.get("execution_allowed", True)),
            "execution_guard_reasons": list(daily_signal.get("execution_guard_reasons") or []),
        },
        "portfolio_snapshot": {
            "current_shares": {str(ticker): float(shares) for ticker, shares in current_shares.items()},
            "cash": float(cash),
            "portfolio_value": plan.portfolio_value,
            "current_values": dict(plan.current_values),
        },
        "rebalance_plan": plan.to_json_dict(),
        "validation": validation.to_json_dict(),
        "manual_approval": _manual_approval_template(required=manual_approval_required),
        "execution": {
            "broker_submitted": False,
            "submitted_at": None,
            "broker": None,
            "broker_order_ids": [],
            "fills": [],
        },
    }
    report["audit_hash"] = _payload_hash({k: v for k, v in report.items() if k != "audit_hash"})
    return report


def dated_rebalance_audit_path(report: dict[str, Any], output_dir: Path = DEFAULT_REBALANCE_AUDIT_DIR) -> Path:
    signal_asof = str(report.get("signal_asof") or "unknown").replace("-", "")
    return output_dir / f"rebalance_plan_{signal_asof}.json"


def write_rebalance_audit_report(
    report: dict[str, Any],
    *,
    latest_path: Path = DEFAULT_LATEST_REBALANCE_AUDIT,
    dated_path: Path | None = None,
) -> dict[str, str]:
    """Write latest and dated copies of a rebalance audit report."""
    resolved_dated_path = dated_path or dated_rebalance_audit_path(report)
    text = _json_dumps(report) + "\n"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_dated_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(text, encoding="utf-8")
    resolved_dated_path.write_text(text, encoding="utf-8")
    return {
        "latest_path": str(latest_path),
        "dated_path": str(resolved_dated_path),
    }
