import json

from group_a_plus.integrations.specialist_router import append_specialist_routing_shadow_log, route_specialist


def test_crash_risk_overrides_high_vol_and_semiconductor_risk() -> None:
    route = route_specialist(
        volatility_gate={"gate": "high_vol_defensive", "high_vol_gate": True},
        market_state={"state": "crash_risk", "bucket": "crash_risk"},
        ncf_live_overlay={
            "tsmc_0050_health": {
                "status": "available",
                "state": "tsmc_weak_confirmed",
            }
        },
        latest_features={"total_risk_score": 10, "tail_risk_score": 2, "drawdown": -0.08},
    )

    assert route["route"] == "crash_deleverage"
    assert route["trusted_specialists"] == ["risk_control", "drawdown_control"]
    assert route["allow_return_prediction"] is False
    assert route["allow_00631l_add"] is False


def test_semiconductor_risk_routes_to_tsmc_specialist_before_high_vol() -> None:
    route = route_specialist(
        volatility_gate={"gate": "neutral_vol", "high_vol_gate": False},
        market_state={"state": "bull_trend", "bucket": "bull_trend"},
        ncf_live_overlay={
            "tsmc_0050_health": {
                "status": "available",
                "state": "tsmc_led_narrow",
                "reference_guidance": {"allow_00631l_add": False},
            }
        },
        latest_features={"total_risk_score": 3, "tail_risk_score": 0, "drawdown": -0.01},
    )

    assert route["route"] == "semiconductor_risk"
    assert "ncf_2330" in route["trusted_specialists"]
    assert route["recommended_action"] == "avoid_00631l_add"
    assert route["allow_00631l_add"] is False


def test_high_vol_routes_to_volatility_and_drawdown_specialists() -> None:
    route = route_specialist(
        volatility_gate={"gate": "high_vol_defensive", "high_vol_gate": True, "low_vol_gate": False},
        market_state={"state": "bull_pullback_deep"},
        latest_features={"total_risk_score": 5, "tail_risk_score": 0, "drawdown": -0.04},
    )

    assert route["route"] == "high_volatility"
    assert route["trusted_specialists"] == ["volatility_model", "drawdown_model"]
    assert route["signal_reliability"] == "suppress_return_prediction"


def test_low_vol_routes_to_trend_and_momentum_specialists() -> None:
    route = route_specialist(
        volatility_gate={"gate": "low_vol_participation", "high_vol_gate": False, "low_vol_gate": True},
        market_state={"state": "bull_trend"},
        latest_features={"total_risk_score": 2, "tail_risk_score": 0, "drawdown": -0.01},
    )

    assert route["route"] == "low_volatility"
    assert route["trusted_specialists"] == ["trend_model", "momentum_model"]
    assert route["allow_return_prediction"] is True
    assert route["allow_00631l_add"] is True


def test_neutral_route_uses_active_calibrated_strategy() -> None:
    route = route_specialist(
        volatility_gate={"gate": "neutral_vol", "high_vol_gate": False, "low_vol_gate": False},
        market_state={"state": "choppy_range_low_risk"},
        latest_features={"total_risk_score": 4, "tail_risk_score": 0, "drawdown": -0.02},
    )

    assert route["route"] == "neutral"
    assert route["trusted_specialists"] == ["calibrated_ensemble", "risk_score"]
    assert route["policy"] == "advisory_only_no_weight_change"


def test_append_specialist_routing_shadow_log_is_idempotent_per_date(tmp_path) -> None:
    log_path = tmp_path / "specialist_routing_shadow_log.jsonl"
    day1 = {"status": "available", "route": "low_volatility", "risk_level": "low"}
    day2 = {"status": "available", "route": "high_volatility", "risk_level": "medium"}
    day1_rerun = {"status": "available", "route": "neutral", "risk_level": "low"}

    append_specialist_routing_shadow_log(log_path, day1, date="2026-07-01", execution_regime="golden1")
    append_specialist_routing_shadow_log(log_path, day2, date="2026-07-02", execution_regime="golden1")
    append_specialist_routing_shadow_log(log_path, day1_rerun, date="2026-07-01", execution_regime="golden1")

    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 2
    assert rows[0]["date"] == "2026-07-01"
    assert rows[0]["route"] == "neutral"
    assert rows[1]["route"] == "high_volatility"


def test_append_specialist_routing_shadow_log_skips_unavailable(tmp_path) -> None:
    log_path = tmp_path / "specialist_routing_shadow_log.jsonl"

    append_specialist_routing_shadow_log(log_path, {"status": "unavailable"}, date="2026-07-01")

    assert not log_path.exists()
