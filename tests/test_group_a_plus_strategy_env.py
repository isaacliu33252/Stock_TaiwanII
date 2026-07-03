#!/usr/bin/env python3
"""Tests for GroupA+ environment health checks."""

from __future__ import annotations

from pathlib import Path

from group_a_plus.operations.strategy_env import build_strategy_env_health


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def test_strategy_env_health_reports_ok_when_required_artifacts_exist(tmp_path: Path) -> None:
    for rel_path in (
        "report/group_a_plus/latest/strategy.json",
        "report/group_a_plus/latest/live_signal.json",
        "results/ncf_00631l_20260630.json",
        "results/ncf_00631l_panel_latest_20260630.csv",
        "config/group_a_plus_watchlist.json",
        ".venv/bin/python",
    ):
        _touch(tmp_path / rel_path)
    (tmp_path / "news").mkdir(parents=True)

    report = build_strategy_env_health(tmp_path)

    assert report["status"] in {"ok", "warning"}
    assert report["missing_files"] == []
    assert report["bad_dirs"] == []


def test_strategy_env_health_reports_missing_required_files(tmp_path: Path) -> None:
    (tmp_path / "results").mkdir(parents=True)
    (tmp_path / "report/group_a_plus/latest").mkdir(parents=True)
    (tmp_path / "news").mkdir(parents=True)

    report = build_strategy_env_health(tmp_path)

    assert report["status"] == "error"
    assert "live_signal" in report["missing_files"]
    assert "watchlist_config" in report["missing_files"]
