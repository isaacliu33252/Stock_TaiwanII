from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate.build_ncf_panel_manifest import build_manifest, build_panel_manifest


def test_panel_manifest_hashes_schema_and_content(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-05"],
            "ensemble_prob_up": [0.40, 0.60],
            "confidence": [0.20, 0.30],
        }
    ).to_csv(panel, index=False, encoding="utf-8-sig")

    first = build_panel_manifest(panel)
    second = build_panel_manifest(panel)

    assert first["row_count"] == 2
    assert first["date_start"] == "2026-01-02"
    assert first["date_end"] == "2026-01-05"
    assert first["schema_hash"] == second["schema_hash"]
    assert first["content_hash"] == second["content_hash"]
    assert first["key_column_stats"]["ensemble_prob_up"]["mean"] == 0.5


def test_panel_manifest_normalizes_unnamed_date_index(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    frame = pd.DataFrame({"ensemble_prob_up": [0.45, 0.55]}, index=pd.to_datetime(["2026-01-02", "2026-01-05"]))
    frame.index.name = "date"
    frame.to_csv(panel, encoding="utf-8-sig")

    report = build_panel_manifest(panel)

    assert report["columns"][0] == "date"
    assert report["date_start"] == "2026-01-02"
    assert report["date_end"] == "2026-01-05"


def test_combined_manifest_changes_when_panel_content_changes(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    pd.DataFrame({"date": ["2026-01-02"], "confidence": [0.10]}).to_csv(panel, index=False)

    first = build_manifest([panel])
    pd.DataFrame({"date": ["2026-01-02"], "confidence": [0.20]}).to_csv(panel, index=False)
    second = build_manifest([panel])

    assert first["combined_hash"] != second["combined_hash"]
    assert first["panels"][0]["schema_hash"] == second["panels"][0]["schema_hash"]
    assert first["panels"][0]["content_hash"] != second["panels"][0]["content_hash"]
