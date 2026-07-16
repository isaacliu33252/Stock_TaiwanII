from __future__ import annotations

from scripts.evaluate.sweep_00631l_compounding_trend_thresholds import _row


def test_row_extracts_thresholds_regime_counts_and_window_deltas() -> None:
    report = {
        "baseline_add_fraction": 0.4,
        "mean_reversion_add_fraction": 0.0,
        "trend_persistent_add_fraction": 1.0,
        "thresholds": {
            "trend_score_min": 4,
            "ar1_trend_min": 0.05,
            "trend_persistence_min": 0.60,
            "reversal_speed_trend_max": 0.45,
        },
        "totals": {
            "blocked_days": 2,
            "accelerated_days": 3,
            "event_days": 5,
            "delta_final_value_sum": 10.0,
            "delta_sharpe_sum": 0.1,
            "delta_max_drawdown_sum": 0.2,
            "positive_final_value_windows": 1,
        },
        "windows": [
            {
                "label": "active_2025_2026",
                "regime_counts": {"TREND_PERSISTENT": 4, "MEAN_REVERTING": 1},
                "delta_vs_baseline": {"final_value": 4.0},
            },
            {
                "label": "live_2024_2026",
                "regime_counts": {"TREND_PERSISTENT": 6, "MEAN_REVERTING": 2},
                "delta_vs_baseline": {"final_value": 6.0},
            },
        ],
    }

    out = _row(report)

    assert out["trend_score_min"] == 4
    assert out["ar1_trend_min"] == 0.05
    assert out["trend_persistent_days"] == 10
    assert out["mean_reverting_days"] == 3
    assert out["active_2025_2026_delta_final_value"] == 4.0
    assert out["live_2024_2026_delta_final_value"] == 6.0
