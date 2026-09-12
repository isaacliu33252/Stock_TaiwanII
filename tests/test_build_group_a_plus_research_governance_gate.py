import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_research_governance_gate import build_gate


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_research_governance_gate_passes_safe_shadow_report(tmp_path: Path) -> None:
    safe = _write(
        tmp_path / "safe_shadow.json",
        {
            "report_type": "example_shadow_review",
            "policy": "research_only_no_weight_change",
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "decision": {"promotion_allowed": False},
        },
    )

    report = build_gate(reports_dir=tmp_path, report_paths=[safe], as_of="2026-09-08")

    assert report["status"] == "passed"
    assert report["summary"]["included_reports"] == 1
    assert report["summary"]["live_mutation_violations"] == 0
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["target_weight_change_allowed"] is False


def test_research_governance_gate_blocks_live_mutation_permission(tmp_path: Path) -> None:
    unsafe = _write(
        tmp_path / "unsafe_shadow.json",
        {
            "report_type": "paper_shadow_gate",
            "policy": "research_only_no_weight_change",
            "decision": {
                "changes_latest_strategy": True,
                "target_weight_change_allowed": True,
            },
        },
    )

    report = build_gate(reports_dir=tmp_path, report_paths=[unsafe], as_of="2026-09-08")

    assert report["status"] == "blocked"
    assert "research_report_declares_live_mutation_permission" in report["blockers"]
    assert report["summary"]["live_mutation_violations"] == 2
    assert {item["field"] for item in report["live_mutation_violations"]} == {
        "decision.changes_latest_strategy",
        "decision.target_weight_change_allowed",
    }


def test_research_governance_gate_routes_promotion_true_to_manual_review(tmp_path: Path) -> None:
    candidate = _write(
        tmp_path / "candidate_readiness.json",
        {
            "report_type": "candidate_readiness_review",
            "policy": "promotion_readiness_only_no_live_weight_change",
            "decision": {"promotion_allowed": True},
        },
    )

    report = build_gate(reports_dir=tmp_path, report_paths=[candidate], as_of="2026-09-08")

    assert report["status"] == "manual_review_required"
    assert report["blockers"] == []
    assert report["summary"]["promotion_manual_review_items"] == 1
    assert report["promotion_manual_review"][0]["field"] == "decision.promotion_allowed"
    assert report["decision"]["promotion_allowed"] is False


def test_research_governance_gate_records_unreadable_reports(tmp_path: Path) -> None:
    broken = tmp_path / "broken_shadow.json"
    broken.write_text("{", encoding="utf-8")

    report = build_gate(reports_dir=tmp_path, report_paths=[broken], as_of="2026-09-08")

    assert report["status"] == "blocked"
    assert "unreadable_research_like_reports" in report["blockers"]
    assert report["summary"]["unreadable_reports"] == 1
