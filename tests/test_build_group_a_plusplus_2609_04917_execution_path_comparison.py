from pathlib import Path

from scripts.evaluate.build_group_a_plusplus_2609_04917_execution_path_comparison import build_report


def test_build_report_marks_turnover_bridge_as_best_shadow_path(tmp_path: Path) -> None:
    report = build_report(
        {
            "official": {"joint": tmp_path / "missing.json"},
            "turnover_bridge_shadow": {"joint": tmp_path / "missing2.json"},
        }
    )

    assert report["status"] == "shadow_bridge_is_best_manual_review_candidate"
    assert report["best_shadow_path"] == "turnover_bridge_shadow"
    assert report["decision"]["live_promotion_allowed"] is False
    assert len(report["paths"]) == 2
