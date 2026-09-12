from __future__ import annotations

import pandas as pd

from scripts.evaluate.ablate_group_a_plus_adaptive_quantile_defensive_cash_floor import (
    _same_family,
    ablate,
)


def test_same_family_accepts_nearby_high_cash_defensive_variants() -> None:
    assert _same_family("cash55_risk7_tail1", "cash55_risk6_tail2")
    assert _same_family("cash55_risk7_tail1", "cash50_risk7_tail1")
    assert not _same_family("cash55_risk7_tail1", "cash45_risk5_tail99")


def test_ablate_candidate_passes_changed_holdouts() -> None:
    report = {
        "base_weights": {
            "group_a_plus_defensive": {
                "0050.TW": 0.4,
                "00631L.TW": 0.0,
                "00632R.TW": 0.0,
                "00679B.TWO": 0.3,
                "cash": 0.3,
            }
        }
    }
    frame = pd.DataFrame(
        [
            {"dt": "2025-03-03", "execution_regime": "group_a_plus_defensive", "total_risk_score": 7, "tail_risk_score": 1},
            {"dt": "2025-03-04", "execution_regime": "group_a_plus_defensive", "total_risk_score": 7, "tail_risk_score": 1},
            {"dt": "2026-07-28", "execution_regime": "group_a_plus_defensive", "total_risk_score": 7, "tail_risk_score": 1},
            {"dt": "2026-07-29", "execution_regime": "group_a_plus_defensive", "total_risk_score": 7, "tail_risk_score": 1},
        ]
    )
    close = pd.DataFrame(
        {
            "0050.TW": [100.0, 97.0, 96.0, 95.0, 94.0, 93.0],
            "00631L.TW": [100.0, 94.0, 92.0, 90.0, 88.0, 86.0],
            "00632R.TW": [10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
            "00679B.TWO": [25.0, 25.0, 25.0, 25.0, 25.0, 25.0],
        },
        index=pd.to_datetime(["2025-03-03", "2025-03-04", "2025-03-05", "2026-07-28", "2026-07-29", "2026-07-30"]),
    )

    result = ablate(
        report,
        frame,
        close,
        candidate="cash55_risk7_tail1",
        cash_floors=[0.50, 0.55],
        total_risk_mins=[6, 7],
        tail_risk_mins=[1, 2],
    )

    assert result["status"] == "ok"
    assert result["summary"]["evaluable_changed_fold_count"] >= 2
    assert result["summary"]["fail_folds"] == []
    assert result["decision"]["target_weight_change_allowed"] is False
