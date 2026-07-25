from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke import (
    ACCEPTED_PROPOSAL_ID,
    build_review,
    write_review,
)


def _validation(path: Path) -> Path:
    path.write_text(
        json.dumps({"summary": {"accepted_proposal_ids": [ACCEPTED_PROPOSAL_ID]}}),
        encoding="utf-8",
    )
    return path


def _db(path: Path, tickers: list[str], rows: int = 320) -> Path:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    frames = []
    for offset, ticker in enumerate(tickers):
        close = pd.Series(range(rows), dtype=float) * 0.1 + 50.0 + offset
        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "dt": dates.date,
                    "open": close,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "volume": 1_000_000,
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE ohlcv (
                ticker TEXT,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        con.register("df", df)
        con.execute("INSERT INTO ohlcv SELECT * FROM df")
        con.unregister("df")
    finally:
        con.close()
    return path


def test_build_review_accepts_multi_ticker_coverage_without_live_effects(tmp_path: Path) -> None:
    tickers = ["0050.TW", "00631L.TW"]
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        db_path=_db(tmp_path / "stock_data.db", tickers),
        tickers=tickers,
        start="2025-01-01",
        min_rows=240,
        min_end_date="2025-12-01",
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_multi_ticker_smoke_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["ticker_count"] == 2
    assert review["summary"]["available_for_manual_offline_review_count"] == 2
    assert review["summary"]["blocked_tickers"] == []
    assert review["blocking_reasons"] == []
    assert all(row["blocking_reasons"] == [] for row in review["ticker_results"])
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_missing_ticker(tmp_path: Path) -> None:
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        db_path=_db(tmp_path / "stock_data.db", ["0050.TW"]),
        tickers=["0050.TW", "00631L.TW"],
        start="2025-01-01",
        min_rows=240,
        min_end_date="2025-12-01",
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert review["summary"]["blocked_tickers"] == ["00631L.TW"]
    assert "blocked_tickers:00631L.TW" in review["blocking_reasons"]
    assert review["decision"]["allow_00631l_add"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "multi.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_multi_ticker_smoke_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_multi_ticker_smoke_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
