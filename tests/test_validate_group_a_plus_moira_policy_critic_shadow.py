from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.validate_group_a_plus_moira_policy_critic_shadow import build_report, write_report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_validation_report_from_globs(tmp_path: Path) -> None:
    _write(
        tmp_path / "results" / "group_a_plus_live_signal_v2_20260801.json",
        {
            "data": {
                "actual_data_date": "2026-08-01",
                "business_stale_days": 2,
                "execution_allowed": False,
                "target_weights": {"0050.TW": 0.3, "00632R.TW": 0.25, "cash": 0.45},
                "latest_prices": {"0050.TW": 100.0, "00632R.TW": 10.0},
                "latest_features": {"total_risk_score": 2, "tail_risk_score": 0, "exit_momentum_5d": 0.1},
            }
        },
    )
    _write(
        tmp_path / "results" / "group_a_plus_live_signal_v2_20260802.json",
        {"data": {"actual_data_date": "2026-08-02", "latest_prices": {"0050.TW": 101.0}}},
    )
    _write(
        tmp_path / "results" / "group_a_plus_execution_plan_v2_20260801.json",
        {
            "data": {
                "actual_data_date": "2026-08-01",
                "current_total_assets": 1000000,
                "current_holdings": {"0050.TW": 4000, "00632R.TW": 0},
                "current_prices": {"0050.TW": 100.0, "00632R.TW": 10.0},
            }
        },
    )

    report = build_report(
        signal_glob=str(tmp_path / "results" / "group_a_plus_live_signal_v2_*.json"),
        plan_glob=str(tmp_path / "results" / "group_a_plus_execution_plan_v2_*.json"),
        as_of="2026-08-02",
        min_trigger_count=1,
    )

    assert report["as_of"] == "2026-08-02"
    assert report["input_coverage"]["signal_record_count"] == 2
    assert "freshness_first_review_gate" in report["summary"]["ready_for_shadow_backtest"]
    assert round(report["trigger_ledger"]["freshness_first_review_gate"][0]["next_0050_return"], 6) == 0.01
    assert report["decision"]["creates_orders"] is False


def test_write_validation_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "validation.json"
    history = tmp_path / "history"
    log = tmp_path / "validation.jsonl"
    report = {
        "as_of": "2026-08-07",
        "input_coverage": {},
        "summary": {"ready_for_shadow_backtest": []},
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "moira_policy_critic_validation_shadow_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
