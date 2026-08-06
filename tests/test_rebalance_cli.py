from __future__ import annotations

import json

import openpyxl

from group_a_plus.portfolio.rebalance_cli import build_report_from_files


def _signal():
    return {
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


def test_build_report_from_files_writes_audit_outputs(tmp_path) -> None:
    signal_path = tmp_path / "live_signal.json"
    holdings_path = tmp_path / "holdings.json"
    latest_path = tmp_path / "latest" / "rebalance_plan.json"
    dated_path = tmp_path / "results" / "rebalance_plan_20260727.json"
    signal_path.write_text(json.dumps(_signal()), encoding="utf-8")
    holdings_path.write_text(
        json.dumps({"cash": 300_000, "holdings": {"0050.TW": 4_000, "00631L.TW": 12_000}}),
        encoding="utf-8",
    )

    result = build_report_from_files(
        signal_path=signal_path,
        holdings_path=holdings_path,
        latest_output=latest_path,
        dated_output=dated_path,
    )

    assert result["paths"] == {"latest_path": str(latest_path), "dated_path": str(dated_path)}
    latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest_payload["report_type"] == "group_a_plus_rebalance_plan_audit"
    assert latest_payload["holding_snapshot"]["current_shares"]["0050.TW"] == 4000.0
    assert latest_payload["validation"]["approved"] is True
    assert latest_payload["manual_approval"]["approved"] is False
    assert json.loads(dated_path.read_text(encoding="utf-8")) == latest_payload


def test_build_report_from_files_accepts_standard_output_wrapper(tmp_path) -> None:
    signal_path = tmp_path / "live_signal_wrapped.json"
    holdings_path = tmp_path / "holdings.json"
    latest_path = tmp_path / "latest" / "rebalance_plan.json"
    signal_path.write_text(json.dumps({"success": True, "data": _signal()}), encoding="utf-8")
    holdings_path.write_text(
        json.dumps({"cash": 300_000, "current_shares": {"0050.TW": 4_000, "00631L.TW": 12_000}}),
        encoding="utf-8",
    )

    result = build_report_from_files(
        signal_path=signal_path,
        holdings_path=holdings_path,
        latest_output=latest_path,
        dated_output=tmp_path / "dated.json",
    )

    assert result["report"]["strategy_id"] == "a2118_a2111_ncf_late_bull_deleverage"
    assert result["report"]["holding_snapshot"]["cash"] == 300_000.0


def test_build_report_from_files_accepts_excel_holdings(tmp_path) -> None:
    signal_path = tmp_path / "live_signal.json"
    excel_path = tmp_path / "holdings.xlsx"
    latest_path = tmp_path / "latest" / "rebalance_plan.json"
    signal_path.write_text(json.dumps(_signal()), encoding="utf-8")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ticker", "shares"])
    ws.append(["0050", 4000])
    ws.append(["00631L", 12000])
    wb.save(excel_path)

    result = build_report_from_files(
        signal_path=signal_path,
        holdings_excel_path=excel_path,
        cash=300_000,
        latest_output=latest_path,
        dated_output=tmp_path / "dated.json",
    )

    assert result["report"]["holding_snapshot"]["current_shares"]["0050.TW"] == 4000.0
    assert result["report"]["holding_snapshot"]["cash"] == 300_000.0
    assert latest_path.exists()
