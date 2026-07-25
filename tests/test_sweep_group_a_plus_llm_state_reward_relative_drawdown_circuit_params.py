from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.sweep_group_a_plus_llm_state_reward_relative_drawdown_circuit_params import (
    build_sweep,
    write_review,
)


def _panel(path: Path, *, rows: int = 135) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00878.TW", "00679B.TWO", "00751B.TWO"]
    records = []
    for ticker in tickers:
        for idx, date in enumerate(dates):
            stress = idx >= 100
            high_dividend = ticker in {"0056.TW", "00713.TW", "00878.TW"}
            records.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": 100.0 + idx,
                    "return": (-0.02 if stress and high_dividend else 0.001),
                    "freeze_id": "unit_freeze",
                    "frozen_manifest_sha256": "a" * 64,
                    "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                    "reward_proxy": 0.08 if high_dividend else -0.02,
                    "realized_volatility": 0.01,
                    "drawdown_depth": 0.01,
                }
            )
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def _baseline(path: Path, panel_path: Path) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=135)
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
                "train_end": dates[94].date().isoformat(),
                "test_start": dates[100].date().isoformat(),
                "test_end": dates[134].date().isoformat(),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_sweep_ranks_candidates_and_blocks_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_sweep(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        triggers=[0.0005, 0.005],
        recoveries=[0.0001],
        min_days=[3],
        min_positive_final_folds=0,
        min_positive_sharpe_folds=0,
        min_non_worse_drawdown_folds=0,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_relative_drawdown_circuit_param_sweep"
    assert review["summary"]["evaluated_count"] == 2
    assert len(review["results"]) == 2
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sweep.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_relative_drawdown_circuit_param_sweep",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_relative_drawdown_circuit_param_sweep_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
