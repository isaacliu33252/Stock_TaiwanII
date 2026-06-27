#!/usr/bin/env python3
"""Create the current formal GroupA+ baseline pointer and snapshot."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
BASELINE_POINTER = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"
BASELINE_SNAPSHOT = PROJECT_ROOT / "results" / "group_a_plus_formal_baseline_20260613.json"


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))


def _load_existing_baseline() -> dict[str, Any]:
    if not BASELINE_POINTER.exists():
        return {}
    return json.loads(BASELINE_POINTER.read_text(encoding="utf-8"))


def _existing_or_latest_reference(
    existing: dict[str, Any],
    config: dict[str, Any],
    key: str,
    fallback: str,
    *,
    choose_newest_json: bool = False,
) -> str:
    latest_reference = dict(config.get("latest_reference", {}) or {})
    candidates = [
        str(value)
        for value in (existing.get(key), latest_reference.get(key), fallback)
        if value
    ]
    if not choose_newest_json:
        return candidates[0]

    def sort_key(value: str) -> tuple[str, float]:
        path = PROJECT_ROOT / value
        if not path.exists():
            return ("", -1.0)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            actual_date = str(payload.get("actual_data_date") or "")
        except Exception:
            actual_date = ""
        return (actual_date, path.stat().st_mtime)

    existing_candidates = [value for value in candidates if (PROJECT_ROOT / value).exists()]
    if not existing_candidates:
        return candidates[0]
    return max(existing_candidates, key=sort_key)


def _current_improvement_review(config: dict[str, Any]) -> dict[str, Any] | None:
    profile = str(config.get("recommended_profile", {}).get("name") or config.get("name") or "")
    if "turn12" in profile:
        return {
            "decision": "promote_balanced_turnover_cap_12pct",
            "reason": (
                "turn12 在 turn08/turn10/turn12 中具備較佳平衡分數。"
                "擴大檢查至 turn15/18/20/25 後，turn12 仍是通過 stress guardrail 的高分 profile。"
                "turn15 的 strict-cost final 較高，但 stress guardrail 較弱，因此保留為 research-only。"
                "如果唯一目標是降低 worst-window final drag，turn08 可作 tail-risk fallback。"
            ),
            "multi_window_aggregate": [],
            "strict_cost_best_by_final": "GroupA+_focused_tdcc_0258_stab3_turn15",
            "strict_cost_best_by_sharpe": "GroupA+_focused_tdcc_0258_stab3_turn15",
            "balanced_profile_score": "results/group_a_plus_turnover_profile_score_20260613.json",
        }
    if "turn08" not in profile:
        return None
    return {
        "decision": "promote_risk_first_turnover_cap_08pct",
        "reason": (
            "turn08 improves multi-window stress robustness versus turn12: "
            "worst-window final drag improves from -24645 to -12073, min Sharpe delta "
            "improves from +0.0122 to +0.0171, and GFC/2015/2016 stress-window costs are lower. "
            "It sacrifices 2025-2026 strict-cost final versus turn12, so this is a risk-first profile."
        ),
        "multi_window_aggregate": [],
        "strict_cost_best_by_final": "GroupA+_focused_tdcc_0258_stab3_turn15",
        "strict_cost_best_by_sharpe": "GroupA+_focused_tdcc_0258_stab3_turn15",
    }


def main() -> None:
    config = _load("group_a_plus_config.json")
    existing = _load_existing_baseline()
    clean_payload_path = "results/group_a_payload_clean_cashdiv_dca8000_20260612.json"
    signal_path = _existing_or_latest_reference(
        existing,
        config,
        "latest_group_a_signal",
        "results/signal_group_a_20260613_004617.json",
        choose_newest_json=True,
    )
    plus_signal_path = _existing_or_latest_reference(
        existing,
        config,
        "latest_group_a_plus_final_signal",
        "results/group_a_plus_final_signal_20260613_6p12data.json",
        choose_newest_json=True,
    )
    stress_path = _existing_or_latest_reference(
        existing,
        config,
        "stress_test_result",
        "results/group_a_plus_multi_window_stress_20260612.json",
    )
    strict_cost_path = _existing_or_latest_reference(
        existing,
        config,
        "strict_cost_result",
        "results/group_a_plus_strict_cost_dca8000_20260612.json",
    )

    clean_payload = _load(clean_payload_path)
    group_a_result = clean_payload["group_a"]["result"]
    signal = _load(signal_path)
    plus_signal = _load(plus_signal_path)
    stress = _load(stress_path)

    baseline = {
        "name": "GroupA+ formal baseline",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "active_baseline",
        "profile": config.get("recommended_profile", {}).get("name", config.get("name")),
        "config": "group_a_plus_config.json",
        "clean_payload": clean_payload_path,
        "latest_group_a_signal": signal_path,
        "latest_group_a_plus_final_signal": plus_signal_path,
        "stress_test_result": stress_path,
        "strict_cost_result": strict_cost_path,
        "policy": {
            "dca": clean_payload["group_a_dca_config"],
            "dividend": clean_payload["group_a_dividend_config"],
            "dynamic_dca": "disabled",
            "dividend_reinvestment": "disabled",
        },
        "group_a_clean_replay": {
            "final_value": float(group_a_result["final_value"]),
            "sharpe": float(group_a_result["rl_metrics"]["sharpe"]),
            "max_drawdown": float(group_a_result["rl_metrics"]["max_drawdown"]),
            "dca_total_contributions": float(group_a_result["dca_total_contributions"]),
            "total_dividend_credited": float(group_a_result["total_dividend_credited"]),
            "dividend_mode": str(group_a_result["dividend_config"]["mode"]),
        },
        "latest_signal": {
            "signal_status": signal.get("signal_status"),
            "signal_reason": signal.get("signal_reason"),
            "requested_as_of_date": signal.get("requested_as_of_date"),
            "actual_data_date": signal.get("actual_data_date"),
            "stale_days": signal.get("stale_days"),
            "action_label": signal.get("action_label"),
            "candidate_target_label": signal.get("candidate_target_label"),
            "effective_target_label": signal.get("effective_target_label"),
        },
        "group_a_plus_final_signal": {
            "status": "active_final_signal",
            "source_status": plus_signal.get("status"),
            "actual_data_date": plus_signal.get("actual_data_date"),
            "signal_status": plus_signal.get("signal_status"),
            "signal_reason": plus_signal.get("signal_reason"),
            "overlay_regime": (plus_signal.get("overlay_policy") or {}).get("regime"),
            "overlay_00679b_weight": plus_signal.get("overlay_00679b_weight"),
            "target_shares": plus_signal.get("target_shares"),
            "execution_summary": plus_signal.get("execution_summary"),
        },
        "stress_summary": {
            label: {
                "base": item.get("base_metrics"),
                "group_a_plus": item.get("group_a_plus_metrics"),
                "delta_plus_vs_base": item.get("delta_plus_vs_base"),
            }
            for label, item in stress.get("strategies", {}).items()
        },
    }
    for key in ("turnover_cap_multi_window_sweep", "strict_cost_turnover_compare"):
        if key in existing:
            baseline[key] = existing[key]
    refreshed_review = _current_improvement_review(config)
    if refreshed_review is not None:
        previous_review = dict(existing.get("improvement_review_20260613") or {})
        refreshed_review["multi_window_aggregate"] = list(previous_review.get("multi_window_aggregate") or [])
        baseline["improvement_review_20260613"] = refreshed_review
    elif "improvement_review_20260613" in existing:
        baseline["improvement_review_20260613"] = existing["improvement_review_20260613"]
    BASELINE_SNAPSHOT.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    BASELINE_POINTER.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Pointer:  {BASELINE_POINTER}")
    print(f"Snapshot: {BASELINE_SNAPSHOT}")
    print(f"Profile:  {baseline['profile']}")
    print(f"Signal:   {baseline['latest_signal']['signal_status']} / {baseline['latest_signal']['signal_reason']}")


if __name__ == "__main__":
    main()
