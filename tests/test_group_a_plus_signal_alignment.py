#!/usr/bin/env python3
"""Tests for GroupA+ multi-source signal alignment."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from group_a_plus.integrations.signal_alignment import (
    append_signal_alignment_shadow_log,
    build_signal_alignment,
    build_signal_alignment_from_file,
    _aligned_confidence,
    _ncf_sources,
    _tbrain_source,
    _weekly_ma_source,
)


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


def test_signal_alignment_from_file_writes_canonical_envelope(tmp_path: Path) -> None:
    live_signal_path = tmp_path / "live_signal.json"
    legacy_output = tmp_path / "report/group_a_plus/latest/signal_alignment.json"
    canonical_output = tmp_path / "outputs/group_a_plus/latest/signal_alignment.json"
    live_signal_path.write_text(json.dumps(_live_signal(), ensure_ascii=False), encoding="utf-8")

    result = build_signal_alignment_from_file(
        live_signal_path,
        output_path=legacy_output,
        canonical_path=canonical_output,
    )

    legacy = json.loads(legacy_output.read_text(encoding="utf-8"))
    canonical = json.loads(canonical_output.read_text(encoding="utf-8"))
    assert legacy == result
    assert canonical["artifact_name"] == "signal_alignment"
    assert canonical["artifact_kind"] == "signal"
    assert canonical["run_mode"] == "production"
    assert canonical["payload"] == result


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


def test_lm_dictionary_source_marked_structural_limitation_and_excluded_from_total() -> None:
    """2026-07-07 Fable audit: lm_dictionary_sentiment English-tokenizes
    Chinese-language watchlist_news.json and is structurally never "ok" --
    it must still appear in `sources` (diagnostic visibility) but not count
    toward `total_sources`, so a permanently-unusable source doesn't read as
    a daily degradation."""
    signal = _live_signal()
    signal["lm_dictionary_sentiment"] = {
        "status": "no_dictionary_hits",
        "risk_score": 0.0,
        "positive_count": 0,
        "negative_count": 0,
        "dictionary_hit_count": 0,
    }

    result = build_signal_alignment(signal)

    lm_source = next(item for item in result["sources"] if item["name"] == "lm_dictionary_sentiment")
    assert lm_source["available"] is False
    assert lm_source["structural_limitation"] == "english_only_dictionary_vs_chinese_news_source"
    assert result["total_sources"] == len(result["sources"]) - 1


def test_aligned_confidence_prefers_panel_aligned_over_composite() -> None:
    assert _aligned_confidence({"confidence": 0.90, "confidence_panel_aligned": 0.12}) == 0.12


def test_aligned_confidence_falls_back_to_composite_when_panel_aligned_absent() -> None:
    assert _aligned_confidence({"confidence": 0.66}) == 0.66
    assert _aligned_confidence({"confidence": 0.66, "confidence_panel_aligned": None}) == 0.66


def test_aligned_confidence_defaults_to_zero_when_both_absent() -> None:
    assert _aligned_confidence({}) == 0.0


def test_ncf_sources_strength_uses_panel_aligned_confidence_not_composite() -> None:
    # H2 (2026-07-09): confidence=0.95 is the volatile composite metric (would
    # dominate the max() and mask any drift); confidence_panel_aligned=0.05 is
    # the walk-forward-consistent value that should actually be used. prob_up
    # near 0.5 keeps _strength_from_prob_up negligible so the confidence term
    # dominates the max(), making this observable.
    overlay = {
        "ncf_00631l": {
            "calibrated_prob_up": 0.51,
            "confidence": 0.95,
            "confidence_panel_aligned": 0.05,
            "direction": "UP",
            "votes_up": 2,
        },
        "ncf_00632r": {
            "calibrated_prob_up": 0.49,
            "confidence": 0.95,
            "confidence_panel_aligned": 0.05,
            "direction": "DOWN",
            "votes_up": 1,
        },
    }
    sources = _ncf_sources({"ncf_live_overlay": overlay})
    by_name = {item["name"]: item for item in sources}

    assert by_name["ncf_00631l"]["strength"] < 0.10
    assert by_name["ncf_00632r_inverse"]["strength"] < 0.10


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


def test_extra_sources_defaults_to_none_with_zero_behavior_change() -> None:
    signal = _live_signal()

    with_default = build_signal_alignment(signal)
    with_explicit_none = build_signal_alignment(signal, extra_sources=None)

    assert with_default == with_explicit_none


def test_extra_sources_are_appended_and_affect_weighted_share() -> None:
    from group_a_plus.integrations.signal_alignment import _source

    signal = _live_signal()
    baseline = build_signal_alignment(signal)
    extra = [_source("shadow_extra", "bullish", 1.0, "test extra source")]

    with_extra = build_signal_alignment(signal, extra_sources=extra)

    assert with_extra["available_sources"] == baseline["available_sources"] + 1
    assert any(source["name"] == "shadow_extra" for source in with_extra["sources"])
    assert with_extra["weighted_share"]["bullish"] > baseline["weighted_share"]["bullish"]


def test_signal_alignment_adds_tsmc_weakness_source_when_available() -> None:
    signal = _live_signal()
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "tsmc_weak_confirmed",
        "ncf_2330_h20_prob_up": 0.42,
        "ncf_2330_prob_fwd_mdd_gt5_h20": 0.55,
        "returns": {
            "2330.TW": {"5d": -0.03},
            "0050_ex_tsmc_proxy": {"5d": -0.01},
        },
    }

    result = build_signal_alignment(signal)

    source = next(s for s in result["sources"] if s["name"] == "ncf_2330_tsmc")
    assert source["available"] is True
    assert source["direction"] == "bearish"


def test_signal_alignment_treats_tsmc_led_narrow_as_neutral() -> None:
    signal = _live_signal()
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "tsmc_led_narrow",
        "ncf_2330_h20_prob_up": 0.77,
        "returns": {
            "2330.TW": {"5d": 0.03},
            "0050_ex_tsmc_proxy": {"5d": -0.005},
        },
    }

    result = build_signal_alignment(signal)

    source = next(s for s in result["sources"] if s["name"] == "ncf_2330_tsmc")
    assert source["available"] is True
    assert source["direction"] == "neutral"


def test_leverage_suitability_tier_0_when_tsmc_weak_confirmed() -> None:
    signal = _live_signal()
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "tsmc_weak_confirmed",
        "reference_guidance": {"reference_action": "manual_review"},
        "ncf_2330_h20_prob_up": 0.42,
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert suitability["tier"] == 0
    assert suitability["label_zh"] == "不利 00631L"
    assert suitability["policy"] == "advisory_only_no_weight_change"


def test_leverage_suitability_tier_1_when_tsmc_led_narrow() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 3
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "tsmc_led_narrow",
        "reference_guidance": {"reference_action": "avoid_add_00631l"},
        "ncf_2330_h20_prob_up": 0.77,
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert suitability["tier"] == 1
    assert suitability["label_zh"] == "只適合 0050"


def test_leverage_suitability_tier_1_when_tsmc_false_breakout() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 2
    signal["ncf_live_overlay"]["ncf_00631l"] = {"calibrated_prob_up": 0.55, "confidence": 0.40, "direction": "UP"}
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "tsmc_false_breakout",
        "reference_guidance": {"reference_action": "avoid_add_00631l"},
        "ncf_2330_h20_prob_up": 0.62,
        "ncf_2330_market_state": {"state": 3, "label_zh": "假突破"},
    }

    result = build_signal_alignment(signal)

    source = next(s for s in result["sources"] if s["name"] == "ncf_2330_tsmc")
    suitability = result["leverage_suitability"]
    assert source["available"] is True
    assert source["direction"] == "neutral"
    assert suitability["tier"] == 1
    assert suitability["inputs"]["ncf_2330_market_state"]["state"] == 3


def test_leverage_suitability_severe_tsmc_tail_can_veto_when_00631l_weak() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 2
    signal["execution_regime"] = "golden1"
    signal["ncf_live_overlay"]["ncf_00631l"] = {
        "calibrated_prob_up": 0.49,
        "confidence": 0.50,
        "direction": "DOWN",
    }
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "mixed",
        "reference_guidance": {"reference_action": "diagnostic_only"},
        "ncf_2330_h20_prob_up": 0.54,
        "ncf_2330_prob_fwd_mdd_gt5_h20": 0.30,
        "ncf_2330_prob_fwd_mdd_gt8_h20": 0.18,
        "ncf_2330_market_state": {"state": 2, "label_zh": "高檔震盪"},
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert suitability["tier"] == 0
    assert suitability["inputs"]["ncf_2330_prob_fwd_mdd_gt8_h20"] == 0.18


def test_leverage_suitability_tier_2_for_mixed_risk_on_context() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 2
    signal["execution_regime"] = "golden1"
    signal["ncf_live_overlay"]["ncf_00631l"] = {"calibrated_prob_up": 0.52, "confidence": 0.20, "direction": "UP"}
    signal["ncf_live_overlay"]["ncf_00632r"] = {"calibrated_prob_up": 0.49, "confidence": 0.20, "direction": "DOWN"}
    signal["ncf_live_overlay"]["cross_ticker_consistency"] = {"market_probability_up": 0.52, "agreement_score": 0.20}
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "mixed",
        "reference_guidance": {"reference_action": "diagnostic_only"},
        "ncf_2330_h20_prob_up": 0.51,
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert suitability["tier"] == 2
    assert suitability["label_zh"] == "可持有 0050 + 小 00631L"


def test_leverage_suitability_tier_2_factor_quality_shadow_momentum_candidate() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 2
    signal["execution_regime"] = "golden1"
    signal["ncf_live_overlay"]["ncf_00631l"] = {"calibrated_prob_up": 0.52, "confidence": 0.20, "direction": "UP"}
    signal["ncf_live_overlay"]["ncf_00632r"] = {"calibrated_prob_up": 0.49, "confidence": 0.20, "direction": "DOWN"}
    signal["ncf_live_overlay"]["cross_ticker_consistency"] = {"market_probability_up": 0.52, "agreement_score": 0.20}
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "mixed",
        "reference_guidance": {"reference_action": "diagnostic_only"},
        "ncf_2330_h20_prob_up": 0.51,
    }
    signal["ncf_live_overlay"]["ncf_2330_checklist"] = {
        "factor_quality_overlay": {
            "signal": "bearish",
            "label": "risk_off",
            "risk_score": 4.0,
            "net_score": -2.0,
        }
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert suitability["tier"] == 2
    assert suitability["shadow_momentum_candidate"] is True
    assert suitability["shadow_momentum_note"].startswith("shadow_momentum_confirm")
    assert suitability["inputs"]["ncf_2330_factor_quality_risk_score"] == 4.0


def test_leverage_suitability_tier_3_when_groupa_and_ncf_are_bullish() -> None:
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 1
    signal["execution_regime"] = "golden1"
    signal["finbert_sentiment"]["risk_score"] = 0.20
    signal["ncf_live_overlay"]["ncf_00631l"] = {"calibrated_prob_up": 0.70, "confidence": 0.80, "direction": "UP"}
    signal["ncf_live_overlay"]["ncf_00632r"] = {"calibrated_prob_up": 0.25, "confidence": 0.80, "direction": "DOWN"}
    signal["ncf_live_overlay"]["cross_ticker_consistency"] = {"market_probability_up": 0.72, "agreement_score": 0.80}
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "healthy_leadership",
        "reference_guidance": {"reference_action": "allow_normal"},
        "ncf_2330_h20_prob_up": 0.68,
    }
    signal["factor_lens_gate"] = {
        "all_key_factors_pass": True,
        "factors": {
            "ncf_00631l_prob_up": {"passed": True, "ic_20d_warning": False},
            "ncf_cross_ticker_market_up": {"passed": True, "ic_20d_warning": False},
        },
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert result["alignment"] == "bullish_alignment"
    assert suitability["tier"] == 3
    assert suitability["label_zh"] == "適合提高 00631L"


def test_leverage_suitability_demotes_from_tier_3_when_chip_data_stale() -> None:
    # Same setup as test_leverage_suitability_tier_3_when_groupa_and_ncf_are_bullish,
    # except chip/derivative source data has been stale long enough to trip
    # a2118's own chip-data-outage fallback (see the 2026-07-04 fix). A stale
    # feed reading total_risk_score=0/1 must not look like a genuinely calm,
    # high-suitability market.
    signal = _live_signal()
    signal["latest_features"]["total_risk_score"] = 1
    signal["latest_features"]["chip_data_core_days_since_source_update"] = 999_999
    signal["execution_regime"] = "golden1"
    signal["finbert_sentiment"]["risk_score"] = 0.20
    signal["ncf_live_overlay"]["ncf_00631l"] = {"calibrated_prob_up": 0.70, "confidence": 0.80, "direction": "UP"}
    signal["ncf_live_overlay"]["ncf_00632r"] = {"calibrated_prob_up": 0.25, "confidence": 0.80, "direction": "DOWN"}
    signal["ncf_live_overlay"]["cross_ticker_consistency"] = {"market_probability_up": 0.72, "agreement_score": 0.80}
    signal["ncf_live_overlay"]["tsmc_0050_health"] = {
        "status": "available",
        "state": "healthy_leadership",
        "reference_guidance": {"reference_action": "allow_normal"},
        "ncf_2330_h20_prob_up": 0.68,
    }
    signal["factor_lens_gate"] = {
        "all_key_factors_pass": True,
        "factors": {
            "ncf_00631l_prob_up": {"passed": True, "ic_20d_warning": False},
            "ncf_cross_ticker_market_up": {"passed": True, "ic_20d_warning": False},
        },
    }

    result = build_signal_alignment(signal)

    suitability = result["leverage_suitability"]
    assert suitability["tier"] != 3
    assert suitability["inputs"]["chip_data_stale"] is True

    risk_source = next(s for s in result["sources"] if s["name"] == "composite_risk_score")
    assert risk_source["available"] is False
    assert risk_source["direction"] == "neutral"


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


def test_append_signal_alignment_shadow_log_is_idempotent_per_date() -> None:
    """Fable audit (2026-07-08, #10): alignment drives real trim/alert/
    market_state behavior with no forward-return tracking -- this log is the
    measurement-only first step, mirroring garch_regime_shadow's
    idempotent-per-date append so re-running daily_signal same-day doesn't
    skew the forward-observation count."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "signal_alignment_shadow_log.jsonl"
        day1 = {"signal_date": "2026-07-01", "alignment": "mixed", "dominant_direction": "bullish"}
        day2 = {"signal_date": "2026-07-02", "alignment": "wide_divergence", "dominant_direction": "bearish"}
        day1_rerun = {"signal_date": "2026-07-01", "alignment": "bearish_alignment", "dominant_direction": "bearish"}

        append_signal_alignment_shadow_log(log_path, day1)
        append_signal_alignment_shadow_log(log_path, day2)
        append_signal_alignment_shadow_log(log_path, day1_rerun)

        lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(lines) == 2
    by_date = {row["date"]: row for row in lines}
    assert by_date["2026-07-01"]["alignment"] == "bearish_alignment"
    assert by_date["2026-07-02"]["alignment"] == "wide_divergence"


def test_append_signal_alignment_shadow_log_skips_missing_date() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "signal_alignment_shadow_log.jsonl"
        append_signal_alignment_shadow_log(log_path, {"alignment": "mixed"})
        assert not log_path.exists()
