"""Portfolio and holding tools for GroupA+ workflows."""

from group_a_plus.portfolio.rebalance_audit import (
    build_rebalance_audit_report,
    dated_rebalance_audit_path,
    write_rebalance_audit_report,
)
from group_a_plus.portfolio.holding_snapshot import (
    HoldingSnapshot,
    holding_snapshot_from_dict,
    load_holding_snapshot_excel,
    load_holding_snapshot_json,
)
from group_a_plus.portfolio.rebalance_plan import (
    PlannedOrder,
    RebalanceConfig,
    RebalancePlan,
    build_rebalance_plan,
)
from group_a_plus.portfolio.rebalance_validation import (
    RebalanceRiskConfig,
    RebalanceValidation,
    RiskCheck,
    validate_rebalance_plan,
)

_FUBON_EXPORTS = {
    "FubonCredentials",
    "fetch_fubon_holding_snapshot",
    "load_fubon_credentials_from_env",
    "parse_fubon_cash",
    "parse_fubon_inventories",
    "write_holding_snapshot",
}

__all__ = [
    "PlannedOrder",
    "RebalanceConfig",
    "RebalancePlan",
    "RebalanceRiskConfig",
    "RebalanceValidation",
    "FubonCredentials",
    "HoldingSnapshot",
    "RiskCheck",
    "build_rebalance_audit_report",
    "build_rebalance_plan",
    "dated_rebalance_audit_path",
    "fetch_fubon_holding_snapshot",
    "holding_snapshot_from_dict",
    "load_holding_snapshot_excel",
    "load_holding_snapshot_json",
    "load_fubon_credentials_from_env",
    "parse_fubon_cash",
    "parse_fubon_inventories",
    "validate_rebalance_plan",
    "write_holding_snapshot",
    "write_rebalance_audit_report",
]


def __getattr__(name: str):
    if name in _FUBON_EXPORTS:
        from group_a_plus.portfolio import fubon_snapshot

        return getattr(fubon_snapshot, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
