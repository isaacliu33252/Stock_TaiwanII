from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_reduced_rank_correlation_proxy import build_proxy, write_proxy


def _build_price_db(db_path: Path, ticker_count: int = 12, days: int = 95) -> None:
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = []
        start = date(2026, 1, 1)
        for ticker_idx in range(ticker_count):
            ticker = f"T{ticker_idx:02d}.TW"
            for day in range(days):
                price = 100.0 + ticker_idx + day * (0.1 + ticker_idx * 0.001)
                rows.append((ticker, str(start + timedelta(days=day)), price))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def test_build_proxy_outputs_shadow_metrics_when_panel_is_available(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _build_price_db(db_path)

    proxy = build_proxy(
        db_path=db_path,
        as_of="2026-04-05",
        window=20,
        min_history=40,
        analysis_lookback=80,
        min_tickers=10,
    )

    assert proxy["status"] == "available_for_manual_review"
    assert proxy["method"]["paper_equivalent"] is False
    assert proxy["coverage"]["usable_ticker_count"] == 12
    assert proxy["coverage"]["snapshot_count"] > 0
    assert proxy["latest"]["state"] in {"normal", "watch", "elevated_fragility"}
    assert proxy["decision"]["proxy_available_for_shadow_review"] is True
    assert proxy["decision"]["promote_to_live"] is False
    assert proxy["decision"]["target_weight_change_allowed"] is False
    assert proxy["decision"]["allow_00631l_add"] is False
    assert proxy["decision"]["allow_00632r_open"] is False
    assert "weak_cross_market_proxy_not_paper_equivalent" in proxy["warning_reasons"]


def test_write_proxy_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "proxy.json"
    history = tmp_path / "history"
    payload = {
        "report_type": "group_a_plus_reduced_rank_correlation_proxy",
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
    }

    write_proxy(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    history_file = history / "reduced_rank_correlation_proxy_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == payload
