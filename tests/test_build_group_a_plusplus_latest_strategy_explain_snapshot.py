import json
from pathlib import Path

from scripts.evaluate.build_group_a_plusplus_latest_strategy_explain_snapshot import build_snapshot


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_latest_strategy_explain_snapshot_summarizes_identity_and_governance(tmp_path: Path) -> None:
    watchlist = _write(
        tmp_path / "watchlist.json",
        {
            "name": "group_a_plusplus_latest_strategy_watchlist",
            "symbols": [{"symbol": "0050.TW"}, {"symbol": "00631L.TW"}, {"symbol": "00713.TW"}],
        },
    )
    weights = _write(
        tmp_path / "weights.json",
        {
            "active_strategy_id": "latest_v1",
            "candidate_status": "research_candidate",
            "status": "available",
            "target_assets": ["0050", "00631L", "cash"],
            "row_count": 2,
            "date_window": {"start": "2026-01-01", "end": "2026-01-02"},
            "execution_regime_counts": {"golden1": 2},
            "regime_weight_map": {"golden1": {"0050": 0.7, "00631L": 0.0, "cash": 0.3}},
            "decision": {"creates_orders": False, "changes_latest_strategy": False},
        },
    )
    governance = _write(
        tmp_path / "research_governance.json",
        {
            "status": "passed",
            "policy": "governance_audit_only_no_weight_change",
            "decision": {"promotion_allowed": False, "target_weight_change_allowed": False},
        },
    )
    registry = _write(
        tmp_path / "registry.json",
        {"status": "available", "summary": {"artifact_count": 3, "live_mutation_true_count": 0, "promotion_true_count": 0}},
    )

    report = build_snapshot(
        watchlist_path=watchlist,
        target_weights_path=weights,
        research_governance_path=governance,
        shadow_registry_path=registry,
        as_of="2026-09-08",
    )

    assert report["status"] == "warning"
    assert report["strategy_identity"]["active_strategy_id"] == "latest_v1"
    assert report["asset_scope"]["missing_watchlist_assets_from_target_weights"] == ["00713"]
    assert "watchlist_assets_missing_from_latest_target_weight_export" in report["warning_reasons"]
    assert report["governance_summary"]["research_governance_gate"]["status"] == "passed"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["promotion_allowed"] is False


def test_latest_strategy_explain_snapshot_available_when_assets_match(tmp_path: Path) -> None:
    watchlist = _write(
        tmp_path / "watchlist.json",
        {"name": "group_a_plusplus", "symbols": [{"symbol": "0050.TW"}, {"symbol": "00713.TW"}]},
    )
    weights = _write(
        tmp_path / "weights.json",
        {
            "status": "available",
            "target_assets": ["0050", "00713", "cash"],
            "regime_weight_map": {"balanced": {"0050": 0.8, "00713": 0.1, "cash": 0.1}},
        },
    )
    empty = _write(tmp_path / "empty.json", {})

    report = build_snapshot(
        watchlist_path=watchlist,
        target_weights_path=weights,
        research_governance_path=empty,
        shadow_registry_path=empty,
        as_of="2026-09-08",
    )

    assert report["status"] == "warning"
    assert "watchlist_assets_missing_from_latest_target_weight_export" not in report["warning_reasons"]
    assert "missing_research_governance_gate" in report["warning_reasons"]


def test_latest_strategy_explain_snapshot_blocks_missing_core_inputs(tmp_path: Path) -> None:
    report = build_snapshot(
        watchlist_path=tmp_path / "missing_watchlist.json",
        target_weights_path=tmp_path / "missing_weights.json",
        research_governance_path=tmp_path / "missing_governance.json",
        shadow_registry_path=tmp_path / "missing_registry.json",
        as_of="2026-09-08",
    )

    assert report["status"] == "blocked"
    assert "missing_group_a_plusplus_watchlist" in report["blocking_reasons"]
    assert "missing_latest_strategy_historical_target_weights" in report["blocking_reasons"]
