from __future__ import annotations

from scripts.evaluate.evaluate_turnover_capped_execution_shadow import turnover_capped_shadow


def test_turnover_capped_shadow_defers_partial_trade_to_fit_cap() -> None:
    plan = {
        "current_total_assets": 100_000.0,
        "current_prices": {"0050.TW": 100.0, "00631L.TW": 50.0, "00679B.TWO": 25.0},
        "current_holdings": {"0050.TW": 10, "00631L.TW": 0, "00679B.TWO": 1000},
        "target_shares": {"0050.TW": 20, "00631L.TW": 100, "00679B.TWO": 0},
        "execution_controls": {"effective_commission_rate": 0.001425, "slippage_rate": 0.0005},
    }

    out = turnover_capped_shadow(plan, cap_ratio=0.10, priority_mode="buys_first")

    assert out["shadow_plan"]["turnover_notional"] <= out["max_turnover_notional"]
    assert out["shadow_plan"]["target_shares"]["0050.TW"] == 20
    assert out["shadow_plan"]["target_shares"]["00631L.TW"] == 100
    assert out["shadow_plan"]["target_shares"]["00679B.TWO"] == 840
    assert out["shadow_plan"]["deferred_trades"]


def test_turnover_capped_shadow_applies_research_target_override() -> None:
    plan = {
        "current_total_assets": 100_000.0,
        "current_prices": {"0050.TW": 100.0, "00631L.TW": 50.0, "00679B.TWO": 25.0},
        "current_holdings": {"0050.TW": 10, "00631L.TW": 0, "00679B.TWO": 1000},
        "target_shares": {"0050.TW": 20, "00631L.TW": 100, "00679B.TWO": 0},
        "execution_controls": {"effective_commission_rate": 0.001425, "slippage_rate": 0.0005},
    }

    out = turnover_capped_shadow(
        plan,
        cap_ratio=0.50,
        priority_mode="risk_first",
        target_overrides={"00631L.TW": 200},
    )

    assert out["full_plan"]["target_overrides"] == {"00631L.TW": 200}
    assert out["full_plan"]["target_shares"]["00631L.TW"] == 200
