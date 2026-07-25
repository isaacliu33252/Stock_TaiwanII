from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import (
    build_review,
    write_review,
)


def _panel(path: Path, *, rows: int = 120) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00878.TW", "00679B.TWO", "00751B.TWO", "00631L.TW", "00632R.TW"]
    records = []
    for ticker in tickers:
        for idx, date in enumerate(dates):
            if ticker == "0050.TW":
                reward, ret = -0.01, 0.002
            elif ticker in {"0056.TW", "00713.TW", "00878.TW"}:
                reward, ret = -0.02, -0.001 if idx > 80 else 0.001
            elif ticker in {"00679B.TWO", "00751B.TWO"}:
                reward, ret = -0.08, 0.0003
            else:
                reward, ret = -0.01, 0.0
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


def _baseline(path: Path, panel_path: Path) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=120)
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
            "cost_bps": 5.0,
        },
        "summary": {
            "positive_final_value_folds": 1,
            "positive_sharpe_folds": 1,
            "non_worse_drawdown_folds": 0,
        },
        "fold_results": [
            {
                "fold": 1,
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[79].date().isoformat(),
                "test_start": dates[85].date().isoformat(),
                "test_end": dates[119].date().isoformat(),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_review_runs_overlay_without_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        min_positive_final_folds=0,
        min_positive_sharpe_folds=0,
        min_non_worse_drawdown_folds=0,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_risk_control_overlay_shadow_backtest"
    assert review["status"] == "available_for_manual_offline_review"
    assert "00631L.TW" not in review["inputs"]["eligible_tickers"]
    assert "00632R.TW" not in review["inputs"]["eligible_tickers"]
    assert review["summary"]["overlay"]["available_fold_count"] == 1
    assert review["decision"]["risk_control_overlay_ready_for_review"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_missing_baseline(tmp_path: Path) -> None:
    review = build_review(
        panel_path=_panel(tmp_path / "panel.parquet"),
        baseline_path=tmp_path / "missing.json",
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert "missing_baseline_shadow_backtest" in review["blocking_reasons"]
    assert review["decision"]["risk_control_overlay_passed_shadow_gate"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "overlay.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_risk_control_overlay_shadow_backtest",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_risk_control_overlay_shadow_backtest_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
