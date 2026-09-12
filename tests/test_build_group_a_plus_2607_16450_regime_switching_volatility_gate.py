from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_regime_switching_volatility_gate import (
    build_gate,
    write_gate,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_regime_switching_volatility_gate_blocks_when_forecast_loses_to_har(tmp_path: Path) -> None:
    quality = tmp_path / "quality.json"
    _write(
        quality,
        {
            "ticker": "0050.TW",
            "window": {"start": "2018-01-02", "end": "2026-08-24", "rows": 2100},
            "rolling_window": 504,
            "n_regimes": 2,
            "use_augmented_features": True,
            "results": {
                "5": {
                    "regime_vs_naive": {"qlike_improvement_pct": -10.0},
                    "regime_vs_har_rv": {"qlike_improvement_pct": -20.0, "win_rate_vs_benchmark": 0.40},
                },
                "10": {
                    "regime_vs_naive": {"qlike_improvement_pct": -5.0},
                    "regime_vs_har_rv": {"qlike_improvement_pct": -7.0, "win_rate_vs_benchmark": 0.45},
                },
                "20": {
                    "regime_vs_naive": {"qlike_improvement_pct": -1.0},
                    "regime_vs_har_rv": {"qlike_improvement_pct": -3.0, "win_rate_vs_benchmark": 0.49},
                },
            },
        },
    )

    gate = build_gate(forecast_quality_path=quality)

    assert gate["report_type"] == "group_a_plus_2607_16450_regime_switching_volatility_gate"
    assert gate["status"] == "blocked_for_live_promotion"
    assert gate["decision"]["target_weight_change_allowed"] is False
    assert gate["decision"]["allow_00631l_add_from_regime_gate"] is False
    assert "h5_underperforms_har_rv_on_qlike" in gate["blocking_reasons"]
    assert "h20_win_rate_below_har_threshold" in gate["blocking_reasons"]


def test_regime_switching_volatility_gate_can_pass_shadow_thresholds(tmp_path: Path) -> None:
    quality = tmp_path / "quality.json"
    _write(
        quality,
        {
            "window": {"end": "2026-08-24"},
            "results": {
                str(h): {
                    "regime_vs_naive": {"qlike_improvement_pct": 1.0},
                    "regime_vs_har_rv": {"qlike_improvement_pct": 2.0, "win_rate_vs_benchmark": 0.55},
                }
                for h in (5, 10, 20)
            },
        },
    )

    gate = build_gate(forecast_quality_path=quality)

    assert gate["status"] == "passed_shadow_forecast_gate"
    assert gate["decision"]["promote_regime_switching_volatility_gate"] is False
    assert gate["blocking_reasons"] == []


def test_write_regime_switching_volatility_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    gate = {
        "report_type": "group_a_plus_2607_16450_regime_switching_volatility_gate",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(gate, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == gate
    assert (history / "2607_16450_regime_switching_volatility_gate_20260824.json").exists()
