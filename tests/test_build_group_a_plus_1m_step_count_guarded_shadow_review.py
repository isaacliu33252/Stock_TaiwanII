from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_1m_step_count_guarded_shadow_review import build_report


def _payload(
    model_name: str,
    timesteps: int,
    equity: list[float],
    *,
    inverse_weight: float = 0.0,
    sjm_dates: list[str] | None = None,
    end_date: str = "2026-08-14",
) -> dict:
    sjm_dates = sjm_dates or ["2026-07-01", "2026-08-04"]
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
                    "volatility": 0.2,
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
            },
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_1m_step_count_review_blocks_inverse_exposure(tmp_path: Path) -> None:
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100.0, 105.0, 106.0]))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100.0, 106.0, 108.0]))
    p1m = _write(tmp_path / "1m.json", _payload("1m", 1000000, [100.0, 110.0, 115.0], inverse_weight=0.2))

    report = build_report(path_100k=p100, path_500k=p500, path_1m=p1m, as_of="2026-08-15")

    assert report["decision"]["one_m_training_steps_helpful"] is True
    assert report["status"] == "blocked_for_latest_replacement"
    assert "1m_saved_logs_include_00632r_exposure" in report["decision"]["blocking_reasons"]
    assert report["inverse_etf_governance"]["1m"]["pva_logged_max_target_weight"] == 0.2
    assert report["overfit_risk"]["signals"]["saved_logs_include_00632r_exposure"] is True


def test_1m_step_count_review_keeps_shadow_when_q3_is_weaker(tmp_path: Path) -> None:
    dates = ["2026-06-30", "2026-07-01"]
    p100 = _write(tmp_path / "100k.json", _payload("100k", 100000, [100.0, 110.0, 109.0], sjm_dates=dates))
    p500 = _write(tmp_path / "500k.json", _payload("500k", 500000, [100.0, 124.0, 121.0], sjm_dates=dates))
    p1m = _write(tmp_path / "1m.json", _payload("1m", 1000000, [100.0, 125.0, 120.0], sjm_dates=dates))

    report = build_report(path_100k=p100, path_500k=p500, path_1m=p1m, as_of="2026-08-15")

    assert report["decision"]["one_m_training_steps_helpful"] is True
    assert "1m_underperforms_100k_in_2026q3_downturn_proxy" in report["decision"]["blocking_reasons"]
    assert report["overfit_risk"]["label"] in {"moderate_overfit_risk", "high_overfit_risk"}
    assert report["overfit_risk"]["signals"]["q3_2026_weaker_than_100k"] is True
    assert report["decision"]["replace_latest"] is False
