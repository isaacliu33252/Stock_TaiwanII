from __future__ import annotations

import json
from pathlib import Path

from scripts.report.build_group_a_plus_handoff_index import build_index, write_outputs


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_build_index_extracts_date_from_filename_and_classifies_closed_negative(tmp_path: Path) -> None:
    _write(
        tmp_path / "GROUP_A_PLUS_PAPER_X_HANDOFF_20260901.md",
        "# Group A+ Paper X Handoff\n\nDesk review: closed_negative, asset pool too small.\n",
    )

    report = build_index(roots=[str(tmp_path)])

    assert report["file_count"] == 1
    record = report["records"][0]
    assert record["date"] == "2026-09-01"
    assert record["status"] == "closed_negative"
    assert "Group A+ Paper X Handoff" == record["title"]


def test_build_index_classifies_adopted_and_not_adopted(tmp_path: Path) -> None:
    _write(
        tmp_path / "A_HANDOFF_20260801.md",
        "# A Handoff\n\nThis change was promoted to production after the review.\n",
    )
    _write(
        tmp_path / "B_HANDOFF_20260802.md",
        "# B Handoff\n\nRecommendation: do not promote, Sharpe gain is not robust.\n",
    )

    report = build_index(roots=[str(tmp_path)])

    by_path = {row["path"]: row for row in report["records"]}
    assert by_path[str(tmp_path / "A_HANDOFF_20260801.md")]["status"] == "adopted"
    assert by_path[str(tmp_path / "B_HANDOFF_20260802.md")]["status"] == "not_adopted"


def test_build_index_flags_follow_up_needed(tmp_path: Path) -> None:
    _write(
        tmp_path / "C_HANDOFF_20260803.md",
        "# C Handoff\n\nStill needs follow-up validation before any decision.\n",
    )

    report = build_index(roots=[str(tmp_path)])

    assert report["records"][0]["follow_up_needed"] is True
    assert report["follow_up_needed_count"] == 1


def test_build_index_sorts_newest_first_and_handles_missing_date(tmp_path: Path) -> None:
    _write(tmp_path / "OLD_HANDOFF_20260601.md", "# Old\n\nnothing notable.\n")
    _write(tmp_path / "NEW_HANDOFF_20260901.md", "# New\n\nnothing notable.\n")
    _write(tmp_path / "UNDATED_HANDOFF.md", "# Undated\n\nnothing notable.\n")

    report = build_index(roots=[str(tmp_path)])

    dates = [row["date"] for row in report["records"]]
    assert dates[0] == "2026-09-01"
    assert dates[1] == "2026-06-01"
    assert dates[2] is None
    assert report["status_counts"]["unclassified"] == 3


def test_write_outputs_writes_json_and_markdown(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "D_HANDOFF_20260904.md", "# D\n\nclosed_negative result.\n")
    report = build_index(roots=[str(tmp_path / "src")])

    output_md = tmp_path / "out" / "INDEX.md"
    output_json = tmp_path / "out" / "index.json"
    write_outputs(report, output_md=output_md, output_json=output_json)

    assert "Group A+ Handoff Index" in output_md.read_text(encoding="utf-8")
    loaded = json.loads(output_json.read_text(encoding="utf-8"))
    assert loaded["file_count"] == 1
