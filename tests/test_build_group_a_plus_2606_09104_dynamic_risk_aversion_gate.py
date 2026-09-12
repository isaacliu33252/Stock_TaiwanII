from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2606_09104_dynamic_risk_aversion_gate import build_gate, write_gate


def _seed_db(path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", periods=320)
    price = 100.0
    rows = []
    for i, dt in enumerate(dates):
        ret = -0.018 if i >= 280 and i % 3 == 0 else 0.001
        price *= 1.0 + ret
        rows.append({"dt": str(dt.date()), "ticker": "0050.TW", "close": price})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_dynamic_risk_aversion_gate_supports_cash_floor_in_high_risk(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)
    forward = _write_json(
        tmp_path / "forward.json",
        {
            "live_signal": {
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "target_weights": {"0050.TW": 0.3, "cash": 0.7},
                "market_state": {"state": "bull_pullback_deep"},
            }
        },
    )
    bled = _write_json(
        tmp_path / "bled.json",
        {
            "target_tail_reviews": [
                {"target_name": "guarded_live_target", "student_t_adjusted_daily_es95": -0.01},
                {"target_name": "raw_a2118_seed_ensemble_target", "student_t_adjusted_daily_es95": -0.04},
            ]
        },
    )
    downside = _write_json(tmp_path / "downside.json", {"latest_pair_signals": [{"pair": "0050.TW_00679B.TWO", "diversification_state": "DIVERSIFICATION_WEAK"}]})

    report = build_gate(
        db_path=db,
        start="2025-01-02",
        end="2026-03-25",
        forward_monitor_path=forward,
        bled_tail_review_path=bled,
        downside_diversification_path=downside,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_dynamic_risk_aversion_gate"
    assert report["status"] == "available_for_shadow_monitoring"
    assert report["risk_aversion"]["state"] in {"HIGH", "EXTREME"}
    assert report["decision"]["supports_current_cash_floor"] is True
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["train_cnn_risk_aversion_now"] is False


def test_dynamic_risk_aversion_gate_blocks_missing_db(tmp_path: Path) -> None:
    report = build_gate(db_path=tmp_path / "missing.db", end="2026-03-25")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_dynamic_risk_aversion_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_dynamic_risk_aversion_gate",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_dynamic_risk_aversion_gate_20260824.json").exists()
