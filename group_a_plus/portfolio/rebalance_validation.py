"""Risk checks for broker-neutral GroupA+ rebalance plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from group_a_plus.portfolio.rebalance_plan import RebalancePlan


DEFAULT_LEVERAGED_TICKER = "00631L.TW"
NCF_STALE_ALERT_TYPE = "ncf_panel_stale"
OPS_HEALTH_ALERT_PREFIX = "ops_health_"


@dataclass(frozen=True)
class RebalanceRiskConfig:
    require_execution_allowed: bool = True
    max_order_value: float = 250_000.0
    max_total_buy_value: float = 500_000.0
    max_turnover_ratio: float = 0.50
    leveraged_ticker: str = DEFAULT_LEVERAGED_TICKER
    max_leveraged_target_weight: float = 0.25
    block_new_risk_on_ncf_stale: bool = True
    block_new_risk_on_ops_health_error: bool = True
    risk_add_tickers: tuple[str, ...] = ("0050.TW", "00631L.TW")
    warning_cash_drift_ratio: float = 0.02


@dataclass(frozen=True)
class RiskCheck:
    name: str
    status: str
    severity: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RebalanceValidation:
    approved: bool
    manual_review_required: bool
    checks: list[RiskCheck]

    @property
    def errors(self) -> list[RiskCheck]:
        return [check for check in self.checks if check.severity == "error" and check.status == "fail"]

    @property
    def warnings(self) -> list[RiskCheck]:
        return [check for check in self.checks if check.severity == "warning" and check.status == "warn"]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "manual_review_required": self.manual_review_required,
            "checks": [check.to_json_dict() for check in self.checks],
            "errors": [check.to_json_dict() for check in self.errors],
            "warnings": [check.to_json_dict() for check in self.warnings],
        }


def _check(status: str, severity: str, name: str, message: str, **metadata: Any) -> RiskCheck:
    return RiskCheck(
        name=name,
        status=status,
        severity=severity,
        message=message,
        metadata=metadata,
    )


def _signal_alert_types(daily_signal: dict[str, Any] | None) -> set[str]:
    if not isinstance(daily_signal, dict):
        return set()
    alerts = daily_signal.get("signal_alerts") or []
    if not isinstance(alerts, list):
        return set()
    return {
        str(alert.get("type"))
        for alert in alerts
        if isinstance(alert, dict) and alert.get("type")
    }


def _has_ops_health_alert(alert_types: set[str]) -> bool:
    return any(alert_type.startswith(OPS_HEALTH_ALERT_PREFIX) for alert_type in alert_types)


def validate_rebalance_plan(
    plan: RebalancePlan,
    *,
    daily_signal: dict[str, Any] | None = None,
    config: RebalanceRiskConfig | None = None,
) -> RebalanceValidation:
    """Validate a broker-neutral rebalance plan before manual/broker execution."""
    cfg = config or RebalanceRiskConfig()
    checks: list[RiskCheck] = []

    if cfg.require_execution_allowed and isinstance(daily_signal, dict):
        execution_allowed = bool(daily_signal.get("execution_allowed", True))
        guard_reasons = list(daily_signal.get("execution_guard_reasons") or [])
        checks.append(
            _check(
                "pass" if execution_allowed else "fail",
                "error",
                "execution_allowed",
                "live signal allows execution" if execution_allowed else "live signal blocks execution",
                guard_reasons=guard_reasons,
            )
        )
    elif cfg.require_execution_allowed:
        checks.append(
            _check(
                "warn",
                "warning",
                "execution_allowed",
                "daily_signal not provided; execution_allowed guard could not be verified",
            )
        )

    max_order_value = max((order.trade_value for order in plan.orders), default=0.0)
    checks.append(
        _check(
            "pass" if max_order_value <= cfg.max_order_value else "fail",
            "error",
            "max_order_value",
            f"max order value {max_order_value:.2f} within limit {cfg.max_order_value:.2f}"
            if max_order_value <= cfg.max_order_value
            else f"max order value {max_order_value:.2f} exceeds limit {cfg.max_order_value:.2f}",
            max_order_value=max_order_value,
            limit=cfg.max_order_value,
        )
    )

    total_buy_value = sum(order.trade_value for order in plan.orders if order.side == "BUY")
    checks.append(
        _check(
            "pass" if total_buy_value <= cfg.max_total_buy_value else "fail",
            "error",
            "max_total_buy_value",
            f"total buy value {total_buy_value:.2f} within limit {cfg.max_total_buy_value:.2f}"
            if total_buy_value <= cfg.max_total_buy_value
            else f"total buy value {total_buy_value:.2f} exceeds limit {cfg.max_total_buy_value:.2f}",
            total_buy_value=total_buy_value,
            limit=cfg.max_total_buy_value,
        )
    )

    turnover_value = sum(order.trade_value for order in plan.orders)
    turnover_ratio = turnover_value / plan.portfolio_value if plan.portfolio_value > 0 else float("inf")
    checks.append(
        _check(
            "pass" if turnover_ratio <= cfg.max_turnover_ratio else "fail",
            "error",
            "max_turnover_ratio",
            f"turnover ratio {turnover_ratio:.4f} within limit {cfg.max_turnover_ratio:.4f}"
            if turnover_ratio <= cfg.max_turnover_ratio
            else f"turnover ratio {turnover_ratio:.4f} exceeds limit {cfg.max_turnover_ratio:.4f}",
            turnover_value=turnover_value,
            turnover_ratio=turnover_ratio,
            limit=cfg.max_turnover_ratio,
        )
    )

    leveraged_weight = float(plan.target_weights.get(cfg.leveraged_ticker, 0.0))
    checks.append(
        _check(
            "pass" if leveraged_weight <= cfg.max_leveraged_target_weight else "fail",
            "error",
            "max_leveraged_target_weight",
            f"{cfg.leveraged_ticker} target weight {leveraged_weight:.4f} within limit {cfg.max_leveraged_target_weight:.4f}"
            if leveraged_weight <= cfg.max_leveraged_target_weight
            else f"{cfg.leveraged_ticker} target weight {leveraged_weight:.4f} exceeds limit {cfg.max_leveraged_target_weight:.4f}",
            ticker=cfg.leveraged_ticker,
            target_weight=leveraged_weight,
            limit=cfg.max_leveraged_target_weight,
        )
    )

    alert_types = _signal_alert_types(daily_signal)
    buy_tickers = {order.ticker for order in plan.orders if order.side == "BUY"}
    risk_adds = sorted(buy_tickers & set(cfg.risk_add_tickers))
    ncf_stale_blocks = cfg.block_new_risk_on_ncf_stale and NCF_STALE_ALERT_TYPE in alert_types and bool(risk_adds)
    checks.append(
        _check(
            "fail" if ncf_stale_blocks else "pass",
            "error",
            "ncf_stale_no_new_risk_adds",
            f"NCF stale alert blocks new risk adds: {risk_adds}" if ncf_stale_blocks else "NCF stale guard passed",
            alert_types=sorted(alert_types),
            risk_add_tickers=risk_adds,
        )
    )

    ops_health_blocks = cfg.block_new_risk_on_ops_health_error and _has_ops_health_alert(alert_types) and bool(risk_adds)
    checks.append(
        _check(
            "fail" if ops_health_blocks else "pass",
            "error",
            "ops_health_no_new_risk_adds",
            f"ops health alert blocks new risk adds: {risk_adds}" if ops_health_blocks else "ops health guard passed",
            alert_types=sorted(alert_types),
            risk_add_tickers=risk_adds,
        )
    )

    cash_drift = abs(plan.cash_after_planned - plan.target_cash)
    cash_drift_ratio = cash_drift / plan.portfolio_value if plan.portfolio_value > 0 else float("inf")
    checks.append(
        _check(
            "warn" if cash_drift_ratio > cfg.warning_cash_drift_ratio else "pass",
            "warning",
            "cash_drift",
            f"planned cash drift {cash_drift_ratio:.4f} exceeds warning limit {cfg.warning_cash_drift_ratio:.4f}"
            if cash_drift_ratio > cfg.warning_cash_drift_ratio
            else "planned cash drift within warning limit",
            cash_after_planned=plan.cash_after_planned,
            target_cash=plan.target_cash,
            cash_drift=cash_drift,
            cash_drift_ratio=cash_drift_ratio,
            limit=cfg.warning_cash_drift_ratio,
        )
    )

    errors = [check for check in checks if check.severity == "error" and check.status == "fail"]
    warnings = [check for check in checks if check.severity == "warning" and check.status == "warn"]
    return RebalanceValidation(
        approved=not errors,
        manual_review_required=bool(errors or warnings),
        checks=checks,
    )
