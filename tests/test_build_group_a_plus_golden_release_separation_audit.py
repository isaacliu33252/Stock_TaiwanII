from pathlib import Path

from scripts.evaluate.build_group_a_plus_golden_release_separation_audit import build_audit


def test_golden_release_separation_audit_passes_clean_commands() -> None:
    report = build_audit(
        commands={"safe": ["python", "script.py", "--output", "report/group_a_plus/latest/safe.json"]},
        as_of="2026-09-08",
    )

    assert report["summary"]["output_target_violations"] == 0
    assert report["blockers"] == []
    assert report["decision"]["changes_golden1_0531"] is False
    assert report["decision"]["changes_golden2_0830"] is False


def test_golden_release_separation_audit_blocks_golden2_output_target() -> None:
    protected = Path("results/golden2_0830/group_a_combined_live_golden2_0830.json")

    report = build_audit(commands={"bad": ["python", "script.py", "--output", str(protected)]}, as_of="2026-09-08")

    assert report["status"] == "blocked"
    assert "pipeline_output_targets_frozen_golden_release_artifacts" in report["blockers"]
    assert report["output_target_violations"] == [
        {"step": "bad", "flag": "--output", "path": "results/golden2_0830/group_a_combined_live_golden2_0830.json"}
    ]
