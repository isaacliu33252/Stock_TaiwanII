from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_sweep import _parse_floats, _summarize_combo, write_sweep


def test_parse_floats_returns_values() -> None:
    assert _parse_floats("0.75, 0.80") == [0.75, 0.8]


def test_parse_floats_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        _parse_floats(" , ")


def test_summarize_combo_totals_window_deltas() -> None:
    windows = [
        {
            "tsi_alert_days": 3,
            "trend_persistent_tsi_alert_days": 1,
            "ensemble_delta_vs_compounding": {"final_value": 10.0, "sharpe_ratio": 0.1, "max_drawdown": 0.0},
        },
        {
            "tsi_alert_days": 2,
            "trend_persistent_tsi_alert_days": 2,
            "ensemble_delta_vs_compounding": {"final_value": -5.0, "sharpe_ratio": -0.2, "max_drawdown": -0.01},
        },
    ]

    summary = _summarize_combo(windows, threshold=0.8, cap=0.5)

    assert summary["threshold"] == 0.8
    assert summary["tsi_trend_cap"] == 0.5
    assert summary["tsi_alert_days"] == 5
    assert summary["trend_persistent_tsi_alert_days"] == 3
    assert summary["ensemble_minus_compounding_final_value_sum"] == 5.0
    assert summary["ensemble_positive_vs_compounding_windows"] == 1
    assert summary["ensemble_non_worse_drawdown_vs_compounding_windows"] == 1


def test_write_sweep_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_sweep",
        "production_effect": "none",
        "summaries": [
            {
                "threshold": 0.8,
                "tsi_trend_cap": 0.5,
                "tsi_alert_days": 3,
                "trend_persistent_tsi_alert_days": 1,
                "ensemble_minus_compounding_final_value_sum": 100.0,
                "ensemble_minus_compounding_sharpe_sum": 0.1,
                "ensemble_minus_compounding_max_drawdown_sum": 0.0,
                "ensemble_positive_vs_compounding_windows": 1,
                "ensemble_non_worse_drawdown_vs_compounding_windows": 1,
            }
        ],
        "best_by_final_value": {"threshold": 0.8, "tsi_trend_cap": 0.5},
        "best_by_drawdown": {"threshold": 0.8, "tsi_trend_cap": 0.5},
        "best_by_window_coverage": {"threshold": 0.8, "tsi_trend_cap": 0.5},
        "decision": {"promotion_allowed": False},
    }
    output = tmp_path / "latest" / "sweep.json"
    output_md = tmp_path / "latest" / "sweep.md"
    history = tmp_path / "history"

    write_sweep(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_compounding_ensemble_sweep"
    assert "TSI Compounding Ensemble Sweep" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_compounding_ensemble_sweep_*.json"))
