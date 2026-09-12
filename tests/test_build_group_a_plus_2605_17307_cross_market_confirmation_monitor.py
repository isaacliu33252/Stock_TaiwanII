from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2605_17307_cross_market_confirmation_monitor import (
    build_monitor,
    write_monitor,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _inputs(tmp_path: Path, *, graph_end: str = "2026-08-25", no_add: bool = False, tsi_alarm: bool = False) -> dict:
    source_status = {
        ticker: {
            "status": "available",
            "latest_date": "2026-08-25",
            "source_table": "external_market_ohlcv",
        }
        for ticker in ("SOXX", "QQQ", "NVDA", "TSM", "^VIX", "TWD=X", "^TNX", "0050.TW", "00631L.TW", "2330.TW")
    }
    return {
        "strategy_path": _write(
            tmp_path / "strategy.json",
            {"active_strategy": {"id": "a2118_a2111_ncf_late_bull_deleverage"}},
        ),
        "tsi_path": _write(
            tmp_path / "tsi.json",
            {
                "status": "available",
                "date": "2026-08-25",
                "alarm_active": tsi_alarm,
                "latest": {"tsi_memory_percentile": 0.50, "tsi_percentile": 0.40, "observations": 20},
                "source_status": source_status,
            },
        ),
        "mingle_path": _write(
            tmp_path / "mingle.json",
            {
                "dates": {"end": "2026-08-25"},
                "decision": {"target_weight_change_allowed": False, "promotion_allowed": False},
                "target_diversification": {"weighted_graph_degree": 8.0, "peripheral_alignment": 0.1},
            },
        ),
        "cross_graph_path": _write(
            tmp_path / "cross_graph.json",
            {
                "data": {
                    "report_type": "cross_market_directed_graph_shadow",
                    "generated_at": "2026-08-25T12:00:00",
                    "source": {"end": graph_end},
                    "action_model": {
                        "policy": "shadow_only_no_weight_change",
                        "latest_shadow_action": "NO_ADD" if no_add else "KEEP",
                        "latest_probabilities": {"REENTER": 0.2, "NO_ADD": 0.7 if no_add else 0.2},
                        "metrics": {"NO_ADD": {"auc": 0.53}, "REENTER": {"auc": 0.48}},
                        "latest_selected_features": ["src_SOXX_ret1d"],
                    },
                }
            },
        ),
        "as_of": "2026-08-25",
    }


def test_monitor_reports_good_when_sources_and_confirmation_are_fresh(tmp_path: Path) -> None:
    report = build_monitor(**_inputs(tmp_path))

    assert report["cross_market_confirmation"]["state"] == "GOOD"
    assert report["decision"]["can_confirm_new_risk_adds"] is True
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["latest_strategy"] == "a2118_a2111_ncf_late_bull_deleverage"


def test_monitor_reports_weak_when_directed_graph_is_stale(tmp_path: Path) -> None:
    report = build_monitor(**_inputs(tmp_path, graph_end="2026-07-15"))

    assert report["cross_market_confirmation"]["state"] == "WEAK"
    assert "directed_graph_shadow_stale_for_daily_confirmation" in report["cross_market_confirmation"]["reasons"]
    assert report["decision"]["can_confirm_new_risk_adds"] is False


def test_monitor_reports_failed_when_no_add_is_active(tmp_path: Path) -> None:
    report = build_monitor(**_inputs(tmp_path, no_add=True))

    assert report["cross_market_confirmation"]["state"] == "FAILED"
    assert "cross_market_graph_no_add_active" in report["cross_market_confirmation"]["reasons"]
    assert report["decision"]["blocks_live_trade"] is False


def test_monitor_reports_failed_when_tsi_alarm_is_active(tmp_path: Path) -> None:
    report = build_monitor(**_inputs(tmp_path, tsi_alarm=True))

    assert report["cross_market_confirmation"]["state"] == "FAILED"
    assert "cross_market_network_stress_high" in report["cross_market_confirmation"]["reasons"]


def test_write_monitor_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2605_17307_cross_market_confirmation_monitor",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_monitor(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2605_17307_cross_market_confirmation_monitor_20260825.json").exists()
