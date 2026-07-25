from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.attribute_group_a_plus_llm_state_reward_baseline_drawdown_failures import (
    build_review,
    write_review,
)


def _panel(path: Path) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=80)
    records = []
    for ticker in ["0050.TW", "0056.TW", "00713.TW", "00631L.TW", "00632R.TW"]:
        for idx, date in enumerate(dates):
            if ticker == "0050.TW":
                reward = -0.01
                ret = -0.03 if 55 <= idx <= 58 else 0.001
            elif ticker == "0056.TW":
                reward = -0.10
                ret = 0.01 if 55 <= idx <= 58 else 0.001
            elif ticker == "00713.TW":
                reward = -0.04
                ret = 0.001
            else:
                reward = -0.02
                ret = 0.0
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
    dates = pd.bdate_range("2024-01-02", periods=80)
    payload = {
        "status": "available_for_manual_offline_review",
        "inputs": {
            "panel_sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest(),
            "eligible_tickers": ["0050.TW", "0056.TW", "00713.TW"],
            "excluded_tickers": ["00631L.TW", "00632R.TW"],
            "low_quantile": 0.3,
            "high_quantile": 0.7,
            "low_score": 0.5,
            "mid_score": 1.0,
            "high_score": 1.5,
            "cost_bps": 0.0,
        },
        "fold_results": [
            {
                "fold": 1,
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[49].date().isoformat(),
                "test_start": dates[50].date().isoformat(),
                "test_end": dates[79].date().isoformat(),
                "delta_vs_equal_weight": {"max_drawdown": -0.01},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_review_attributes_drawdown_failure_without_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        top_n=2,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_baseline_drawdown_attribution"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["failing_drawdown_fold_count"] == 1
    assert review["summary"]["attributed_fold_count"] == 1
    assert review["summary"]["worst_fold"] == 1
    assert review["failing_fold_attribution"][0]["attribution"]["worst_active_contribution_tickers"]
    assert review["decision"]["drawdown_issue_requires_additional_risk_control"] is True
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
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "attribution.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_baseline_drawdown_attribution",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_baseline_drawdown_attribution_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
