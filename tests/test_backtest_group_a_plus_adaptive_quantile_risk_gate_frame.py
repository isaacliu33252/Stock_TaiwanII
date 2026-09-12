from __future__ import annotations

import pandas as pd

from scripts.evaluate.backtest_group_a_plus_adaptive_quantile_risk_gate_frame import evaluate_frame


def test_frame_backtest_applies_regime_weights_and_shadow_limits() -> None:
    report = {
        "base_weights": {
            "golden1": {"0050.TW": 0.5, "00631L.TW": 0.2, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.3}
        }
    }
    frame = pd.DataFrame(
        [
            {
                "dt": "2026-01-02",
                "execution_regime": "golden1",
                "base_regime": "golden1",
                "total_risk_score": 7,
                "tail_risk_score": 2,
                "realized_vol_ratio_20_60": 1.5,
                "return_0050_1d": -0.01,
            }
        ]
    )
    close = pd.DataFrame(
        {
            "0050.TW": [100.0, 99.0],
            "00631L.TW": [100.0, 94.0],
            "00632R.TW": [10.0, 10.3],
            "00679B.TWO": [25.0, 25.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    result = evaluate_frame(report, frame, close)

    assert result["status"] == "ok"
    assert result["sample"]["rows"] == 1
    assert result["gate_activity"]["cap_00631l_days"] == 1
    assert result["rows"][0]["gated_00631l_weight"] == 0.0
    assert result["gated_metrics"]["worst_day"] > result["raw_metrics"]["worst_day"]
    assert result["decision"]["target_weight_change_allowed"] is False
