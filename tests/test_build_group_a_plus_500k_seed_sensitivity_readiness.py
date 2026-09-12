from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_500k_seed_sensitivity_readiness import build_report


def _payload(model_name: str, timesteps: int, final_value: float, *, sharpe: float, vol: float) -> dict:
    return {
        "timesteps": timesteps,
        "group_a": {
            "model_name": model_name,
            "result": {
                "backtest_start": "2025-01-02",
                "backtest_end": "2026-08-14",
                "final_value": final_value,
                "rl_metrics": {
                    "total_return": final_value / 100.0 - 1.0,
                    "annual_return": 0.1,
                    "sharpe": sharpe,
                    "max_drawdown": -0.1,
                    "volatility": vol,
                },
                "num_trades": 1,
                "fees_paid_estimate": 1.0,
                "pva_sigmoid_count": 0,
                "dca_total_contributions": 0.0,
                "sjm_state_history": [{"date": "2025-01-02"}],
                "equity_curve": [100.0, final_value],
                "pva_sigmoid_history": [],
                "inverse_forced_exit_history": [],
                "inverse_hedge_config": {"forced_exit_count": 0},
            },
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_seed_sensitivity_blocks_when_required_seeds_are_missing(tmp_path: Path) -> None:
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, 120.0, sharpe=1.0, vol=0.2))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, 130.0, sharpe=1.2, vol=0.22))
    pz = _write(tmp_path / "zero.json", _payload("zero", 500000, 128.0, sharpe=1.1, vol=0.25))

    report = build_report(
        path_100k=p100,
        path_500k=p500,
        path_500k_zero_inverse=pz,
        required_seeds=[7, 13],
        as_of="2026-08-15",
    )

    assert report["status"] == "blocked_for_seed_sensitivity"
    assert report["missing_required_seeds"] == [7, 13]
    assert "missing_required_independent_500k_zero_inverse_seed_runs" in report["decision"]["blocking_reasons"]
    assert report["decision"]["replace_latest"] is False
    assert "--seed 7" in report["seed_inventory"]["7"]["train_command"]
