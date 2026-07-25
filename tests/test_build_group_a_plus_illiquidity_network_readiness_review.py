from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_illiquidity_network_readiness_review import build_review, write_review


def test_build_review_blocks_without_high_frequency_liquidity_inputs(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    with duckdb.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE ohlcv (
                ticker VARCHAR,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        rows = []
        for ticker in ("0050.TW", "00631L.TW", "00632R.TW"):
            price = 100.0
            for day in range(70):
                dt = f"2026-05-{day + 1:02d}" if day < 31 else f"2026-06-{day - 30:02d}" if day < 61 else f"2026-07-{day - 60:02d}"
                price *= 1.001
                rows.append((ticker, dt, price, price * 1.01, price * 0.99, price, 1000 + day))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    review = build_review(db_path=db, as_of="2026-07-20")

    assert review["report_type"] == "group_a_plus_illiquidity_network_readiness_review"
    assert review["status"] == "blocked"
    assert review["actual_data_end"] == "2026-07-09"
    assert review["decision"]["illiquidity_network_ready"] is False
    assert review["decision"]["daily_ohlcv_liquidity_stress_proxy_available"] is True
    assert review["decision"]["crash_guard_allowed"] is False
    assert "missing_high_frequency_bid_ask" in review["blocking_reasons"]
    assert "missing_market_wide_failure_events" in review["blocking_reasons"]
    assert "nmi_illiquidity_network_not_implemented" in review["blocking_reasons"]
    plan = review["data_backfill_plan"]
    assert plan["current_decision"]["high_frequency_backfill"] == "deferred"
    assert plan["current_decision"]["allowed_next_step"] == "daily_ohlcv_volume_proxy_only_research_dashboard"
    assert plan["minimum_viable_tables"]["intraday_bid_ask_quotes"]["minimum_frequency"] == "1min_or_better"
    assert plan["proxies_allowed_now"]["daily_ohlcv_volume_proxy"]["paper_equivalent"] is False
    proxy = review["daily_ohlcv_liquidity_stress_proxy"]
    assert proxy["status"] == "available_research_proxy"
    assert proxy["paper_equivalent"] is False
    assert proxy["coverage_tickers"] == 3
    assert proxy["stress_state"] in {"normal", "watch", "elevated", "stress", "unavailable"}
    assert proxy["state_thresholds"]["elevated_gte"] == 0.20
    assert proxy["manual_review_required"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
        "report_type": "group_a_plus_illiquidity_network_readiness_review",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "illiquidity_network_readiness_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
