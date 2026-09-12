from __future__ import annotations

from backtest_group_a_plus_overlay import _group_a_plus_target, _variant_config


def test_cap_guard_no_inverse_releases_base_00632r_to_cash() -> None:
    base_config = {}
    config = _variant_config(base_config, "cap_guard_no_inverse")
    event = {
        "target_weights": {
            "0050.TW": 0.40,
            "00631L.TW": 0.10,
            "00632R.TW": 0.40,
            "00679B.TWO": 0.00,
        },
        "target_cash_weight": 0.10,
    }

    target, cash, report = _group_a_plus_target(event, "risk_on", config)

    assert target["00632R.TW"] == 0.0
    assert cash > 0.45
    assert report["inverse_forbid_gate"]["enabled"] is True
    assert report["inverse_forbid_gate"]["removed_weight"] > 0.39


def test_forbid_auto_exposure_prevents_severe_inverse_addition() -> None:
    config = {
        "overlay": {"dynamic_weight_bands": {"severe": 0.0}},
        "leverage_control": {"max_weight_by_regime": {"severe": 1.0}},
        "inverse_control": {
            "enabled": True,
            "forbid_auto_exposure": True,
            "ticker": "00632R.TW",
            "severe_inverse_weight": 0.10,
        },
    }
    event = {
        "target_weights": {
            "0050.TW": 0.90,
            "00631L.TW": 0.00,
            "00632R.TW": 0.00,
            "00679B.TWO": 0.00,
        },
        "target_cash_weight": 0.10,
    }

    target, _cash, report = _group_a_plus_target(event, "severe", config)

    assert target["00632R.TW"] == 0.0
    assert report["inverse_control"]["enabled"] is False
    assert report["inverse_forbid_gate"]["enabled"] is True
