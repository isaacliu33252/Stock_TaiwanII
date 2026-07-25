from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_speculative_influence_network_readiness_review import (
    build_review,
    write_review,
)


def test_build_review_blocks_without_sin_inputs(tmp_path: Path) -> None:
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
            for day in range(3):
                rows.append((ticker, f"2026-07-{day + 15:02d}", 100.0, 101.0, 99.0, 100.0, 1000))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    review = build_review(db_path=db, as_of="2026-07-20")

    assert review["report_type"] == "group_a_plus_speculative_influence_network_readiness_review"
    assert review["status"] == "blocked"
    assert review["actual_data_end"] == "2026-07-17"
    assert review["decision"]["speculative_influence_network_ready"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["data"]["broad_universe_ready"] is False
    assert "broad_stock_universe_insufficient_for_sin" in review["blocking_reasons"]
    assert "missing_sector_or_style_mapping" in review["blocking_reasons"]
    assert "missing_hmm_bubble_state_probabilities" in review["blocking_reasons"]
    assert "missing_transfer_entropy_network" in review["blocking_reasons"]
    assert "sornette_andersen_hmm_not_implemented" in review["blocking_reasons"]
    assert "transfer_entropy_sin_not_implemented" in review["blocking_reasons"]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
        "report_type": "group_a_plus_speculative_influence_network_readiness_review",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "speculative_influence_network_readiness_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
