from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.relative_exposure_thesis import (
    append_relative_exposure_thesis_log,
    build_relative_exposure_thesis,
)


def _signal() -> dict:
    return {
        "requested_as_of_date": "2026-08-10",
        "actual_data_date": "2026-08-07",
        "business_stale_days": 0,
        "execution_allowed": True,
        "execution_regime": "golden1",
        "base_regime": "golden1",
        "signal_alignment": {"alignment": "bullish_alignment", "dominant_direction": "bullish"},
        "market_state": {"state": "bullish_low_risk", "label_zh": "低風險偏多"},
        "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.0, "00632R.TW": 0.0, "cash": 0.5},
        "latest_features": {
            "total_risk_score": 1,
            "tail_risk_score": 0,
            "ma_gap": 0.03,
            "drawdown": -0.02,
            "exit_momentum_5d": 0.04,
        },
    }


def test_relative_exposure_supports_leverage_only_in_clean_bullish_context() -> None:
    result = build_relative_exposure_thesis(_signal())

    assert result["thesis_class"] == "leverage_expansion_thesis_supported"
    assert result["decision"]["target_weight_change_allowed"] is False
    assert "low_risk_bullish_context_supports_leverage" in result["reason_codes"]


def test_relative_exposure_detects_defensive_deleverage_context() -> None:
    signal = _signal()
    signal["execution_regime"] = "group_a_plus_defensive"
    signal["latest_features"]["total_risk_score"] = 7
    signal["target_weights"] = {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3}

    result = build_relative_exposure_thesis(signal)

    assert result["thesis_class"] == "delever_to_cash_or_0050"
    assert "defensive_or_tail_risk_context" in result["reason_codes"]


def test_relative_exposure_marks_00632r_as_short_term_hedge_review_only() -> None:
    signal = _signal()
    signal["target_weights"] = {"0050.TW": 0.3, "00632R.TW": 0.27, "cash": 0.43}
    signal["execution_allowed"] = False

    result = build_relative_exposure_thesis(signal)

    assert result["thesis_class"] == "short_term_inverse_hedge_review_only"
    assert result["decision"]["allow_00632r_open"] is False
    assert "current_00632r_weight_present" in result["reason_codes"]


def test_relative_exposure_blocks_new_risk_when_signal_conflicted() -> None:
    signal = _signal()
    signal["signal_alignment"] = {"alignment": "wide_divergence", "dominant_direction": "mixed"}

    result = build_relative_exposure_thesis(signal)

    assert result["thesis_class"] == "thesis_conflicted_no_new_risk"
    assert result["blocking_evidence"] == ["signal_alignment_conflicted=wide_divergence"]


def test_relative_exposure_log_is_idempotent_by_date(tmp_path: Path) -> None:
    path = tmp_path / "relative.jsonl"
    report = build_relative_exposure_thesis(_signal())

    append_relative_exposure_thesis_log(path, report, date="2026-08-07")
    append_relative_exposure_thesis_log(path, report, date="2026-08-07")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
