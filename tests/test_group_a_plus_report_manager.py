#!/usr/bin/env python3
"""Tests for GroupA+ report rendering."""

from __future__ import annotations

from group_a_plus_report_manager import GroupAPlusReportManager


def test_daily_status_html_renders_pre_trade_guard_block() -> None:
    html = GroupAPlusReportManager.render_daily_status_html(
        {
            "overall_status": "warn",
            "profile": "a2118",
            "generated_at": "2026-07-09T23:30:00",
            "check_date": "2026-07-09",
            "signal": {
                "signal_status": "ok",
                "signal_reason": "active strategy regime",
                "actual_data_date": "2026-07-09",
                "business_stale_days": 0,
                "calendar_stale_days": 0,
            },
            "group_a_plus": {
                "overlay_regime": "golden1",
                "cash_after_cost": 1000.0,
                "target_shares": {"0050.TW": 40, "00631L.TW": 100},
                "pre_trade_guard": {
                    "name": "volatility_gate_no_00631l_add",
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
                            "blocked_delta_shares": 50,
                            "reason": "volatility_gate_no_00631l_add",
                        }
                    ],
                },
            },
            "checks": [],
            "source_paths": {},
        }
    )

    assert "Pre-Trade Guard" in html
    assert "00631L Add" in html
    assert "blocked" in html
    assert "advisory_no_auto_weight_change" in html
    assert "volatility_gate_no_00631l_add" in html
    assert ">50<" in html
