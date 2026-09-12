from __future__ import annotations

from pathlib import Path

from scripts.run.run_a2120_daily_shadow_pipeline import (
    _build_fresh_execution_plan_snapshot,
    build_latest_summary,
)


def test_build_latest_summary_exposes_shadow_state_and_artifacts() -> None:
    out = build_latest_summary(
        date_stamp="20260715",
        diagnostic={"latest": {"date": "2026-07-15", "compounding_regime": "TREND_PERSISTENT"}},
        replay={
            "replay": {
                "raw_action": "FAST_REENTER_CANDIDATE",
                "recommended_action": "BLOCKED_BY_HARD_GUARD",
                "hard_blockers": ["turnover cap"],
                "shadow_target_shares_before_hard_guards": 942,
            }
        },
        turnover={"result": {"shadow_plan": {"target_shares": {"00631L.TW": 942}, "turnover_ratio": 0.499}}},
        scorecard={
            "candidate": {"name": "score3_ar0_persist50_rev50__base40_mr0_trend100"},
            "decision": {"shadow_gate": "pass", "production": "do_not_promote"},
        },
        combined={"combined": {"combined_action": "BLOCKED_BY_HARD_GUARD"}},
        risk_sensitive_replay={
            "replay": {
                "raw_action": "FAST_REENTER_CANDIDATE",
                "recommended_action": "BLOCKED_BY_HARD_GUARD",
                "weak_trend_edge_gate": "ce20_negative",
                "weak_trend_edge_active": True,
                "allowed_fraction_for_regime": 0.9,
                "shadow_target_shares_before_hard_guards": 900,
            }
        },
        risk_sensitive_turnover={
            "result": {"shadow_plan": {"target_shares": {"00631L.TW": 900}, "turnover_ratio": 0.47}}
        },
        artifacts={"scorecard": "report/group_a_plus/shadow/a2120.json"},
    )

    assert out["production_effect"] == "none"
    assert out["daily_state"]["compounding_regime"] == "TREND_PERSISTENT"
    assert out["daily_state"]["recommended_action"] == "BLOCKED_BY_HARD_GUARD"
    assert out["daily_state"]["combined_action"] == "BLOCKED_BY_HARD_GUARD"
    assert out["daily_state"]["turnover50_target_00631l"] == 942
    assert out["risk_sensitive_variant"]["name"] == "ce20_negative_to_trend90"
    assert out["risk_sensitive_variant"]["weak_trend_edge_active"] is True
    assert out["risk_sensitive_variant"]["turnover50_target_00631l"] == 900
    assert out["scorecard_decision"]["shadow_gate"] == "pass"
    assert out["artifacts"]["scorecard"] == "report/group_a_plus/shadow/a2120.json"


def test_fresh_execution_plan_snapshot_is_best_effort_on_failure(tmp_path, monkeypatch) -> None:
    """2026-08-22: the snapshot generator must never break the rest of the
    a2120 shadow chain -- if build_execution_plan() raises for any reason
    (missing workbook, bad holdings row, DB issue), the function must log and
    return None rather than propagate, so run_pipeline() falls back to
    whatever --execution-plan was already given.
    """

    def _boom(**_kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "scripts.run.run_a2120_daily_shadow_pipeline.build_execution_plan", _boom
    )

    result = _build_fresh_execution_plan_snapshot(
        diagnostic_path=tmp_path / "diagnostic.json",
        date_stamp="20260822",
        output_dir=tmp_path,
        latest_dir=tmp_path,
        db_path=tmp_path / "stock_data.db",
    )

    assert result is None
    # No snapshot files should be written when generation fails.
    assert not any(tmp_path.glob("*shadow_snapshot*"))


def test_fresh_execution_plan_snapshot_writes_shadow_only_paths(tmp_path, monkeypatch) -> None:
    """The snapshot must land under the given output/latest dirs -- never at
    the real report/group_a_plus/latest/execution_plan.json production path.
    """

    fake_plan = {"actual_data_date": "2026-08-21", "target_shares": {}}

    def _fake_build(**_kwargs):
        return fake_plan

    monkeypatch.setattr(
        "scripts.run.run_a2120_daily_shadow_pipeline.build_execution_plan", _fake_build
    )

    output_dir = tmp_path / "results"
    latest_dir = tmp_path / "latest"
    output_dir.mkdir()
    latest_dir.mkdir()

    result = _build_fresh_execution_plan_snapshot(
        diagnostic_path=tmp_path / "diagnostic.json",
        date_stamp="20260822",
        output_dir=output_dir,
        latest_dir=latest_dir,
        db_path=tmp_path / "stock_data.db",
    )

    assert result == output_dir / "group_a_plus_execution_plan_a2120_shadow_snapshot_20260822.json"
    assert result.exists()
    assert (latest_dir / "execution_plan_a2120_shadow_snapshot.json").exists()
    assert (latest_dir / "execution_plan.json") != result
    assert not (latest_dir / "execution_plan.json").exists()
