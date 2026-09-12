from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_500k_multi_window_oos_review import build_report


DATES = [
    "2025-01-02",
    "2025-06-30",
    "2025-07-01",
    "2025-12-31",
    "2026-01-02",
    "2026-06-30",
    "2026-07-01",
    "2026-08-04",
]


def _payload(model_name: str, timesteps: int, equity: list[float]) -> dict:
    return {
        "timesteps": timesteps,
        "group_a": {
            "model_name": model_name,
            "result": {
                "backtest_start": DATES[0],
                "backtest_end": "2026-08-14",
                "final_value": equity[-1],
                "rl_metrics": {
                    "total_return": equity[-1] / equity[0] - 1.0,
                    "annual_return": 0.1,
                    "sharpe": 1.0,
                    "max_drawdown": -0.1,
                    "volatility": 0.2,
                },
                "num_trades": 1,
                "fees_paid_estimate": 1.0,
                "pva_sigmoid_count": 0,
                "dca_total_contributions": 0.0,
                "sjm_state_history": [{"date": date} for date in DATES],
                "equity_curve": equity,
                "pva_sigmoid_history": [],
                "inverse_forced_exit_history": [],
                "inverse_hedge_config": {"forced_exit_count": 0},
            },
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_multi_window_blocks_when_zero_inverse_loses_to_100k_in_stress_windows(tmp_path: Path) -> None:
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100, 110, 111, 120, 121, 125, 124, 130, 134]))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100, 112, 113, 125, 126, 132, 130, 135, 140]))
    pz = _write(tmp_path / "zero.json", _payload("zero", 500000, [100, 111, 112, 124, 125, 130, 126, 129, 131]))

    report = build_report(path_100k=p100, path_500k=p500, path_500k_zero_inverse=pz, as_of="2026-08-15")

    assert report["status"] == "blocked_for_latest_replacement"
    assert "500k_zero_inverse_loses_to_100k_in_at_least_one_oos_window" in report["decision"]["blocking_reasons"]
    assert "500k_zero_inverse_underperforms_100k_in_2026q3_partial" in report["decision"]["blocking_reasons"]
    assert report["decision"]["replace_latest"] is False


def test_multi_window_marks_2020_and_2022_as_not_oos(tmp_path: Path) -> None:
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100, 105, 106, 108, 109, 111, 112, 113, 114]))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100, 106, 107, 110, 111, 114, 115, 116, 117]))
    pz = _write(tmp_path / "zero.json", _payload("zero", 500000, [100, 106, 107, 110, 111, 114, 115, 116, 117]))

    report = build_report(path_100k=p100, path_500k=p500, path_500k_zero_inverse=pz, as_of="2026-08-15")

    assert "2020_covid" in report["requested_windows_not_counted_as_oos"]
    assert report["requested_windows_not_counted_as_oos"]["2020_covid"]["reason"] == (
        "inside_2020_2024_training_window_for_these_checkpoints"
    )
    assert "2022_rate_hike" in report["requested_windows_not_counted_as_oos"]
