from __future__ import annotations

from scripts.evaluate.build_gjr_post_trigger_severity_shadow import build_gjr_post_trigger_shadow


def _signal() -> dict:
    return {
        "actual_data_date": "2026-08-24",
        "execution_regime": "golden1",
        "latest_features": {
            "tail_risk_score": 1,
            "drawdown": -0.09,
            "ma_gap": 0.05,
            "exit_momentum_5d": -0.02,
        },
    }


def _gjr(**overrides) -> dict:
    base = {
        "status": "available",
        "date": "2026-08-24",
        "evidence_level": "none",
        "forecast_variance_ratio_gjr_over_symmetric": 0.98,
        "gjr_asymmetry_shock": False,
        "latest_return": -0.01,
        "likelihood_ratio_test": {"p_value": 0.01},
    }
    base.update(overrides)
    return base


def _oos(tail_sig: bool = False) -> dict:
    return {
        "overall": {
            "qlike_diebold_mariano": {
                "significant_at_5pct": True,
                "a_more_accurate": True,
                "p_value": 0.03,
            }
        },
        "tail_5pct_worst_realized_days": {
            "underpred_frac_gjr": 1.0,
            "qlike_diebold_mariano": {
                "significant_at_5pct": tail_sig,
                "a_more_accurate": True,
                "p_value": 0.056,
            },
        },
    }


def _opportunity() -> dict:
    return {
        "breakdown_by_tuned_regime": {
            "trigger_day_count": 22,
            "TREND_PERSISTENT": {
                "count": 6,
                "forward_20d_mean": 0.127,
                "forward_20d_positive_rate": 0.667,
            },
        }
    }


def test_inactive_when_existing_a2126_trigger_not_active() -> None:
    signal = _signal()
    signal["latest_features"]["tail_risk_score"] = 0

    result = build_gjr_post_trigger_shadow(
        signal=signal,
        gjr_shadow=_gjr(),
        oos_report=_oos(),
        opportunity_report=_opportunity(),
        realized_vol_ratio_20_60=1.4,
    )

    assert result["status"] == "inactive"
    assert result["recommended_shadow_action"] == "inactive_no_existing_trigger"
    assert "a2126_tail_risk_condition_inactive" in result["blockers"]


def test_low_severity_when_trigger_active_but_gjr_has_no_shock() -> None:
    result = build_gjr_post_trigger_shadow(
        signal=_signal(),
        gjr_shadow=_gjr(),
        oos_report=_oos(),
        opportunity_report=_opportunity(),
        realized_vol_ratio_20_60=1.4,
    )

    assert result["status"] == "active_shadow_candidate"
    assert result["recommended_shadow_action"] == "low_severity_defer_or_minimal_cap"
    assert result["severity_cap_fraction_of_existing_leverage_cap"] == 0.25
    assert "gjr_tail_oos_gate_not_significant_so_severity_only" in result["warnings"]


def test_full_cap_when_trigger_active_and_gjr_asymmetry_shock() -> None:
    result = build_gjr_post_trigger_shadow(
        signal=_signal(),
        gjr_shadow=_gjr(evidence_level="weak", forecast_variance_ratio_gjr_over_symmetric=1.3, gjr_asymmetry_shock=True),
        oos_report=_oos(tail_sig=True),
        opportunity_report=_opportunity(),
        realized_vol_ratio_20_60=1.4,
    )

    assert result["status"] == "active_shadow_candidate"
    assert result["recommended_shadow_action"] == "full_existing_leverage_cap_allowed"
    assert result["severity_cap_fraction_of_existing_leverage_cap"] == 1.0


def test_oos_overall_gate_blocks_even_if_trigger_active() -> None:
    oos = _oos()
    oos["overall"]["qlike_diebold_mariano"]["significant_at_5pct"] = False

    result = build_gjr_post_trigger_shadow(
        signal=_signal(),
        gjr_shadow=_gjr(),
        oos_report=oos,
        opportunity_report=_opportunity(),
        realized_vol_ratio_20_60=1.4,
    )

    assert result["status"] == "inactive"
    assert "gjr_overall_oos_gate_not_significant" in result["blockers"]
