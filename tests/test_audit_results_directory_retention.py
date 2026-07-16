from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "audit_results_directory_retention.py"
    spec = importlib.util.spec_from_file_location("_test_audit_results_retention", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_family_strips_date_suffix() -> None:
    module = _load_module()
    assert module._family("group_a_plus_switch_policy_backtest_20260618.json") == "group_a_plus_switch_policy_backtest"
    assert module._family("ncf_00631l_panel_latest_20260707_120301.csv") == "ncf_00631l_panel_latest"
    assert module._family("no_date_here.json") == "no_date_here"


def test_audit_flags_unreferenced_large_file_as_candidate(tmp_path: Path) -> None:
    module = _load_module()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    search_root = tmp_path / "repo"
    search_root.mkdir()

    big = results_dir / "orphan_sweep_20260618.json"
    big.write_bytes(b"0" * 2_000_000)
    referenced = results_dir / "pinned_panel_20260707.csv"
    referenced.write_bytes(b"0" * 2_000_000)
    (search_root / "strategy.json").write_text(
        '{"path": "results/pinned_panel_20260707.csv"}', encoding="utf-8",
    )

    report = module.audit_results_directory(
        results_dir=results_dir, search_root=tmp_path, min_size_bytes=1_000_000,
    )

    candidate_paths = {row["path"] for row in report["large_file_deletion_candidates"]}
    protected_paths = {row["path"] for row in report["large_files_protected_referenced_elsewhere"]}
    assert "results/orphan_sweep_20260618.json" in candidate_paths
    assert "results/pinned_panel_20260707.csv" in protected_paths


def test_audit_does_not_delete_anything(tmp_path: Path) -> None:
    module = _load_module()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    f = results_dir / "some_file_20260618.json"
    f.write_bytes(b"0" * 2_000_000)

    module.audit_results_directory(results_dir=results_dir, search_root=tmp_path, min_size_bytes=1_000_000)

    assert f.exists()
