from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_event_aware_execution_quality_shadow import build_report, write_report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_event_quality_report_from_files(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "success": True,
            "data": {
                "actual_data_date": "2026-08-07",
                "business_stale_days": 2,
                "execution_allowed": False,
                "target_weights": {"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.25, "cash": 0.45},
                "latest_features": {"total_risk_score": 2, "tail_risk_score": 0},
            },
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "success": True,
            "data": {
                "current_total_assets": 1000000,
                "current_cash_input": 500000,
                "current_holdings": {"0050.TW": 3000, "00632R.TW": 0},
                "current_prices": {"0050.TW": 100, "00632R.TW": 10},
            },
        },
    )
    thesis = _write(tmp_path / "thesis.json", {"thesis_class": "short_term_inverse_hedge_review_only"})

    report = build_report(live_signal_path=live, execution_plan_path=plan, relative_thesis_path=thesis, as_of="2026-08-07")

    assert report["as_of"] == "2026-08-07"
    assert report["status"] == "blocked_review_only"
    assert "execution_guard_satisfied" in report["blockers"]
    assert report["sources"]["live_signal"] == str(live)
    assert report["decision"]["creates_orders"] is False


def test_write_event_quality_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "quality.json"
    history = tmp_path / "history"
    log = tmp_path / "quality.jsonl"
    report = {
        "as_of": "2026-08-07",
        "status": "caution_review_only",
        "quality_score": 0.8,
        "blockers": [],
        "warnings": ["x"],
        "inputs": {},
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "event_aware_execution_quality_shadow_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["status"] == "caution_review_only"
