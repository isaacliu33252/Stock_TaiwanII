from __future__ import annotations

from group_a_plus.integrations.signal_alignment_shadow_variant import (
    _compounding_regime_source,
    _crash_risk_alert_source,
    _trough_nowcast_source,
    build_signal_alignment_shadow_variant,
)


def _live_signal() -> dict:
    return {
        "strategy_id": "a2118",
        "actual_data_date": "2026-06-29",
        "execution_regime": "golden1",
        "latest_features": {"total_risk_score": 2, "chip_score": 1, "derivative_score": 0},
        "finbert_sentiment": {"status": "ok", "risk_score": 0.20},
        "ncf_live_overlay": {
            "ncf_00631l": {"calibrated_prob_up": 0.60, "confidence": 0.66, "direction": "UP"},
            "ncf_00632r": {"calibrated_prob_up": 0.40, "confidence": 0.49, "direction": "DOWN"},
            "cross_ticker_consistency": {"market_probability_up": 0.58, "agreement_score": 0.80},
        },
        "trough_nowcast": {"state": "NO_TROUGH"},
    }


def test_trough_nowcast_source_no_trough_is_unavailable() -> None:
    source = _trough_nowcast_source({"state": "NO_TROUGH"})

    assert source["available"] is False
    assert source["direction"] == "neutral"


def test_trough_nowcast_source_partial_reentry_is_bullish() -> None:
    source = _trough_nowcast_source({"state": "PARTIAL_REENTRY", "reentry_confirmation_score": 5})

    assert source["available"] is True
    assert source["direction"] == "bullish"
    assert source["strength"] == 0.8


def test_trough_nowcast_source_capitulation_warning_is_bearish() -> None:
    source = _trough_nowcast_source({"state": "CAPITULATION_WARNING", "capitulation_score": 4})

    assert source["direction"] == "bearish"
    assert source["strength"] == 0.7


def test_trough_nowcast_source_defaults_to_unavailable_when_missing() -> None:
    source = _trough_nowcast_source(None)

    assert source["available"] is False


def test_compounding_regime_source_trend_persistent_is_bullish() -> None:
    source = _compounding_regime_source({"compounding_regime": "TREND_PERSISTENT", "trend_score": 4})

    assert source["direction"] == "bullish"
    assert source["strength"] == 0.7


def test_compounding_regime_source_mean_reverting_is_bearish() -> None:
    source = _compounding_regime_source({"compounding_regime": "MEAN_REVERTING", "mean_reversion_score": 5})

    assert source["direction"] == "bearish"
    assert source["strength"] == 0.8


def test_compounding_regime_source_transitional_is_neutral() -> None:
    source = _compounding_regime_source({"compounding_regime": "TRANSITIONAL"})

    assert source["direction"] == "neutral"
    assert source["available"] is True


def test_compounding_regime_source_unavailable_when_missing_regime() -> None:
    source = _compounding_regime_source({})

    assert source["available"] is False


def test_crash_risk_alert_source_scales_strength_with_category_score() -> None:
    source = _crash_risk_alert_source({"status": "available", "category_score": 3, "watch_level": "high"})

    assert source["direction"] == "bearish"
    assert source["strength"] == 1.0


def test_crash_risk_alert_source_zero_score_is_neutral_but_available() -> None:
    source = _crash_risk_alert_source({"status": "available", "category_score": 0})

    assert source["direction"] == "neutral"
    assert source["available"] is True


def test_crash_risk_alert_source_unavailable_when_status_not_available() -> None:
    source = _crash_risk_alert_source({"status": "unavailable"})

    assert source["available"] is False


def test_build_signal_alignment_shadow_variant_includes_all_three_new_sources() -> None:
    result = build_signal_alignment_shadow_variant(
        _live_signal(),
        compounding_regime_latest={"compounding_regime": "TREND_PERSISTENT", "trend_score": 3},
        crash_risk_alert={"status": "available", "category_score": 2, "watch_level": "medium"},
    )

    names = {source["name"] for source in result["sources"]}
    assert {"trough_nowcast", "compounding_regime", "crash_risk_alert"} <= names
    assert result["variant"] == "shadow_plus_trough_compounding_crash_alert"
    assert result["research_only"] is True
    assert result["production_effect"] == "none"


def test_build_signal_alignment_shadow_variant_reads_trough_nowcast_from_live_signal_by_default() -> None:
    live_signal = _live_signal()
    live_signal["trough_nowcast"] = {"state": "PARTIAL_REENTRY", "reentry_confirmation_score": 4}

    result = build_signal_alignment_shadow_variant(live_signal)

    trough_source = next(s for s in result["sources"] if s["name"] == "trough_nowcast")
    assert trough_source["direction"] == "bullish"
    assert trough_source["available"] is True
