from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_llm_state_reward_high_dividend_active_pain_frozen_manifest import PROPOSAL_ID
from scripts.evaluate.export_group_a_plus_llm_state_reward_high_dividend_active_pain_walk_forward_panel import (
    build_panel,
    write_outputs,
)


def _source_panel(path: Path, *, rows: int = 130) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00878.TW", "00679B.TWO", "00751B.TWO", "00631L.TW", "00632R.TW"]
    records = []
    for ticker in tickers:
        close = 100.0
        for idx, date in enumerate(dates):
            high_dividend = ticker in {"0056.TW", "00713.TW", "00878.TW"}
            ret = -0.01 if high_dividend and idx > 110 else 0.001
            close *= 1.0 + ret
            records.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": close,
                    "return": ret,
                    "reward_proxy": 0.08 if high_dividend else -0.03,
                    "drawdown_depth": 0.10 if high_dividend and idx > 110 else 0.01,
                    "realized_volatility": 0.04 if high_dividend and idx > 110 else 0.01,
                    "freeze_id": "old_freeze",
                    "frozen_manifest_sha256": "b" * 64,
                    "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                }
            )
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def _baseline(path: Path, panel_path: Path) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=130)
    payload = {
        "status": "available_for_manual_offline_review",
        "inputs": {
            "panel_sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest(),
            "eligible_tickers": ["0050.TW", "0056.TW", "00679B.TWO", "00713.TW", "00751B.TWO", "00878.TW"],
            "excluded_tickers": ["00631L.TW", "00632R.TW"],
            "low_quantile": 0.3,
            "high_quantile": 0.7,
            "low_score": 0.5,
            "mid_score": 1.0,
            "high_score": 1.5,
        },
        "fold_results": [
            {
                "fold": 1,
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[89].date().isoformat(),
                "test_start": dates[95].date().isoformat(),
                "test_end": dates[129].date().isoformat(),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest(path: Path) -> Path:
    payload = {
        "status": "frozen_for_manual_offline_review",
        "as_of": "2026-07-21",
        "freeze": {
            "freeze_id": "unit_v3",
            "proposal_id": PROPOSAL_ID,
            "frozen_manifest_sha256": "c" * 64,
            "state_columns": [
                "active_bucket_weight",
                "active_bucket_return_contribution",
                "active_bucket_drawdown_depth",
                "reward_signal_concentration_hhi",
                "high_dividend_active_pain",
            ],
            "reward_columns": ["active_bucket_drawdown_penalty", "original_reward_proxy", "redesigned_reward_proxy"],
            "reward_params": {
                "active_penalty_scale": 20.0,
                "drawdown_scale": 1.0,
                "return_pain_scale": 4.0,
                "concentration_scale": 0.1,
            },
        },
        "decision": {"offline_walk_forward_panel_export_allowed": True},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_panel_exports_fold_aware_v3_panel_without_live_effects(tmp_path: Path) -> None:
    source = _source_panel(tmp_path / "source.parquet")
    panel, review = build_panel(
        frozen_panel_path=source,
        baseline_path=_baseline(tmp_path / "baseline.json", source),
        manifest_path=_manifest(tmp_path / "manifest.json"),
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["fold_count"] == 1
    assert review["summary"]["ticker_count"] == 6
    assert review["summary"]["finite_redesigned_reward_ratio"] == 1.0
    assert set(panel["freeze_id"]) == {"unit_v3"}
    assert set(panel["proposal_id"]) == {PROPOSAL_ID}
    assert "redesigned_reward_proxy" in panel.columns
    assert "high_dividend_active_pain" in panel.columns
    assert "00631L.TW" not in set(panel["ticker"])
    assert "00632R.TW" not in set(panel["ticker"])
    assert review["decision"]["offline_walk_forward_input_ready"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_panel_blocks_missing_manifest(tmp_path: Path) -> None:
    source = _source_panel(tmp_path / "source.parquet")
    panel, review = build_panel(
        frozen_panel_path=source,
        baseline_path=_baseline(tmp_path / "baseline.json", source),
        manifest_path=tmp_path / "missing.json",
    )

    assert panel.empty
    assert review["status"] == "blocked"
    assert "missing_v3_frozen_manifest" in review["blocking_reasons"]
    assert review["decision"]["promote_to_live"] is False


def test_write_outputs_writes_panel_review_and_history(tmp_path: Path) -> None:
    panel = pd.DataFrame({"fold": [1], "date": pd.to_datetime(["2024-01-01"]), "ticker": ["0050.TW"], "redesigned_reward_proxy": [0.0]})
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review",
        "as_of": "2026-07-21",
        "status": "available_for_manual_offline_review",
        "summary": {"row_count": 1},
        "decision": {"promote_to_live": False},
    }

    output = write_outputs(
        panel,
        review,
        panel_output=tmp_path / "panel.parquet",
        review_output=tmp_path / "review.json",
        history_dir=tmp_path / "history",
    )

    assert (tmp_path / "panel.parquet").exists()
    assert len(output["outputs"]["panel_sha256"]) == 64
    history_file = tmp_path / "history" / "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == output
