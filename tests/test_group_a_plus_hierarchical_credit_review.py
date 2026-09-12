from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.hierarchical_credit_review import (
    append_hierarchical_credit_review_log,
    build_hierarchical_credit_review,
)


def _signal(
    *,
    requested: str = "2026-08-07",
    actual: str = "2026-08-06",
    stale: int = 0,
    allowed: bool = True,
    weights: dict[str, float] | None = None,
    prices: dict[str, float] | None = None,
    alignment: str = "bullish_alignment",
    direction: str = "bullish",
    total_risk: int = 2,
    tail_risk: int = 0,
) -> dict:
    return {
        "success": True,
        "data": {
            "requested_as_of_date": requested,
            "actual_data_date": actual,
            "business_stale_days": stale,
            "execution_allowed": allowed,
            "execution_regime": "golden1",
            "target_weights": weights or {"0050.TW": 0.5, "00631L.TW": 0.2, "00632R.TW": 0.0, "cash": 0.3},
            "latest_prices": prices or {"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0},
            "signal_alignment": {"alignment": alignment, "dominant_direction": direction},
            "latest_features": {"total_risk_score": total_risk, "tail_risk_score": tail_risk},
        },
    }


def test_credit_review_prioritizes_data_and_execution_when_guard_blocks() -> None:
    forecast = _signal(stale=2, allowed=True, prices={"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0})
    actual = _signal(stale=2, allowed=False, prices={"0050.TW": 99.8, "00631L.TW": 29.9, "00632R.TW": 10.01})

    report = build_hierarchical_credit_review(forecast, actual, as_of="2026-08-07")

    assert report["primary_attribution"] == "data_freshness_error"
    assert "execution_error" in report["secondary_attributions"]
    assert "stale_data_forecast=2_actual=2" in report["evidence"]
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False


def test_credit_review_flags_bullish_selection_error_on_negative_0050_move() -> None:
    forecast = _signal(
        weights={"0050.TW": 0.5, "00631L.TW": 0.2, "00632R.TW": 0.0, "cash": 0.3},
        prices={"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0},
    )
    actual = _signal(prices={"0050.TW": 98.5, "00631L.TW": 29.0, "00632R.TW": 10.15})

    report = build_hierarchical_credit_review(forecast, actual)

    assert report["forecast"]["posture"] == "leveraged_bullish"
    assert report["primary_attribution"] == "selection_error"
    assert "bullish_posture_met_negative_0050_return" in report["evidence"]


def test_credit_review_treats_small_move_as_market_noise() -> None:
    forecast = _signal(
        weights={"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.27, "cash": 0.43},
        prices={"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0},
    )
    actual = _signal(prices={"0050.TW": 100.2, "00631L.TW": 30.1, "00632R.TW": 9.99})

    report = build_hierarchical_credit_review(forecast, actual)

    assert report["primary_attribution"] == "market_noise"
    assert "0050_move_small" in report["evidence"]


def test_hierarchical_credit_review_log_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "credit.jsonl"
    report = build_hierarchical_credit_review(_signal(), _signal(), as_of="2026-08-07")

    append_hierarchical_credit_review_log(log, report, date="2026-08-07")
    append_hierarchical_credit_review_log(log, report | {"confidence": 0.9}, date="2026-08-07")

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["confidence"] == 0.9
