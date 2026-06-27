from __future__ import annotations

import pytest
import pandas as pd

from group_a_00679b_continuous_shadow import (
    _apply_cash_constraint,
    _apply_group_a_plus_execution_control,
    _apply_group_a_plus_leverage_control,
    _apply_group_a_plus_turnover_cap,
    _execution_rows,
    _infer_group_a_plus_regime,
    _resolve_00679b_cache,
    _resolve_00679b_overlay_weight,
    _resolve_turnover_penalty,
)


CURRENT_SHARES = {
    "0050.TW": 10,
    "00631L.TW": 0,
    "00679B.TWO": 10,
}
PRICES = {
    "0050.TW": 100.0,
    "00631L.TW": 40.0,
    "00679B.TWO": 25.0,
}


def _summary(target_shares: dict[str, int], total_assets: float) -> dict:
    _, summary = _execution_rows(
        CURRENT_SHARES,
        target_shares,
        PRICES,
        {},
        total_assets,
        commission_rate=0.001425,
        etf_sell_tax_rate=0.001,
        slippage_rate=0.0005,
        min_trade_value=0.0,
        batch_count=1,
        batch_threshold=1_000_000.0,
    )
    return summary


def test_cash_constraint_keeps_fundable_target_unchanged() -> None:
    target = {"0050.TW": 12, "00631L.TW": 0, "00679B.TWO": 10}
    adjusted, report = _apply_cash_constraint(
        CURRENT_SHARES,
        target,
        PRICES,
        total_assets=1_500.0,
        commission_rate=0.001425,
        etf_sell_tax_rate=0.001,
        slippage_rate=0.0005,
        min_trade_value=0.0,
    )

    assert adjusted == target
    assert report["applied"] is False
    assert report["reason"] == "cash_after_cost_nonnegative"


def test_cash_constraint_scales_buy_orders_until_cash_after_cost_is_nonnegative() -> None:
    target = {"0050.TW": 25, "00631L.TW": 20, "00679B.TWO": 10}
    unconstrained = _summary(target, total_assets=2_000.0)
    assert unconstrained["cash_after_cost"] < 0

    adjusted, report = _apply_cash_constraint(
        CURRENT_SHARES,
        target,
        PRICES,
        total_assets=2_000.0,
        commission_rate=0.001425,
        etf_sell_tax_rate=0.001,
        slippage_rate=0.0005,
        min_trade_value=0.0,
    )
    constrained = _summary(adjusted, total_assets=2_000.0)

    assert report["applied"] is True
    assert report["reason"] == "scaled_buy_orders_to_keep_cash_after_cost_nonnegative"
    assert adjusted["0050.TW"] <= target["0050.TW"]
    assert adjusted["00631L.TW"] <= target["00631L.TW"]
    assert adjusted["00679B.TWO"] == target["00679B.TWO"]
    assert constrained["cash_after_cost"] >= 0


def test_group_a_plus_regime_prefers_source_event_regime() -> None:
    signal = {
        "signal_reason": "meta_ensemble_shadow",
        "source_event": {
            "regime": "risk_off",
            "overlay": {"tdcc_state": "caution"},
        },
    }

    regime, _ = _infer_group_a_plus_regime(signal)

    assert regime == "risk_off"


def test_group_a_plus_regime_detects_severe_overlay() -> None:
    signal = {
        "signal_reason": "meta_ensemble_shadow",
        "source_event": {
            "regime": "risk_off",
            "overlay": {"severe_inverse_allowed": True},
        },
    }

    regime, _ = _infer_group_a_plus_regime(signal)

    assert regime == "severe"


def test_group_a_plus_regime_does_not_treat_profile_name_severe_as_current_regime() -> None:
    signal = {
        "signal_reason": "meta_ensemble_shadow_adaptive_momcash_price_severe12_vote",
        "source_event": {
            "regime": "risk_off",
            "overlay": {"severe_inverse_allowed": False},
        },
    }

    regime, _ = _infer_group_a_plus_regime(signal)

    assert regime == "risk_off"


