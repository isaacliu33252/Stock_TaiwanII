from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_high_dividend_active_pain_offline_smoke import (
    PROPOSAL_ID,
    build_review,
    write_review,
)


def _panel(path: Path, *, rows: int = 170) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00878.TW", "00679B.TWO", "00751B.TWO", "00631L.TW", "00632R.TW"]
    records = []
    for ticker in tickers:
        close = 100.0
        for idx, date in enumerate(dates):
            stress = 110 <= idx <= 145
            high_dividend = ticker in {"0056.TW", "00713.TW", "00878.TW"}
            bond = ticker in {"00679B.TWO", "00751B.TWO"}
            if high_dividend:
                reward = 0.08
                ret = -0.018 if stress else 0.001
                drawdown = 0.12 if stress else 0.01
                vol = 0.06 if stress else 0.01
            elif bond:
                reward = -0.04
                ret = 0.001
                drawdown = 0.02
                vol = 0.015
            elif ticker == "0050.TW":
                reward = -0.01
                ret = -0.003 if stress else 0.001
                drawdown = 0.04 if stress else 0.01
                vol = 0.025 if stress else 0.01
            else:
                reward = -0.01
                ret = 0.0
                drawdown = 0.01
                vol = 0.01
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
    dates = pd.bdate_range("2024-01-02", periods=170)
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
            "positive_final_value_folds": 0,
            "positive_sharpe_folds": 0,
            "non_worse_drawdown_folds": 0,
        },
        "fold_results": [
            {
                "fold": 1,
                "status": "available_for_manual_offline_review",
                "train_start": dates[0].date().isoformat(),
                "train_end": dates[99].date().isoformat(),
                "test_start": dates[104].date().isoformat(),
                "test_end": dates[169].date().isoformat(),
                "delta_vs_equal_weight": {"max_drawdown": -0.02},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _dgr(path: Path, panel_path: Path, *, passed: bool = True) -> Path:
    payload = {
        "status": "available_for_manual_offline_review",
        "proposal_id": PROPOSAL_ID,
        "inputs": {
            "panel_sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest(),
            "active_penalty_scale": 20.0,
            "drawdown_scale": 1.0,
            "return_pain_scale": 4.0,
            "concentration_scale": 0.1,
        },
        "decision": {
            "high_dividend_active_pain_dgr_passed": passed,
            "offline_smoke_allowed_after_dgr_green": passed,
            "promote_to_live": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_review_runs_offline_smoke_after_dgr_green_without_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        dgr_path=_dgr(tmp_path / "dgr.json", panel_path),
        min_positive_final_folds=0,
        min_positive_sharpe_folds=0,
        min_non_worse_drawdown_folds=0,
        require_event_improvement=False,
        as_of="2026-07-21",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_offline_smoke"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["proposal_id"] == PROPOSAL_ID
    assert review["summary"]["high_dividend_active_pain_offline_smoke"]["available_fold_count"] == 1
    assert "00631L.TW" not in review["inputs"]["eligible_tickers"]
    assert "00632R.TW" not in review["inputs"]["eligible_tickers"]
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_when_dgr_is_not_green(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        dgr_path=_dgr(tmp_path / "dgr.json", panel_path, passed=False),
        as_of="2026-07-21",
    )

    assert review["status"] == "blocked"
    assert "high_dividend_active_pain_dgr_not_green" in review["blocking_reasons"]
    assert review["decision"]["high_dividend_active_pain_offline_smoke_passed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "smoke.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_offline_smoke",
        "as_of": "2026-07-21",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_high_dividend_active_pain_offline_smoke_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
