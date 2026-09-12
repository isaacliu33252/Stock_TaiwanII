from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2605_17307_adaptive_retraining_cadence_audit import (
    build_audit,
    write_audit,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _base_inputs(tmp_path: Path, *, forward_rows: int = 2, parity: float = 0.0) -> dict:
    return {
        "strategy_path": _write(
            tmp_path / "strategy.json",
            {"active_strategy": {"id": "a2118_a2111_ncf_late_bull_deleverage"}},
        ),
        "seed_gate_path": _write(
            tmp_path / "seed_gate.json",
            {
                "status": "blocked",
                "blockers": ["forward_shadow_monitoring_history_insufficient"],
                "criteria": {"minimum_forward_rows": 20, "minimum_parity_pass_rate": 0.95},
                "summary": {"forward_rows": forward_rows, "parity_pass_rate": parity},
            },
        ),
        "seed_monitor_path": _write(tmp_path / "seed_monitor.json", {"status": "forward_shadow_row_available"}),
        "sac_smoke_path": _write(
            tmp_path / "sac_smoke.json",
            {
                "decision": {"can_run_local_sac_environment_smoke": True, "paper_style_sac_training_ready": False},
                "data_panel": {"observations": 1613, "paper_style_wfo_observation_shortfall": 151},
                "blocking_reasons": ["no_sac_oos_promotion_gate_exists_for_groupa_plus_live_weights"],
            },
        ),
        "extreme_monitor_path": _write(
            tmp_path / "extreme.json",
            {"latest_state": {"risk_aversion_state": "HIGH"}, "last_extreme_date": "2026-03-31"},
        ),
        "downside_shadow_path": _write(
            tmp_path / "downside.json",
            {"report_type": "a2118_downside_diversification_forecast_shadow", "decision": {"target_weight_change_allowed": False}},
        ),
    }


def test_audit_does_not_retrain_when_forward_history_is_insufficient(tmp_path: Path) -> None:
    report = build_audit(**_base_inputs(tmp_path, forward_rows=2, parity=0.0))

    assert report["latest_strategy"] == "a2118_a2111_ncf_late_bull_deleverage"
    assert report["decision"]["train_any_model_now"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    seed = report["audited_items"][0]
    assert seed["cadence_decision"]["next_action"] == "continue_daily_forward_shadow_until_minimum_rows"
    assert seed["cadence_decision"]["retrain_now"] is False


def test_audit_opens_retraining_review_only_after_enough_bad_forward_rows(tmp_path: Path) -> None:
    report = build_audit(**_base_inputs(tmp_path, forward_rows=20, parity=0.5))

    assert report["decision"]["train_any_model_now"] is True
    assert report["decision"]["models_requiring_retraining_review"] == [
        "a2118_seed_averaging_preferred_ensemble_42_43_44"
    ]
    seed = report["audited_items"][0]
    assert seed["cadence_decision"]["retrain_now"] is True
    assert seed["cadence_decision"]["next_action"] == "open_retraining_or_policy_mapping_review_before_any_promotion"


def test_extreme_state_opens_promotion_review_but_not_training(tmp_path: Path) -> None:
    inputs = _base_inputs(tmp_path, forward_rows=2, parity=0.0)
    inputs["extreme_monitor_path"] = _write(
        tmp_path / "extreme.json",
        {"latest_state": {"risk_aversion_state": "EXTREME"}, "last_extreme_date": "2026-08-25"},
    )

    report = build_audit(**inputs)

    assert report["decision"]["train_any_model_now"] is False
    assert report["decision"]["promotion_reviews_open_now"] == ["2606_09104_risk_aversion_prior_monitor"]


def test_write_audit_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2605_17307_adaptive_retraining_cadence_audit",
        "decision": {"train_any_model_now": False},
    }

    write_audit(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert list(history.glob("2605_17307_adaptive_retraining_cadence_audit_*.json"))
