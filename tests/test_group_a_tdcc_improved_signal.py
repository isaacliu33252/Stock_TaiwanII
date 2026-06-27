from __future__ import annotations

import pytest

from run_group_a_tdcc_improved_signal import (
    _load_conditional_inverse_overlay_config,
    _load_inverse_hold_overlay_config,
    _write_improved_signal,
    apply_conditional_inverse_overlay,
    apply_inverse_hold_overlay,
    apply_tdcc_overlay,
)


CONFIG = {
    "primary_ticker": "0050",
    "leverage_ticker": "00631L",
    "inverse_ticker": "00632R",
    "caution": {"leverage_weight_cap": 0.1},
    "risk_off": {"leverage_weight_cap": 0.0},
    "released_leverage_budget_destination": "cash",
}
BASE_SIGNAL = {
    "signal_status": "rebalance",
    "signal_reason": "pva_overlay_s",
    "target_weights": {
        "0050.TW": 0.58,
        "00631L.TW": 0.12,
        "00632R.TW": 0.0,
    },
    "target_cash_weight": 0.30,
}


def test_tdcc_normal_keeps_base_targets() -> None:
    overlay = apply_tdcc_overlay(BASE_SIGNAL, {"state": "normal"}, CONFIG)
    assert overlay["changed"] is False
    assert overlay["target_weights"] == BASE_SIGNAL["target_weights"]
    assert overlay["target_cash_weight"] == 0.30
    assert overlay["signal_reason"] == "pva_overlay_s"


def test_tdcc_caution_caps_leverage_and_retains_released_budget_as_cash() -> None:
    overlay = apply_tdcc_overlay(BASE_SIGNAL, {"state": "caution"}, CONFIG)
    assert overlay["changed"] is True
    assert overlay["target_weights"]["00631L.TW"] == 0.1
    assert abs(overlay["target_cash_weight"] - 0.32) < 1e-12
    assert overlay["signal_reason"] == "tdcc_shareholding_caution"


def test_tdcc_risk_off_removes_leverage_and_retains_released_budget_as_cash() -> None:
    overlay = apply_tdcc_overlay(BASE_SIGNAL, {"state": "risk_off"}, CONFIG)
    assert overlay["changed"] is True
    assert overlay["target_weights"]["00631L.TW"] == 0.0
    assert abs(overlay["target_cash_weight"] - 0.42) < 1e-12
    assert overlay["signal_status"] == "rebalance"
    assert overlay["signal_reason"] == "tdcc_shareholding_risk_off"


def test_tdcc_can_move_released_budget_to_primary() -> None:
    config = {**CONFIG, "released_leverage_budget_destination": "primary"}
    overlay = apply_tdcc_overlay(BASE_SIGNAL, {"state": "risk_off"}, config)
    assert overlay["target_weights"]["00631L.TW"] == 0.0
    assert abs(overlay["target_weights"]["0050.TW"] - 0.70) < 1e-12
    assert abs(overlay["target_cash_weight"] - 0.30) < 1e-12


def test_tdcc_can_split_released_budget_between_primary_and_cash() -> None:
    config = {
        **CONFIG,
        "released_leverage_budget_destination": "split_primary_cash",
        "released_to_primary_fraction": 0.25,
    }
    overlay = apply_tdcc_overlay(BASE_SIGNAL, {"state": "risk_off"}, config)
    assert overlay["target_weights"]["00631L.TW"] == 0.0
    assert abs(overlay["target_weights"]["0050.TW"] - 0.61) < 1e-12
    assert abs(overlay["target_cash_weight"] - 0.39) < 1e-12


def test_tdcc_can_add_inverse_hedge_from_cash_when_enabled() -> None:
    config = {
        **CONFIG,
        "inverse_hedge_on_tdcc_risk_off": {
            "enabled": True,
            "weight": 0.05,
            "require_base_local_risk_off": False,
        },
    }
    overlay = apply_tdcc_overlay(BASE_SIGNAL, {"state": "risk_off"}, config)
    assert overlay["target_weights"]["00631L.TW"] == 0.0
    assert abs(overlay["target_weights"]["00632R.TW"] - 0.05) < 1e-12
    assert abs(overlay["target_cash_weight"] - 0.37) < 1e-12


