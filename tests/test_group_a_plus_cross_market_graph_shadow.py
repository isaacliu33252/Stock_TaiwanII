from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.cross_market_graph_shadow import load_cross_market_graph_shadow


def test_load_cross_market_graph_shadow_reads_standard_output_report(tmp_path: Path) -> None:
    report = {
        "success": True,
        "data": {
            "report_type": "cross_market_directed_graph_shadow",
            "generated_at": "2026-07-15T12:00:00",
            "source": {
                "edge_window": 250,
                "stability_threshold": 0.2,
                "source_tickers_available": ["TSM", "SOXX"],
                "target_tickers_available": ["0050.TW", "00631L.TW"],
            },
            "action_model": {
                "policy": "shadow_only_no_weight_change",
                "latest_shadow_action": "NO_ADD",
                "latest_probabilities": {"REENTER": 0.40, "NO_ADD": 0.66},
                "latest_selected_features": ["src_SOXX_ret1d"],
                "metrics": {"NO_ADD": {"auc": 0.53}},
                "metrics_by_year": {"2022": {"NO_ADD": {"auc": 0.56}}},
                "metrics_by_condition": {
                    "condition_0050_5d_abs_ge_2pct": {"NO_ADD": {"auc": 0.54}}
                },
            },
            "promotion_assessment": {
                "recommended_use": "NO_ADD_ONLY_SHADOW_FILTER",
                "promote_to_reentry_signal": False,
            },
        },
    }
    path = tmp_path / "cross_market_directed_graph_shadow_test.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    snapshot = load_cross_market_graph_shadow(report_path=path)

    assert snapshot["status"] == "available"
    assert snapshot["no_add_active"] is True
    assert snapshot["allow_auto_weight_change"] is False
    assert snapshot["latest_probabilities"]["NO_ADD"] == 0.66
    assert snapshot["selected_features"] == ["src_SOXX_ret1d"]
    assert snapshot["promotion_assessment"]["recommended_use"] == "NO_ADD_ONLY_SHADOW_FILTER"
    assert snapshot["metrics_by_year"]["2022"]["NO_ADD"]["auc"] == 0.56
    assert snapshot["metrics_by_condition"]["condition_0050_5d_abs_ge_2pct"]["NO_ADD"]["auc"] == 0.54


def test_load_cross_market_graph_shadow_reports_missing_file(tmp_path: Path) -> None:
    snapshot = load_cross_market_graph_shadow(results_dir=tmp_path)

    assert snapshot["status"] == "unavailable"
    assert snapshot["policy"] == "shadow_only_no_weight_change"


def test_load_cross_market_graph_shadow_prefers_fixed_latest_pointer(tmp_path: Path) -> None:
    older = {
        "data": {
            "action_model": {
                "latest_shadow_action": "KEEP",
                "latest_probabilities": {"REENTER": 0.1, "NO_ADD": 0.1},
            }
        }
    }
    latest = {
        "data": {
            "action_model": {
                "latest_shadow_action": "NO_ADD",
                "latest_probabilities": {"REENTER": 0.2, "NO_ADD": 0.7},
            }
        }
    }
    (tmp_path / "cross_market_directed_graph_shadow_default_tuned_yearly_20260715.json").write_text(
        json.dumps(older),
        encoding="utf-8",
    )
    (tmp_path / "cross_market_directed_graph_shadow_latest.json").write_text(
        json.dumps(latest),
        encoding="utf-8",
    )

    snapshot = load_cross_market_graph_shadow(results_dir=tmp_path)

    assert snapshot["report_path"].endswith("cross_market_directed_graph_shadow_latest.json")
    assert snapshot["latest_shadow_action"] == "NO_ADD"
    assert snapshot["no_add_active"] is True


def test_load_cross_market_graph_shadow_requires_conservative_no_add_probability(tmp_path: Path) -> None:
    report = {
        "data": {
            "action_model": {
                "policy": "shadow_only_no_weight_change",
                "latest_shadow_action": "NO_ADD",
                "latest_probabilities": {"REENTER": 0.40, "NO_ADD": 0.58},
            },
        },
    }
    path = tmp_path / "cross_market_directed_graph_shadow_default_tuned_thresholds_test.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    snapshot = load_cross_market_graph_shadow(results_dir=tmp_path)

    assert snapshot["latest_shadow_action"] == "NO_ADD"
    assert snapshot["no_add_active"] is False
    assert snapshot["thresholds"]["no_add_alert_probability"] == 0.65
