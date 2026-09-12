from __future__ import annotations

from pathlib import Path
from datetime import date, timedelta

import duckdb

from scripts.evaluate import build_group_a_plus_2608_08405_erosion_persistence_shadow as module


def _make_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv(dt DATE, ticker VARCHAR, close DOUBLE, volume DOUBLE)")
        for ticker in ["0050.TW", "00631L.TW"]:
            close = 100.0
            rows = []
            for i in range(140):
                shock = 1.0 + (0.002 if i % 5 in {0, 1} else -0.001)
                close *= shock
                volume = 1_000_000 + (100_000 if i % 5 in {0, 1} else 10_000)
                rows.append(((date(2026, 1, 1) + timedelta(days=i)).isoformat(), ticker, close, volume))
            con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?)", rows)
    finally:
        con.close()


def test_erosion_persistence_shadow_proxy_available_but_not_kernel(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    _make_db(db)

    report = module.build_report(
        db_path=db,
        tickers=("0050.TW", "00631L.TW"),
        as_of=None,
        hold_periods=(20, 60),
    )
    markdown = module._markdown(report)

    assert report["status"] == "proxy_available_not_calibrated_kernel"
    assert report["summary"]["proxy_available_count"] == 2
    assert report["decision"]["steady_state_kernel_calibrated_to_group_a_plus"] is False
    assert report["decision"]["capacity_deattenuation_allowed"] is False
    assert "proxy_not_causal_capacity_evidence" in report["blocking_reasons"]
    assert "## Ticker Estimates" in markdown


def test_erosion_persistence_shadow_blocks_without_ohlcv(tmp_path: Path) -> None:
    db = tmp_path / "missing.duckdb"

    report = module.build_report(
        db_path=db,
        tickers=("0050.TW",),
        as_of=None,
        hold_periods=(20,),
    )

    assert report["status"] == "blocked"
    assert "ohlcv_proxy_persistence_unavailable" in report["blocking_reasons"]
    assert report["decision"]["latest_strategy_change_allowed"] is False
