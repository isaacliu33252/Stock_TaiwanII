from __future__ import annotations

from scripts.evaluate.build_a2120_small_00631l_reentry_shadow import build_small_reentry_shadow


def _signal() -> dict:
    return {
        "actual_data_date": "2026-08-24",
        "execution_allowed": True,
        "execution_regime": "golden1",
        "target_weights": {
            "0050.TW": 0.45,
            "00631L.TW": 0.0,
            "00632R.TW": 0.0,
            "00679B.TWO": 0.0,
            "cash": 0.55,
        },
        "latest_features": {"tail_risk_score": 0, "total_risk_score": 5},
        "trough_nowcast": {
            "inputs": {
                "signal_alignment": {"alignment": "mixed", "dominant_direction": "neutral"},
            },
        },
    }


def _a2120() -> dict:
    return {
        "daily_state": {
            "date": "2026-08-24",
            "compounding_regime": "TREND_PERSISTENT",
            "raw_action": "FAST_REENTER_CANDIDATE",
            "recommended_action": "FAST_REENTER_CANDIDATE",
            "hard_blockers": [],
        },
        "scorecard_decision": {
            "daily_advisory": "enable_daily_advisory_shadow_only",
            "production": "do_not_promote",
        },
    }


def test_small_reentry_adds_5pct_00631l_from_cash_when_all_clear() -> None:
    result = build_small_reentry_shadow(signal=_signal(), a2120=_a2120())

    assert result["status"] == "active_shadow_candidate"
    assert result["proposed_shadow_target_weights"]["00631L.TW"] == 0.05
    assert result["proposed_shadow_target_weights"]["cash"] == 0.50
    assert result["delta_weights"]["00631L.TW"] == 0.05


def test_stale_a2120_blocks_live_small_reentry() -> None:
    a2120 = _a2120()
    a2120["daily_state"]["date"] = "2026-08-21"

    result = build_small_reentry_shadow(signal=_signal(), a2120=a2120)

    assert result["status"] == "inactive"
    assert "a2120_daily_state_not_aligned_with_live_signal" in result["blockers"]
    assert result["candidate_target_weights_if_blockers_clear"]["00631L.TW"] == 0.05


def test_bearish_dominant_direction_blocks_00631l_stage() -> None:
    signal = _signal()
    signal["trough_nowcast"]["inputs"]["signal_alignment"]["dominant_direction"] = "bearish"

    result = build_small_reentry_shadow(signal=signal, a2120=_a2120())

    assert result["status"] == "inactive"
    assert "dominant_direction_bearish" in result["blockers"]


def test_full_reentry_hard_blockers_block_small_shadow_until_replayed() -> None:
    a2120 = _a2120()
    a2120["daily_state"]["hard_blockers"] = ["turnover ratio exceeds automatic limit"]

    result = build_small_reentry_shadow(signal=_signal(), a2120=a2120)

    assert result["status"] == "inactive"
    assert "a2120_full_reentry_has_hard_blockers" in result["blockers"]
