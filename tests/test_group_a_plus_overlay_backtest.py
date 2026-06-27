from __future__ import annotations

import pandas as pd
import pytest

from backtest_group_a_plus_overlay import (
    _apply_dca_purchases,
    _apply_group_a_plus_risk_overlays,
    _apply_staged_execution,
    _fast_risk_off_overlay,
    _grid_variant_configs,
    _group_a_plus_target,
    _leverage_stop_cooldown_overlay,
    _plus_regime,
    _promotion_gate,
    _variant_config,
)


def test_plus_regime_maps_neutral_to_caution_overlay_band() -> None:
    assert _plus_regime({"regime": "neutral", "tdcc_state": "normal"}) == "risk_on"
    assert _plus_regime({"regime": "neutral", "tdcc_state": "caution"}) == "caution"
    assert _plus_regime({"regime": "risk_off", "tdcc_state": "risk_off"}) == "risk_off"


def test_group_a_plus_target_applies_dynamic_bond_and_leverage_cap() -> None:
    event = {
        "target_weights": {
            "0050.TW": 0.6075,
            "00631L.TW": 0.08,
            "00632R.TW": 0.0,
        },
        "target_cash_weight": 0.3125,
    }
    config = {
        "overlay": {"dynamic_weight_bands": {"risk_off": 0.20}},
        "leverage_control": {
            "ticker": "00631L.TW",
            "release_to": "cash",
            "max_weight_by_regime": {"risk_off": 0.04},
        },
    }

    target, cash, report = _group_a_plus_target(event, "risk_off", config)

    assert target["00679B.TWO"] == pytest.approx(0.20)
    assert target["00631L.TW"] == pytest.approx(0.032)
    assert target["0050.TW"] == pytest.approx(0.486)
    assert cash == pytest.approx(0.282)
    assert report["leverage_released_to_cash"] == pytest.approx(0.04)


def test_staged_execution_scales_risk_off_buys_but_keeps_sells_full() -> None:
    current = {
        "0050.TW": 0.10,
        "00631L.TW": 0.05,
        "00632R.TW": 0.02,
        "00679B.TWO": 0.25,
    }
    target = {
        "0050.TW": 0.50,
        "00631L.TW": 0.04,
        "00632R.TW": 0.0,
        "00679B.TWO": 0.20,
    }
    config = {
        "execution_control": {
            "buy_fraction_by_regime": {"risk_off": 0.5},
            "sell_fraction_by_regime": {"risk_off": 1.0},
        }
    }

    adjusted, cash, report = _apply_staged_execution(
        current,
        target,
        target_cash=0.26,
        regime="risk_off",
        config=config,
    )

    assert adjusted["0050.TW"] == pytest.approx(0.30)
    assert adjusted["00631L.TW"] == pytest.approx(0.04)
    assert adjusted["00632R.TW"] == pytest.approx(0.0)
    assert adjusted["00679B.TWO"] == pytest.approx(0.20)
    assert cash == pytest.approx(0.46)
    assert report["buy_fraction"] == pytest.approx(0.5)


def test_staged_execution_applies_turnover_cap_after_execution_fractions() -> None:
    current = {
        "0050.TW": 0.10,
        "00631L.TW": 0.00,
        "00632R.TW": 0.00,
        "00679B.TWO": 0.20,
    }
    target = {
        "0050.TW": 0.50,
        "00631L.TW": 0.10,
        "00632R.TW": 0.00,
        "00679B.TWO": 0.10,
    }
    config = {
        "overlay": {"ticker": "00679B.TWO"},
        "execution_control": {
            "buy_fraction_by_regime": {"risk_off": 1.0},
            "sell_fraction_by_regime": {"risk_off": 1.0},
            "defensive_sleeve_sell_fraction_by_regime": {"risk_off": 1.0},
            "max_turnover_ratio_by_regime": {"risk_off": 0.25},
        },
    }

    adjusted, cash, report = _apply_staged_execution(
        current,
        target,
        target_cash=0.30,
        regime="risk_off",
        config=config,
    )

    assert report["turnover_cap_applied"] is True
    assert report["final_turnover_ratio"] <= 0.25 + 1e-12
    assert adjusted["0050.TW"] < target["0050.TW"]
    assert adjusted["00631L.TW"] < target["00631L.TW"]
    assert adjusted["00679B.TWO"] > target["00679B.TWO"]
    assert cash > 0.0


