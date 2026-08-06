from __future__ import annotations

from group_a_plus.portfolio.rebalance_plan import RebalanceConfig, build_rebalance_plan
from group_a_plus.portfolio.rebalance_validation import RebalanceRiskConfig, validate_rebalance_plan


def _signal(**overrides):
    base = {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "actual_data_date": "2026-07-27",
        "execution_allowed": True,
        "execution_guard_reasons": [],
        "signal_alerts": [],
        "target_weights": {
            "0050.TW": 0.50,
            "00631L.TW": 0.20,
            "cash": 0.30,
        },
        "latest_prices": {
            "0050.TW": 100.0,
            "00631L.TW": 25.0,
        },
    }
    base.update(overrides)
    return base


def _plan(signal=None):
    return build_rebalance_plan(
        signal or _signal(),
        current_shares={"0050.TW": 4_000, "00631L.TW": 12_000},
        cash=300_000.0,
        config=RebalanceConfig(min_trade_value=1_000.0),
    )


def _check_by_name(validation):
    return {check.name: check for check in validation.checks}


def test_validate_rebalance_plan_approves_normal_plan() -> None:
    validation = validate_rebalance_plan(_plan(), daily_signal=_signal())

    assert validation.approved is True
    assert validation.manual_review_required is False
    checks = _check_by_name(validation)
    assert checks["execution_allowed"].status == "pass"
    assert checks["max_leveraged_target_weight"].status == "pass"


def test_validate_rebalance_plan_blocks_when_live_signal_disallows_execution() -> None:
    signal = _signal(execution_allowed=False, execution_guard_reasons=["external data stale"])
    validation = validate_rebalance_plan(_plan(signal), daily_signal=signal)

    assert validation.approved is False
    checks = _check_by_name(validation)
    assert checks["execution_allowed"].status == "fail"
    assert checks["execution_allowed"].metadata["guard_reasons"] == ["external data stale"]


def test_validate_rebalance_plan_blocks_large_order_value() -> None:
    validation = validate_rebalance_plan(
        _plan(),
        daily_signal=_signal(),
        config=RebalanceRiskConfig(max_order_value=50_000.0),
    )

    assert validation.approved is False
    checks = _check_by_name(validation)
    assert checks["max_order_value"].status == "fail"
    assert checks["max_order_value"].metadata["max_order_value"] == 100_000.0


def test_validate_rebalance_plan_blocks_leveraged_weight_above_limit() -> None:
    signal = _signal(target_weights={"0050.TW": 0.30, "00631L.TW": 0.40, "cash": 0.30})
    validation = validate_rebalance_plan(
        build_rebalance_plan(
            signal,
            current_shares={"0050.TW": 3_000, "00631L.TW": 8_000},
            cash=500_000.0,
            config=RebalanceConfig(min_trade_value=1_000.0),
        ),
        daily_signal=signal,
        config=RebalanceRiskConfig(max_leveraged_target_weight=0.25),
    )

    assert validation.approved is False
    assert _check_by_name(validation)["max_leveraged_target_weight"].status == "fail"


def test_validate_rebalance_plan_blocks_risk_adds_when_ncf_stale() -> None:
    signal = _signal(signal_alerts=[{"type": "ncf_panel_stale"}])
    validation = validate_rebalance_plan(_plan(signal), daily_signal=signal)

    assert validation.approved is False
    check = _check_by_name(validation)["ncf_stale_no_new_risk_adds"]
    assert check.status == "fail"
    assert check.metadata["risk_add_tickers"] == ["0050.TW"]


def test_validate_rebalance_plan_warns_on_cash_drift() -> None:
    plan = build_rebalance_plan(
        _signal(),
        current_shares={"0050.TW": 3_800, "00631L.TW": 8_000},
        cash=420_000.0,
        config=RebalanceConfig(min_trade_value=1.0, lot_sizes={"0050.TW": 1_000}),
    )
    validation = validate_rebalance_plan(
        plan,
        daily_signal=_signal(),
        config=RebalanceRiskConfig(warning_cash_drift_ratio=0.005),
    )

    assert validation.approved is True
    assert validation.manual_review_required is True
    assert _check_by_name(validation)["cash_drift"].status == "warn"