def test_dynamic_group_a_plus_overlay_weight_uses_config_band() -> None:
    signal = {"source_event": {"regime": "caution", "overlay": {}}}
    config = {
        "overlay": {
            "dynamic_weight_bands": {
                "risk_on": 0.10,
                "caution": 0.15,
                "risk_off": 0.20,
                "severe": 0.25,
            }
        }
    }

    weight, policy = _resolve_00679b_overlay_weight(
        signal=signal,
        config=config,
        requested_weight=None,
        dynamic_overlay=True,
    )

    assert weight == 0.15
    assert policy["mode"] == "dynamic"
    assert policy["regime"] == "caution"


def test_turnover_penalty_prefers_cli_override() -> None:
    config = {
        "execution_control": {
            "live_turnover_penalty_by_regime": {"risk_off": 0.10},
            "default_turnover_penalty_by_regime": {"risk_off": 0.25},
        },
        "latest_reference": {"recommended_live_turnover_penalty": 0.15},
    }

    penalty, policy = _resolve_turnover_penalty(config, "risk_off", 0.35)

    assert penalty == pytest.approx(0.35)
    assert policy["source"] == "cli"


def test_turnover_penalty_uses_live_config_before_default() -> None:
    config = {
        "execution_control": {
            "live_turnover_penalty_by_regime": {"risk_off": 0.10},
            "default_turnover_penalty_by_regime": {"risk_off": 0.25},
        },
        "latest_reference": {"recommended_live_turnover_penalty": 0.15},
    }

    penalty, policy = _resolve_turnover_penalty(config, "risk_off", None)

    assert penalty == pytest.approx(0.10)
    assert policy["source"] == "config_live"


def test_turnover_penalty_uses_latest_reference_recommendation_for_existing_config() -> None:
    config = {
        "execution_control": {
            "default_turnover_penalty_by_regime": {"risk_off": 0.25},
        },
        "latest_reference": {"recommended_live_turnover_penalty": 0.10},
    }

    penalty, policy = _resolve_turnover_penalty(config, "risk_off", None)

    assert penalty == pytest.approx(0.10)
    assert policy["source"] == "config_latest_reference"


def test_resolve_00679b_cache_prefers_actual_date_file(tmp_path) -> None:
    stale = tmp_path / "00679B_TWO_20200101_20260604_1d_raw_v1.parquet"
    fresh = tmp_path / "00679B_TWO_20200101_20260605_1d_raw_v1.parquet"
    pd.DataFrame({"date": ["2026-06-04"]}).to_parquet(stale)
    pd.DataFrame({"date": ["2026-06-05"]}).to_parquet(fresh)

    resolved = _resolve_00679b_cache(stale, "2026-06-05")

    assert resolved == fresh


def test_manual_group_a_plus_overlay_weight_keeps_backward_compatibility() -> None:
    signal = {"source_event": {"regime": "risk_off", "overlay": {}}}
    config = {"overlay": {"dynamic_weight_bands": {"risk_off": 0.20}}}

    weight, policy = _resolve_00679b_overlay_weight(
        signal=signal,
        config=config,
        requested_weight=0.12,
        dynamic_overlay=False,
    )

    assert weight == 0.12
    assert policy["mode"] == "manual"


def test_group_a_plus_leverage_control_caps_00631l_and_releases_to_cash() -> None:
    weights = {
        "0050.TW": 0.486,
        "00631L.TW": 0.064,
        "00632R.TW": 0.0,
        "00679B.TWO": 0.20,
        "cash": 0.25,
    }
    config = {
        "leverage_control": {
            "ticker": "00631L.TW",
            "release_to": "cash",
            "max_weight_by_regime": {"risk_off": 0.04},
        }
    }

    adjusted, report = _apply_group_a_plus_leverage_control(
        weights,
        config=config,
        regime="risk_off",
    )

    assert report["applied"] is True
    assert adjusted["00631L.TW"] == pytest.approx(0.04)
    assert adjusted["cash"] == pytest.approx(0.274)
    assert sum(adjusted.values()) == pytest.approx(1.0)


