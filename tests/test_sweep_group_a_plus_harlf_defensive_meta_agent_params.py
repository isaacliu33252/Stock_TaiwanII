from __future__ import annotations

from scripts.evaluate.sweep_group_a_plus_harlf_defensive_meta_agent_params import build_sweep


def test_harlf_defensive_sweep_stays_research_only() -> None:
    rows = []
    for idx in range(1, 10):
        month = f"2026-{idx:02d}"
        rows.extend(
            [
                {"month": month, "branch": "equal_weight", "net_return": 0.01, "turnover_cost": 0.0},
                {"month": month, "branch": "combined", "net_return": 0.02, "turnover_cost": 0.001},
                {"month": month, "branch": "market_only", "net_return": 0.03, "turnover_cost": 0.001},
                {"month": month, "branch": "sentiment_only", "net_return": 0.04, "turnover_cost": 0.001},
            ]
        )

    report = build_sweep(branch_report={"branch_returns": rows}, thresholds=(0.1, 10.0))

    assert report["status"] == "available"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert len(report["rows"]) == 2
