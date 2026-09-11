from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_golden2_promotion_candidate_review import _next_required_work, build_review


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _metrics(final: float = 100.0) -> dict:
    return {"final_value": final, "sharpe_ratio": 1.0, "max_drawdown": -0.1}


def test_review_blocks_metric_only_golden2_candidate_until_same_window_rows_exist(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        {
            "experiment": "baseline",
            "baseline": {"metrics": _metrics(100.0)},
            "summary": {"best_by_final_value": {"metrics": _metrics(101.0), "trigger_days": 1}},
            "window": {"start": "2025-01-02", "end": "2026-07-02"},
        },
    )
    promotion_gate = _write(
        tmp_path / "promotion.json",
        {
            "decision": "blocked_model_gates_manual_approval_pending",
            "blocking_gates": ["panel_drift", "multi_window"],
            "metrics_gate": {"status": "fail"},
            "panel_drift_gate": {"status": "fail"},
            "multi_window_gate": {"status": "fail"},
        },
    )
    multi_window = _write(tmp_path / "multi.json", {"decision": "research_only_no_multi_window_pass"})
    release = _write(
        tmp_path / "release.json",
        {"release_date": "2026-08-30", "status": "frozen_release", "source_state": {"actual_data_date": "2026-08-28"}},
    )
    metric_only = _write(
        tmp_path / "golden2.json",
        {
            "experiment": "golden2",
            "window": {"start": "2025-01-02", "end": "2026-05-29"},
            "metrics": _metrics(99.0),
        },
    )
    latest_2024 = _write(tmp_path / "latest_2024.json", {"metrics": _metrics(120.0)})
    latest_2025 = _write(tmp_path / "latest_2025.json", {"metrics": _metrics(110.0)})
    drift = _write(
        tmp_path / "drift.json",
        {"column_summary": {"h20_prob_up": {"max_abs_delta": 0.2, "max_abs_delta_date": "2026-02-10"}}},
    )
    dfl = _write(tmp_path / "dfl.json", {"summary": {"all_checks_pass": False}, "conclusion": "review_required_shadow_only"})
    cvar = _write(tmp_path / "cvar.json", {"status": "blocked", "decision": {"target_weight_change_allowed": False}})
    daily = _write(tmp_path / "daily.json", {"overall_status": "ok"})

    report = build_review(
        baseline_path=baseline,
        promotion_gate_path=promotion_gate,
        multi_window_gate_path=multi_window,
        golden2_release_path=release,
        golden2_backtest_path=metric_only,
        latest_2024_2026_path=latest_2024,
        latest_2025_2026_path=latest_2025,
        panel_drift_path=drift,
        dfl_audit_path=dfl,
        cvar_forward_path=cvar,
        daily_status_path=daily,
    )

    assert report["status"] == "blocked_prepare_multi_window_backtest"
    assert report["compatible_candidate_count"] == 0
    assert "no_golden2_promotion_compatible_candidate_rows" in report["blocking_reasons"]
    assert "panel_drift_gate_failed" in report["blocking_reasons"]
    assert report["candidate_compatibility"][0]["metrics_available"] is True
    assert report["candidate_compatibility"][0]["promotion_candidate_compatible"] is False


