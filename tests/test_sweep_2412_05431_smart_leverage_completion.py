from __future__ import annotations

from scripts.evaluate.sweep_2412_05431_smart_leverage_completion import _summarize_variant


def _window(label: str, bucket: str, *, final_delta: float, sharpe_delta: float, mdd_delta: float) -> dict:
    return {
        "label": label,
        "bucket": bucket,
        "delta_vs_benchmark": {
            "final_value": final_delta,
            "sharpe_ratio": sharpe_delta,
            "max_drawdown": mdd_delta,
        },
        "delta_vs_latest_a2118": {
            "final_value": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        },
        "target_weight_average": {"00631L.TW": 0.05},
    }


def test_completion_summary_requires_incident_passes() -> None:
    report = {
        "params": {"example": True},
        "windows": [
            _window("holdout_ok", "standard_holdout", final_delta=1.0, sharpe_delta=0.1, mdd_delta=0.0),
            _window("incident_bad", "incident", final_delta=-1.0, sharpe_delta=0.1, mdd_delta=0.0),
        ],
    }

    summary = _summarize_variant("test_variant", report)

    assert summary["standard_holdout_pass_windows"] == 1
    assert summary["incident_pass_windows"] == 0
    assert summary["promotion_ready"] is False
    assert summary["blocker_counts"]["benchmark_final_value"] == 1
