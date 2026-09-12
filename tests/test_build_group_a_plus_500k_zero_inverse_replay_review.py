from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_500k_zero_inverse_replay_review import build_report


def _payload(
    model_name: str,
    timesteps: int,
    equity: list[float],
    *,
    inverse_weight: float = 0.0,
    volatility: float = 0.2,
    sjm_dates: list[str] | None = None,
    end_date: str = "2026-08-14",
    daily_inverse_weight: float | None = None,
) -> dict:
    sjm_dates = sjm_dates or ["2026-07-01", "2026-08-04"]
    daily_history = []
    if daily_inverse_weight is not None:
        daily_history = [
            {
                "decision_date": sjm_dates[0],
                "execution_date": sjm_dates[1],
                "decision_weights": {"00632R.TW": daily_inverse_weight},
                "execution_pre_trade_weights": {"00632R.TW": daily_inverse_weight},
                "base_target_weights": {"00632R.TW": daily_inverse_weight},
                "candidate_target_weights": {"00632R.TW": daily_inverse_weight},
                "final_target_weights": {"00632R.TW": daily_inverse_weight},
                "close_weights": {"00632R.TW": daily_inverse_weight},
            }
        ]
    return {
        "timesteps": timesteps,
        "train_start": "2020-01-01",
        "train_end": "2024-12-31",
        "group_a": {
            "model_name": model_name,
            "result": {
                "backtest_start": sjm_dates[0],
                "backtest_end": end_date,
                "final_value": equity[-1],
                "rl_metrics": {
                    "total_return": equity[-1] / equity[0] - 1.0,
                    "annual_return": 0.1,
                    "sharpe": timesteps / 100000.0,
                    "max_drawdown": -0.1,
                    "volatility": volatility,
                },
                "num_trades": 3,
                "fees_paid_estimate": 10.0,
                "pva_sigmoid_count": 1,
                "dca_total_contributions": 0.0,
                "sjm_state_history": [{"date": value} for value in sjm_dates],
                "equity_curve": equity,
                "pva_sigmoid_history": [
                    {
                        "date": "2026-08-04",
                        "target_weights": {"00632R.TW": inverse_weight},
                    }
                ],
                "inverse_forced_exit_history": [],
                "inverse_hedge_config": {"forced_exit_count": 0},
                "daily_target_weight_history": daily_history,
            },
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_zero_inverse_replay_clears_governance_but_blocks_if_edge_not_retained(tmp_path: Path) -> None:
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100.0, 105.0, 106.0]))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100.0, 110.0, 120.0], inverse_weight=0.2))
    pz = _write(tmp_path / "zero.json", _payload("500k_zero", 500000, [100.0, 106.0, 108.0]))

    report = build_report(path_100k=p100, path_500k=p500, path_500k_zero_inverse=pz, as_of="2026-08-15")

    assert report["decision"]["zero_inverse_governance_cleared"] is True
    assert report["decision"]["still_better_than_100k"] is True
    assert report["decision"]["retains_original_500k_edge"] is False
    assert report["status"] == "blocked_for_latest_replacement"
    assert "zero_inverse_replay_does_not_retain_original_500k_edge" in report["decision"]["blocking_reasons"]
    assert report["decision"]["replace_latest"] is False


def test_zero_inverse_replay_blocks_if_issue_window_is_weaker_than_100k(tmp_path: Path) -> None:
    dates = ["2026-08-04", "2026-08-10"]
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100.0, 110.0, 112.0], sjm_dates=dates))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100.0, 120.0, 125.0], sjm_dates=dates))
    pz = _write(tmp_path / "zero.json", _payload("500k_zero", 500000, [100.0, 111.0, 111.5], sjm_dates=dates))

    report = build_report(path_100k=p100, path_500k=p500, path_500k_zero_inverse=pz, as_of="2026-08-15")

    assert report["decision"]["zero_inverse_governance_cleared"] is True
    assert "zero_inverse_replay_underperforms_100k_in_20260804_issue_window" in report["decision"]["blocking_reasons"]
    assert report["decision"]["promote_500k_zero_inverse_to_production"] is False


def test_zero_inverse_replay_uses_complete_daily_exposure_log(tmp_path: Path) -> None:
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100.0, 105.0, 106.0]))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100.0, 110.0, 120.0], inverse_weight=0.2))
    pz = _write(
        tmp_path / "zero.json",
        _payload("500k_zero", 500000, [100.0, 108.0, 109.0], daily_inverse_weight=0.0),
    )

    report = build_report(path_100k=p100, path_500k=p500, path_500k_zero_inverse=pz, as_of="2026-08-15")
    inverse = report["inverse_etf_governance"]["500k_zero_inverse"]

    assert inverse["complete_daily_exposure_log_available"] is True
    assert inverse["daily_log_rows"] == 1
    assert inverse["daily_log_max_00632r_weight"] == 0.0
    assert "complete_daily_target_weight_log_missing" not in report["decision"]["warning_reasons"]
