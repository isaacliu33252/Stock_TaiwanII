from __future__ import annotations

import pandas as pd

from scripts.evaluate.compare_group_a_plus_harlf_compound_vs_latest_strategy import build_comparison


def _daily_frame(month_ends: dict[str, float]) -> pd.DataFrame:
    index = pd.to_datetime(list(month_ends))
    return pd.DataFrame({"portfolio_value": list(month_ends.values())}, index=index)


def test_harlf_comparison_aligns_next_month_outcomes_without_live_changes() -> None:
    harlf = {
        "report_type": "group_a_plus_harlf_meta_agent_shadow",
        "monthly_decisions": [
            {"month": "2026-01", "net_return": 0.05},
            {"month": "2026-02", "net_return": 0.04},
        ],
    }
    latest = _daily_frame({"2026-01-31": 100.0, "2026-02-28": 103.0, "2026-03-31": 105.0})
    golden = _daily_frame({"2026-01-31": 100.0, "2026-02-28": 102.0, "2026-03-31": 104.0})

    report = build_comparison(harlf_report=harlf, latest_frame=latest, golden_frame=golden)

    assert report["status"] == "available"
    assert report["monthly_returns"][0]["month"] == "2026-01"
    assert round(report["monthly_returns"][0]["latest_strategy"], 4) == 0.03
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False


def test_harlf_comparison_blocks_without_harlf_rows() -> None:
    report = build_comparison(harlf_report={}, latest_frame=pd.DataFrame(), golden_frame=pd.DataFrame())

    assert report["status"] == "blocked"
    assert "missing_harlf_monthly_decisions" in report["blocking_reasons"]
