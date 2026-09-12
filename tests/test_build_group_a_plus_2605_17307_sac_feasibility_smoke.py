from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate import build_group_a_plus_2605_17307_sac_feasibility_smoke as smoke


def test_smoke_report_never_allows_live_sac_weights(monkeypatch, tmp_path: Path) -> None:
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    returns = pd.DataFrame(
        {
            "0050.TW": 0.001,
            "00631L.TW": 0.002,
            "00632R.TW": -0.001,
            "00679B.TWO": 0.0002,
        },
        index=dates,
    )
    monkeypatch.setattr(smoke, "_load_return_panel", lambda *args, **kwargs: (returns, "2025-02-21", []))
    monkeypatch.setattr(smoke, "_module_available", lambda name: True)

    strategy = tmp_path / "strategy.json"
    strategy.write_text(
        json.dumps({"active_strategy": {"id": "a2118_a2111_ncf_late_bull_deleverage"}}),
        encoding="utf-8",
    )

    report = smoke.build_smoke_report(
        db_path=tmp_path / "stock.db",
        strategy_path=strategy,
        live_snapshot_path=tmp_path / "missing_snapshot.json",
        ladder_path=tmp_path / "missing_ladder.json",
    )

    assert report["report_type"] == "group_a_plus_2605_17307_sac_feasibility_smoke"
    assert report["decision"]["can_run_local_sac_environment_smoke"] is True
    assert report["decision"]["train_sac_now"] is False
    assert report["decision"]["allow_sac_generated_target_weights"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["replace_a2118"] is False
    assert "stable_baselines3_sac_uses_box_action_not_native_dirichlet_simplex_policy" in report["blocking_reasons"]


def test_smoke_report_blocks_missing_modules_and_missing_db(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(smoke, "_module_available", lambda name: name != "stable_baselines3")

    report = smoke.build_smoke_report(
        db_path=tmp_path / "missing.db",
        strategy_path=tmp_path / "missing_strategy.json",
        live_snapshot_path=tmp_path / "missing_snapshot.json",
        ladder_path=tmp_path / "missing_ladder.json",
    )

    assert report["decision"]["can_run_local_sac_environment_smoke"] is False
    assert report["decision"]["paper_style_sac_training_ready"] is False
    assert "stock_database_missing" in report["blocking_reasons"]
    assert "python_module_missing:stable_baselines3" in report["blocking_reasons"]


def test_write_report_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2605_17307_sac_feasibility_smoke",
        "data_panel": {"resolved_end": "2026-08-25"},
        "decision": {"train_sac_now": False},
    }

    smoke.write_report(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2605_17307_sac_feasibility_smoke_20260825.json").exists()
