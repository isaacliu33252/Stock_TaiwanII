from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2607_16450_tail_dependence_monitor import build_monitor, write_monitor


def _seed_db(path: Path) -> None:
    idx = pd.bdate_range("2026-01-01", periods=80)
    base_rets = []
    for i in range(len(idx)):
        base_rets.append(-0.03 if i % 10 == 0 else 0.002)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for dt, base_ret in zip(idx, base_rets):
        asset_rets = {
            "0050.TW": base_ret,
            "00631L.TW": -0.06 if base_ret < 0 else 0.004,
            "00679B.TWO": 0.001 if base_ret < 0 else 0.0005,
        }
        for ticker, ret in asset_rets.items():
            prices[ticker] *= 1.0 + ret
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": prices[ticker]})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def test_tail_dependence_monitor_flags_00631l_lower_tail_dependence(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    monitor = build_monitor(
        db_path=db,
        start="2026-01-01",
        end="2026-04-30",
        tickers=("0050.TW", "00631L.TW", "00679B.TWO"),
        window=40,
        alpha=0.20,
        high_tail_dependence_threshold=0.60,
    )

    assert monitor["report_type"] == "group_a_plus_2607_16450_tail_dependence_monitor"
    assert monitor["status"] == "available_for_monitoring"
    assert monitor["decision"]["target_weight_change_allowed"] is False
    assert monitor["decision"]["allow_00631l_add_from_tail_dependence"] is False
    assert "00631l_lower_tail_dependence_high_vs_0050" in monitor["warning_reasons"]
    high_assets = {row["asset"] for row in monitor["high_tail_dependence_pairs"]}
    assert "00631L.TW" in high_assets


def test_tail_dependence_monitor_blocks_missing_database(tmp_path: Path) -> None:
    monitor = build_monitor(db_path=tmp_path / "missing.db", end="2026-04-30", window=40)

    assert monitor["status"] == "blocked"
    assert "stock_database_missing" in monitor["blocking_reasons"]
    assert monitor["decision"]["allow_00631l_add_from_tail_dependence"] is False


def test_write_tail_dependence_monitor_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    monitor = {
        "report_type": "group_a_plus_2607_16450_tail_dependence_monitor",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_monitor(monitor, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == monitor
    assert (history / "2607_16450_tail_dependence_monitor_20260824.json").exists()
