from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_reduced_rank_correlation_readiness_review import (
    build_review,
    write_review,
)


def test_build_review_blocks_when_universe_and_method_are_not_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE ohlcv AS
            SELECT *
            FROM (
                VALUES
                    ('0050.TW', DATE '2026-07-15', 100.0),
                    ('0050.TW', DATE '2026-07-16', 101.0),
                    ('00631L.TW', DATE '2026-07-15', 180.0),
                    ('00631L.TW', DATE '2026-07-16', 181.0),
                    ('00632R.TW', DATE '2026-07-15', 3.5),
                    ('00632R.TW', DATE '2026-07-16', 3.4)
            ) AS t(ticker, dt, close)
            """
        )

    review = build_review(db_path=db_path, as_of="2026-07-20")

    assert review["status"] == "blocked"
    assert review["data_readiness"]["local_ticker_count"] == 3
    assert review["data_readiness"]["broad_sector_universe_ready"] is False
    assert review["decision"]["reduced_rank_correlation_ready"] is False
    assert review["decision"]["paper_equivalent_ready"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "broad_stock_universe_below_reduced_rank_requirement" in review["blocking_reasons"]
    assert "sector_metadata_missing" in review["blocking_reasons"]
    assert "reduced_rank_correlation_matrix_not_implemented" in review["blocking_reasons"]
    assert "averaged_distance_transition_monitor_not_implemented" in review["blocking_reasons"]
    assert "kmeans_market_state_snapshot_not_implemented" in review["blocking_reasons"]
    assert "taiwan_crash_window_walkforward_validation_missing" in review["blocking_reasons"]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_reduced_rank_correlation_readiness_review",
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "reduced_rank_correlation_readiness_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
