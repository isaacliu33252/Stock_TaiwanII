from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_golden2_same_window_candidate_backtests as module


def _report(final: float, triggers: int) -> dict:
    return {
        "strategy": "a2118",
        "backtest_mode": "ncf_late_bull_regime_overlay",
        "window": {"start": "2025-01-02", "end": "2026-08-31", "rows": 10},
        "metrics": {"final_value": final, "sharpe_ratio": 1.0, "max_drawdown": -0.1},
        "execution": {"late_bull_trigger_days": triggers, "rebalance_count": 1, "transaction_cost": 2.0},
    }


def test_build_report_runs_baseline_and_candidate(monkeypatch, tmp_path: Path) -> None:
    calls: list[str | None] = []

    monkeypatch.setattr(module, "_resolve_end_date", lambda db, end: "2026-08-31" if end == "latest" else end)

    def fake_run_a2118(**kwargs):
        calls.append(kwargs.get("ncf_panel_631l_path"))
        final = 105.0 if kwargs.get("ncf_panel_631l_path") else 100.0
        triggers = 3 if kwargs.get("ncf_panel_631l_path") else 0
        return _report(final, triggers), None

    monkeypatch.setattr(module, "run_a2118", fake_run_a2118)
    windows = [{"label": "active", "start": "2025-01-02", "end": "latest", "panel": "panel.csv", "bucket": "tuning"}]

    report = module.build_report(windows=windows, db=tmp_path / "stock.db", initial_value=1_000_000.0)

    assert calls == [None, str(module.PROJECT_ROOT / "panel.csv")]
    assert report["window_count"] == 1
    item = report["reports"][0]
    assert item["baseline"]["metrics"]["final_value"] == 100.0
    assert item["rows"][0]["name"] == "golden2_latest_ncf_panel"
    assert item["rows"][0]["metrics"]["final_value"] == 105.0
    assert item["rows"][0]["trigger_days"] == 3


def test_write_outputs_exports_window_files(tmp_path: Path) -> None:
    report = {
        "policy": "research_only",
        "candidate_name": "golden2_latest_ncf_panel",
        "window_count": 1,
        "reports": [
            {
                "label": "active",
                "window": {"start": "2025-01-02", "end": "2026-08-31"},
                "baseline": {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.1}},
                "rows": [
                    {
                        "name": "golden2_latest_ncf_panel",
                        "metrics": {"final_value": 105.0, "sharpe_ratio": 1.1, "max_drawdown": -0.09},
                        "trigger_days": 2,
                    }
                ],
            }
        ],
    }

    module.write_outputs(report, tmp_path / "latest.json", tmp_path / "latest.md", tmp_path / "history")

    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest.md").exists()
    assert (tmp_path / "golden2_same_window_candidate_backtests" / "active.json").exists()
    assert json.loads((tmp_path / "golden2_same_window_candidate_backtests" / "active.json").read_text())["label"] == "active"
