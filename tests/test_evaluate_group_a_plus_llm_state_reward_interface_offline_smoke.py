from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (
    ACCEPTED_PROPOSAL_ID,
    DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
    build_review,
    write_review,
)


def _validation(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "summary": {"accepted_proposal_ids": [ACCEPTED_PROPOSAL_ID]},
                "decision": {
                    "promote_to_live": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _validation_with_downside_tail(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "summary": {
                    "accepted_proposal_ids": [
                        ACCEPTED_PROPOSAL_ID,
                        DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
                    ]
                },
                "decision": {
                    "promote_to_live": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _ohlcv(path: Path, rows: int = 320) -> Path:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series(range(rows), dtype=float) * 0.1 + 50.0
    df = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000,
        }
    )
    df.to_parquet(path)
    return path


def _duckdb_ohlcv(path: Path, rows: int = 320) -> Path:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series(range(rows), dtype=float) * 0.1 + 50.0
    df = pd.DataFrame(
        {
            "ticker": "0050.TW",
            "dt": dates.date,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000,
        }
    )
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


def test_build_review_accepts_offline_smoke_without_live_effects(tmp_path: Path) -> None:
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        data_path=_ohlcv(tmp_path / "ohlcv.parquet"),
        use_db=False,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_offline_smoke_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["blocking_reasons"] == []
    assert review["inputs"]["accepted_proposal_found"] is True
    assert review["data_range"]["rows"] == 320
    assert review["feature_proxy"]["relative_momentum"]["uses_future_data"] is False
    assert review["feature_proxy"]["realized_volatility"]["uses_future_data"] is False
    assert review["reward_proxy"]["reward_proxy"]["bounded_range"] == [-0.25, 0.0]
    assert review["finite_summary"]["columns"]["relative_momentum"]["finite_count"] > 0
    assert review["finite_summary"]["columns"]["realized_volatility"]["finite_count"] > 0
    assert review["decision"]["available_for_manual_offline_review"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_prefers_duckdb_ohlcv_when_available(tmp_path: Path) -> None:
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        data_path=_ohlcv(tmp_path / "fallback.parquet", rows=140),
        db_path=_duckdb_ohlcv(tmp_path / "stock_data.db", rows=320),
        db_ticker="0050.TW",
        db_start="2025-01-01",
        as_of="2026-07-20",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["inputs"]["data_source"] == "duckdb_ohlcv"
    assert review["data_range"]["rows"] == 320
    assert review["decision"]["promote_to_live"] is False


def test_build_review_accepts_downside_tail_decay_proposal(tmp_path: Path) -> None:
    review = build_review(
        validation_path=_validation_with_downside_tail(tmp_path / "validation.json"),
        data_path=_ohlcv(tmp_path / "ohlcv.parquet"),
        use_db=False,
        proposal_id=DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
        as_of="2026-07-20",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["inputs"]["accepted_proposal_id"] == DOWNSIDE_TAIL_DECAY_PROPOSAL_ID
    assert review["feature_proxy"]["downside_deviation"]["uses_future_data"] is False
    assert review["feature_proxy"]["drawdown_depth"]["uses_future_data"] is False
    assert review["feature_proxy"]["ema_cross_strength"]["uses_future_data"] is False
    assert review["reward_proxy"]["volatility_scaling_penalty"]["bounded_range"] == [0.0, 0.25]
    assert review["reward_proxy"]["letf_tail_decay_cost"]["bounded_range"] == [0.0, 0.25]
    assert review["finite_summary"]["columns"]["downside_deviation"]["finite_count"] > 0
    assert review["finite_summary"]["columns"]["ema_cross_strength"]["finite_count"] > 0
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False


def test_build_review_blocks_when_accepted_proposal_missing(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps({"summary": {"accepted_proposal_ids": ["other_proposal"]}}),
        encoding="utf-8",
    )

    review = build_review(
        validation_path=validation,
        data_path=_ohlcv(tmp_path / "ohlcv.parquet"),
        use_db=False,
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert "accepted_sample_proposal_missing" in review["blocking_reasons"]
    assert review["decision"]["available_for_manual_offline_review"] is False
    assert review["decision"]["allow_00631l_add"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "smoke.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_offline_smoke_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_offline_smoke_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