def test_inverse_hold_overlay_moves_expired_00632r_weight_to_0050(tmp_path) -> None:
    overlay = {
        "state": "normal",
        "changed": False,
        "signal_status": "hold",
        "signal_reason": "base_hold",
        "base_target_weights": {
            "0050.TW": 0.60,
            "00631L.TW": 0.10,
            "00632R.TW": 0.05,
        },
        "base_target_cash_weight": 0.25,
        "target_weights": {
            "0050.TW": 0.60,
            "00631L.TW": 0.10,
            "00632R.TW": 0.05,
        },
        "target_cash_weight": 0.25,
    }
    base_signal = {
        "actual_data_date": "2026-06-05",
        "current_shares": {"0050.TW": 100, "00631L.TW": 0, "00632R.TW": 10},
    }
    hold_config = {
        "ticker": "00632R.TW",
        "release_to": "0050.TW",
        "max_holding_calendar_days": 10,
    }
    state_path = tmp_path / "hold_state.json"
    state_path.write_text(
        '{"active": true, "holding_start_date": "2026-05-20"}',
        encoding="utf-8",
    )

    improved, details = apply_inverse_hold_overlay(
        overlay,
        base_signal,
        hold_config,
        state_path=state_path,
    )

    assert details["enabled"] is True
    assert details["capped"] is True
    assert details["holding_days"] == 16
    assert details["released_weight"] == 0.05
    assert improved["target_weights"]["00632R.TW"] == 0.0
    assert abs(improved["target_weights"]["0050.TW"] - 0.65) < 1e-12
    assert improved["signal_status"] == "rebalance"
    assert "inverse_hold_limit_00632R.TW_10d" in improved["signal_reason"]
    assert details["days_remaining"] == 0


def test_inverse_hold_overlay_blocks_older_data_from_overwriting_state(tmp_path) -> None:
    overlay = {
        "state": "normal",
        "changed": False,
        "signal_status": "hold",
        "signal_reason": "base_hold",
        "base_target_weights": {
            "0050.TW": 0.60,
            "00631L.TW": 0.10,
            "00632R.TW": 0.05,
        },
        "base_target_cash_weight": 0.25,
        "target_weights": {
            "0050.TW": 0.60,
            "00631L.TW": 0.10,
            "00632R.TW": 0.05,
        },
        "target_cash_weight": 0.25,
    }
    base_signal = {
        "actual_data_date": "2026-06-04",
        "current_shares": {"0050.TW": 100, "00631L.TW": 0, "00632R.TW": 10},
    }
    hold_config = {
        "ticker": "00632R.TW",
        "release_to": "0050.TW",
        "max_holding_calendar_days": 10,
    }
    state_path = tmp_path / "hold_state.json"
    original_state = (
        '{"active": true, "holding_start_date": "2026-05-20", '
        '"last_seen_date": "2026-06-05"}'
    )
    state_path.write_text(original_state, encoding="utf-8")

    improved, details = apply_inverse_hold_overlay(
        overlay,
        base_signal,
        hold_config,
        state_path=state_path,
    )

    assert details["date_regression_blocked"] is True
    assert details["capped"] is False
    assert improved["target_weights"]["00632R.TW"] == 0.05
    assert state_path.read_text(encoding="utf-8") == original_state


def test_inverse_hold_overlay_config_typo_is_not_silent(tmp_path) -> None:
    missing = tmp_path / "missing.json"
    try:
        _load_inverse_hold_overlay_config(str(missing))
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("missing hold overlay config should raise FileNotFoundError")


