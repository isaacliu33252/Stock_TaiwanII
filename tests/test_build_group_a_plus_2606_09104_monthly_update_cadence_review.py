from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2606_09104_monthly_update_cadence_review import build_review, write_review


def _seed_db(path: Path) -> None:
    dates = pd.bdate_range("2024-01-02", periods=260)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00632R.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for i, dt in enumerate(dates):
        cycle = 0.003 if (i // 20) % 2 == 0 else -0.002
        rets = {
            "0050.TW": cycle,
            "00631L.TW": cycle * 1.8,
            "00632R.TW": -cycle * 0.8,
            "00679B.TWO": 0.0001,
        }
        for ticker, ret in rets.items():
            prices[ticker] *= 1.0 + ret
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": prices[ticker]})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def _forward_monitor(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "live_signal": {
                    "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                    "target_weights": {"0050.TW": 0.3, "cash": 0.7},
                    "market_state": {"state": "bull_pullback_deep"},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_monthly_update_cadence_review_compares_shadow_refreshes(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    report = build_review(
        db_path=db,
        start="2024-01-02",
        end="2024-12-31",
        train_window=70,
        horizon=10,
        eval_step=5,
        weekly_update_interval=5,
        monthly_update_interval=21,
        min_prediction_dates=20,
        forward_monitor_path=_forward_monitor(tmp_path / "forward.json"),
    )

    assert report["report_type"] == "group_a_plus_2606_09104_monthly_update_cadence_review"
    assert report["status"] == "available_for_shadow_monitoring"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["use_daily_refresh_for_live_trading"] is False
    assert report["decision"]["use_weekly_refresh_for_live_trading"] is False
    assert report["decision"]["use_monthly_refresh_for_live_trading"] is False
    assert report["cadence_comparison"]["daily_refresh"]["prediction_dates"] >= 20
    assert report["cadence_comparison"]["weekly_hold_last_prior"]["prediction_dates"] >= 20
    assert report["cadence_comparison"]["monthly_hold_last_prior"]["prediction_dates"] >= 20


def test_monthly_update_cadence_review_blocks_missing_db(tmp_path: Path) -> None:
    report = build_review(db_path=tmp_path / "missing.db", end="2024-12-31")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_monthly_update_cadence_review_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_monthly_update_cadence_review",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_review(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_monthly_update_cadence_review_20260824.json").exists()
