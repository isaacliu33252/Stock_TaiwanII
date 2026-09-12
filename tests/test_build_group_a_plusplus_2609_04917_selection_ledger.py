from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plusplus_2609_04917_selection_ledger as module


def test_selection_ledger_blocks_without_frozen_spec(tmp_path: Path) -> None:
    profit = tmp_path / "profit.json"
    root = tmp_path / "latest"
    root.mkdir()
    profit.write_text(json.dumps({"active_shadow_candidates": ["staged_reentry"]}), encoding="utf-8")
    (root / "tsi_no_add_sweep.json").write_text(
        json.dumps({"report_type": "sweep", "top_variants": [{"variant": "a"}]}),
        encoding="utf-8",
    )

    report = module.build_report(profit_readiness_path=profit, search_roots=[root], as_of="2026-09-09")

    assert report["status"] == "blocked"
    assert report["artifact_count"] == 1
    assert "frozen_confirmatory_specification_missing" in report["blocking_reasons"]
    assert report["decision"]["selection_ledger_available"] is True
    assert report["decision"]["confirmatory_specification_frozen"] is False
    assert report["decision"]["target_weight_change_allowed"] is False


def test_selection_ledger_available_with_frozen_spec(tmp_path: Path) -> None:
    profit = tmp_path / "profit.json"
    root = tmp_path / "latest"
    spec = tmp_path / "frozen_spec.md"
    root.mkdir()
    profit.write_text(json.dumps({"active_shadow_candidates": ["candidate"]}), encoding="utf-8")
    spec.write_text("candidate spec", encoding="utf-8")
    (root / "candidate_oos_validation.json").write_text(
        json.dumps({"status": "available", "decision": {"promotion_allowed": False}}),
        encoding="utf-8",
    )

    report = module.build_report(profit_readiness_path=profit, search_roots=[root], frozen_spec_path=spec)

    assert report["status"] == "available_for_confirmatory_review"
    assert report["blocking_reasons"] == []
    assert report["decision"]["confirmatory_specification_frozen"] is True
    assert report["decision"]["promotion_allowed"] is False


def test_selection_ledger_markdown_includes_artifacts(tmp_path: Path) -> None:
    profit = tmp_path / "profit.json"
    root = tmp_path / "latest"
    root.mkdir()
    profit.write_text("{}", encoding="utf-8")
    (root / "abc_seed_sweep.md").write_text("x", encoding="utf-8")

    report = module.build_report(profit_readiness_path=profit, search_roots=[root])
    markdown = module._markdown(report)

    assert "abc_seed_sweep.md" in markdown
    assert "frozen_confirmatory_specification_missing" in markdown