def test_review_compares_candidate_rows_when_available(tmp_path: Path) -> None:
    baseline = _write(tmp_path / "baseline.json", {"metrics": _metrics(100.0)})
    promotion_gate = _write(
        tmp_path / "promotion.json",
        {
            "decision": "research_only",
            "blocking_gates": [],
            "metrics_gate": {"status": "pass"},
            "panel_drift_gate": {"status": "pass"},
            "multi_window_gate": {"status": "pass"},
        },
    )
    multi_window = _write(tmp_path / "multi.json", {"decision": "candidate_available"})
    release = _write(
        tmp_path / "release.json",
        {"release_date": "2026-08-30", "status": "frozen_release", "source_state": {"actual_data_date": "2026-08-31"}},
    )
    candidate = _write(
        tmp_path / "candidate.json",
        {"experiment": "candidate", "rows": [{"name": "golden2_row", **_metrics(105.0), "trigger_days": 2}]},
    )
    drift = _write(
        tmp_path / "drift.json",
        {"column_summary": {"h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2026-02-10"}}},
    )
    dfl = _write(tmp_path / "dfl.json", {"summary": {"all_checks_pass": True}, "conclusion": "pass"})
    cvar = _write(tmp_path / "cvar.json", {"status": "ok", "decision": {"target_weight_change_allowed": True}})
    daily = _write(tmp_path / "daily.json", {"overall_status": "ok"})

    report = build_review(
        baseline_path=baseline,
        promotion_gate_path=promotion_gate,
        multi_window_gate_path=multi_window,
        golden2_release_path=release,
        golden2_backtest_path=candidate,
        latest_2024_2026_path=candidate,
        latest_2025_2026_path=candidate,
        panel_drift_path=drift,
        dfl_audit_path=dfl,
        cvar_forward_path=cvar,
        daily_status_path=daily,
    )

    assert report["compatible_candidate_count"] == 3
    assert report["comparison"]["candidate_row_count"] == 1
    assert report["comparison"]["formal_upgrade_pass_count"] == 1


def test_review_picks_up_golden2_same_window_dir_candidate_rows(tmp_path: Path) -> None:
    baseline = _write(tmp_path / "baseline.json", {"metrics": _metrics(100.0)})
    promotion_gate = _write(
        tmp_path / "promotion.json",
        {
            "decision": "blocked_model_gates_manual_approval_pending",
            "blocking_gates": ["multi_window"],
            "metrics_gate": {"status": "pass"},
            "panel_drift_gate": {"status": "pass"},
            "multi_window_gate": {"status": "fail"},
        },
    )
    multi_window = _write(tmp_path / "multi.json", {"decision": "research_only_no_multi_window_pass"})
    release = _write(
        tmp_path / "release.json",
        {"release_date": "2026-08-30", "status": "frozen_release", "source_state": {"actual_data_date": "2026-08-31"}},
    )
    incompatible = _write(tmp_path / "legacy.json", {"experiment": "legacy", "metrics": _metrics(99.0)})
    same_window_dir = tmp_path / "same_window"
    _write(
        same_window_dir / "2020_covid.json",
        {"baseline": {"metrics": _metrics(100.0)}, "rows": [{"name": "golden2_row", "metrics": _metrics(105.0)}]},
    )
    drift = _write(
        tmp_path / "drift.json",
        {"column_summary": {"h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2026-02-10"}}},
    )
    dfl = _write(tmp_path / "dfl.json", {"summary": {"all_checks_pass": True}, "conclusion": "pass"})
    cvar = _write(tmp_path / "cvar.json", {"status": "ok", "decision": {"target_weight_change_allowed": True}})
    daily = _write(tmp_path / "daily.json", {"overall_status": "ok"})

    report = build_review(
        baseline_path=baseline,
        promotion_gate_path=promotion_gate,
        multi_window_gate_path=multi_window,
        golden2_release_path=release,
        golden2_backtest_path=incompatible,
        latest_2024_2026_path=incompatible,
        latest_2025_2026_path=incompatible,
        golden2_same_window_dir=same_window_dir,
        panel_drift_path=drift,
        dfl_audit_path=dfl,
        cvar_forward_path=cvar,
        daily_status_path=daily,
    )

    assert "no_golden2_promotion_compatible_candidate_rows" not in report["blocking_reasons"]
    assert report["compatible_candidate_count"] == 1
    assert "no_multi_window_candidate_available" in report["blocking_reasons"]
    assert any("candidate rows are available" in step for step in report["next_required_work"])
    assert not any("build same-window golden2/latest backtest" in step for step in report["next_required_work"])


def test_next_required_work_reports_none_when_no_blockers() -> None:
    steps = _next_required_work([], [Path("a.json")])

    assert steps == ["none -- all gates pass; still requires manual promotion approval before any live weight change"]


def test_next_required_work_maps_each_blocker_to_a_concrete_step() -> None:
    steps = _next_required_work(["dfl_latest_audit_not_promotion_ready"], [Path("a.json")])

    assert len(steps) == 2
    assert "candidate rows are available" in steps[0]
    assert "DFL active-date audit" in steps[1]
