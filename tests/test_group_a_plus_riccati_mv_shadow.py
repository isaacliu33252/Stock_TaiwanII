from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from group_a_plus.integrations.riccati_mv_shadow import (
    MeanVarianceSpec,
    active_set_stability_audit,
    build_expected_return_proxy,
    build_riccati_mv_shadow_report,
    cap_only_shadow_weights,
    constrained_mv_shadow_weights,
    damped_cap_weights,
    error_decomposition_snapshot,
    low_risk_negative_control,
    matched_budget_re_evaluation_comparator,
    portfolio_stats,
    realized_volatility_ratio,
    shrink_covariance,
    stability_tuned_re_evaluation_gate,
    two_pass_re_evaluation_shadow,
)


def test_portfolio_stats_and_shrunk_covariance_are_finite() -> None:
    idx = pd.bdate_range("2026-01-02", periods=160)
    returns = pd.DataFrame(
        {
            "0050.TW": np.linspace(-0.01, 0.012, len(idx)),
            "00631L.TW": np.linspace(-0.02, 0.024, len(idx)),
            "00632R.TW": np.linspace(0.015, -0.018, len(idx)),
            "00679B.TWO": np.linspace(0.001, -0.001, len(idx)),
        },
        index=idx,
    )
    cov = shrink_covariance(returns, shrinkage=0.3)
    mu = returns.tail(63).mean()
    stats = portfolio_stats({"0050.TW": 0.5, "00631L.TW": 0.1, "cash": 0.4}, mu, cov)

    assert stats["daily_variance"] >= 0.0
    assert stats["annualized_volatility"] > 0.0


def test_realized_volatility_ratio_uses_00631l_anchor() -> None:
    idx = pd.bdate_range("2026-01-02", periods=80)
    returns = pd.DataFrame(
        {
            "00631L.TW": np.r_[np.full(60, 0.01), np.linspace(-0.03, 0.03, 20)],
            "0050.TW": np.full(80, 0.001),
        },
        index=idx,
    )

    assert realized_volatility_ratio(returns) is not None


def test_stability_tuned_re_evaluation_gate_requires_tail_and_stress() -> None:
    low = stability_tuned_re_evaluation_gate(
        latest_features={"tail_risk_score": 0, "drawdown": -0.04},
        realized_vol_ratio_20_60=1.6,
    )
    stressed = stability_tuned_re_evaluation_gate(
        latest_features={"tail_risk_score": 2, "drawdown": -0.11},
        realized_vol_ratio_20_60=1.0,
    )
    volatile = stability_tuned_re_evaluation_gate(
        latest_features={"tail_risk_score": 2, "drawdown": -0.04},
        realized_vol_ratio_20_60=1.4,
    )

    assert low["gate_active"] is False
    assert stressed["gate_active"] is True
    assert volatile["gate_active"] is True
    assert volatile["params"]["cap_beta"] == 0.5


def test_damped_cap_weights_applies_half_step_to_00631l_only() -> None:
    target = {"0050.TW": 0.47, "00631L.TW": 0.10, "00632R.TW": 0.16, "00679B.TWO": 0.0, "cash": 0.27}
    cap = {"0050.TW": 0.47, "00631L.TW": 0.06, "00632R.TW": 0.05, "00679B.TWO": 0.0, "cash": 0.42}

    weights = damped_cap_weights(target, cap, cap_beta=0.5)

    assert weights["00631L.TW"] == 0.08
    assert weights["00632R.TW"] == 0.16
    assert np.isclose(weights["cash"], 0.29)


def test_low_risk_negative_control_passes_only_when_gate_stays_inactive() -> None:
    features = {"tail_risk_score": 0, "drawdown": -0.03}
    passed = low_risk_negative_control(
        tuned_gate={"gate_active": False},
        latest_features=features,
        realized_vol_ratio_20_60=0.8,
    )
    failed = low_risk_negative_control(
        tuned_gate={"gate_active": True},
        latest_features=features,
        realized_vol_ratio_20_60=0.8,
    )

    assert passed["low_risk_state"] is True
    assert passed["passed"] is True
    assert failed["passed"] is False
    assert failed["verdict"] == "negative_control_failed"


def test_constrained_mv_shadow_respects_cash_and_caps() -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    mu = pd.Series({"0050.TW": 0.0002, "00631L.TW": 0.0008, "00632R.TW": -0.0005, "00679B.TWO": 0.00005})
    cov = pd.DataFrame(np.diag([0.0001, 0.0004, 0.00035, 0.00002]), index=tickers, columns=tickers)
    weights, diagnostic = constrained_mv_shadow_weights(
        mu,
        cov,
        baseline_weights={"0050.TW": 0.5, "00631L.TW": 0.1, "00632R.TW": 0.2, "cash": 0.2},
        spec=MeanVarianceSpec(grid_step=0.05, min_cash=0.25),
    )

    assert diagnostic["status"] == "ok"
    assert weights["cash"] >= 0.25
    assert weights["00631L.TW"] <= 0.20
    assert weights["00632R.TW"] <= 0.25


