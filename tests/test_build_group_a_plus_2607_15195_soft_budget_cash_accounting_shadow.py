from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2607_15195_soft_budget_cash_accounting_shadow import (
    build_shadow,
    write_shadow,
)


def _seed_db(path: Path) -> None:
    rows = []
    for dt in pd.bdate_range("2026-07-01", periods=30):
        for ticker, price, volume in [
            ("0050.TW", 100.0, 5_000_000),
            ("00631L.TW", 30.0, 20_000_000),
            ("00632R.TW", 10.0, 8_000_000),
            ("00679B.TWO", 25.0, 3_000_000),
        ]:
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": price, "volume": volume})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE, volume BIGINT)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    live = tmp_path / "live.json"
    forward = tmp_path / "forward.json"
    live.write_text(
        json.dumps(
            {
                "as_of": "2026-08-24",
                "portfolio_state": {
                    "cash_balance": 670_000.0,
                    "total_assets": 1_000_000.0,
                    "shares": {"0050.TW": 3000, "00631L.TW": 400, "00632R.TW": 0, "00679B.TWO": 100},
                    "latest_prices": {"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0, "00679B.TWO": 25.0},
                    "weights": {"0050.TW": 0.30, "00631L.TW": 0.012, "00632R.TW": 0.0, "00679B.TWO": 0.0025},
                    "cash_weight": 0.67,
                },
                "target_weights_for_action": {"0050.TW": 0.70, "00631L.TW": 0.30, "00632R.TW": 0.0, "00679B.TWO": 0.0},
            }
        ),
        encoding="utf-8",
    )
    forward.write_text(
        json.dumps(
            {
                "as_of": "2026-08-24",
                "live_signal": {
                    "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                    "target_weights": {
                        "0050.TW": 0.30,
                        "00631L.TW": 0.0,
                        "00632R.TW": 0.0,
                        "00679B.TWO": 0.0,
                        "cash": 0.70,
                    },
                    "market_state": {"state": "bull_pullback_deep"},
                },
            }
        ),
        encoding="utf-8",
    )
    return live, forward


def test_soft_budget_cash_accounting_shadow_prefers_partial_raw_alignment(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)
    live, forward = _write_inputs(tmp_path)

    report = build_shadow(
        db_path=db,
        live_snapshot_path=live,
        forward_monitor_path=forward,
        fractions=(0.0, 0.25, 0.5, 0.75, 1.0),
        budget_penalty_bps_per_l1_unit=5.0,
        min_trade_notional=1000,
    )

    assert report["report_type"] == "group_a_plus_2607_15195_soft_budget_cash_accounting_shadow"
    assert report["status"] == "available_for_shadow_monitoring"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["raw_a2118_can_override_guarded_target"] is False
    reviews = {row["target_name"]: row for row in report["target_ladder_reviews"]}
    assert reviews["raw_a2118_seed_ensemble_target"]["best_shadow_fraction"] < 1.0
    assert "raw_a2118_target_prefers_partial_alignment_under_soft_budget" in report["warning_reasons"]


def test_soft_budget_cash_accounting_shadow_blocks_missing_inputs(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    forward = tmp_path / "forward.json"
    live.write_text("{}", encoding="utf-8")
    forward.write_text("{}", encoding="utf-8")

    report = build_shadow(db_path=tmp_path / "missing.db", live_snapshot_path=live, forward_monitor_path=forward)

    assert report["status"] == "blocked"
    assert "portfolio_state_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_soft_budget_cash_accounting_shadow_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2607_15195_soft_budget_cash_accounting_shadow",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_shadow(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2607_15195_soft_budget_cash_accounting_shadow_20260824.json").exists()
