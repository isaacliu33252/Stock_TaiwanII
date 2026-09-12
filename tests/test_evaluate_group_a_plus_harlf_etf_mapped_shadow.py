from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_harlf_etf_mapped_shadow import build_mapped_shadow


def test_harlf_etf_mapped_shadow_removes_2330_from_meta_weights() -> None:
    close = pd.DataFrame(
        {
            "0050": [100.0, 105.0, 103.0],
            "00631L": [50.0, 60.0, 54.0],
            "00632R": [10.0, 9.0, 9.5],
            "00679B": [30.0, 30.3, 30.6],
            "2330": [800.0, 880.0, 836.0],
        },
        index=pd.to_datetime(["2026-01-31", "2026-02-28", "2026-03-31"]),
    )
    branch = {
        "branch_returns": [
            {
                "month": "2026-01",
                "branch": "sentiment_only",
                "weights": {"0050": 0.25, "00631L": 0.25, "00632R": 0.0, "00679B": 0.0, "2330": 0.5},
            },
            {
                "month": "2026-02",
                "branch": "sentiment_only",
                "weights": {"0050": 0.0, "00631L": 0.5, "00632R": 0.0, "00679B": 0.0, "2330": 0.5},
            },
        ]
    }
    meta = {
        "monthly_decisions": [
            {"month": "2026-01", "selected_branch": "sentiment_only"},
            {"month": "2026-02", "selected_branch": "sentiment_only"},
        ]
    }

    report = build_mapped_shadow(branch_report=branch, meta_report=meta, close=close)

    assert report["status"] == "available"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    for payload in report["variants"].values():
        assert payload["non_etf_assets"] == []
        assert "2330" not in payload["meta_agent_used_assets"]
        assert payload["meta_agent_metrics"]["n"] == 2


def test_harlf_etf_mapped_shadow_blocks_missing_close_prices() -> None:
    report = build_mapped_shadow(branch_report={}, meta_report={}, close=pd.DataFrame())

    assert report["status"] == "blocked"
    assert "missing_close_prices" in report["blocking_reasons"]
    assert report["decision"]["promotion_ready"] is False
