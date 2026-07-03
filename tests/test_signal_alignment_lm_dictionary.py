from __future__ import annotations

from group_a_plus.integrations.signal_alignment import build_signal_alignment


def test_lm_dictionary_sentiment_is_low_weight_alignment_source() -> None:
    alignment = build_signal_alignment(
        {
            "strategy_id": "unit",
            "actual_data_date": "2026-07-01",
            "execution_regime": "golden1",
            "latest_features": {"total_risk_score": 1, "chip_score": 0, "derivative_score": 0},
            "finbert_sentiment": {"status": "ok", "risk_score": 0.2},
            "lm_dictionary_sentiment": {
                "status": "ok",
                "risk_score": 0.8,
                "positive_count": 1,
                "negative_count": 4,
                "dictionary_hit_count": 5,
            },
            "ncf_live_overlay": {},
            "factor_lens_gate": {},
            "tbrain_shadow": {"status": "unavailable"},
        }
    )

    lm_sources = [src for src in alignment["sources"] if src["name"] == "lm_dictionary_sentiment"]

    assert len(lm_sources) == 1
    assert lm_sources[0]["available"] is True
    assert lm_sources[0]["direction"] == "bearish"
    assert lm_sources[0]["strength"] <= 0.5
