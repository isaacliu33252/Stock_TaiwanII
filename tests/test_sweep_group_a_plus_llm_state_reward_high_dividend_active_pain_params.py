from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_high_dividend_active_pain_dgr import PROPOSAL_ID
from scripts.evaluate.sweep_group_a_plus_llm_state_reward_high_dividend_active_pain_params import (
    build_sweep,
    write_review,
)


def _panel(path: Path, *, rows: int = 155) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00878.TW", "00679B.TWO", "00751B.TWO", "00631L.TW", "00632R.TW"]
    records = []
    for ticker in tickers:
        close = 100.0
        for idx, date in enumerate(dates):
            stress = idx >= 105
            high_dividend = ticker in {"0056.TW", "00713.TW", "00878.TW"}
            bond = ticker in {"00679B.TWO", "00751B.TWO"}
            if high_dividend:
                reward, ret = 0.08, -0.015 if stress else 0.001
                drawdown, vol = (0.10, 0.05) if stress else (0.01, 0.01)
            elif bond:
                reward, ret = -0.04, 0.001
                drawdown, vol = 0.02, 0.015
            elif ticker == "0050.TW":
                reward, ret = -0.01, -0.002 if stress else 0.001
                drawdown, vol = (0.04, 0.025) if stress else (0.01, 0.01)
            else:
                reward, ret = -0.01, 0.0
                drawdown, vol = 0.01, 0.01
            close *= 1.0 + ret
            records.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": close,
                    "return": ret,
                    "volume": 1_000_000,
                    "freeze_id": "unit_freeze",
                    "frozen_manifest_sha256": "a" * 64,
                    "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                    "reward_proxy": reward,
                    "realized_volatility": vol,
                    "drawdown_depth": drawdown,
                }
            )
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def _baseline(path: Path, panel_path: Path) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=155)
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
        "fold_results": [
            {
                "fold": 1,
                "status": "available_for_manual_offline_review",
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[99].date().isoformat(),
                "test_start": dates[105].date().isoformat(),
                "test_end": dates[154].date().isoformat(),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _dgr(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "proposal_id": PROPOSAL_ID,
                "decision": {"high_dividend_active_pain_dgr_passed": True, "promote_to_live": False},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_sweep_ranks_v3_candidates_and_blocks_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_sweep(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        dgr_path=_dgr(tmp_path / "dgr.json"),
        active_penalty_scales=[10.0, 20.0],
        return_pain_scales=[2.0],
        concentration_scales=[0.1],
        min_positive_final_folds=0,
        min_positive_sharpe_folds=0,
        min_non_worse_drawdown_folds=0,
        min_passed_candidates=1,
        as_of="2026-07-21",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_param_sweep"
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
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_param_sweep",
        "as_of": "2026-07-21",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_high_dividend_active_pain_param_sweep_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
