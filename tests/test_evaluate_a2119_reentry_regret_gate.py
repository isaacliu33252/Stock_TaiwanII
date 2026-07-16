from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.evaluate.evaluate_a2119_reentry_regret_gate import (
    A2119_ACTIONS,
    _event_study_for_window,
    _summarize_results,
)


def test_a2119_actions_exclude_cap_and_deleverage_actions() -> None:
    assert A2119_ACTIONS == ("KEEP", "NO_ADD", "REENTER")
    assert "CAP10" not in A2119_ACTIONS


def test_summarize_results_aggregates_action_counts_and_reliability() -> None:
    summary = _summarize_results(
        [
            {
                "action_counts": {"KEEP": 10, "NO_ADD": 2},
                "non_keep_days": 2,
                "selective_reliability": {
                    "candidate_non_keep_days": 5,
                    "accepted_non_keep_days": 2,
                },
                "delta_vs_baseline": {
                    "delta_final_value": 1.0,
                    "delta_sharpe_ratio": 0.1,
                    "delta_max_drawdown": 0.0,
                },
            },
            {
                "action_counts": {"KEEP": 8, "REENTER": 1},
                "non_keep_days": 1,
                "selective_reliability": {
                    "candidate_non_keep_days": 2,
                    "accepted_non_keep_days": 1,
                },
                "delta_vs_baseline": {
                    "delta_final_value": -1.0,
                    "delta_sharpe_ratio": 0.1,
                    "delta_max_drawdown": 0.0,
                },
            },
        ]
    )

    assert summary["windows"] == 2
    assert summary["triple_pass_windows"] == 1
    assert summary["candidate_non_keep_days"] == 3
    assert summary["action_counts"] == {"KEEP": 18, "NO_ADD": 2, "REENTER": 1}
    assert summary["selective_reliability_acceptance_rate"] == 3 / 7


def test_event_study_reports_00631l_increase_regret() -> None:
    dates = pd.bdate_range("2026-01-01", periods=3)
    frame = pd.DataFrame({"execution_regime": ["defensive", "recovery", "golden1"]}, index=dates)
    target_weights = pd.DataFrame(
        {
            "0050.TW": [0.6, 0.6, 0.6],
            "00631L.TW": [0.0, 0.1, 0.12],
            "00632R.TW": [0.0, 0.0, 0.0],
            "00679B.TWO": [0.0, 0.0, 0.0],
            "cash": [0.4, 0.3, 0.28],
        },
        index=dates,
    )
    labels = pd.DataFrame(
        {"KEEP": [0.0, 0.0, 0.0], "NO_ADD": [0.0, -0.01, 0.02], "REENTER": [0.0, 0.0, 0.0]},
        index=dates,
    )
    prices = pd.DataFrame(index=dates)
    with (
        patch("scripts.evaluate.evaluate_a2119_reentry_regret_gate.run_a2118", return_value=({}, frame)),
        patch("scripts.evaluate.evaluate_a2119_reentry_regret_gate._targets_from_report", return_value=target_weights),
        patch("scripts.evaluate.evaluate_a2119_reentry_regret_gate._load_total_return_prices", return_value=(prices, {})),
        patch("scripts.evaluate.evaluate_a2119_reentry_regret_gate._build_action_labels", return_value=labels),
    ):
        out = _event_study_for_window(
            label="unit",
            start="2026-01-01",
            end="2026-01-05",
            panel_path=None,
            db_path=Path("dummy.db"),
            initial_value=1_000_000.0,
            horizon=20,
            lambda_mdd=0.35,
            gamma_turnover=0.015,
            eta_missed_rebound=0.30,
            commission_rate=0.001,
            slippage_rate=0.0,
            equity_etf_sell_tax=0.001,
        )

    assert out["summary"]["00631l_increase_events"] == 2
    assert out["summary"]["no_add_help_count"] == 1
    assert out["summary"]["no_add_hurt_count"] == 1
    assert out["events"][1]["realized_regret"]["NO_ADD"] == 0.02
