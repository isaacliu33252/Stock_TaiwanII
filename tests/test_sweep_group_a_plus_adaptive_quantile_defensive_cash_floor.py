from __future__ import annotations

import pandas as pd

from scripts.evaluate.sweep_group_a_plus_adaptive_quantile_defensive_cash_floor import sweep


def test_sweep_defensive_cash_floor_finds_risk_reduction_candidate() -> None:
    report = {
        "base_weights": {
            "golden1": {"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.7},
            "group_a_plus_defensive": {
                "0050.TW": 0.4,
                "00631L.TW": 0.0,
                "00632R.TW": 0.0,
                "00679B.TWO": 0.3,
                "cash": 0.3,
            },
        }
    }
    frame = pd.DataFrame(
        [
            {"dt": "2026-01-02", "execution_regime": "group_a_plus_defensive", "total_risk_score": 7, "tail_risk_score": 1},
            {"dt": "2026-01-05", "execution_regime": "group_a_plus_defensive", "total_risk_score": 7, "tail_risk_score": 1},
        ]
    )
    close = pd.DataFrame(
        {
            "0050.TW": [100.0, 97.0, 96.0],
            "00631L.TW": [100.0, 94.0, 92.0],
            "00632R.TW": [10.0, 10.3, 10.4],
            "00679B.TWO": [25.0, 25.0, 25.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
    )

    result = sweep(
        report,
        frame,
        close,
        cash_floors=[0.45],
        total_risk_mins=[6],
        tail_risk_mins=[2],
    )

    best = result["top_variants"][0]
    assert result["status"] == "ok"
    assert best["changed_days"] == 2
    assert best["delta_worst_day_delta"] > 0
    assert result["decision"]["target_weight_change_allowed"] is False
