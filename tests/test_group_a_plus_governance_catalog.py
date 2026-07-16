#!/usr/bin/env python3
"""Regression checks for the GroupA+ runner catalog."""

from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.governance.catalog import build_catalog
from group_a_plus.governance.latest import SUPPORTED_STRATEGIES


def test_execution_plan_catalog_requires_cash_and_compounding_guard() -> None:
    catalog = build_catalog("2026-01-01", "2026-07-14")
    execution_plan = next(item for item in catalog["runners"] if item["id"] == "execution_plan_v2")

    assert "cash_balance" in execution_plan["required_runtime_inputs"]
    assert "manual_only_reason" in execution_plan
    assert "--cash-balance {cash_balance}" in execution_plan["module_command_template"]
    assert "--compounding-regime latest" in execution_plan["module_command_template"]
    assert "compounding_regime_no_00631l_add" in execution_plan["guards"]
    assert "portfolio_snapshot_mismatch" in execution_plan["guards"]


def _write_manifest(path: Path, active_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "active_strategy": {"id": active_id, "runner": SUPPORTED_STRATEGIES[active_id]},
            }
        ),
        encoding="utf-8",
    )


def test_catalog_includes_every_supported_strategy_without_duplicates() -> None:
    catalog = build_catalog("2026-01-01", "2026-07-14")
    ids = [item["id"] for item in catalog["runners"]]
    modules = {item["module"] for item in catalog["runners"] if "module" in item}

    assert len(ids) == len(set(ids))
    for strategy_id, module_path in SUPPORTED_STRATEGIES.items():
        assert module_path in modules, f"{strategy_id} ({module_path}) missing from catalog"


def test_active_resolves_from_strategy_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "strategy.json"
    _write_manifest(manifest_path, "a2119_a2111_finbert_gate")

    catalog = build_catalog("2026-01-01", "2026-07-14", manifest_path=manifest_path)
    active_entry = next(item for item in catalog["runners"] if item["id"] == "a2119_a2111_finbert_gate")

    assert catalog["active"] == "a2119_a2111_finbert_gate"
    assert active_entry["kind"] == "active_strategy"
    other_entry = next(item for item in catalog["runners"] if item["id"] == "a2118_a2111_ncf_late_bull_deleverage")
    assert other_entry["kind"] == "shadow_candidate"


def test_active_falls_back_when_manifest_missing(tmp_path: Path) -> None:
    catalog = build_catalog("2026-01-01", "2026-07-14", manifest_path=tmp_path / "does_not_exist.json")

    assert catalog["active"] == "a2118_a2111_ncf_late_bull_deleverage"


def test_legacy_a213_runner_is_no_longer_marked_active() -> None:
    catalog = build_catalog("2026-01-01", "2026-07-14")
    legacy = next(item for item in catalog["runners"] if item["id"] == "a213_runner")

    assert legacy["kind"] == "legacy_superseded"


def test_new_strategy_entries_have_runnable_module_command_template() -> None:
    catalog = build_catalog("2026-01-01", "2026-07-14")
    a2118 = next(item for item in catalog["runners"] if item["id"] == "a2118_a2111_ncf_late_bull_deleverage")

    assert a2118["module"] == "group_a_plus.runners.a2118"
    assert "python3 -m group_a_plus.runners.a2118" in a2118["module_command_template"]
    assert "--start {start} --end {end}" in a2118["module_command_template"]
    assert a2118["description"]
