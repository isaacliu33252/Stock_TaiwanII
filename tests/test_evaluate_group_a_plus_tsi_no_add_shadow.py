from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import (
    add_tsi_to_detector_frame,
    build_tsi_overlap_report,
    write_report,
)


def test_tsi_overlap_reports_unique_coverage() -> None:
    idx = pd.bdate_range("2026-01-02", periods=4)
    detectors = pd.DataFrame(
        {
            "volatility_gate": [True, False, False, False],
            "extreme_warning_proxy": [False, False, False, False],
            "compounding_mean_reverting": [False, True, False, False],
            "crash_risk_alert_2of3": [False, False, True, False],
            "market_state_crash_like": [False, False, False, False],
            "specialist_router_crash_deleverage": [False, False, False, False],
        },
        index=idx,
    )
    tsi = pd.Series([False, True, True, True], index=idx)

    report = build_tsi_overlap_report(add_tsi_to_detector_frame(detectors, tsi))

    assert report["report_type"] == "group_a_plus_tsi_detector_overlap"
    assert report["active_days"]["tsi_stress_alert"] == 3
    assert report["tsi_unique_coverage"]["days_active_while_no_blocking_guard_active"] == 2
    assert report["tsi_unique_coverage"]["days_active_while_no_existing_alert_or_blocking_active"] == 1


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_no_add_shadow",
        "policy": "slow_or_block_incremental_00631l_add_only_when_tsi_stress_alert_active",
        "tsi_threshold": 0.9,
        "alert_mode": "tsi_only",
        "guard_add_fraction": 0.0,
        "production_effect": "none",
        "overlap": {
            "window": {"start": "2026-01-02", "end": "2026-01-07"},
            "tsi_unique_coverage": {
                "active_days": 3,
                "days_active_while_no_blocking_guard_active": 2,
                "days_active_while_no_existing_alert_or_blocking_active": 1,
            },
        },
        "windows": [
            {
                "label": "fixture",
                "kind": "test",
                "tsi_alert_days": 2,
                "tsi_no_add": {"blocked_days": 1},
                "delta_vs_baseline": {"final_value": 100.0, "sharpe_ratio": 0.1, "max_drawdown": 0.0},
            }
        ],
        "totals": {"blocked_days": 1},
        "decision": {"promotion_allowed": False, "target_weight_change_allowed": False},
    }
    output = tmp_path / "latest" / "tsi_no_add_shadow.json"
    output_md = tmp_path / "latest" / "tsi_no_add_shadow.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_no_add_shadow"
    assert "No-Add Counterfactual" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_no_add_shadow_*.json"))
