#!/usr/bin/env python3
"""Tests for GroupA+ daily status payload assembly."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from scripts.misc.check_group_a_plus_daily_status import _live_status_report, _markdown_text


def _write_standard(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps({"success": True, "data": data, "metadata": {}, "error": None}, ensure_ascii=False),
        encoding="utf-8",
    )


def _args(live_signal: Path, execution_plan: Path) -> Namespace:
    return Namespace(
        live_signal=str(live_signal),
        execution_plan=str(execution_plan),
        compounding_regime=str(live_signal.parent / "missing_compounding_regime.json"),
        dfl_advisory=str(live_signal.parent / "missing_dfl_advisory.json"),
        dfl_shadow_ensemble=str(live_signal.parent / "missing_dfl_shadow_ensemble.json"),
        dfl_active_date_audit=str(live_signal.parent / "missing_dfl_active_date_audit.json"),
        check_date="2026-07-09",
        max_business_stale_days=3,
    )


def _live_signal_data() -> dict:
    return {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "strategy_status": "active",
        "requested_as_of_date": "2026-07-09",
        "actual_data_date": "2026-07-09",
        "execution_allowed": True,
        "execution_guard_reasons": [],
        "execution_warning_reasons": [],
        "action": "rebalance_to_target",
        "regime_reason": "active strategy regime",
        "execution_regime": "golden1",
        "target_weights": {"0050.TW": 0.8, "00631L.TW": 0.2},
        "reference_target_shares_before_cost": {"0050.TW": 100, "00631L.TW": 150},
        "estimated_cash_after_rounding_before_cost": 1000.0,
        "data_freshness": {"optional_sources": {}},
    }


def test_live_status_includes_aligned_execution_plan_pre_trade_guard(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
            "pre_trade_guard": {
                "status": "blocked",
                "ticker": "00631L.TW",
                "allow_00631l_add": False,
                "policy": "advisory_no_auto_weight_change",
                "blocked_trades": [
                    {
                        "ticker": "00631L.TW",
                        "side": "buy",
                        "current_shares": 100,
                        "requested_target_shares": 150,
                        "guarded_target_shares": 100,
                    }
                ],
            },
            "compounding_regime_pre_trade_guard": {
                "status": "blocked",
                "ticker": "00631L.TW",
                "allow_00631l_add": False,
                "compounding_regime": "MEAN_REVERTING",
                "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
            },
            "pre_trade_guards": [
                {"name": "volatility_gate_no_00631l_add", "status": "blocked"},
                {"name": "compounding_regime_no_00631l_add", "status": "blocked"},
            ],
        },
    )

    report = _live_status_report(_args(live_signal, execution_plan))
    guard = report["group_a_plus"]["pre_trade_guard"]

    assert guard["status"] == "blocked"
    assert guard["allow_00631l_add"] is False
    assert [check for check in report["checks"] if check["name"] == "execution_plan_pre_trade_guard"][0]["status"] == "ok"
    markdown = _markdown_text(report)
    assert "## Pre-Trade Guard" in markdown
    assert "## 00631L Compounding Guard" in markdown
    assert "00631L add: `blocked`" in markdown


def test_live_status_ignores_stale_execution_plan_guard(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-08",
            "pre_trade_guard": {"status": "blocked", "allow_00631l_add": False},
        },
    )

    report = _live_status_report(_args(live_signal, execution_plan))
    guard_check = [check for check in report["checks"] if check["name"] == "execution_plan_pre_trade_guard"][0]

    assert report["group_a_plus"]["pre_trade_guard"] == {}
    assert guard_check["status"] == "warn"
    assert report["overall_status"] == "warn"


def test_live_status_includes_compounding_regime_diagnostic(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    compounding = tmp_path / "compounding.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    compounding.write_text(
        json.dumps(
            {
                "report_type": "00631l_leveraged_compounding_regime",
                "generated_at": "2026-07-09T18:00:00",
                "active_allocation_impact": "none",
                "latest": {
                    "date": "2026-07-09",
                    "compounding_regime": "MEAN_REVERTING",
                    "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
                    "trend_score": 3,
                    "mean_reversion_score": 4,
                    "rolling_AR1_5d": -0.12,
                    "rolling_AR1_20d": -0.08,
                    "variance_ratio": 0.91,
                    "trend_persistence": 0.50,
                    "reversal_speed": 0.65,
                    "positive_return_streak": 0.0,
                    "negative_return_streak": 2.0,
                    "drawdown_recovery_ratio": 0.70,
                    "00631L_vs_0050_relative_momentum": -0.02,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.compounding_regime = str(compounding)

    report = _live_status_report(args)
    diagnostic = report["group_a_plus"]["compounding_regime_diagnostic"]

    assert diagnostic["status"] == "ok"
    assert diagnostic["compounding_regime"] == "MEAN_REVERTING"
    assert diagnostic["active_allocation_impact"] == "none"
    markdown = _markdown_text(report)
    assert "## 00631L Compounding Regime" in markdown
    assert "MEAN_REVERTING" in markdown


def test_live_status_includes_dfl_advisory(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dfl = tmp_path / "dfl.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    dfl.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_type": "a2118_dfl_advisory",
                "status": "available",
                "policy": "advisory_only_no_auto_weight_change",
                "action": "CAP10",
                "advisory_active": True,
                "selected_decision": {"predicted_regret": 0.0012},
                "selective_variants": {
                    "p50": {
                        "status": "available",
                        "action": "KEEP",
                        "advisory_active": False,
                        "selected_decision": None,
                    },
                    "p70": {
                        "status": "available",
                        "action": "CAP10",
                        "advisory_active": True,
                        "selected_decision": {"reliability_error_percentile": 0.42},
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_advisory = str(dfl)

    report = _live_status_report(args)
    advisory = report["group_a_plus"]["dfl_advisory"]

    assert advisory["status"] == "available"
    assert advisory["action"] == "CAP10"
    markdown = _markdown_text(report)
    assert "## A21.18 DFL Advisory" in markdown
    assert "Predicted regret: `0.0012`" in markdown
    assert "### Selective Variants" in markdown
    assert "`p70` action `CAP10` active `True` reliability `0.42`" in markdown


def test_live_status_includes_dfl_active_date_audit(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    audit = tmp_path / "dfl_audit.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    audit.write_text(
        json.dumps(
            {
                "report_type": "a2118_dfl_active_date_audit",
                "status": "research_only",
                "conclusion": "passes_replay_audit_with_warnings_shadow_only",
                "summary": {
                    "active_days": 7,
                    "all_checks_pass": True,
                    "warning_days": 3,
                    "existing_guard_overlap_days": 0,
                    "total_estimated_cost_bps": 8.0749,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_active_date_audit = str(audit)

    report = _live_status_report(args)
    active_date_audit = report["group_a_plus"]["dfl_active_date_audit"]

    assert active_date_audit["status"] == "research_only"
    assert active_date_audit["summary"]["active_days"] == 7
    markdown = _markdown_text(report)
    assert "## A21.18 DFL Active-Date Audit" in markdown
    assert "passes_replay_audit_with_warnings_shadow_only" in markdown
    assert "Total estimated cost bps / 1M: `8.0749`" in markdown


def _write_frozen_dfl_source(path: Path, *, live_max_date: str, oos_max_date: str = "2019-12-31") -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "a2118_decision_focused_action_shadow",
                "status": "available",
                "generated_at": f"{live_max_date}T14:45:49",
                "results": [
                    {
                        "label": "live_2024_2026",
                        "bucket": "tuning_window",
                        "recent_decisions": [{"date": live_max_date, "action": "KEEP"}],
                        "non_keep_decisions": [],
                    },
                    {
                        "label": "2019_recovery",
                        "bucket": "out_of_sample",
                        "recent_decisions": [{"date": oos_max_date, "action": "KEEP"}],
                        "non_keep_decisions": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_live_status_dfl_frozen_input_staleness_ok_within_threshold(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dfl = tmp_path / "dfl.json"
    frozen_source = tmp_path / "frozen_source.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {"strategy_id": "a2118_a2111_ncf_late_bull_deleverage", "actual_data_date": "2026-07-09"},
    )
    _write_frozen_dfl_source(frozen_source, live_max_date="2026-07-05")
    dfl.write_text(
        json.dumps(
            {
                "status": "available",
                "action": "KEEP",
                "advisory_active": False,
                "input": str(frozen_source),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_advisory = str(dfl)

    report = _live_status_report(args)
    staleness = report["group_a_plus"]["dfl_frozen_input_staleness"]
    check = [c for c in report["checks"] if c["name"] == "dfl_advisory_frozen_input_staleness"][0]

    assert staleness["status"] == "ok"
    assert staleness["max_live_window_decision_date"] == "2026-07-05"
    assert staleness["calendar_gap_days"] == 4
    assert check["status"] == "ok"
    assert report["overall_status"] == "ok"


def test_live_status_dfl_frozen_input_staleness_warns_past_threshold(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dfl = tmp_path / "dfl.json"
    frozen_source = tmp_path / "frozen_source.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {"strategy_id": "a2118_a2111_ncf_late_bull_deleverage", "actual_data_date": "2026-07-09"},
    )
    # Frozen backtest was generated 2026-06-14 and never re-run -- 25 calendar
    # days behind check_date, well past the default 14-day threshold.
    _write_frozen_dfl_source(frozen_source, live_max_date="2026-06-14")
    dfl.write_text(
        json.dumps(
            {
                "status": "available",
                "action": "KEEP",
                "advisory_active": False,
                "input": str(frozen_source),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_advisory = str(dfl)

    report = _live_status_report(args)
    staleness = report["group_a_plus"]["dfl_frozen_input_staleness"]
    check = [c for c in report["checks"] if c["name"] == "dfl_advisory_frozen_input_staleness"][0]

    assert staleness["calendar_gap_days"] == 25
    assert check["status"] == "warn"
    assert report["overall_status"] == "warn"


def test_live_status_dfl_frozen_input_staleness_not_applicable_when_dfl_unavailable(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {"strategy_id": "a2118_a2111_ncf_late_bull_deleverage", "actual_data_date": "2026-07-09"},
    )

    report = _live_status_report(_args(live_signal, execution_plan))
    check = [c for c in report["checks"] if c["name"] == "dfl_advisory_frozen_input_staleness"][0]

    assert check["status"] == "ok"
    assert report["overall_status"] == "ok"


def test_live_status_includes_dfl_shadow_ensemble(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    ensemble = tmp_path / "ensemble.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    ensemble.write_text(
        json.dumps(
            {
                "report_type": "a2118_dfl_shadow_ensemble",
                "status": "available",
                "policy": "shadow_only_no_auto_weight_change",
                "ensemble_level": "watch",
                "manual_review_required": True,
                "signals": {
                    "base": {"action": "KEEP", "active": False, "reliability_error_percentile": None},
                    "p50": {"action": "KEEP", "active": False, "reliability_error_percentile": None},
                    "p70": {"action": "CAP10", "active": True, "reliability_error_percentile": 0.42},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_shadow_ensemble = str(ensemble)

    report = _live_status_report(args)
    shadow = report["group_a_plus"]["dfl_shadow_ensemble"]

    assert shadow["ensemble_level"] == "watch"
    markdown = _markdown_text(report)
    assert "## A21.18 DFL Shadow Ensemble" in markdown
    assert "Level: `watch`" in markdown
    assert "`p70` action `CAP10` active `True` reliability `0.42`" in markdown
