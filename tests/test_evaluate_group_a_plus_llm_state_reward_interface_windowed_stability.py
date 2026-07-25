from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (
    ACCEPTED_PROPOSAL_ID,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_windowed_stability import (
    build_review,
    write_review,
)


def _validation(path: Path) -> Path:
    path.write_text(
        json.dumps({"summary": {"accepted_proposal_ids": [ACCEPTED_PROPOSAL_ID]}}),
        encoding="utf-8",
    )
    return path


def _available_review(path: Path) -> Path:
    path.write_text(json.dumps({"status": "available_for_manual_offline_review"}), encoding="utf-8")
    return path


def _db(path: Path, tickers: list[str], rows: int = 360) -> Path:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    base = pd.Series(range(rows), dtype=float) * 0.1 + 50.0
    frames = []
    for ticker in tickers:
        if ticker == "00632R.TW":
            close = 10_000.0 / base
        elif ticker == "00631L.TW":
            close = base * 1.8
        else:
            close = base
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


def test_build_review_accepts_windowed_stability_without_live_effects(tmp_path: Path) -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW"]
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        multi_ticker_smoke_path=_available_review(tmp_path / "multi.json"),
        feature_stability_path=_available_review(tmp_path / "feature.json"),
        db_path=_db(tmp_path / "stock_data.db", tickers),
        tickers=tickers,
        rolling_windows=[63, 126],
        stress_windows=[
            {"name": "synthetic_stress", "start": "2025-06-01", "end": "2026-03-31", "type": "stress_window"}
        ],
        min_overlap=40,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_windowed_stability_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["ticker_count"] == 3
    assert review["summary"]["available_ticker_count"] == 3
    assert review["blocking_reasons"] == []
    assert review["decision"]["windowed_stability_ready_for_research_review"] is True
    relationships = review["stress_window_relationships"][0]["relationships"]
    by_target = {row["target"]: row for row in relationships}
    assert by_target["00631L.TW"]["relationship"] == "high_positive_benchmark_correlation"
    assert by_target["00632R.TW"]["relationship"] == "high_negative_benchmark_correlation"
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_missing_target_frame(tmp_path: Path) -> None:
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        multi_ticker_smoke_path=_available_review(tmp_path / "multi.json"),
        feature_stability_path=_available_review(tmp_path / "feature.json"),
        db_path=_db(tmp_path / "stock_data.db", ["0050.TW"]),
        tickers=["0050.TW", "00631L.TW"],
        rolling_windows=[63],
        stress_windows=[
            {"name": "synthetic_stress", "start": "2025-06-01", "end": "2026-03-31", "type": "stress_window"}
        ],
        min_overlap=40,
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert review["summary"]["missing_tickers"] == ["00631L.TW"]
    assert "missing_feature_frames:00631L.TW" in review["blocking_reasons"]
    assert review["decision"]["allow_00631l_add"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "windowed.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_windowed_stability_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_windowed_stability_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