def test_active_set_stability_audit_reports_perturbation_matches() -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    mu = pd.Series({"0050.TW": 0.0002, "00631L.TW": 0.0001, "00632R.TW": 0.0006, "00679B.TWO": 0.00005})
    cov = pd.DataFrame(np.diag([0.0001, 0.0006, 0.0003, 0.00002]), index=tickers, columns=tickers)
    target = {"0050.TW": 0.45, "00631L.TW": 0.15, "00632R.TW": 0.10, "00679B.TWO": 0.0, "cash": 0.30}

    audit = active_set_stability_audit(
        mu,
        cov,
        target_weights=target,
        spec=MeanVarianceSpec(grid_step=0.05, min_cash=0.25),
    )

    assert audit["policy"] == "research_only_no_weight_change"
    assert audit["source_paper"]["id"] == "2608.17808"
    assert audit["scenario_count"] == 4
    assert 0.0 <= audit["stability_ratio"] <= 1.0
    assert audit["promotion_decision"] == "diagnostic_only_requires_walk_forward_confirmation"


def test_matched_budget_re_evaluation_comparator_reports_frozen_consensus() -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    mu = pd.Series({"0050.TW": 0.0002, "00631L.TW": 0.0001, "00632R.TW": 0.0006, "00679B.TWO": 0.00005})
    cov = pd.DataFrame(np.diag([0.0001, 0.0006, 0.0003, 0.00002]), index=tickers, columns=tickers)
    target = {"0050.TW": 0.45, "00631L.TW": 0.15, "00632R.TW": 0.10, "00679B.TWO": 0.0, "cash": 0.30}
    re_eval = two_pass_re_evaluation_shadow(
        mu,
        cov,
        target_weights=target,
        spec=MeanVarianceSpec(grid_step=0.05, min_cash=0.25),
    )

    report = matched_budget_re_evaluation_comparator(
        mu,
        cov,
        target_weights=target,
        spec=MeanVarianceSpec(grid_step=0.05, min_cash=0.25),
        re_evaluation_shadow=re_eval,
    )

    assert report["policy"] == "research_only_no_weight_change"
    assert report["source_paper"]["id"] == "2608.17808"
    assert "00631L.TW" in report["current_policy_cap_flags"]
    assert "00631L.TW" in report["frozen_policy_consensus_flags"]
    assert 0.0 <= report["frozen_policy_vote_fraction"]["00631L.TW"] <= 1.0
    assert report["promotion_decision"] == "diagnostic_only_not_a_trade_signal"


def test_error_decomposition_snapshot_explains_inactive_tuned_gate() -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    cov = pd.DataFrame(np.diag([0.0001, 0.0006, 0.0003, 0.00002]), index=tickers, columns=tickers)
    target = {"0050.TW": 0.45, "00631L.TW": 0.15, "00632R.TW": 0.10, "00679B.TWO": 0.0, "cash": 0.30}
    shadow = {"0050.TW": 0.45, "00631L.TW": 0.10, "00632R.TW": 0.10, "00679B.TWO": 0.0, "cash": 0.35}

    report = error_decomposition_snapshot(
        target_weights=target,
        shadow_weights=shadow,
        optimizer={"status": "ok", "grid_step": 0.05},
        expected_return_sources={"ncf_sources": {"00631L.TW": {"status": "ok"}}},
        cov=cov,
        active_set_stability={"verdict": "stable_active_set"},
        matched_budget={"agrees_with_frozen_budget": True, "verdict": "current_policy_re_evaluation_supported"},
        tuned_gate={"gate_active": False},
        cap_only_vol_reduction=0.01,
    )

    assert report["policy"] == "research_only_no_weight_change"
    assert report["source_paper"]["id"] == "2608.17808"
    assert report["blockers"] == ["stability_tuned_gate_inactive"]
    assert report["verdict"] == "diagnostic_supported_but_not_actionable"


