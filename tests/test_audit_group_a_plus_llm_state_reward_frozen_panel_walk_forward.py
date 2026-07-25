from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.audit_group_a_plus_llm_state_reward_frozen_panel_walk_forward import (
    build_review,
    write_review,
)


def _panel(path: Path, *, rows: int = 900, tickers: list[str] | None = None) -> Path:
    tickers = tickers or ["0050.TW", "00631L.TW"]
    dates = pd.bdate_range("2022-01-03", periods=rows)
    records = []
    for ticker in tickers:
        for idx, date in enumerate(dates):
            records.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": 100.0 + idx,
                    "return": 0.001,
                    "freeze_id": "unit_freeze",
                    "frozen_manifest_sha256": "a" * 64,
                    "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                    "downside_deviation": 0.01,
                    "realized_volatility": 0.02,
                    "drawdown_depth": 0.03,
                    "ema_cross_strength": 0.04,
                    "drawdown_penalty": 0.03,
                    "volatility_scaling_penalty": 0.02,
                    "letf_tail_decay_cost": 0.01,
                    "reward_proxy": -0.02,
                }
            )
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def _review(path: Path, panel_path: Path, *, panel_hash: str | None = None) -> Path:
    panel_hash = panel_hash or hashlib.sha256(panel_path.read_bytes()).hexdigest()
    path.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "outputs": {"panel_sha256": panel_hash},
                "summary": {
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
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_review_accepts_frozen_panel_and_plans_purged_folds(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        panel_review_path=_review(tmp_path / "panel_review.json", panel_path),
        n_splits=3,
        test_size=60,
        purge=5,
        min_train_size=252,
        forward_horizon=5,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_frozen_panel_walk_forward_audit"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["row_count"] == 1800
    assert review["summary"]["date_count"] == 900
    assert review["summary"]["fold_count"] == 3
    assert review["summary"]["purge_covers_forward_horizon"] is True
    assert all(fold["purge_observations"] == 5 for fold in review["folds"])
    assert review["decision"]["frozen_panel_leakage_audit_passed"] is True
    assert review["decision"]["purged_walk_forward_plan_ready"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_hash_mismatch_and_short_purge(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        panel_review_path=_review(tmp_path / "panel_review.json", panel_path, panel_hash="b" * 64),
        n_splits=2,
        test_size=50,
        purge=2,
        min_train_size=252,
        forward_horizon=5,
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert "frozen_panel_hash_mismatch" in review["blocking_reasons"]
    assert "purge_less_than_forward_horizon:2<5" in review["blocking_reasons"]
    assert review["decision"]["purged_walk_forward_plan_ready"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "audit.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_walk_forward_audit",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_frozen_panel_walk_forward_audit_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
