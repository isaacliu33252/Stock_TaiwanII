from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_forward_shadow import build_shadow, write_shadow


def _seed_db(path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", periods=360)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for i, dt in enumerate(dates):
        if 240 <= i < 300:
            r_0050 = -0.004 if i % 2 == 0 else 0.002
            r_631 = r_0050 * 1.6 + 0.002
        elif 300 <= i < 330:
            r_0050 = 0.004
            r_631 = 0.008
        else:
            r_0050 = 0.001
            r_631 = 0.002
        rets = {"0050.TW": r_0050, "00631L.TW": r_631, "00679B.TWO": 0.0001}
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


def test_micro_add_forward_shadow_remains_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    report = build_shadow(
        db_path=db,
        start="2025-01-02",
        end="2026-05-20",
        horizon=20,
        lookback=126,
        min_events=5,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_micro_add_forward_shadow"
    assert report["status"] == "available_for_shadow_monitoring"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_micro_add_from_this_shadow"] is False
    assert report["high_extreme_event_summary"]["event_count"] >= 5


def test_micro_add_forward_shadow_blocks_missing_db(tmp_path: Path) -> None:
    report = build_shadow(db_path=tmp_path / "missing.db", end="2026-05-20")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_micro_add_forward_shadow_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_micro_add_forward_shadow",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_shadow(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_micro_add_forward_shadow_20260824.json").exists()
