from __future__ import annotations

import json

import pytest

from group_a_plus.dashboard.static_dashboard import build_dashboard_from_files, build_dashboard_html


def test_build_dashboard_html_escapes_signal_content() -> None:
    html = build_dashboard_html(
        live_signal={
            "strategy_id": "<script>alert(1)</script>",
            "strategy_status": "active",
            "execution_allowed": True,
            "actual_data_date": "2026-07-27",
            "target_weights": {"0050.TW": 0.5, "cash": 0.5},
            "latest_prices": {"0050.TW": 101.5},
            "market_state": {"label_zh": "低風險盤整"},
        },
        holdings_snapshot={"current_shares": {"0050.TW": 1000}, "cash": 50000},
    )

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "0050.TW" in html
    assert "50.0%" in html


def test_build_dashboard_from_files_accepts_wrapped_live_signal(tmp_path) -> None:
    signal_path = tmp_path / "live_signal.json"
    holdings_path = tmp_path / "holdings.json"
    output_path = tmp_path / "dashboard.html"
    signal_path.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    "strategy_id": "a2118",
                    "strategy_status": "active",
                    "execution_allowed": True,
                    "actual_data_date": "2026-07-27",
                    "target_weights": {"0050.TW": 0.5, "cash": 0.5},
                    "latest_prices": {"0050.TW": 100},
                },
            }
        ),
        encoding="utf-8",
    )
    holdings_path.write_text(
        json.dumps({"current_shares": {"0050.TW": 1000}, "cash": 100000}),
        encoding="utf-8",
    )

    result = build_dashboard_from_files(
        signal_path=signal_path,
        ops_health_path=tmp_path / "missing_ops.json",
        crash_risk_path=tmp_path / "missing_crash.json",
        rebalance_path=tmp_path / "missing_rebalance.json",
        holdings_path=holdings_path,
        output_path=output_path,
    )

    assert result["holdings_loaded"] is True
    assert result["rebalance_loaded"] is False
    assert output_path.exists()
    assert "Group A+ Dashboard" in output_path.read_text(encoding="utf-8")


def test_build_dashboard_from_files_requires_live_signal(tmp_path) -> None:
    with pytest.raises(ValueError, match="live signal unavailable"):
        build_dashboard_from_files(
            signal_path=tmp_path / "missing_signal.json",
            output_path=tmp_path / "dashboard.html",
        )