def test_grid_variant_configs_build_expected_risk_off_controls() -> None:
    configs = _grid_variant_configs(
        {"overlay": {}, "leverage_control": {}, "execution_control": {}},
        risk_off_bonds=[0.06],
        risk_off_buys=[0.85],
        risk_off_bond_sells=[0.50],
        risk_off_turnover_caps=[0.35],
    )

    config = configs["grid_b06_buy85_bsell50_turn35"]

    assert config["overlay"]["dynamic_weight_bands"]["risk_off"] == pytest.approx(0.06)
    assert config["overlay"]["dynamic_weight_bands"]["caution"] == pytest.approx(0.03)
    assert config["execution_control"]["buy_fraction_by_regime"]["risk_off"] == pytest.approx(0.85)
    assert config["execution_control"]["defensive_sleeve_sell_fraction_by_regime"]["risk_off"] == pytest.approx(0.50)
    assert config["execution_control"]["max_turnover_ratio_by_regime"]["risk_off"] == pytest.approx(0.35)


def test_live_return_guard_matches_latest_grid_winner_controls() -> None:
    config = _variant_config(
        {"overlay": {}, "leverage_control": {}, "execution_control": {}},
        "live_return_guard",
    )

    assert config["overlay"]["dynamic_weight_bands"] == {
        "risk_on": 0.0,
        "caution": 0.02,
        "risk_off": 0.04,
        "severe": 0.08,
    }
    assert config["leverage_control"]["max_weight_by_regime"]["risk_off"] == pytest.approx(0.06)
    assert config["execution_control"]["buy_fraction_by_regime"]["risk_off"] == pytest.approx(0.70)
    assert config["execution_control"]["defensive_sleeve_sell_fraction_by_regime"]["risk_off"] == pytest.approx(0.75)
    assert config["execution_control"]["max_turnover_ratio_by_regime"]["risk_off"] == pytest.approx(0.25)


def test_cap_guard_optimized_keeps_bull_market_pass_through_and_removes_risk_off_leverage() -> None:
    config = _variant_config(
        {"overlay": {}, "leverage_control": {}, "execution_control": {}},
        "cap_guard_optimized",
    )

    assert config["overlay"]["dynamic_weight_bands"] == {
        "risk_on": 0.0,
        "caution": 0.0,
        "risk_off": 0.0,
        "severe": 0.0,
    }
    assert config["leverage_control"]["max_weight_by_regime"] == {
        "risk_on": 0.20,
        "caution": 0.18,
        "risk_off": 0.00,
        "severe": 0.00,
    }
    assert config["execution_control"]["buy_fraction_by_regime"]["risk_off"] == pytest.approx(1.0)
    assert config["execution_control"]["max_turnover_ratio_by_regime"]["risk_off"] == pytest.approx(1.0)


def test_focused_hybrid_turnover_profile_keeps_severe_cap_tighter_than_risk_off() -> None:
    config = _variant_config(
        {"overlay": {}, "leverage_control": {}, "execution_control": {}},
        "focused_tdcc_0258_stab3_turn15_sev08",
    )

    caps = config["execution_control"]["max_turnover_ratio_by_regime"]

    assert caps["risk_off"] == pytest.approx(0.15)
    assert caps["severe"] == pytest.approx(0.08)
    assert caps["risk_on"] == pytest.approx(1.0)
    assert caps["caution"] == pytest.approx(1.0)


def test_fast_risk_off_overlay_triggers_on_0050_three_day_price_shock() -> None:
    dates = pd.date_range("2026-06-01", periods=6, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 99.0, 98.0, 96.0, 95.0],
            "00631L.TW": [40.0, 40.0, 39.0, 38.0, 37.0, 36.0],
            "00632R.TW": [10.0] * 6,
            "00679B.TWO": [26.0] * 6,
        },
        index=dates,
    )
    config = {
        "fast_risk_off_control": {
            "enabled": True,
            "reference_ticker": "0050.TW",
            "lookback_days": 3,
            "drawdown_threshold": -0.03,
            "duration_days": 5,
            "override_regime": "risk_off",
            "cap_ticker": "00631L.TW",
            "cap_weight": 0.0,
            "cash_floor": 0.30,
        }
    }

    regime, active_until, report = _fast_risk_off_overlay(prices, dates[-1], config)

    assert regime == "risk_off"
    assert active_until is not None
    assert report["active"] is True
    assert report["reason"] == "price_shock_triggered"
    assert report["cap_ticker"] == "00631L.TW"


