from __future__ import annotations

from scripts.evaluate.evaluate_2506_19200_letf_profit_harvest_shadow import (
    _candidate_pass,
    _summarize,
)


def _window(label: str, *, harvest_days: int, effective_trim_weight: float) -> dict:
    return {
        "label": label,
        "bucket": "holdout",
        "delta_vs_baseline": {
            "final_value": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "transaction_cost": 0.0,
            "turnover_value": 0.0,
        },
        "profit_harvest_info": {"profit_harvest_days": harvest_days},
        "effective_trim_weight": effective_trim_weight,
    }


def test_noop_profit_harvest_trigger_is_not_a_pass() -> None:
    item = _window("noop_holdout", harvest_days=5, effective_trim_weight=0.0)

    assert _candidate_pass(item) is False


def test_noop_profit_harvest_trigger_is_not_promotion_ready() -> None:
    summary = _summarize([_window("noop_holdout", harvest_days=5, effective_trim_weight=0.0)])

    assert summary["promotion_ready"] is False
    assert summary["holdout"]["total_profit_harvest_days"] == 5
    assert summary["holdout"]["total_effective_harvest_days"] == 0
    assert "no effective 00631L trim exposure" in summary["reason"]
