from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from scripts.evaluate import build_group_a_plus_00632r_discipline_guard as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_trade_check(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "trade_check"
    ws.append(["ticker", "side"])
    ws.append(["00632R.TW", "buy"])
    ws.append(["0050.TW", "buy"])
    wb.save(path)


def test_00632r_discipline_guard_blocks_dca_and_inverse_adds(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    letf = tmp_path / "letf.json"
    tail = tmp_path / "tail.json"
    trade_check = tmp_path / "trade_check.xlsx"
    _write_json(
        live,
        {
            "data": {
                "requested_as_of_date": "2026-09-07",
                "actual_data_date": "2026-09-04",
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "target_weights": {"0050.TW": 0.527, "00631L.TW": 0.173, "00632R.TW": 0.0, "cash": 0.30},
            }
        },
    )
    _write_json(letf, {"decision": {"allow_00632r_open": False}})
    _write_json(tail, {"decision": {"allow_00632r_open": False, "manual_hedge_discussion_allowed": False}})
    _write_trade_check(trade_check)

    report = module.build_guard(
        live_signal_path=live,
        letf_readiness_path=letf,
        tail_gate_path=tail,
        trade_check_path=trade_check,
        max_manual_weight=0.05,
    )

    assert report["decision"]["latest_strategy_rule_added"] is True
    assert report["decision"]["allow_00632r_dca"] is False
    assert report["decision"]["allow_00632r_averaging_down"] is False
    assert report["decision"]["allow_00632r_open"] is False
    assert report["decision"]["default_defense_asset"] == "cash"
    assert report["rules"]["manual_exception_max_weight"] == 0.05
    assert report["checks"]["latest_strategy_default_zero_weight_ok"] is True
    assert "dedicated_hedge_gates_do_not_allow_00632r_open" in report["blocking_reasons"]
    assert "recent_trade_review_found_00632r_buy_or_dca_records" in report["blocking_reasons"]


def test_00632r_discipline_guard_flags_nonzero_latest_weight(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    letf = tmp_path / "letf.json"
    tail = tmp_path / "tail.json"
    _write_json(live, {"target_weights": {"00632R.TW": 0.04, "cash": 0.30}})
    _write_json(letf, {"decision": {"allow_00632r_open": True}})
    _write_json(tail, {"decision": {"allow_00632r_open": True, "manual_hedge_discussion_allowed": True}})

    report = module.build_guard(
        live_signal_path=live,
        letf_readiness_path=letf,
        tail_gate_path=tail,
        trade_check_path=None,
        max_manual_weight=0.05,
    )
    markdown = module._markdown(report)

    assert report["checks"]["latest_strategy_default_zero_weight_ok"] is False
    assert "latest_strategy_00632r_target_must_default_to_zero" in report["blocking_reasons"]
    assert report["decision"]["latest_strategy_change_allowed"] is False
    assert "00632R Discipline Guard" in markdown