def test_group_a_plus_leverage_control_keeps_weight_below_cap() -> None:
    weights = {"00631L.TW": 0.03, "cash": 0.97}
    config = {
        "leverage_control": {
            "ticker": "00631L.TW",
            "max_weight_by_regime": {"risk_off": 0.04},
        }
    }

    adjusted, report = _apply_group_a_plus_leverage_control(
        weights,
        config=config,
        regime="risk_off",
    )

    assert report["applied"] is False
    assert adjusted == weights


def test_group_a_plus_execution_control_scales_risk_off_buys() -> None:
    current = {"0050.TW": 100, "00631L.TW": 0, "00679B.TWO": 10000}
    target = {"0050.TW": 500, "00631L.TW": 100, "00679B.TWO": 10000}
    config = {
        "execution_control": {
            "buy_fraction_by_regime": {"risk_off": 0.5},
            "sell_fraction_by_regime": {"risk_off": 1.0},
        }
    }

    adjusted, report = _apply_group_a_plus_execution_control(
        current,
        target,
        config=config,
        regime="risk_off",
    )

    assert report["applied"] is True
    assert adjusted["0050.TW"] == 300
    assert adjusted["00631L.TW"] == 50
    assert adjusted["00679B.TWO"] == 10000


def test_group_a_plus_execution_control_keeps_full_risk_off_sells() -> None:
    current = {"0050.TW": 500}
    target = {"0050.TW": 100}
    config = {
        "execution_control": {
            "buy_fraction_by_regime": {"risk_off": 0.5},
            "sell_fraction_by_regime": {"risk_off": 1.0},
        }
    }

    adjusted, report = _apply_group_a_plus_execution_control(
        current,
        target,
        config=config,
        regime="risk_off",
    )

    assert report["applied"] is False
    assert adjusted["0050.TW"] == 100


def test_group_a_plus_execution_control_stages_defensive_sleeve_sells() -> None:
    current = {"0050.TW": 100, "00679B.TWO": 10000}
    target = {"0050.TW": 50, "00679B.TWO": 4000}
    config = {
        "overlay": {"ticker": "00679B.TWO"},
        "execution_control": {
            "buy_fraction_by_regime": {"risk_off": 0.85},
            "sell_fraction_by_regime": {"risk_off": 1.0},
            "defensive_sleeve_sell_fraction_by_regime": {"risk_off": 0.5},
        },
    }

    adjusted, report = _apply_group_a_plus_execution_control(
        current,
        target,
        config=config,
        regime="risk_off",
    )

    assert report["applied"] is True
    assert adjusted["0050.TW"] == 50
    assert adjusted["00679B.TWO"] == 7000
    assert report["defensive_sleeve_sell_fraction"] == pytest.approx(0.5)


def test_group_a_plus_turnover_cap_scales_trade_deltas() -> None:
    current = {"0050.TW": 0, "00631L.TW": 0, "00679B.TWO": 100}
    target = {"0050.TW": 10, "00631L.TW": 10, "00679B.TWO": 80}
    prices = {"0050.TW": 100.0, "00631L.TW": 50.0, "00679B.TWO": 25.0}
    config = {
        "execution_control": {
            "max_turnover_ratio_by_regime": {"risk_off": 0.5},
        }
    }

    adjusted, report = _apply_group_a_plus_turnover_cap(
        current,
        target,
        prices,
        config=config,
        regime="risk_off",
        total_assets=2_000.0,
    )

    assert report["applied"] is True
    assert report["initial_turnover_ratio"] == pytest.approx(1.0)
    assert report["final_turnover_ratio"] <= 0.5
    assert adjusted == {"0050.TW": 5, "00631L.TW": 5, "00679B.TWO": 90}
