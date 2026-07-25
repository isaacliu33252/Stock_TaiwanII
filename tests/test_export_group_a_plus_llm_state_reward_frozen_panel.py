from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import (
    build_panel,
    write_outputs,
)


def _db(path: Path, tickers: list[str], rows: int = 80) -> Path:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    frames = []
    for ticker_idx, ticker in enumerate(tickers):
        close = pd.Series(range(rows), dtype=float) * (0.1 + ticker_idx * 0.02) + 50.0 + ticker_idx
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


def _frozen_manifest(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "frozen_for_manual_offline_review",
                "as_of": "2026-07-20",
                "freeze": {
                    "freeze_id": "unit_freeze",
                    "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                    "frozen_manifest_sha256": "a" * 64,
                    "state_columns": [
                        "downside_deviation",
                        "realized_volatility",
                        "drawdown_depth",
                        "ema_cross_strength",
                    ],
                    "reward_columns": [
                        "drawdown_penalty",
                        "volatility_scaling_penalty",
                        "letf_tail_decay_cost",
                        "reward_proxy",
                    ],
                    "reward_params": {
                        "drawdown_weight": 0.3,
                        "volatility_weight": 0.5,
                        "tail_decay_weight": 0.1,
                        "volatility_scale": 4.0,
                        "tail_decay_scale": 4.0,
                    },
                },
                "decision": {"offline_feature_reward_export_allowed": True},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_panel_exports_frozen_columns_without_live_effects(tmp_path: Path) -> None:
    tickers = ["0050.TW", "00631L.TW"]
    panel, review = build_panel(
        frozen_manifest_path=_frozen_manifest(tmp_path / "frozen.json"),
        db_path=_db(tmp_path / "stock_data.db", tickers),
        tickers=tickers,
        start="2025-01-01",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_frozen_panel_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["row_count"] == 160
    assert review["summary"]["available_ticker_count"] == 2
    assert review["summary"]["finite_reward_ratio"] == 1.0
    assert set(panel["freeze_id"]) == {"unit_freeze"}
    assert set(panel["frozen_manifest_sha256"]) == {"a" * 64}
    assert "downside_deviation" in panel.columns
    assert "reward_proxy" in panel.columns
    assert review["decision"]["offline_walk_forward_input_ready"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_panel_blocks_missing_manifest(tmp_path: Path) -> None:
    panel, review = build_panel(
        frozen_manifest_path=tmp_path / "missing.json",
        db_path=_db(tmp_path / "stock_data.db", ["0050.TW"]),
        tickers=["0050.TW"],
        start="2025-01-01",
    )

    assert panel.empty
    assert review["status"] == "blocked"
    assert "missing_frozen_manifest" in review["blocking_reasons"]
    assert review["decision"]["offline_walk_forward_input_ready"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_outputs_writes_panel_review_and_history(tmp_path: Path) -> None:
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"]),
            "ticker": ["0050.TW"],
            "close": [100.0],
            "reward_proxy": [-0.01],
        }
    )
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_review",
        "as_of": "2026-07-20",
        "status": "available_for_manual_offline_review",
        "summary": {"row_count": 1},
        "decision": {"promote_to_live": False},
    }
    output_review = write_outputs(
        panel,
        review,
        panel_output=tmp_path / "panel.parquet",
        review_output=tmp_path / "review.json",
        history_dir=tmp_path / "history",
    )

    assert (tmp_path / "panel.parquet").exists()
    assert len(output_review["outputs"]["panel_sha256"]) == 64
    assert json.loads((tmp_path / "review.json").read_text(encoding="utf-8")) == output_review
    history_file = tmp_path / "history" / "llm_state_reward_interface_frozen_panel_review_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == output_review
