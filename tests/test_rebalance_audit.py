from __future__ import annotations

import json

from group_a_plus.portfolio.rebalance_audit import (
    build_rebalance_audit_report,
    dated_rebalance_audit_path,
    write_rebalance_audit_report,
)
from group_a_plus.portfolio.rebalance_plan import RebalanceConfig, build_rebalance_plan
from group_a_plus.portfolio.rebalance_validation import validate_rebalance_plan


def _signal(**overrides):
    base = {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "generated_at": "2026-07-28T07:13:10",
        "requested_as_of_date": "2026-07-27",
        "actual_data_date": "2026-07-27",
        "execution_regime": "golden1",
        "regime_reason": "A20.7 formal defensive state is inactive",
        "execution_allowed": True,
        "execution_guard_reasons": [],
        "strategy_status": "active",
        "signal_version": 2,
        "target_weights": {
            "0050.TW": 0.50,
            "00631L.TW": 0.20,
            "cash": 0.30,
        },
        "latest_prices": {
            "0050.TW": 100.0,
            "00631L.TW": 25.0,
        },
        "ncf_panel_coverage": {
            "panel_631l_path": None,
            "panel_631l_last_date": "2026-07-16",
        },
    }
    base.update(overrides)
    return base


def _plan_and_validation(signal):
    plan = build_rebalance_plan(
        signal,
        current_shares={"0050.TW": 4_000, "00631L.TW": 12_000},
        cash=300_000.0,
        config=RebalanceConfig(min_trade_value=1_000.0),
    )
    return plan, validate_rebalance_plan(plan, daily_signal=signal)


def test_build_rebalance_audit_report_keeps_manual_approval_separate() -> None:
    signal = _signal()
    plan, validation = _plan_and_validation(signal)

    report = build_rebalance_audit_report(
        daily_signal=signal,
        plan=plan,
        validation=validation,
        current_shares={"0050.TW": 4_000, "00631L.TW": 12_000},
        cash=300_000.0,
        generated_at="2026-07-29T09:00:00",
    )

    assert report["report_type"] == "group_a_plus_rebalance_plan_audit"
    assert report["signal"]["data_snapshot_hash"]
    assert report["validation"]["approved"] is True
    assert report["manual_approval"] == {
        "required": True,
        "approved": False,
        "approved_by": None,
        "approved_at": None,
        "notes": "",
    }
    assert report["execution"]["broker_submitted"] is False
    assert report["audit_hash"]


def test_rebalance_audit_hash_is_deterministic_for_same_payload() -> None:
    signal = _signal()
    plan, validation = _plan_and_validation(signal)
    kwargs = {
        "daily_signal": signal,
        "plan": plan,
        "validation": validation,
        "current_shares": {"0050.TW": 4_000, "00631L.TW": 12_000},
        "cash": 300_000.0,
        "generated_at": "2026-07-29T09:00:00",
    }

    report_a = build_rebalance_audit_report(**kwargs)
    report_b = build_rebalance_audit_report(**kwargs)

    assert report_a["audit_hash"] == report_b["audit_hash"]


def test_dated_rebalance_audit_path_uses_signal_asof(tmp_path) -> None:
    path = dated_rebalance_audit_path({"signal_asof": "2026-07-27"}, output_dir=tmp_path)
    assert path == tmp_path / "rebalance_plan_20260727.json"


def test_write_rebalance_audit_report_writes_latest_and_dated(tmp_path) -> None:
    signal = _signal()
    plan, validation = _plan_and_validation(signal)
    report = build_rebalance_audit_report(
        daily_signal=signal,
        plan=plan,
        validation=validation,
        current_shares={"0050.TW": 4_000, "00631L.TW": 12_000},
        cash=300_000.0,
        generated_at="2026-07-29T09:00:00",
    )

    paths = write_rebalance_audit_report(
        report,
        latest_path=tmp_path / "latest" / "rebalance_plan.json",
        dated_path=tmp_path / "results" / "rebalance_plan_20260727.json",
    )

    latest_payload = json.loads((tmp_path / "latest" / "rebalance_plan.json").read_text(encoding="utf-8"))
    dated_payload = json.loads((tmp_path / "results" / "rebalance_plan_20260727.json").read_text(encoding="utf-8"))
    assert latest_payload == report
    assert dated_payload == report
    assert paths == {
        "latest_path": str(tmp_path / "latest" / "rebalance_plan.json"),
        "dated_path": str(tmp_path / "results" / "rebalance_plan_20260727.json"),
    }
