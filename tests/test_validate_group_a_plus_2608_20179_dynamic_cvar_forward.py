from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.evaluate import validate_group_a_plus_2608_20179_dynamic_cvar_forward as module


def test_future_path_metrics_return_and_drawdown() -> None:
    metrics = module._future_path_metrics(pd.Series([0.10, -0.20, 0.05]), horizon=3)

    assert metrics["return"] == pytest.approx((1.10 * 0.80 * 1.05) - 1.0)
    assert metrics["max_drawdown"] == pytest.approx(-0.20)
    assert metrics["worst_daily_return"] == pytest.approx(-0.20)


def test_summarize_events_calculates_breach_group_means() -> None:
    summary = module._summarize_events(
        [
            {
                "underperforms_0050": True,
                "future_relative_return": -0.03,
                "future_00631l_return": -0.05,
                "future_00631l_mdd": -0.08,
                "latest_minus_no_00631l_future_return": -0.01,
                "latest_minus_no_letf_future_return": -0.02,
            },
            {
                "underperforms_0050": False,
                "future_relative_return": 0.01,
                "future_00631l_return": 0.02,
                "future_00631l_mdd": -0.01,
                "latest_minus_no_00631l_future_return": 0.01,
                "latest_minus_no_letf_future_return": 0.02,
            },
        ]
    )

    assert summary["event_count"] == 2
    assert summary["underperform_rate"] == pytest.approx(0.5)
    assert summary["mean_future_relative_return"] == pytest.approx(-0.01)


def test_build_report_outputs_forward_validation_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_signal = tmp_path / "live_signal.json"
    golden2 = tmp_path / "golden2.json"
    payload = {
        "actual_data_date": "2026-09-01",
        "target_weights": {
            "0050.TW": 0.47,
            "00631L.TW": 0.10,
            "00632R.TW": 0.16,
            "cash": 0.27,
        },
    }
    live_signal.write_text(json.dumps(payload), encoding="utf-8")
    golden2.write_text(json.dumps(payload), encoding="utf-8")
    dates = pd.date_range("2025-01-01", periods=180, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0 * (1.0005**i) for i in range(len(dates))],
            "00631L.TW": [50.0 * (1.0010**i) for i in range(len(dates))],
            "00632R.TW": [10.0 * (0.9995**i) for i in range(len(dates))],
            "00679B.TWO": [25.0 * (1.0001**i) for i in range(len(dates))],
        },
        index=dates,
    )
    monkeypatch.setattr(module, "_load_close_panel", lambda *args, **kwargs: prices)

    report = module.build_report(
        db_path=tmp_path / "stock.duckdb",
        live_signal_path=live_signal,
        golden2_signal_path=golden2,
        start="2025-01-01",
        end="2025-09-01",
        windows=(20, 40),
        horizons=(5, 10),
        background_risk_buffer=0.10,
        max_events=3,
    )

    assert report["report_type"] == "group_a_plus_2608_20179_dynamic_cvar_forward_validation"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["summary"]["valid_windows"] == 2
    assert set(report["validations"]) == {"20", "40"}


def test_write_markdown_renders_forward_validation_table(tmp_path: Path) -> None:
    output = tmp_path / "forward.md"
    report = {
        "status": "blocked_for_live_promotion",
        "as_of": "2026-09-01",
        "policy": "research_only_dynamic_cvar_forward_validation_no_weight_change",
        "summary": {"forward_validation_passed": False, "forward_validation_pass_windows": 0, "valid_windows": 1},
        "validations": {
            "63": {
                "horizons": {
                    "5": {
                        "breach": {"event_count": 10},
                        "non_breach": {"event_count": 10},
                        "breach_minus_non_breach": {
                            "underperform_rate": 0.1,
                            "mean_latest_minus_no_00631l_future_return": -0.01,
                        },
                        "forward_validation_passed": False,
                    }
                }
            }
        },
    }

    module.write_markdown(report, output)

    text = output.read_text(encoding="utf-8")
    assert "2608.20179 Dynamic CVaR Forward Validation" in text
    assert "Shadow validation only" in text
