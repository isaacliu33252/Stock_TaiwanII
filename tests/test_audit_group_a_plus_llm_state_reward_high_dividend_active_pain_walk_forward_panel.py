from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.audit_group_a_plus_llm_state_reward_high_dividend_active_pain_walk_forward_panel import (
    PROPOSAL_ID,
    build_review,
    write_review,
)


def _panel(path: Path, *, rows: int = 60, tickers: list[str] | None = None) -> Path:
    tickers = tickers or ["0050.TW", "0056.TW", "00679B.TWO"]
    dates = pd.bdate_range("2024-01-02", periods=rows)
    records = []
    for fold in [1, 2]:
        test_dates = dates[:30] if fold == 1 else dates[30:]
        train_end = pd.Timestamp("2023-12-26") if fold == 1 else test_dates[0] - pd.Timedelta(days=7)
        for date in test_dates:
            for ticker in tickers:
                records.append(
                    {
                        "fold": fold,
                        "date": date,
                        "ticker": ticker,
                        "train_start": pd.Timestamp("2023-01-01"),
                        "train_end": train_end,
                        "test_start": test_dates[0],
                        "test_end": test_dates[-1],
                        "return": 0.001,
                        "freeze_id": "unit_v3",
                        "frozen_manifest_sha256": "c" * 64,
                        "proposal_id": PROPOSAL_ID,
                        "original_reward_proxy": -0.01,
                        "redesigned_reward_proxy": -0.02,
                        "active_bucket_weight": 0.1,
                        "active_bucket_return_contribution": -0.001,
                        "active_bucket_drawdown_depth": 0.01,
                        "reward_signal_concentration_hhi": 0.5,
                        "high_dividend_active_pain": 0.02,
                        "active_bucket_drawdown_penalty": 0.4,
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
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_review_accepts_v3_fold_aware_panel(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        panel_review_path=_review(tmp_path / "review.json", panel_path),
        forward_horizon=5,
        as_of="2026-07-21",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["fold_count"] == 2
    assert review["summary"]["duplicate_fold_date_ticker_rows"] == 0
    assert review["summary"]["frozen_manifest_hash_count"] == 1
    assert review["summary"]["folds_complete"] is True
    assert review["decision"]["v3_walk_forward_panel_audit_passed"] is True
    assert review["decision"]["v3_shadow_gate_update_allowed"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_hash_mismatch(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        panel_review_path=_review(tmp_path / "review.json", panel_path, panel_hash="b" * 64),
        as_of="2026-07-21",
    )

    assert review["status"] == "blocked"
    assert "v3_panel_hash_mismatch" in review["blocking_reasons"]
    assert review["decision"]["v3_shadow_gate_update_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "audit.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit",
        "as_of": "2026-07-21",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
