from __future__ import annotations

import pytest

from scripts.evaluate.evaluate_a2118_dfl_active_date_audit import (
    build_active_date_audit,
    estimate_cap10_cost_per_initial_value,
    turnover_proxy,
)


def _price_lookup(_date: str) -> dict[str, float]:
    return {"0050.TW": 200.0, "00631L.TW": 40.0}


def test_turnover_proxy_uses_00631l_weight_delta_twice() -> None:
    decision = {"base_00631l_weight": 0.126, "final_00631l_weight": 0.106}

    assert turnover_proxy(decision) == pytest.approx(0.04)


def test_estimate_cap10_cost_per_initial_value_counts_sell_and_buy_costs() -> None:
    decision = {"base_00631l_weight": 0.126, "final_00631l_weight": 0.106}

    cost = estimate_cap10_cost_per_initial_value(
        decision,
        initial_value=1_000_000,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )

    assert cost["sell_00631l_notional"] == pytest.approx(20_000)
    assert cost["buy_0050_notional"] == pytest.approx(20_000)
    assert cost["estimated_cost"] == pytest.approx(97.0)
    assert cost["estimated_cost_bps"] == pytest.approx(0.97)


def test_active_date_audit_summarizes_passing_shadow_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.evaluate.evaluate_a2118_dfl_active_date_audit._panel_dates",
        lambda _path: {"2025-01-13"},
    )
    dfl_report = {
        "status": "research_only",
        "method": {
            "actions": ["KEEP", "NO_ADD", "CAP10", "REENTER"],
            "stabilizers": {
                "edge_threshold": 0.0005,
                "reenter_edge_threshold": -0.0005,
                "regret_clip": 0.02,
                "turnover_cap": 0.05,
            },
        },
        "results": [
            {
                "label": "live_2024_2026",
                "bucket": "tuning_window",
                "window": {"start": "2024-01-02", "end": "2026-07-13"},
                "ncf_panel": "panel.csv",
                "non_keep_decisions": [
                    {
                        "date": "2025-01-13",
                        "action": "CAP10",
                        "predicted_regret": 0.0008,
                        "predicted_regrets": {"CAP10": 0.0008},
                        "base_00631l_weight": 0.126,
                        "final_00631l_weight": 0.106,
                        "action_allowed": True,
                    }
                ],
            }
        ],
    }
    overlap_report = {
        "results": [
            {
                "label": "live_2024_2026",
                "decisions": [
                    {
                        "date": "2025-01-13",
                        "volatility_gate": "low_vol_participation",
                        "volatility_high_vol": False,
                        "a2118_extreme_warning_proxy": False,
                        "covered_by_existing_guard": False,
                    }
                ],
            }
        ]
    }

    payload = build_active_date_audit(
        dfl_report,
        overlap_report=overlap_report,
        price_lookup=_price_lookup,
        initial_value=1_000_000,
    )

    assert payload["summary"]["active_days"] == 1
    assert payload["summary"]["all_checks_pass"] is True
    assert payload["summary"]["warning_days"] == 0
    assert payload["summary"]["existing_guard_overlap_days"] == 0
    assert payload["conclusion"] == "passes_replay_audit_shadow_only"
    row = payload["decisions"][0]
    assert row["checks"]["all_pass"] is True
    assert row["share_delta_estimates_per_initial_value"]["00631L.TW"] == pytest.approx(-500)
    assert row["share_delta_estimates_per_initial_value"]["0050.TW"] == pytest.approx(100)


def test_active_date_audit_flags_failed_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.evaluate.evaluate_a2118_dfl_active_date_audit._panel_dates",
        lambda _path: set(),
    )
    dfl_report = {
        "status": "research_only",
        "method": {
            "actions": ["KEEP", "CAP10"],
            "stabilizers": {
                "edge_threshold": 0.0005,
                "regret_clip": 0.02,
                "turnover_cap": 0.05,
            },
        },
        "results": [
            {
                "label": "bad_window",
                "ncf_panel": "panel.csv",
                "non_keep_decisions": [
                    {
                        "date": "2025-01-13",
                        "action": "CAP10",
                        "predicted_regret": 0.0001,
                        "base_00631l_weight": 0.16,
                        "final_00631l_weight": 0.10,
                        "action_allowed": False,
                    }
                ],
            }
        ],
    }

    payload = build_active_date_audit(dfl_report, price_lookup=_price_lookup, initial_value=1_000_000)

    assert payload["summary"]["all_checks_pass"] is False
    assert payload["summary"]["failed_days"] == 1
    checks = payload["decisions"][0]["checks"]
    assert checks["action_allowed"] is False
    assert checks["panel_date_available"] is False
    assert checks["edge_pass"] is False
    assert checks["turnover_cap_configured"] is True
    assert payload["decisions"][0]["warnings"]["turnover_proxy_above_cap"] is True
    assert payload["conclusion"] == "review_required_shadow_only"
