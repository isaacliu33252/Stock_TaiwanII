"""Read-only cross-market directed graph shadow snapshot.

The expensive graph fit is produced by
scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py.  Daily signal
generation only consumes the latest report so it cannot stall live execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from group_a_plus.paths import PROJECT_ROOT


DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"
DEFAULT_PREFERRED_PATTERNS = (
    "cross_market_directed_graph_shadow_latest.json",
    "cross_market_directed_graph_shadow_default_tuned_yearly_*.json",
    "cross_market_directed_graph_shadow_default_tuned_thresholds_*.json",
    "cross_market_directed_graph_shadow_default_tuned_*.json",
    "cross_market_directed_graph_shadow_walkforward_v*.json",
    "cross_market_directed_graph_shadow*.json",
)
NO_ADD_ALERT_THRESHOLD = 0.65


def _unwrap_standard_output(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _latest_report_path(
    results_dir: Path = DEFAULT_RESULTS_DIR,
    patterns: tuple[str, ...] = DEFAULT_PREFERRED_PATTERNS,
) -> Path | None:
    for pattern in patterns:
        candidates = [path for path in results_dir.glob(pattern) if path.is_file()]
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
    return None


def load_cross_market_graph_shadow(
    *,
    report_path: Path | None = None,
    results_dir: Path = DEFAULT_RESULTS_DIR,
) -> dict[str, Any]:
    path = report_path or _latest_report_path(results_dir)
    if path is None:
        return {
            "status": "unavailable",
            "reason": "missing_cross_market_graph_report",
            "policy": "shadow_only_no_weight_change",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = _unwrap_standard_output(payload)
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc),
            "report_path": str(path),
            "policy": "shadow_only_no_weight_change",
        }

    action_model = report.get("action_model") or {}
    latest = action_model.get("latest_probabilities") or {}
    reenter_prob = latest.get("REENTER")
    no_add_prob = latest.get("NO_ADD")
    try:
        reenter_value = float(reenter_prob) if reenter_prob is not None else None
        no_add_value = float(no_add_prob) if no_add_prob is not None else None
    except (TypeError, ValueError):
        reenter_value = None
        no_add_value = None
    latest_action = str(action_model.get("latest_shadow_action") or "UNKNOWN")
    no_add_active = bool(
        no_add_value is not None
        and no_add_value >= NO_ADD_ALERT_THRESHOLD
        and (reenter_value is None or no_add_value > reenter_value)
    )
    return {
        "status": "available",
        "report_path": str(path),
        "report_type": report.get("report_type"),
        "generated_at": report.get("generated_at"),
        "policy": action_model.get("policy", "shadow_only_no_weight_change"),
        "latest_shadow_action": latest_action,
        "no_add_active": no_add_active,
        "recommended_action": "pause_new_risk_adds_manual_review" if no_add_active else "none",
        "allow_auto_weight_change": False,
        "allow_00631l_add_reference": not no_add_active,
        "thresholds": {
            "no_add_alert_probability": NO_ADD_ALERT_THRESHOLD,
        },
        "latest_probabilities": {
            "REENTER": reenter_value,
            "NO_ADD": no_add_value,
        },
        "metrics": action_model.get("metrics"),
        "promotion_assessment": report.get("promotion_assessment"),
        "metrics_by_year": action_model.get("metrics_by_year"),
        "metrics_by_condition": action_model.get("metrics_by_condition"),
        "selected_features": action_model.get("latest_selected_features")
        or action_model.get("selected_features"),
        "source": {
            key: (report.get("source") or {}).get(key)
            for key in (
                "start",
                "end",
                "edge_window",
                "tstat_threshold",
                "stability_threshold",
                "min_windows",
                "walk_forward_edge_selection",
                "min_train_days",
                "retrain_step",
                "source_tickers_available",
                "target_tickers_available",
            )
        },
    }
