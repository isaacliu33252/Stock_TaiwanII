from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_500k_seed_sensitivity_aggregation import build_report


DATES = ["2025-01-02", "2026-07-01", "2026-08-04"]


def _payload(model_name: str, seed: int, equity: list[float], *, sharpe: float, mdd: float, vol: float) -> dict:
    return {
        "seed": seed,
        "timesteps": 500000,
        "group_a": {
            "model_name": model_name,
            "result": {
                "backtest_start": DATES[0],
                "backtest_end": "2026-08-14",
                "final_value": equity[-1],
                "rl_metrics": {
                    "total_return": equity[-1] / equity[0] - 1.0,
                    "annual_return": 0.1,
                    "sharpe": sharpe,
                    "max_drawdown": mdd,
                    "volatility": vol,
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
                "daily_target_weight_history": [
                    {
                        "decision_date": "2026-08-04",
                        "execution_date": "2026-08-14",
                        "decision_weights": {"00632R.TW": 0.0},
                        "execution_pre_trade_weights": {"00632R.TW": 0.0},
                        "base_target_weights": {"00632R.TW": 0.0},
                        "candidate_target_weights": {"00632R.TW": 0.0},
                        "final_target_weights": {"00632R.TW": 0.0},
                        "close_weights": {"00632R.TW": 0.0},
                    }
                ],
            },
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_seed_sensitivity_aggregation_blocks_unstable_stress_windows(tmp_path: Path) -> None:
    baseline = _write(tmp_path / "100k.json", _payload("100k", 42, [100.0, 110.0, 112.0, 114.0], sharpe=2.0, mdd=-0.1, vol=0.2))
    seed_a = _write(tmp_path / "s7.json", _payload("s7", 7, [100.0, 112.0, 111.0, 113.0], sharpe=1.9, mdd=-0.2, vol=0.3))
    seed_b = _write(tmp_path / "s13.json", _payload("s13", 13, [100.0, 113.0, 114.0, 116.0], sharpe=2.1, mdd=-0.09, vol=0.21))

    report = build_report(
        path_100k=baseline,
        seed_runs={"7": seed_a, "13": seed_b},
        as_of="2026-08-15",
    )

    assert report["status"] == "blocked_for_latest_replacement"
    assert "not_all_seeds_beat_100k_in_2026q3_partial" in report["decision"]["blocking_reasons"]
    assert "at_least_one_seed_sharpe_below_100k" in report["decision"]["blocking_reasons"]
    assert "at_least_one_seed_mdd_worse_than_100k" in report["decision"]["blocking_reasons"]
    assert report["summary"]["inverse_block_count"] == 0
