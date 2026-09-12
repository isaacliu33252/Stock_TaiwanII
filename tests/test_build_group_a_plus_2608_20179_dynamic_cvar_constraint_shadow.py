from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.evaluate import build_group_a_plus_2608_20179_dynamic_cvar_constraint_shadow as module


def test_state_bucket_marks_cvar_breach_as_adverse() -> None:
    assert (
        module._state_bucket(
            latest_return=0.01,
            latest_drawdown=-0.01,
            residual95=0.002,
            near_threshold=0.001,
        )
        == "adverse_cvar_breach"
    )


def test_pacing_multiplier_blocks_on_positive_residual() -> None:
    assert module._pacing_multiplier("favorable", 0.001, None) == 0.0
    assert module._pacing_multiplier("neutral", -0.001, None) == 0.5
    assert module._pacing_multiplier("favorable", -0.001, -0.001) == 1.0


def test_write_markdown_renders_constraint_summary(tmp_path: Path) -> None:
    output = tmp_path / "shadow.md"
    report = {
        "status": "blocked_for_live_promotion",
        "as_of": "2026-09-01",
        "policy": "research_only_dynamic_cvar_constraint_shadow_no_weight_change",
        "decision": {
            "allow_00631l_add": False,
            "recommended_00631l_add_pacing_multiplier": 0.0,
        },
        "summary": {
            "cvar_residual_breach_windows": 1,
            "latest_worse_than_no_00631l_es95_windows": 1,
            "latest_worse_than_no_letf_es95_windows": 1,
            "sensitivity_breach_windows_by_buffer": {"0.00": 1, "0.10": 1},
        },
        "rolling_windows": {
            "63": {
                "metrics": {"expected_shortfall_loss_95": 0.02, "expected_shortfall_loss_99": 0.03},
                "budget": {"loss_cvar95_budget": 0.018, "loss_cvar99_budget": 0.027},
                "residual": {"loss_cvar95_residual": 0.002, "loss_cvar99_residual": 0.003},
                "relative_baselines": {
                    "no_00631l_to_cash": {"relative_gap": {"es95_delta_vs_baseline": 0.01}},
                    "no_letf_to_cash": {"relative_gap": {"es95_delta_vs_baseline": 0.02}},
                    "golden1_0531_static": {"relative_gap": {"es95_delta_vs_baseline": -0.01}},
                },
                "state": {"bucket": "adverse_cvar_breach", "pacing_multiplier": 0.0},
            }
        },
    }

    module.write_markdown(report, output)

    text = output.read_text(encoding="utf-8")
    assert "2608.20179 Dynamic CVaR Constraint Shadow" in text
    assert "adverse_cvar_breach" in text
    assert "Budget Sensitivity" in text
    assert "No target-weight change" in text


def test_build_report_blocks_when_upstream_tail_gate_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live_signal = tmp_path / "live_signal.json"
    rolling_gate = tmp_path / "rolling_gate.json"
    golden2_signal = tmp_path / "golden2.json"
    live_signal.write_text(
        json.dumps(
            {
                "actual_data_date": "2026-09-01",
                "target_weights": {
                    "0050.TW": 0.47,
                    "00631L.TW": 0.10,
                    "00632R.TW": 0.16,
                    "cash": 0.27,
                },
            }
        ),
        encoding="utf-8",
    )
    rolling_gate.write_text(
        json.dumps(
            {
                "status": "available_for_shadow_monitoring",
                "summary": {"allow_00631l_add": False},
            }
        ),
        encoding="utf-8",
    )
    golden2_signal.write_text(
        json.dumps(
            {
                "actual_data_date": "2026-08-30",
                "target_weights": {"0050.TW": 0.47, "00631L.TW": 0.10, "00632R.TW": 0.16},
                "target_cash_weight": 0.27,
            }
        ),
        encoding="utf-8",
    )
    dates = pd.date_range("2026-01-01", periods=300, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0 + i * 0.05 for i in range(len(dates))],
            "00631L.TW": [50.0 + i * 0.04 for i in range(len(dates))],
            "00632R.TW": [10.0 - i * 0.002 for i in range(len(dates))],
            "00679B.TWO": [25.0 + i * 0.001 for i in range(len(dates))],
        },
        index=dates,
    )
    monkeypatch.setattr(module, "_load_close_panel", lambda *args, **kwargs: prices)

    report = module.build_report(
        db_path=tmp_path / "stock.duckdb",
        live_signal_path=live_signal,
        rolling_tail_gate_path=rolling_gate,
        golden2_signal_path=golden2_signal,
        end="2026-09-01",
        windows=(63, 126),
        background_risk_buffer=0.10,
        sensitivity_buffers=(0.0, 0.1),
        near_threshold=0.001,
    )

    assert report["status"] == "blocked_for_live_promotion"
    assert report["summary"]["upstream_rolling_tail_gate_blocks_00631l"] is True
    assert report["summary"]["sensitivity_breach_windows_by_buffer"]["0.10"] >= 0
    assert "golden2_0830" in report["parameters"]["baseline_weights"]
    assert report["decision"]["allow_00631l_add"] is False
    assert "upstream_2606_26625_rolling_tail_gate_blocks_00631l_add" in report["blocking_reasons"]
