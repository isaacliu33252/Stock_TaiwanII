from __future__ import annotations

from scripts.evaluate.evaluate_group_a_plus_specialist_router_conditioning import _approx_route


def test_crash_risk_market_state_takes_priority_over_vol_gates() -> None:
    route = _approx_route(high_vol=True, low_vol=False, fine_market_state="crash_risk")

    assert route == "crash_deleverage"


def test_high_vol_gate_wins_when_not_crash_risk() -> None:
    route = _approx_route(high_vol=True, low_vol=False, fine_market_state="bull_trend")

    assert route == "high_volatility"


def test_low_vol_gate_used_when_not_high_vol_or_crash() -> None:
    route = _approx_route(high_vol=False, low_vol=True, fine_market_state="bull_trend")

    assert route == "low_volatility"


def test_defaults_to_neutral_when_no_gate_active() -> None:
    route = _approx_route(high_vol=False, low_vol=False, fine_market_state=None)

    assert route == "neutral"


def test_defaults_to_neutral_when_gates_unavailable() -> None:
    route = _approx_route(high_vol=None, low_vol=None, fine_market_state=None)

    assert route == "neutral"
