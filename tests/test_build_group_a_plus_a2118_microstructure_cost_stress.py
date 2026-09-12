from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from scripts.evaluate.build_group_a_plus_a2118_microstructure_cost_stress import (
    COST_SCENARIOS,
    _reprice_target_holding,
    _simulate_costed_curve_with_impact,
    _trade_cost_with_impact,
    build_report,
)


def _adv(value: float = 1_000_000.0) -> dict[str, float]:
    return {
        "0050.TW": value,
        "00631L.TW": value,
        "00632R.TW": value,
        "00679B.TWO": value,
    }


def test_flat_model_ignores_adv() -> None:
    cost, turnover, extra, participation = _trade_cost_with_impact(
        {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0},
        {"0050.TW": 100_000.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0},
        0.001425,
        0.0005,
        0.001,
        _adv(),
        "flat",
        0.0,
        1.0,
    )
    assert turnover == 100_000.0
    assert cost == 100_000.0 * (0.001425 + 0.0005)
    assert extra["0050.TW"] == 0.0
    assert participation["0050.TW"] == 0.0


def test_quadratic_impact_grows_faster_than_linear_at_high_participation() -> None:
    target = {"0050.TW": 900_000.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0}
    current = {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0}
    adv = _adv(1_000_000.0)  # 90% participation
    linear_cost, *_ = _trade_cost_with_impact(current, target, 0.0, 0.0, 0.0, adv, "linear_liquidity", 5.0, 1.0)
    quadratic_cost, *_ = _trade_cost_with_impact(current, target, 0.0, 0.0, 0.0, adv, "quadratic_impact", 5.0, 1.0)
    # at 90% participation, quadratic (x * p^2) cost < linear (x * p) cost per unit bps,
    # but the quadratic model must still respond to ADV -- verify it is nonzero and
    # that halving ADV (doubling participation) raises quadratic cost more than linear cost.
    assert quadratic_cost > 0.0
    assert linear_cost > 0.0
    stressed_adv = _adv(500_000.0)
    linear_cost_stressed, *_ = _trade_cost_with_impact(
        current, target, 0.0, 0.0, 0.0, stressed_adv, "linear_liquidity", 5.0, 1.0
    )
    quadratic_cost_stressed, *_ = _trade_cost_with_impact(
        current, target, 0.0, 0.0, 0.0, stressed_adv, "quadratic_impact", 5.0, 1.0
    )
    linear_ratio = linear_cost_stressed / linear_cost
    quadratic_ratio = quadratic_cost_stressed / quadratic_cost
    assert quadratic_ratio > linear_ratio


def test_adv_stress_divisor_shrinks_effective_adv_and_raises_cost() -> None:
    target = {"0050.TW": 100_000.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0}
    current = {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0}
    adv = _adv(1_000_000.0)
    normal_cost, *_ = _trade_cost_with_impact(current, target, 0.0, 0.0, 0.0, adv, "linear_liquidity", 5.0, 1.0)
    stressed_cost, *_ = _trade_cost_with_impact(current, target, 0.0, 0.0, 0.0, adv, "linear_liquidity", 5.0, 5.0)
    assert stressed_cost > normal_cost


def test_bond_etf_sell_tax_exemption_still_applies_under_impact_models() -> None:
    current = {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 100_000.0}
    target = {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0}
    cost, *_ = _trade_cost_with_impact(
        current, target, 0.001425, 0.0005, 0.001, _adv(), "quadratic_impact", 25.0, 1.0
    )
    # sell tax (0.001) must be excluded for the bond ETF -- only commission + slippage apply.
    assert cost < 100_000.0 * (0.001425 + 0.0005 + 0.001)


def test_simulate_costed_curve_with_impact_matches_flat_baseline_when_no_impact() -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    prices = pd.DataFrame({t: [100.0, 101.0, 102.0] for t in tickers}, index=idx)
    adv = pd.DataFrame({t: [1_000_000.0] * 3 for t in tickers}, index=idx)
    regimes = pd.Series(["a", "a", "b"], index=idx)
    weights_by_regime = {
        "a": {"0050.TW": 1.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.0},
        "b": {"0050.TW": 0.0, "00631L.TW": 1.0, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.0},
    }
    curve_flat, stats_flat = _simulate_costed_curve_with_impact(
        prices, adv, regimes, weights_by_regime, 1_000_000.0, 0.001425, 0.0005, 0.001, "flat", 0.0, 1.0
    )
    curve_impact, stats_impact = _simulate_costed_curve_with_impact(
        prices, adv, regimes, weights_by_regime, 1_000_000.0, 0.001425, 0.0005, 0.001, "quadratic_impact", 25.0, 1.0
    )
    assert stats_flat["extra_impact_cost"] == 0.0
    assert stats_impact["extra_impact_cost"] > 0.0
    # the impact model must always cost at least as much as the flat baseline
    assert curve_impact.iloc[-1] <= curve_flat.iloc[-1]


def test_all_cost_scenarios_defined_for_current_stress_and_2x() -> None:
    names = {s["name"] for s in COST_SCENARIOS}
    assert "1x_current_cost" in names
    assert any("stress_liquidity" in n for n in names)
    assert any("2x_realistic_impact" in n for n in names)


def test_reprice_target_holding_reports_unavailable_without_snapshot(tmp_path) -> None:
    with (
        patch(
            "scripts.evaluate.build_group_a_plus_a2118_microstructure_cost_stress._load_target_holding_json",
            return_value={},
        ),
    ):
        result = _reprice_target_holding(tmp_path / "missing.db")
    assert result["status"] == "unavailable"


@patch("scripts.evaluate.build_group_a_plus_a2118_microstructure_cost_stress._reprice_target_holding")
@patch("scripts.evaluate.build_group_a_plus_a2118_microstructure_cost_stress._load_adv_history")
@patch("scripts.evaluate.build_group_a_plus_a2118_microstructure_cost_stress._load_total_return_prices")
@patch("scripts.evaluate.build_group_a_plus_a2118_microstructure_cost_stress.run_a2118")
def test_build_report_runs_all_scenarios_at_every_nav_scale(
    mock_run_a2118, mock_prices, mock_adv, mock_reprice
) -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    idx = pd.date_range("2024-01-01", periods=4, freq="B")
    regime = pd.Series(["golden", "golden", "defensive", "defensive"], index=idx)
    frame = pd.DataFrame({"execution_regime": regime}, index=idx)
    weights_by_regime = {
        "golden": {"0050.TW": 0.7, "00631L.TW": 0.3, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.0},
        "defensive": {"0050.TW": 0.4, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.3, "cash": 0.3},
    }
    mock_run_a2118.return_value = ({"base_weights": weights_by_regime}, frame)
    mock_prices.return_value = (pd.DataFrame({t: [100.0] * 4 for t in tickers}, index=idx), {})
    mock_adv.return_value = pd.DataFrame({t: [1_000_000.0] * 4 for t in tickers}, index=idx)
    mock_reprice.return_value = {"status": "ok"}

    report = build_report(nav_scales=(1_000_000.0, 10_000_000.0))

    assert len(report["nav_scale_results"]) == 2
    for nav_row in report["nav_scale_results"]:
        assert len(nav_row["scenarios"]) == len(COST_SCENARIOS)
    assert report["raw_vs_guarded_target_reprice_at_current_aum"] == {"status": "ok"}
