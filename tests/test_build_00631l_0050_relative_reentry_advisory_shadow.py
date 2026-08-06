from __future__ import annotations

import json
from pathlib import Path

from scripts.run.build_00631l_0050_relative_reentry_advisory_shadow import build_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _opportunity_payload(end: str = "2026-08-03", decision_date: str = "2026-08-03") -> dict:
    return {
        "status": "shadow_only_no_live_action",
        "summary": {"windows": 1, "action_counts": {"KEEP": 1, "SHIFT_00631L_5": 1}, "non_keep_days": 1},
        "results": [
            {
                "label": "live_2024_2026",
                "bucket": "tuning_window",
                "window": {"start": "2024-01-02", "end": end},
                "method": {
                    "slow_bear_gate": {"blocked_days": 3},
                    "risk_up_permission_gate": {"blocked_days": 4},
                },
                "action_counts": {"KEEP": 1, "SHIFT_00631L_5": 1},
                "non_keep_days": 1,
                "non_keep_decisions": [
                    {
                        "date": decision_date,
                        "action": "SHIFT_00631L_5",
                        "shift_00631l_weight": 0.05,
                        "candidate_action_before_reliability": "SHIFT_00631L_5",
                        "reliability_gate_pass": True,
                        "action_allowed": True,
                        "block_reason": None,
                        "risk_up_permission_probability": 0.71,
                    }
                ],
                "recent_decisions": [
                    {
                        "date": decision_date,
                        "action": "SHIFT_00631L_5",
                        "shift_00631l_weight": 0.05,
                        "candidate_action_before_reliability": "SHIFT_00631L_5",
                        "reliability_gate_pass": True,
                        "action_allowed": True,
                        "block_reason": None,
                        "risk_up_permission_probability": 0.71,
                    }
                ],
                "realized_selected_edge": {
                    "count": 1,
                    "mean": 0.002,
                    "positive_rate": 1.0,
                    "worst": 0.002,
                    "p10": 0.002,
                    "median": 0.002,
                    "p90": 0.002,
                },
            },
            {
                "label": "2018_correction",
                "bucket": "out_of_sample",
                "window": {"start": "2018-01-02", "end": "2018-12-31"},
                "method": {
                    "slow_bear_gate": {"blocked_days": 10},
                    "risk_up_permission_gate": {"blocked_days": 20},
                },
                "action_counts": {"KEEP": 225},
                "non_keep_days": 0,
                "non_keep_decisions": [],
                "recent_decisions": [],
                "realized_selected_edge": {"count": 0, "mean": None, "positive_rate": None},
            },
        ],
    }


def test_report_allows_advisory_only_when_all_gates_pass(tmp_path: Path) -> None:
    opportunity = tmp_path / "relative.json"
    live_signal = tmp_path / "live.json"
    trust_log = tmp_path / "trust.jsonl"
    risk_log = tmp_path / "risk.jsonl"
    _write_json(opportunity, _opportunity_payload())
    _write_json(live_signal, {"actual_data_date": "2026-08-03", "requested_as_of_date": "2026-08-04"})
    _write_jsonl(trust_log, [{"date": "2026-08-03", "trust_level": "TRUST", "reasons": []}])
    _write_jsonl(risk_log, [{"date": "2026-08-03", "mechanism": "NORMAL", "reasons": []}])

    report = build_report(
        opportunity_path=opportunity,
        live_signal_path=live_signal,
        strategy_trust_log=trust_log,
        risk_mechanism_log=risk_log,
    )

    assert report["policy"] == "shadow_only_no_auto_weight_change"
    assert report["active_allocation_impact"] == "none"
    assert report["advisory_allowed"] is True
    assert report["recommended_action"] == "manual_review_consider_5pct_0050_to_00631l_shift"
    assert report["advisory_rule"]["cumulative_signals"] == "not_allowed"
    assert report["tail_risk_evaluation"]["stress_windows"]["2018_correction_non_keep_days"] == 0
    assert report["tail_risk_evaluation"]["selected_edge_worst_across_active_windows"] == 0.002


def test_report_blocks_when_coverage_stale_or_trust_abstains(tmp_path: Path) -> None:
    opportunity = tmp_path / "relative.json"
    live_signal = tmp_path / "live.json"
    trust_log = tmp_path / "trust.jsonl"
    risk_log = tmp_path / "risk.jsonl"
    _write_json(opportunity, _opportunity_payload(end="2026-07-15", decision_date="2026-07-15"))
    _write_json(live_signal, {"actual_data_date": "2026-08-03", "requested_as_of_date": "2026-08-04"})
    _write_jsonl(trust_log, [{"date": "2026-08-03", "trust_level": "ABSTAIN", "reasons": ["data_quality"]}])
    _write_jsonl(risk_log, [{"date": "2026-08-03", "mechanism": "NORMAL", "reasons": []}])

    report = build_report(
        opportunity_path=opportunity,
        live_signal_path=live_signal,
        strategy_trust_log=trust_log,
        risk_mechanism_log=risk_log,
    )

    assert report["advisory_allowed"] is False
    assert report["recommended_action"] == "keep_shadow_only"
    assert "coverage_fresh_for_live_date" in report["gates"]["blockers"]
    assert "exact_live_date_decision_available" in report["gates"]["blockers"]
    assert "strategy_trust_pass" in report["gates"]["blockers"]
