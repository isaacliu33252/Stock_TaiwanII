from __future__ import annotations

import argparse

import pandas as pd

from scripts.evaluate import sweep_group_a_plus_2609_08106_latest_target_replay_params as sweep


def _args(**overrides) -> argparse.Namespace:
    values = {
        "db": "FinRL/data/stock_data.db",
        "target_weights": "report/group_a_plus/latest/latest_strategy_historical_target_weights.csv",
        "start": None,
        "end": None,
        "window": 42,
        "thresholds": "1.5,2.0",
        "shift_weights": "0.01,0.03",
        "cost_bps_values": "5,10",
        "momentum_5d_max": 0.0,
        "drawdown_max": -0.03,
        "ann_vol_min": 0.35,
        "initial_value": 1_000_000.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_parse_float_list() -> None:
    assert sweep._parse_float_list("1.5, 2.0,2.5") == [1.5, 2.0, 2.5]


def test_param_sweep_summarizes_grid_and_stays_shadow_only(monkeypatch) -> None:
    weights = pd.DataFrame(
        {"00631L.TW": [0.2, 0.2]},
        index=pd.to_datetime(["2026-09-09", "2026-09-10"]),
    )
    monkeypatch.setattr(sweep.replay, "_load_target_weights", lambda path: weights)
    monkeypatch.setattr(sweep.replay, "_load_prices", lambda db, start, end, warmup: weights)
    monkeypatch.setattr(sweep.replay.sleeve, "_score_frame", lambda prices, window: weights)
    monkeypatch.setattr(sweep.replay, "_simulate", lambda prices, weights, cost_bps: (pd.Series([0.0]), {}))

    def fake_run_one(args, *, threshold, shift_weight, cost_bps, **kwargs):
        delta = threshold + shift_weight - cost_bps / 100.0
        return {
            "threshold": threshold,
            "shift_weight": shift_weight,
            "cost_bps": cost_bps,
            "event_count": 3,
            "days_with_00631l_weight": 9,
            "delta_total_return": delta,
            "delta_annual_return": delta,
            "delta_sharpe": delta,
            "delta_max_drawdown": 0.01,
            "delta_total_turnover": shift_weight * 10,
            "positive_core_metrics": delta > 0,
        }

    monkeypatch.setattr(sweep, "_run_one", fake_run_one)

    report = sweep.build_report(_args())

    assert report["summary"]["grid_count"] == 8
    assert report["summary"]["positive_core_metric_count"] == 8
    assert report["rows"][0]["delta_sharpe"] >= report["rows"][-1]["delta_sharpe"]
    assert report["decision"]["advisory_import_allowed"] is True
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["order_generation_allowed"] is False


def test_param_sweep_markdown_states_no_live_weight_change(monkeypatch) -> None:
    weights = pd.DataFrame(
        {"00631L.TW": [0.2, 0.2]},
        index=pd.to_datetime(["2026-09-09", "2026-09-10"]),
    )
    monkeypatch.setattr(sweep.replay, "_load_target_weights", lambda path: weights)
    monkeypatch.setattr(sweep.replay, "_load_prices", lambda db, start, end, warmup: weights)
    monkeypatch.setattr(sweep.replay.sleeve, "_score_frame", lambda prices, window: weights)
    monkeypatch.setattr(sweep.replay, "_simulate", lambda prices, weights, cost_bps: (pd.Series([0.0]), {}))
    monkeypatch.setattr(
        sweep,
        "_run_one",
        lambda args, *, threshold, shift_weight, cost_bps, **kwargs: {
            "threshold": threshold,
            "shift_weight": shift_weight,
            "cost_bps": cost_bps,
            "event_count": 1,
            "days_with_00631l_weight": 2,
            "delta_total_return": 0.01,
            "delta_annual_return": 0.01,
            "delta_sharpe": 0.1,
            "delta_max_drawdown": 0.0,
            "delta_total_turnover": 0.1,
            "positive_core_metrics": True,
        },
    )

    markdown = sweep.render_markdown(sweep.build_report(_args(thresholds="2.0", shift_weights="0.03", cost_bps_values="10")))

    assert "# 2609.08106 Latest Target-Weight Replay Param Sweep" in markdown
    assert "Do not change latest GroupA++ target weights" in markdown