def test_conditional_inverse_overlay_caps_00632r_when_stress_active(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "run_group_a_tdcc_improved_signal._conditional_inverse_stress_assessment",
        lambda base_signal, config, *, db_path: {"active": True, "condition": "stress_any"},
    )
    overlay = {
        "state": "normal",
        "changed": False,
        "signal_status": "hold",
        "signal_reason": "base_hold",
        "base_target_weights": {"0050.TW": 0.50, "00631L.TW": 0.10, "00632R.TW": 0.30},
        "base_target_cash_weight": 0.10,
        "target_weights": {"0050.TW": 0.50, "00631L.TW": 0.10, "00632R.TW": 0.30},
        "target_cash_weight": 0.10,
    }
    config = {"ticker": "00632R.TW", "release_to": "0050.TW", "cap": 0.10, "condition": "stress_any"}

    improved, details = apply_conditional_inverse_overlay(
        overlay,
        {"actual_data_date": "2026-06-05"},
        config,
        db_path=tmp_path / "dummy.db",
    )

    assert details["stress_active"] is True
    assert details["released_weight"] == pytest.approx(0.20)
    assert improved["target_weights"]["00632R.TW"] == pytest.approx(0.10)
    assert improved["target_weights"]["0050.TW"] == pytest.approx(0.70)
    assert "conditional_inverse_cap_00632R.TW_0.10" in improved["signal_reason"]


def test_conditional_inverse_overlay_releases_all_00632r_when_stress_inactive(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "run_group_a_tdcc_improved_signal._conditional_inverse_stress_assessment",
        lambda base_signal, config, *, db_path: {"active": False, "condition": "stress_any"},
    )
    overlay = {
        "state": "normal",
        "changed": False,
        "signal_status": "hold",
        "signal_reason": "base_hold",
        "base_target_weights": {"0050.TW": 0.50, "00631L.TW": 0.10, "00632R.TW": 0.30},
        "base_target_cash_weight": 0.10,
        "target_weights": {"0050.TW": 0.50, "00631L.TW": 0.10, "00632R.TW": 0.30},
        "target_cash_weight": 0.10,
    }
    config = {"ticker": "00632R.TW", "release_to": "0050.TW", "cap": 0.10, "condition": "stress_any"}

    improved, details = apply_conditional_inverse_overlay(
        overlay,
        {"actual_data_date": "2026-06-05"},
        config,
        db_path=tmp_path / "dummy.db",
    )

    assert details["stress_active"] is False
    assert details["allowed_cap"] == 0.0
    assert details["released_weight"] == 0.30
    assert improved["target_weights"]["00632R.TW"] == 0.0
    assert improved["target_weights"]["0050.TW"] == 0.80


def test_conditional_inverse_overlay_config_typo_is_not_silent(tmp_path) -> None:
    missing = tmp_path / "missing.json"
    try:
        _load_conditional_inverse_overlay_config(str(missing))
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("missing conditional inverse overlay config should raise FileNotFoundError")


def test_write_improved_signal_treats_missing_current_shares_as_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("run_group_a_tdcc_improved_signal.DEFAULT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("run_group_a_tdcc_improved_signal.LATEST_JSON", tmp_path / "latest.json")
    monkeypatch.setattr("run_group_a_tdcc_improved_signal.LATEST_CSV", tmp_path / "latest.csv")
    base_signal_path = tmp_path / "base.json"
    base_signal_path.write_text("{}", encoding="utf-8")
    base_signal = {
        "requested_as_of_date": "2026-06-06",
        "actual_data_date": "2026-06-05",
        "latest_prices": {"0050.TW": 100.0, "00631L.TW": 50.0, "00632R.TW": 20.0},
        "current_shares": {"0050.TW": 1},
        "current_total_portfolio_value": 1_000.0,
    }
    overlay = {
        "state": "normal",
        "signal_status": "rebalance",
        "signal_reason": "unit_test",
        "base_target_weights": {"0050.TW": 0.5, "00631L.TW": 0.3, "00632R.TW": 0.0},
        "base_target_cash_weight": 0.2,
        "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.3, "00632R.TW": 0.0},
        "target_cash_weight": 0.2,
    }
    config = {
        "strategy_name": "unit_test_strategy",
        "status": "shadow_candidate",
        "base_strategy": "Golden1_0531",
    }

    _, _, summary = _write_improved_signal(
        base_signal_path,
        base_signal,
        {"state": "normal"},
        overlay,
        config,
    )

    assert summary["target_shares"]["00631L.TW"] == 6
    assert summary["trade_log"][1]["current_shares"] == 0
