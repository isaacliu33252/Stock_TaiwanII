from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_diagnostic_refinement import (
    build_review,
    write_review,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (
    ACCEPTED_PROPOSAL_ID,
    DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
)


def _validation(path: Path) -> Path:
    path.write_text(
        json.dumps({"summary": {"accepted_proposal_ids": [ACCEPTED_PROPOSAL_ID]}}),
        encoding="utf-8",
    )
    return path


def _validation_with_downside_tail(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "accepted_proposal_ids": [
                        ACCEPTED_PROPOSAL_ID,
                        DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _available_review(path: Path) -> Path:
    path.write_text(json.dumps({"status": "available_for_manual_offline_review", "warning_reasons": []}), encoding="utf-8")
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


def test_build_review_accepts_diagnostic_refinement_without_live_effects(tmp_path: Path) -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW"]
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        feature_stability_path=_available_review(tmp_path / "feature.json"),
        windowed_stability_path=_available_review(tmp_path / "windowed.json"),
        db_path=_db(tmp_path / "stock_data.db", tickers),
        tickers=tickers,
        start="2025-01-01",
        min_rows=80,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_diagnostic_refinement_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["ticker_count"] == 3
    assert review["summary"]["available_ticker_count"] == 3
    assert review["blocking_reasons"] == []
    assert review["aggregate_diagnostics"]["finite_reward_min_ratio"] == 1.0
    assert review["summary"]["reward_alignment_grade"] in {"green", "yellow", "red", "unavailable"}
    assert review["summary"]["reward_alignment_objective"] == "future_return_alignment"
    assert review["summary"]["return_alignment_grade"] == review["summary"]["reward_alignment_grade"]
    assert review["summary"]["downside_alignment_grade"] in {"green", "yellow", "red", "unavailable"}
    assert review["diagnostic_gates"]["reward_future_return_alignment"]["ppo_training_queue_allowed"] in {
        True,
        False,
    }
    assert "reward_future_downside_alignment" in review["diagnostic_gates"]
    assert "overall_reward_alignment" in review["diagnostic_gates"]
    assert review["decision"]["diagnostic_refinement_ready_for_research_review"] is True
    assert review["decision"]["diagnostic_refinement_grade"] == review["summary"]["reward_alignment_grade"]
    assert review["decision"]["ppo_training_queue_allowed_by_dgr"] == review["summary"][
        "ppo_training_queue_allowed_by_alignment"
    ]
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_missing_ticker_frame(tmp_path: Path) -> None:
    review = build_review(
        validation_path=_validation(tmp_path / "validation.json"),
        feature_stability_path=_available_review(tmp_path / "feature.json"),
        windowed_stability_path=_available_review(tmp_path / "windowed.json"),
        db_path=_db(tmp_path / "stock_data.db", ["0050.TW"]),
        tickers=["0050.TW", "00631L.TW"],
        start="2025-01-01",
        min_rows=80,
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert review["summary"]["missing_tickers"] == ["00631L.TW"]
    assert "missing_feature_frames:00631L.TW" in review["blocking_reasons"]
    assert review["decision"]["allow_00631l_add"] is False


def test_build_review_scores_downside_tail_decay_proposal(tmp_path: Path) -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW"]
    review = build_review(
        validation_path=_validation_with_downside_tail(tmp_path / "validation.json"),
        feature_stability_path=_available_review(tmp_path / "feature.json"),
        windowed_stability_path=_available_review(tmp_path / "windowed.json"),
        db_path=_db(tmp_path / "stock_data.db", tickers),
        tickers=tickers,
        start="2025-01-01",
        min_rows=80,
        proposal_id=DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
        downside_drawdown_weight=0.3,
        downside_volatility_weight=0.5,
        downside_tail_decay_weight=0.1,
        volatility_penalty_scale=4.0,
        tail_decay_scale=4.0,
        as_of="2026-07-20",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["inputs"]["accepted_proposal_id"] == DOWNSIDE_TAIL_DECAY_PROPOSAL_ID
    assert review["inputs"]["downside_tail_decay_params"] == {
        "drawdown_weight": 0.3,
        "volatility_weight": 0.5,
        "tail_decay_weight": 0.1,
        "volatility_scale": 4.0,
        "tail_decay_scale": 4.0,
    }
    assert "downside_deviation_to_future_downside" in review["aggregate_diagnostics"]["feature_ic_mean"]
    assert "drawdown_depth_to_future_downside" in review["aggregate_diagnostics"]["feature_ic_mean"]
    assert review["summary"]["reward_alignment_grade"] in {"green", "yellow", "red", "unavailable"}
    assert review["summary"]["reward_alignment_objective"] == "future_downside_alignment"
    assert review["summary"]["downside_alignment_grade"] == review["summary"]["reward_alignment_grade"]
    assert review["summary"]["downside_alignment_direction"] in {
        "negative_reward_vs_positive_downside",
        "positive_reward_vs_positive_downside",
        "zero_alignment",
        "unavailable",
    }
    assert review["diagnostic_gates"]["reward_future_downside_alignment"]["semantic"][
        "risk_sensitive_useful"
    ] in {True, False}
    assert review["decision"]["ppo_training_queue_allowed_by_dgr"] == review["summary"][
        "ppo_training_queue_allowed_by_alignment"
    ]
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "dgr.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_diagnostic_refinement_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_diagnostic_refinement_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
