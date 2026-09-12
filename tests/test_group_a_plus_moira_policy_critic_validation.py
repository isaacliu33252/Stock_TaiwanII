from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.moira_policy_critic_validation import (
    append_moira_policy_critic_validation_log,
    build_moira_policy_critic_validation,
    load_plan_records,
    load_signal_records,
)


def _signal(date: str, *, stale: int, allowed: bool, close: float, target_0050: float, target_00632r: float) -> dict:
    return {
        "date": date,
        "path": f"signal_{date}.json",
        "signal": {
            "actual_data_date": date,
            "business_stale_days": stale,
            "execution_allowed": allowed,
            "target_weights": {"0050.TW": target_0050, "00632R.TW": target_00632r, "cash": 1 - target_0050 - target_00632r},
            "latest_prices": {"0050.TW": close, "00632R.TW": 10.0},
            "latest_features": {"total_risk_score": 2, "tail_risk_score": 0, "exit_momentum_5d": 0.1},
        },
    }


def test_policy_critic_validation_counts_artifact_replay_triggers() -> None:
    records = [
        _signal("2026-08-01", stale=2, allowed=False, close=100.0, target_0050=0.30, target_00632r=0.25),
        _signal("2026-08-02", stale=0, allowed=True, close=101.0, target_0050=0.30, target_00632r=0.00),
    ]
    plans = {
        "2026-08-01": {
            "current_total_assets": 1000000,
            "current_cash_input": 500000,
            "current_holdings": {"0050.TW": 4000, "00632R.TW": 0},
            "current_prices": {"0050.TW": 100.0, "00632R.TW": 10.0},
            "staged_buys": [],
        }
    }

    report = build_moira_policy_critic_validation(
        signal_records=records,
        plan_records=plans,
        as_of="2026-08-02",
        min_trigger_count_for_backtest=1,
    )

    by_id = {row["proposal_id"]: row for row in report["validations"]}
    assert by_id["freshness_first_review_gate"]["trigger_count"] == 1
    assert by_id["execution_guard_hard_stop_for_new_risk"]["trigger_count"] == 1
    assert by_id["large_inverse_hedge_staging_review"]["trigger_count"] == 1
    assert by_id["low_risk_bullish_beta_reduction_cooldown"]["trigger_count"] == 1
    assert by_id["hedge_thesis_blocker_echo"]["trigger_count"] == 1
    assert round(by_id["freshness_first_review_gate"]["mean_next_0050_return"], 6) == 0.01
    assert report["trigger_ledger"]["freshness_first_review_gate"][0]["date"] == "2026-08-01"
    assert report["trigger_ledger"]["large_inverse_hedge_staging_review"][0]["reason"] == (
        "large_00632r_increase_without_staging"
    )
    assert report["summary"]["ready_for_shadow_backtest"]
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["guarded_candidate_allowed"] is False


def test_load_records_unwraps_files_and_deduplicates_dates(tmp_path: Path) -> None:
    signal_path = tmp_path / "group_a_plus_live_signal_v2_20260801.json"
    signal_path.write_text(
        json.dumps({"success": True, "data": {"actual_data_date": "2026-08-01", "latest_prices": {"0050.TW": 100}}}),
        encoding="utf-8",
    )
    plan_path = tmp_path / "group_a_plus_execution_plan_v2_20260801.json"
    plan_path.write_text(json.dumps({"data": {"actual_data_date": "2026-08-01"}}), encoding="utf-8")

    signals = load_signal_records([signal_path, signal_path])
    plans = load_plan_records([plan_path])

    assert len(signals) == 1
    assert signals[0]["date"] == "2026-08-01"
    assert "2026-08-01" in plans


def test_policy_critic_validation_log_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "validation.jsonl"
    report = build_moira_policy_critic_validation(signal_records=[], plan_records={}, as_of="2026-08-07")

    append_moira_policy_critic_validation_log(log, report, date="2026-08-07")
    append_moira_policy_critic_validation_log(log, report | {"summary": {"x": 1}}, date="2026-08-07")

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["summary"] == {"x": 1}
