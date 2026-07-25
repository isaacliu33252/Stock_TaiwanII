from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.audit_group_a_plus_llm_state_reward_drawdown_failure_events import (
    build_review,
    write_review,
)


def _panel(path: Path, *, rows: int = 130) -> Path:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    tickers = ["0050.TW", "0056.TW", "00713.TW", "00878.TW", "00679B.TWO", "00751B.TWO", "00631L.TW", "00632R.TW"]
    records = []
    for ticker in tickers:
        for idx, date in enumerate(dates):
            stress = idx >= 104
            high_dividend = ticker in {"0056.TW", "00713.TW", "00878.TW"}
            bond = ticker in {"00679B.TWO", "00751B.TWO"}
            if high_dividend:
                reward, ret = 0.08, -0.025 if stress else 0.001
            elif bond:
                reward, ret = -0.04, 0.001 if stress else 0.0003
            elif ticker == "0050.TW":
                reward, ret = -0.01, -0.004 if stress else 0.001
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
                    "realized_volatility": 0.01 if not stress else 0.05,
                    "drawdown_depth": 0.01 if not stress else 0.12,
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
                "test_end": dates[129].date().isoformat(),
                "delta_vs_equal_weight": {"max_drawdown": -0.02},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_review_audits_failure_event_windows_without_live_effects(tmp_path: Path) -> None:
    panel_path = _panel(tmp_path / "panel.parquet")
    review = build_review(
        panel_path=panel_path,
        baseline_path=_baseline(tmp_path / "baseline.json", panel_path),
        window=3,
        top_n=3,
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_drawdown_failure_event_audit"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["audited_failing_fold_count"] == 1
    assert review["summary"]["dominant_negative_event_bucket"] in {"high_dividend", "market_core", "bond"}
    assert "00631L.TW" not in review["inputs"]["eligible_tickers"]
    assert "00632R.TW" not in review["inputs"]["eligible_tickers"]
    event = review["failing_fold_events"][0]["event_window"]
    assert event["event_days"] >= 1
    assert event["daily_events"]
    assert "bucket_active_weight" in event["daily_events"][0]
    assert "worst_active_contribution_tickers" in event["daily_events"][0]
    assert review["decision"]["state_redesign_diagnostic_ready"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
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
    output = tmp_path / "latest" / "event_audit.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_drawdown_failure_event_audit",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_drawdown_failure_event_audit_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
