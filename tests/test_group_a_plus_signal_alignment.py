#!/usr/bin/env python3
"""Tests for GroupA+ multi-source signal alignment."""

from __future__ import annotations

from group_a_plus.integrations.signal_alignment import build_signal_alignment, _tbrain_source, _weekly_ma_source


def _live_signal() -> dict:
    return {
        "strategy_id": "a2118",
        "actual_data_date": "2026-06-29",
        "execution_regime": "ncf_late_bull_hedge",
        "latest_features": {
            "total_risk_score": 9,
            "chip_score": 7,
            "derivative_score": 2,
        },
        "finbert_sentiment": {
            "status": "ok",
            "risk_score": 0.60,
        },
        "ncf_live_overlay": {
            "ncf_00631l": {"calibrated_prob_up": 0.38, "confidence": 0.66, "direction": "DOWN"},
            "ncf_00632r": {"calibrated_prob_up": 0.68, "confidence": 0.49, "direction": "UP"},
            "cross_ticker_consistency": {"market_probability_up": 0.31, "agreement_score": 0.87},
        },
        "factor_lens_gate": {
            "all_key_factors_pass": True,
            "factors": {
                "ncf_00631l_prob_up": {"passed": True, "ic_20d_warning": False},
                "ncf_cross_ticker_market_up": {"passed": True, "ic_20d_warning": False},
            },
        },
    }


def test_signal_alignment_detects_current_bearish_alignment() -> None:
    result = build_signal_alignment(_live_signal())

    assert result["dominant_direction"] == "bearish"
    assert result["direction_counts"]["bearish"] >= 5
    assert result["alignment"] in {"bearish_alignment", "mixed"}
    # M7 (2026-07-02 Fable 5 audit): execution_regime="ncf_late_bull_hedge"
    # is excluded from the vote (it's derived from the ncf_00631l source
    # already counted separately) -- 7 sources total minus that one = 6
    # available. See test_execution_regime_excluded_when_ncf_hedge_active
    # below for the dedicated regression test.
    assert result["available_sources"] == 6


def test_execution_regime_excluded_when_ncf_hedge_active() -> None:
    """M7: execution_regime must not double-count the NCF signal that
    already drives ncf_00631l/ncf_00632r_inverse/ncf_cross_ticker when the
    regime itself is NCF-derived (ncf_late_bull_hedge[_soft])."""
    signal = _live_signal()
    result = build_signal_alignment(signal)
    regime_source = next(s for s in result["sources"] if s["name"] == "execution_regime")
    assert regime_source["available"] is False

    signal["execution_regime"] = "ncf_late_bull_hedge_soft"
    result = build_signal_alignment(signal)
    regime_source = next(s for s in result["sources"] if s["name"] == "execution_regime")
    assert regime_source["available"] is False


def test_execution_regime_still_votes_for_technical_defensive_regime() -> None:
    """group_a_plus_defensive is MA/price-derived, not NCF-derived -- it
    must remain an independent vote, unlike the NCF-derived hedge regimes."""
    signal = _live_signal()
    signal["execution_regime"] = "group_a_plus_defensive"

    result = build_signal_alignment(signal)

    regime_source = next(s for s in result["sources"] if s["name"] == "execution_regime")
    assert regime_source["available"] is True
    assert regime_source["direction"] == "bearish"


def test_signal_alignment_marks_wide_divergence_when_factor_lens_opposes_ncf() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 1
    signal["finbert_sentiment"]["risk_score"] = 0.20
    signal["execution_regime"] = "golden1"

    result = build_signal_alignment(signal)

    assert result["direction_counts"]["bullish"] >= 3
    assert result["direction_counts"]["bearish"] >= 3
    assert result["alignment"] == "wide_divergence"
    assert result["confidence_penalty"] >= 0.25


def test_signal_alignment_handles_missing_optional_sources() -> None:
    signal = {
        "strategy_id": "x",
        "actual_data_date": "2026-06-29",
        "execution_regime": "golden1",
        "latest_features": {},
        "ncf_live_overlay": {},
    }

    result = build_signal_alignment(signal)

    assert result["available_sources"] >= 1
    assert result["confidence_penalty"] >= 0.10


def test_tbrain_source_uses_quantile_band_when_j_below_fixed_cutoff_but_within_band() -> None:
    # J=0.32 is above the fixed 0.30 cutoff, but at/under the ticker's own
    # expanding low quantile (0.35) -> the adaptive band should still flag bearish.
    signal = {
        "tbrain_shadow": {
            "status": "available",
            "features": {
                "tbrain_kdj_k_9_3_3": 0.40,
                "tbrain_kdj_d_9_3_3": 0.50,
                "tbrain_kdj_j_9_3_3": 0.32,
                "tbrain_kdj_j_9_3_3_q_low": 0.35,
                "tbrain_kdj_j_9_3_3_q_high": 0.80,
                "tbrain_kdj_k_5_21_11": 0.40,
                "tbrain_kdj_d_5_21_11": 0.55,
            },
        }
    }

    result = _tbrain_source(signal)

    assert result["direction"] == "bearish"
    assert "J_q_low" in result["reason"]


def test_tbrain_source_falls_back_to_fixed_cutoffs_without_quantile_band() -> None:
    signal = {
        "tbrain_shadow": {
            "status": "available",
            "features": {
                "tbrain_kdj_k_9_3_3": 0.45,
                "tbrain_kdj_d_9_3_3": 0.50,
                "tbrain_kdj_j_9_3_3": 0.40,
                "tbrain_kdj_k_5_21_11": 0.45,
                "tbrain_kdj_d_5_21_11": 0.50,
            },
        }
    }

    result = _tbrain_source(signal)

    assert result["direction"] == "neutral"
    assert "J_q_low" not in result["reason"]


def test_weekly_ma_source_reports_bullish_when_bull_aligned() -> None:
    signal = {
        "tbrain_shadow": {
            "weekly_ma": {
                "status": "available",
                "bull_aligned": True,
                "bear_aligned": False,
                "ma_short": 110.0,
                "ma_mid": 105.0,
                "ma_long": 100.0,
            }
        }
    }

    result = _weekly_ma_source(signal)

    assert result["available"] is True
    assert result["direction"] == "bullish"
    assert result["strength"] > 0.0


def test_weekly_ma_source_unavailable_without_shadow() -> None:
    result = _weekly_ma_source({})

    assert result["available"] is False
    assert result["direction"] == "neutral"
