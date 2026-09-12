from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plusplus_2609_04917_information_bom as module


def test_information_bom_flags_missing_availability_and_model_fields(tmp_path: Path) -> None:
    json_path = tmp_path / "signal.json"
    csv_path = tmp_path / "panel.csv"
    json_path.write_text(json.dumps({"actual_data_date": "2026-09-09", "target_weights": {"cash": 1.0}}), encoding="utf-8")
    csv_path.write_text("date,feature\n2026-09-09,1.0\n", encoding="utf-8")

    report = module.build_report(
        artifacts=[("signal", json_path), ("panel", csv_path)],
        as_of="2026-09-09",
    )

    assert report["status"] == "warning"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert "availability_or_generation_time_missing" in report["warning_artifacts"]["signal"]
    assert "model_or_policy_version_missing" in report["warning_artifacts"]["signal"]
    assert "availability_time_column_missing" in report["warning_artifacts"]["panel"]
    assert "model_version_column_missing" in report["warning_artifacts"]["panel"]


def test_information_bom_blocks_missing_artifact(tmp_path: Path) -> None:
    existing = tmp_path / "signal.json"
    missing = tmp_path / "missing.json"
    existing.write_text(
        json.dumps({"actual_data_date": "2026-09-09", "generated_at": "2026-09-09T12:00:00", "model_version": "v1"}),
        encoding="utf-8",
    )

    report = module.build_report(artifacts=[("signal", existing), ("missing", missing)])

    assert report["status"] == "blocked"
    assert report["missing_artifacts"] == ["missing"]
    assert report["artifacts"][1]["blockers"] == ["artifact_missing"]


def test_information_bom_accepts_models_block_as_model_provenance(tmp_path: Path) -> None:
    path = tmp_path / "ncf_00631l_latest_20260909.json"
    path.write_text(
        json.dumps(
            {
                "actual_data_date": "2026-09-09",
                "generated_at": "2026-09-09T12:00:00",
                "models": {"classification": {"kind": "logistic"}, "regression": {"kind": "ridge"}},
            }
        ),
        encoding="utf-8",
    )

    report = module.build_report(artifacts=[("ncf_signal", path)])

    assert report["status"] == "available"
    assert report["warning_artifacts"] == {}


def test_markdown_lists_artifact_warnings(tmp_path: Path) -> None:
    path = tmp_path / "panel.csv"
    path.write_text("date,feature\n2026-09-09,1.0\n", encoding="utf-8")
    report = module.build_report(artifacts=[("panel", path)])
    markdown = module._markdown(report)

    assert "| panel | warning |" in markdown
    assert "availability_time_column_missing" in markdown
