from __future__ import annotations

from scripts.evaluate.diagnose_group_a_plus_harlf_oos_failure import build_diagnosis


def test_harlf_oos_failure_diagnosis_identifies_drawdown_gate_failure() -> None:
    comparison = {
        "monthly_returns": [
            {"month": "2026-01", "harlf_compound": 0.04, "latest_strategy": 0.02, "golden01_0531": 0.02},
            {"month": "2026-02", "harlf_compound": -0.04, "latest_strategy": -0.02, "golden01_0531": -0.02},
            {"month": "2026-03", "harlf_compound": 0.06, "latest_strategy": 0.02, "golden01_0531": 0.02},
            {"month": "2026-04", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
        ]
    }
    temporal = {"holdout_window": {"months": ["2026-04"], "n": 1}, "blocking_reasons": ["x"]}
    mapped = {
        "variants": {
            "drop_2330_renormalize": {
                "branch_returns": [
                    {"month": "2026-01", "branch": "sentiment_only", "net_return": 0.04},
                    {"month": "2026-02", "branch": "sentiment_only", "net_return": -0.04},
                    {"month": "2026-03", "branch": "sentiment_only", "net_return": 0.06},
                ]
            }
        }
    }

    report = build_diagnosis(comparison=comparison, mapped_shadow=mapped, temporal_oos=temporal)

    assert report["status"] == "available"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["current_8pct_sleeve_rejected"] is True
    assert report["primary_failure"]["minimum_positive_weight_passed_drawdown_gate"] is False
    assert report["primary_failure"]["drawdown_gate_blocker_months"] == ["2026-02"]


def test_harlf_oos_failure_diagnosis_blocks_missing_inputs() -> None:
    report = build_diagnosis(comparison={}, mapped_shadow={}, temporal_oos={})

    assert report["status"] == "blocked"
    assert "missing_comparison_monthly_returns" in report["blocking_reasons"]
    assert report["decision"]["promotion_ready"] is False