def test_expected_return_proxy_uses_fresh_ncf(tmp_path: Path) -> None:
    idx = pd.bdate_range("2026-01-02", periods=90)
    returns = pd.DataFrame(
        0.0,
        index=idx,
        columns=["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"],
    )
    ncf_path = tmp_path / "ncf_00631l_latest_20260827.json"
    ncf_path.write_text(
        json.dumps(
            {
                "last_close_date": "2026-08-27",
                "horizon_ensemble": {"weighted_return": 0.01, "direction": "UP", "confidence": 0.8},
            }
        ),
        encoding="utf-8",
    )

    mu, sources = build_expected_return_proxy(returns, as_of="2026-08-27", results_dir=tmp_path)

    assert mu["00631L.TW"] > 0.0
    assert sources["ncf_sources"]["00631L.TW"]["status"] == "ok"


def test_cap_only_shadow_never_adds_inverse_or_leveraged_legs() -> None:
    target = {"0050.TW": 0.47, "00631L.TW": 0.10, "00632R.TW": 0.16, "cash": 0.27}
    raw_shadow = {"0050.TW": 0.075, "00631L.TW": 0.05, "00632R.TW": 0.25, "00679B.TWO": 0.0, "cash": 0.625}

    guarded, events = cap_only_shadow_weights(target, raw_shadow)

    assert guarded["00631L.TW"] == 0.05
    assert guarded["00632R.TW"] == 0.16
    assert guarded["cash"] == 0.32
    assert [event["ticker"] for event in events] == ["00631L.TW"]


def test_two_pass_re_evaluation_shadow_is_research_only_and_cap_only() -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    mu = pd.Series({"0050.TW": 0.0002, "00631L.TW": 0.0001, "00632R.TW": 0.0006, "00679B.TWO": 0.00005})
    cov = pd.DataFrame(np.diag([0.0001, 0.0006, 0.0003, 0.00002]), index=tickers, columns=tickers)
    target = {"0050.TW": 0.45, "00631L.TW": 0.15, "00632R.TW": 0.10, "00679B.TWO": 0.0, "cash": 0.30}

    report = two_pass_re_evaluation_shadow(
        mu,
        cov,
        target_weights=target,
        spec=MeanVarianceSpec(grid_step=0.05, min_cash=0.25),
    )

    second = report["second_pass"]["cap_only_weights"]
    assert report["policy"] == "research_only_no_weight_change"
    assert report["source_paper"]["id"] == "2608.17808"
    assert second["00631L.TW"] <= report["first_pass"]["cap_only_weights"]["00631L.TW"] + 1e-12
    assert second["00632R.TW"] <= report["first_pass"]["cap_only_weights"]["00632R.TW"] + 1e-12
    assert second["cash"] >= report["first_pass"]["cap_only_weights"]["cash"] - 1e-12
    assert report["promotion_decision"] == "shadow_only_requires_multi_window_backtest_before_guard_use"


def test_shadow_report_contract(monkeypatch, tmp_path: Path) -> None:
    idx = pd.bdate_range("2025-01-02", periods=260)
    base = np.linspace(100.0, 120.0, len(idx))
    panel = pd.DataFrame(
        {
            "0050.TW": base,
            "00631L.TW": base * 1.2,
            "00632R.TW": 120.0 - (base - 100.0) * 0.8,
            "00679B.TWO": np.linspace(30.0, 31.0, len(idx)),
        },
        index=idx,
    )

    import group_a_plus.integrations.riccati_mv_shadow as module

    monkeypatch.setattr(module, "load_close_panel", lambda *args, **kwargs: panel)
    plan = {"data": {"target_weights": {"0050.TW": 0.48, "00631L.TW": 0.08, "00632R.TW": 0.23, "cash": 0.21}}}
    report = build_riccati_mv_shadow_report(
        db_path=tmp_path / "unused.db",
        as_of="2026-08-27",
        execution_plan=plan,
        results_dir=tmp_path,
        spec=MeanVarianceSpec(grid_step=0.05),
    )

    assert report["status"] == "ok"
    assert report["policy"] == "research_only_no_weight_change"
    assert report["promotion_decision"] == "shadow_only_needs_backtest_before_any_guard_or_strategy_change"
    assert "shadow_mean_variance_weights" in report
    assert "cap_only_shadow_weights" in report
    assert "adjoint_policy_iteration_shadow" in report
    assert "two_pass_cap_only_weights" in report
    assert "two_pass_recommendations" in report
    assert "stability_tuned_re_evaluation_gate" in report
    assert "stability_tuned_two_pass_weights" in report
    assert "stability_tuned_recommendations" in report
    assert "negative_control" in report
    assert "active_set_stability" in report
    assert "matched_budget_re_evaluation_comparator" in report
    assert "error_decomposition" in report
    assert "cap_only_shadow_stats" in report["risk_state"]
    assert "target_shares" not in report
    assert "execution_regime" not in report
