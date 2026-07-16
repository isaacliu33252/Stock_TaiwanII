from __future__ import annotations

from scripts.evaluate.sweep_00631l_compounding_rebalance_grid import _row


def test_row_extracts_window_deltas_and_totals() -> None:
    report = {
        "baseline_add_fraction": 0.4,
        "mean_reversion_add_fraction": 0.0,
        "trend_persistent_add_fraction": 1.0,
        "ce_filter": "none",
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
            {"label": "active_2025_2026", "delta_vs_baseline": {"final_value": 4.0}},
            {"label": "live_2024_2026", "delta_vs_baseline": {"final_value": 6.0}},
        ],
    }

    out = _row(report)

    assert out["baseline_add_fraction"] == 0.4
    assert out["accelerated_days"] == 3
    assert out["active_2025_2026_delta_final_value"] == 4.0
    assert out["live_2024_2026_delta_final_value"] == 6.0
