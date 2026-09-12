from __future__ import annotations

from scripts.evaluate.build_group_a_plus_staged_reentry_shadow import build_staged_reentry_shadow


def _base_signal() -> dict:
    return {
        "execution_allowed": True,
        "execution_regime": "golden1",
        "actual_data_date": "2026-08-24",
        "requested_as_of_date": "2026-08-25",
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "target_weights": {
            "0050.TW": 0.30,
            "00631L.TW": 0.0,
            "00632R.TW": 0.0,
            "00679B.TWO": 0.0,
            "cash": 0.70,
        },
        "latest_features": {
            "ma_gap": 0.05,
            "drawdown": -0.065,
            "exit_momentum_5d": -0.02,
            "total_risk_score": 6,
            "tail_risk_score": 0,
        },
        "market_state": {"state": "bull_pullback_deep", "bucket": "bull_pullback"},
        "trough_nowcast": {
            "state": "NO_TROUGH",
            "capitulation_score": 2,
            "reentry_confirmation_score": 1,
            "full_reentry_checks": {
                "risk_unwind_confirm": True,
                "local_price_confirm": False,
                "cross_market_confirm": False,
            },
            "inputs": {
                "market_proxy": {
                    "no_fresh_0050_lower_low_3d": True,
                    "latest_0050_close": 103.8,
                    "prior_0050_3d_low": 103.1,
                },
                "signal_alignment": {"alignment": "wide_divergence", "dominant_direction": "bearish"},
            },
        },
    }


def test_first_stage_reentry_moves_cash_to_0050_only() -> None:
    result = build_staged_reentry_shadow(_base_signal())

    assert result["status"] == "active_shadow_candidate"
    assert result["proposed_shadow_target_weights"]["0050.TW"] == 0.45
    assert result["proposed_shadow_target_weights"]["cash"] == 0.55
    assert result["proposed_shadow_target_weights"]["00631L.TW"] == 0.0
    assert "dominant_direction_bearish_blocks_00631l_stage" in result["warnings"]


def test_tail_risk_blocks_reentry() -> None:
    signal = _base_signal()
    signal["latest_features"]["tail_risk_score"] = 1

    result = build_staged_reentry_shadow(signal)

    assert result["status"] == "inactive"
    assert "tail_risk_score_positive" in result["blockers"]
    assert result["proposed_shadow_target_weights"]["0050.TW"] == 0.30


def test_fresh_lower_low_blocks_reentry() -> None:
    signal = _base_signal()
    signal["trough_nowcast"]["inputs"]["market_proxy"]["no_fresh_0050_lower_low_3d"] = False

    result = build_staged_reentry_shadow(signal)

    assert result["status"] == "inactive"
    assert "fresh_0050_lower_low_not_cleared" in result["blockers"]
