#!/usr/bin/env python3
"""Build the 00631L/0050 relative re-entry advisory shadow report.

The input opportunity evaluator remains a shadow model. This builder only
turns it into a daily, human-readable advisory snapshot with explicit gates;
it never changes target weights or execution instructions.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_opportunity_shadow.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_STRATEGY_TRUST_LOG = PROJECT_ROOT / "results" / "strategy_trust_shadow_log.jsonl"
DEFAULT_RISK_MECHANISM_LOG = PROJECT_ROOT / "results" / "risk_mechanism_shadow_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.md"

PASSING_RISK_MECHANISMS = {"NORMAL", "RECOVERY"}
PASSING_TRUST_LEVELS = {"TRUST"}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _read_last_jsonl(path: str | Path) -> dict[str, Any] | None:
    resolved = _resolve(path)
    if not resolved.exists():
        return None
    last: dict[str, Any] | None = None
    for line in resolved.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        last = json.loads(line)
    return last


def _unwrap_standard(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _live_actual_date(live_signal: dict[str, Any] | None) -> str | None:
    if not live_signal:
        return None
    data = _unwrap_standard(live_signal)
    date = data.get("actual_data_date") or data.get("requested_as_of_date")
    return str(date) if date else None


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _window_priority(window: dict[str, Any]) -> tuple[int, str]:
    label = str(window.get("label") or "")
    bucket = str(window.get("bucket") or "")
    if label == "live_2024_2026":
        rank = 0
    elif label == "active_2025_2026":
        rank = 1
    elif bucket == "tuning_window":
        rank = 2
    else:
        rank = 3
    return (rank, label)


def _primary_window(payload: dict[str, Any]) -> dict[str, Any] | None:
    windows = [row for row in payload.get("results", []) or [] if isinstance(row, dict)]
    if not windows:
        return None
    return sorted(windows, key=_window_priority)[0]


def _all_decisions(window: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("non_keep_decisions", "recent_decisions"):
        for row in window.get(key, []) or []:
            if not isinstance(row, dict) or not row.get("date"):
                continue
            item = dict(row)
            item["source_list"] = key
            out.append(item)
    out.sort(key=lambda row: (str(row.get("date")), 0 if row.get("source_list") == "non_keep_decisions" else 1))
    deduped: dict[str, dict[str, Any]] = {}
    for row in out:
        deduped[str(row["date"])] = row
    return [deduped[date] for date in sorted(deduped)]


def _selected_decision(window: dict[str, Any], as_of: str | None) -> dict[str, Any] | None:
    decisions = _all_decisions(window)
    if not decisions:
        return None
    if as_of:
        for row in decisions:
            if str(row.get("date")) == as_of:
                return row
        prior = [row for row in decisions if str(row.get("date")) <= as_of]
        if prior:
            return prior[-1]
    return decisions[-1]


def _max_window_end(payload: dict[str, Any]) -> str | None:
    ends = []
    for row in payload.get("results", []) or []:
        if not isinstance(row, dict):
            continue
        window = row.get("window") if isinstance(row.get("window"), dict) else {}
        end = window.get("end")
        if end:
            ends.append(str(end))
    return max(ends) if ends else None


def _window_tail_summary(window: dict[str, Any]) -> dict[str, Any]:
    selected = window.get("realized_selected_edge") if isinstance(window.get("realized_selected_edge"), dict) else {}
    method = window.get("method") if isinstance(window.get("method"), dict) else {}
    slow_bear = method.get("slow_bear_gate") if isinstance(method.get("slow_bear_gate"), dict) else {}
    permission = method.get("risk_up_permission_gate") if isinstance(method.get("risk_up_permission_gate"), dict) else {}
    return {
        "label": window.get("label"),
        "bucket": window.get("bucket"),
        "non_keep_days": window.get("non_keep_days"),
        "action_counts": window.get("action_counts"),
        "selected_edge": {
            "count": selected.get("count"),
            "mean": selected.get("mean"),
            "positive_rate": selected.get("positive_rate"),
            "worst": selected.get("worst"),
            "p10": selected.get("p10"),
            "median": selected.get("median"),
            "p90": selected.get("p90"),
        },
        "blocked_days": {
            "slow_bear": slow_bear.get("blocked_days"),
            "risk_up_permission": permission.get("blocked_days"),
        },
    }


def _aggregate_tail_risk(payload: dict[str, Any]) -> dict[str, Any]:
    windows = [row for row in payload.get("results", []) or [] if isinstance(row, dict)]
    summaries = [_window_tail_summary(row) for row in windows]
    selected = [row["selected_edge"] for row in summaries if row["selected_edge"].get("count")]
    worst_values = [float(row["worst"]) for row in selected if row.get("worst") is not None]
    return {
        "selected_edge_worst_across_active_windows": min(worst_values) if worst_values else None,
        "stress_windows": {
            "2018_correction_non_keep_days": next(
                (row.get("non_keep_days") for row in summaries if row.get("label") == "2018_correction"), None
            ),
            "inflation_2022_non_keep_days": next(
                (row.get("non_keep_days") for row in summaries if row.get("label") == "inflation_2022"), None
            ),
        },
        "window_summaries": summaries,
        "limitations": [
            "Drawdown-impact and 5/10/20-day path details are not yet persisted separately; selected edge uses the evaluator's 20-day utility label.",
            "A live/advisory candidate is blocked if data coverage is behind the live signal date.",
        ],
    }


def _gate_snapshot(
    *,
    trust: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    actual_date: str | None,
    coverage_end: str | None,
    selected: dict[str, Any] | None,
    primary_window: dict[str, Any] | None,
) -> dict[str, Any]:
    trust_level = str((trust or {}).get("trust_level") or "MISSING")
    risk_mechanism = str((risk or {}).get("mechanism") or "MISSING")
    selected_date = str((selected or {}).get("date") or "") or None
    coverage_fresh = bool(actual_date and coverage_end and actual_date <= coverage_end)
    exact_date_match = bool(actual_date and selected_date == actual_date)
    model_action = str((selected or {}).get("action") or "KEEP")
    candidate_action = str((selected or {}).get("candidate_action_before_reliability") or model_action)

    checks = {
        "opportunity_input_available": primary_window is not None,
        "coverage_fresh_for_live_date": coverage_fresh,
        "exact_live_date_decision_available": exact_date_match,
        "strategy_trust_pass": trust_level in PASSING_TRUST_LEVELS,
        "risk_mechanism_pass": risk_mechanism in PASSING_RISK_MECHANISMS,
        "model_action_non_keep": model_action != "KEEP",
        "model_internal_gates_pass": bool((selected or {}).get("action_allowed", False)) and bool(
            (selected or {}).get("reliability_gate_pass", False)
        ),
    }
    blockers = [name for name, ok in checks.items() if not ok and name != "model_action_non_keep"]
    advisory_allowed = all(checks.values())
    if advisory_allowed:
        recommended_action = "manual_review_consider_5pct_0050_to_00631l_shift"
    elif candidate_action != "KEEP" and model_action == "KEEP":
        recommended_action = "keep_shadow_only_candidate_blocked_by_model_gate"
    else:
        recommended_action = "keep_shadow_only"
    return {
        "checks": checks,
        "blockers": blockers,
        "latest_strategy_trust": trust,
        "latest_risk_mechanism": risk,
        "coverage": {
            "actual_data_date": actual_date,
            "opportunity_coverage_end": coverage_end,
            "selected_decision_date": selected_date,
        },
        "recommended_action": recommended_action,
        "advisory_allowed": advisory_allowed,
    }


def build_report(
    *,
    opportunity_path: Path,
    live_signal_path: Path,
    strategy_trust_log: Path,
    risk_mechanism_log: Path,
    as_of: str | None = None,
) -> dict[str, Any]:
    if not opportunity_path.exists():
        return {
            "schema_version": 1,
            "report_type": "00631l_0050_relative_reentry_advisory_shadow",
            "status": "unavailable",
            "policy": "shadow_only_no_auto_weight_change",
            "active_allocation_impact": "none",
            "reason": "relative_reentry_opportunity_shadow_missing",
            "input": str(opportunity_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
    opportunity = _load_json(opportunity_path)
    live_signal = _load_json(live_signal_path) if live_signal_path.exists() else None
    actual_date = as_of or _live_actual_date(live_signal)
    primary = _primary_window(opportunity)
    selected = _selected_decision(primary, actual_date) if primary else None
    coverage_end = _max_window_end(opportunity)
    trust = _read_last_jsonl(strategy_trust_log)
    risk = _read_last_jsonl(risk_mechanism_log)
    gates = _gate_snapshot(
        trust=trust,
        risk=risk,
        actual_date=actual_date,
        coverage_end=coverage_end,
        selected=selected,
        primary_window=primary,
    )
    selected_action = str((selected or {}).get("action") or "KEEP")
    shift_weight = float((selected or {}).get("shift_00631l_weight") or 0.0)
    payload = {
        "schema_version": 1,
        "report_type": "00631l_0050_relative_reentry_advisory_shadow",
        "status": "available",
        "policy": "shadow_only_no_auto_weight_change",
        "active_allocation_impact": "none",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": actual_date,
        "input": str(opportunity_path),
        "live_signal": str(live_signal_path),
        "model_snapshot": {
            "primary_window": (primary or {}).get("label"),
            "source_status": opportunity.get("status"),
            "summary": opportunity.get("summary"),
            "selected_decision": selected,
        },
        "advisory_rule": {
            "candidate_action": selected_action,
            "target_shift_from_0050_to_00631l": shift_weight if selected_action != "KEEP" else 0.0,
            "max_shift_from_0050_to_00631l": 0.05,
            "holding_observation_horizon_trading_days": 20,
            "cumulative_signals": "not_allowed",
            "withdrawal_rule": (
                "Revert to A21.18 baseline on the next KEEP decision, any strategy-trust non-TRUST state, "
                "FAST_CRASH/PERSISTENT_DRAWDOWN risk mechanism, stale opportunity coverage, or after 20 trading days."
            ),
            "conflict_rule": "A21.18 live allocation and hard risk guards override this report.",
        },
        "gates": gates,
        "tail_risk_evaluation": _aggregate_tail_risk(opportunity),
        "promotion_requirements": {
            "daily_latest_min_observation_days": 5,
            "preferred_observation_days_before_advisory": 10,
            "requires_strategy_trust": "TRUST",
            "requires_risk_mechanism": sorted(PASSING_RISK_MECHANISMS),
            "requires_exact_live_date_decision": True,
            "requires_fresh_opportunity_coverage": True,
            "requires_manual_review": True,
        },
        "recommended_action": gates["recommended_action"],
        "advisory_allowed": gates["advisory_allowed"],
    }
    return _clean(payload)


def _format_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4%}"
    except (TypeError, ValueError):
        return "n/a"


def build_markdown(payload: dict[str, Any]) -> str:
    gates = payload.get("gates") if isinstance(payload.get("gates"), dict) else {}
    model = payload.get("model_snapshot") if isinstance(payload.get("model_snapshot"), dict) else {}
    tail = payload.get("tail_risk_evaluation") if isinstance(payload.get("tail_risk_evaluation"), dict) else {}
    lines = [
        "# Relative Reentry Advisory Shadow",
        "",
        f"- as_of: `{payload.get('as_of')}`",
        f"- status: `{payload.get('status')}`",
        f"- policy: `{payload.get('policy')}`",
        f"- recommended_action: `{payload.get('recommended_action')}`",
        f"- advisory_allowed: `{payload.get('advisory_allowed')}`",
        f"- primary_window: `{model.get('primary_window')}`",
        f"- summary: `{model.get('summary')}`",
        f"- blockers: `{gates.get('blockers')}`",
        f"- coverage: `{gates.get('coverage')}`",
        f"- worst_selected_edge: `{_format_pct(tail.get('selected_edge_worst_across_active_windows'))}`",
        "",
        "This is shadow-only and has no live allocation impact.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--strategy-trust-log", default=str(DEFAULT_STRATEGY_TRUST_LOG))
    parser.add_argument("--risk-mechanism-log", default=str(DEFAULT_RISK_MECHANISM_LOG))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    payload = build_report(
        opportunity_path=_resolve(args.input),
        live_signal_path=_resolve(args.live_signal),
        strategy_trust_log=_resolve(args.strategy_trust_log),
        risk_mechanism_log=_resolve(args.risk_mechanism_log),
        as_of=args.as_of,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(build_markdown(payload), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Markdown: {output_md}")
    print(f"Status: {payload.get('status')} recommended_action={payload.get('recommended_action')}")


if __name__ == "__main__":
    main()
