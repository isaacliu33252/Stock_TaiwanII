from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.sweep_group_a_plus_llm_state_reward_downside_tail_decay_params import (
    build_review,
    write_review,
)


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


def test_build_review_sweeps_downside_tail_params_without_live_effects(tmp_path: Path) -> None:
    review = build_review(
        db_path=_db(tmp_path / "stock_data.db", ["0050.TW", "00631L.TW", "00632R.TW"]),
        tickers=["0050.TW", "00631L.TW", "00632R.TW"],
        start="2025-01-01",
        min_rows=80,
        drawdown_weights=[0.3, 0.5],
        volatility_weights=[0.1],
        tail_decay_weights=[0.2],
        volatility_scales=[2.0],
        tail_decay_scales=[4.0, 6.0],
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_downside_tail_decay_param_sweep"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["evaluated_count"] == 4
    assert review["summary"]["best_params"] is not None
    assert review["top_candidates"]
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sweep.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_downside_tail_decay_param_sweep",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_downside_tail_decay_param_sweep_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