def test_leverage_stop_cooldown_triggers_on_00631l_trailing_drawdown() -> None:
    dates = pd.date_range("2026-06-01", periods=25, freq="B")
    lev_prices = [40.0 + i for i in range(20)] + [56.0, 54.0, 52.0, 50.0, 48.0]
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0] * 25,
            "00631L.TW": lev_prices,
            "00632R.TW": [10.0] * 25,
            "00679B.TWO": [26.0] * 25,
        },
        index=dates,
    )
    config = {
        "leverage_stop_cooldown": {
            "enabled": True,
            "ticker": "00631L.TW",
            "lookback_days": 20,
            "trailing_stop_pct": -0.10,
            "absolute_lookback_days": 5,
            "absolute_stop_pct": -0.50,
            "cooldown_days": 5,
            "cap_weight": 0.0,
        }
    }

    active_until, report = _leverage_stop_cooldown_overlay(prices, dates[-1], config)

    assert active_until is not None
    assert report["active"] is True
    assert report["reason"] == "trailing_stop_triggered"
    assert report["ticker"] == "00631L.TW"


def test_risk_overlays_release_00631l_weight_to_cash() -> None:
    weights = {
        "0050.TW": 0.60,
        "00631L.TW": 0.15,
        "00632R.TW": 0.0,
        "00679B.TWO": 0.0,
    }
    fast_report = {"active": True, "reason": "price_shock_triggered", "cap_ticker": "00631L.TW", "cap_weight": 0.0}
    stop_report = {"active": False}

    adjusted, cash, report = _apply_group_a_plus_risk_overlays(
        weights,
        0.25,
        fast_report=fast_report,
        stop_report=stop_report,
    )

    assert adjusted["00631L.TW"] == pytest.approx(0.0)
    assert cash == pytest.approx(0.40)
    assert report["applied"] is True


def test_apply_dca_purchases_buys_recorded_0050_contribution() -> None:
    dt = pd.Timestamp("2025-01-20")
    price_row = pd.Series({"0050.TW": 50.0, "00631L.TW": 200.0, "00632R.TW": 5.0, "00679B.TWO": 27.0})
    shares = {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0}
    dca_map = {
        dt: [
            {
                "date": "2025-01-20",
                "total_contribution": 5000.0,
                "purchases": {"0050.TW": {"cash_contribution": 5000.0}},
            }
        ]
    }

    cash, fees, contributions = _apply_dca_purchases(
        dt,
        price_row,
        shares,
        cash=1000.0,
        dca_map=dca_map,
        commission_rate=0.001425,
    )

    expected_fee = 5000.0 * 0.001425 / 1.001425
    assert cash == pytest.approx(1000.0)
    assert fees == pytest.approx(expected_fee)
    assert contributions == pytest.approx(5000.0)
    assert shares["0050.TW"] == pytest.approx((5000.0 - expected_fee) / 50.0)


def test_promotion_gate_keeps_return_dragging_overlay_in_shadow() -> None:
    base = {
        "final_value": 2_200_000.0,
        "sharpe_ratio": 2.75,
        "max_drawdown": -0.17,
        "volatility": 0.22,
    }
    plus = {
        "minimal": {
            "metrics": {
                "final_value": 1_970_000.0,
                "sharpe_ratio": 2.72,
                "max_drawdown": -0.168,
                "volatility": 0.205,
            }
        }
    }

    gate = _promotion_gate(base, plus)

    assert gate["decision"] == "shadow_risk_control_only"
    assert gate["variants"][0]["risk_control_candidate"] is True
    assert gate["variants"][0]["return_upgrade_candidate"] is False
    assert gate["variants"][0]["retrain_candidate"] is False


def test_promotion_gate_marks_close_sharpe_variant_as_promotion_candidate() -> None:
    base = {
        "final_value": 2_200_000.0,
        "sharpe_ratio": 2.75,
        "max_drawdown": -0.17,
        "volatility": 0.22,
    }
    plus = {
        "candidate": {
            "metrics": {
                "final_value": 2_178_000.0,
                "sharpe_ratio": 2.73,
                "max_drawdown": -0.165,
                "volatility": 0.205,
            }
        }
    }

    gate = _promotion_gate(base, plus)

    assert gate["decision"] == "promotion_candidate"
    assert gate["variants"][0]["return_upgrade_candidate"] is True
