from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (
    build_review,
    write_review,
)


def _panel(path: Path, *, rows: int = 360) -> Path:
    dates = pd.bdate_range("2023-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00631L.TW", "00632R.TW"]
    records = []
    for ticker in tickers:
        for idx, date in enumerate(dates):
            if ticker == "0050.TW":
                reward = -0.01
                ret = 0.002
            elif ticker == "0056.TW":
                reward = -0.10
                ret = -0.001
            elif ticker == "00713.TW":
                reward = -0.04
                ret = 0.0005
            elif ticker == "00631L.TW":
                reward = -0.001
                ret = 0.01
            else:
                reward = -0.20
                ret = -0.01
            records.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": 100.0 + idx,
                    "return": ret,
                    "freeze_id": "unit_freeze",
                    "frozen_manifest_sha256": "a" * 64,
                    "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                    "reward_proxy": reward,
                }
            )
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def _audit(path: Path, panel_path: Path) -> Path:
    dates = pd.bdate_range("2023-01-02", periods=360)
    payload = {
        "status": "available_for_manual_offline_review",
        "inputs": {"actual_panel_sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest()},
        "folds": [
            {
                "fold": 1,
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[251].date().isoformat(),
                "test_start": dates[257].date().isoformat(),
                "test_end": dates[319].date().isoformat(),
            },
            {
                "fold": 2,
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[299].date().isoformat(),
                "test_start": dates[305].date().isoformat(),
                "test_end": dates[359].date().isoformat(),
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_review_runs_no_model_oos_baseline_without_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        walk_forward_audit_path=_audit(tmp_path / "audit.json", panel_path),
        min_positive_final_folds=1,
        min_positive_sharpe_folds=1,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_frozen_panel_baseline_shadow_backtest"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["inputs"]["eligible_tickers"] == ["0050.TW", "0056.TW", "00713.TW"]
    assert "00631L.TW" not in review["inputs"]["eligible_tickers"]
    assert "00632R.TW" not in review["inputs"]["eligible_tickers"]
    assert review["summary"]["available_fold_count"] == 2
    assert review["summary"]["positive_final_value_folds"] >= 1
    assert review["decision"]["baseline_shadow_backtest_ready_for_review"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_missing_audit(tmp_path: Path) -> None:
    review = build_review(
        panel_path=_panel(tmp_path / "panel.parquet"),
        walk_forward_audit_path=tmp_path / "missing.json",
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert "missing_walk_forward_audit" in review["blocking_reasons"]
    assert review["decision"]["next_shadow_model_design_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "baseline.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_baseline_shadow_backtest",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_frozen_panel_baseline_shadow_backtest_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
