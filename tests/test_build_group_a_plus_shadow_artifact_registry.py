import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_shadow_artifact_registry import build_registry


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_shadow_artifact_registry_indexes_research_like_json_and_markdown(tmp_path: Path) -> None:
    artifact = _write(
        tmp_path / "paper_shadow.json",
        {
            "report_type": "example_shadow_review",
            "policy": "research_only_no_weight_change",
            "status": "available",
            "decision": {"promotion_allowed": False},
        },
    )
    artifact.with_suffix(".md").write_text("# report\n", encoding="utf-8")

    report = build_registry(reports_dir=tmp_path, as_of="2026-09-08")

    assert report["status"] == "available"
    assert report["summary"]["artifact_count"] == 1
    assert report["summary"]["missing_markdown_count"] == 0
    assert report["artifacts"][0]["path"].endswith("paper_shadow.json")
    assert report["artifacts"][0]["markdown_path"].endswith("paper_shadow.md")
    assert report["decision"]["target_weight_change_allowed"] is False


def test_shadow_artifact_registry_records_missing_markdown(tmp_path: Path) -> None:
    _write(
        tmp_path / "readiness_gate.json",
        {
            "report_type": "example_readiness_gate",
            "policy": "research_only_no_weight_change",
        },
    )

    report = build_registry(reports_dir=tmp_path, as_of="2026-09-08")

    assert report["summary"]["artifact_count"] == 1
    assert report["summary"]["missing_markdown_count"] == 1
    assert report["missing_markdown"][0].endswith("readiness_gate.json")


def test_shadow_artifact_registry_ignores_non_research_json(tmp_path: Path) -> None:
    _write(
        tmp_path / "live_signal.json",
        {
            "report_type": "group_a_plus_live_signal",
            "policy": "production_signal",
            "status": "ok",
        },
    )

    report = build_registry(reports_dir=tmp_path, as_of="2026-09-08")

    assert report["summary"]["artifact_count"] == 0
    assert report["summary"]["by_family"] == {}


def test_shadow_artifact_registry_blocks_unreadable_json(tmp_path: Path) -> None:
    (tmp_path / "broken_shadow.json").write_text("{", encoding="utf-8")

    report = build_registry(reports_dir=tmp_path, as_of="2026-09-08")

    assert report["status"] == "blocked"
    assert report["summary"]["unreadable_count"] == 1
