#!/usr/bin/env python3
"""Build an A21.20 LETF compounding-regime shadow scorecard.

This consolidates the preferred tuned-threshold evidence into one promotion
gate artifact.  It is research-only, does not run trading logic, and does not
modify production strategy manifests.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_7WIN = PROJECT_ROOT / "results" / "00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_7win_20260715.json"
DEFAULT_COST20 = PROJECT_ROOT / "results" / "00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_7win_cost20bps_20260715.json"
DEFAULT_TURNOVER = PROJECT_ROOT / "results" / "turnover_capped_execution_shadow_20260715_tunedtrend_00631l942_risk_first.json"
DEFAULT_OVERLAP = PROJECT_ROOT / "results" / "a2120_a2119_tunedtrend_overlap_audit_20260715.json"
DEFAULT_REPLAY = PROJECT_ROOT / "results" / "00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50_20260715.json"
DEFAULT_ROLLING = PROJECT_ROOT / "results" / "00631l_compounding_rolling_windows_252d_step126_12win_cost20bps_20260715.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "shadow" / "a2120_letf_compounding_shadow_scorecard_20260715.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _check(name: str, passed: bool, actual: Any, required: str, severity: str = "fail") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "required": required,
        "severity": severity,
    }


def _totals(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("totals") if isinstance(report.get("totals"), dict) else {}


def _replay(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("replay") if isinstance(report.get("replay"), dict) else {}


def build_scorecard(
    *,
    seven_window_report: dict[str, Any],
    cost20_report: dict[str, Any],
    turnover_report: dict[str, Any],
    overlap_report: dict[str, Any],
    replay_report: dict[str, Any],
    rolling_report: dict[str, Any],
) -> dict[str, Any]:
    seven = _totals(seven_window_report)
    cost20 = _totals(cost20_report)
    turnover_result = turnover_report.get("result") if isinstance(turnover_report.get("result"), dict) else {}
    shadow_plan = turnover_result.get("shadow_plan") if isinstance(turnover_result.get("shadow_plan"), dict) else {}
    replay = _replay(replay_report)
    rolling_summary = rolling_report.get("summary") if isinstance(rolling_report.get("summary"), dict) else {}
    rolling_pref = (
        rolling_summary.get("preferred_delta_final_value")
        if isinstance(rolling_summary.get("preferred_delta_final_value"), dict)
        else {}
    )
    rolling_incremental = (
        rolling_summary.get("incremental_delta_final_value")
        if isinstance(rolling_summary.get("incremental_delta_final_value"), dict)
        else {}
    )

    checks = [
        _check(
            "seven_window_positive",
            _int(seven.get("positive_final_value_windows")) >= 7 and _num(seven.get("delta_final_value_sum")) > 0.0,
            {
                "positive_final_value_windows": _int(seven.get("positive_final_value_windows")),
                "delta_final_value_sum": _num(seven.get("delta_final_value_sum")),
            },
            "7/7 positive windows and positive total final-value delta",
        ),
        _check(
            "cost20_positive",
            _int(cost20.get("positive_final_value_windows")) >= 7 and _num(cost20.get("delta_final_value_sum")) > 0.0,
            {
                "transaction_cost_bps": _num(cost20_report.get("transaction_cost_bps")),
                "positive_final_value_windows": _int(cost20.get("positive_final_value_windows")),
                "delta_final_value_sum": _num(cost20.get("delta_final_value_sum")),
            },
            "20 bps cost stress remains 7/7 positive with positive total final-value delta",
        ),
        _check(
            "rolling_cost20_stability",
            bool(rolling_summary.get("pass"))
            and _num(rolling_pref.get("positive_rate")) >= 0.65
            and _num(rolling_pref.get("median")) > 0.0
            and _num(rolling_pref.get("min")) > -2500.0,
            {
                "windows": _int(rolling_summary.get("windows")),
                "transaction_cost_bps": _num(rolling_report.get("transaction_cost_bps")),
                "preferred_positive_rate": _num(rolling_pref.get("positive_rate")),
                "preferred_median": _num(rolling_pref.get("median")),
                "preferred_min": _num(rolling_pref.get("min")),
                "incremental_positive_rate": _num(rolling_incremental.get("positive_rate")),
                "incremental_min": _num(rolling_incremental.get("min")),
            },
            "252d/126d rolling stability with 20 bps cost passes preferred final-value gate",
        ),
        _check(
            "turnover50_reentry_complete",
            _num(shadow_plan.get("turnover_ratio")) <= 0.50
            and _int((shadow_plan.get("target_shares") or {}).get("00631L.TW")) >= _int(replay.get("shadow_target_shares_before_hard_guards")),
            {
                "turnover_ratio": _num(shadow_plan.get("turnover_ratio")),
                "target_00631l": _int((shadow_plan.get("target_shares") or {}).get("00631L.TW")),
                "required_00631l": _int(replay.get("shadow_target_shares_before_hard_guards")),
            },
            "50% turnover-capped shadow completes the tuned 00631L reentry target",
        ),
        _check(
            "a2119_no_conflict",
            _int(overlap_report.get("overlap_no_add_help")) == 0
            and _int(overlap_report.get("overlap_no_add_hurt")) >= _int(overlap_report.get("overlap_events")),
            {
                "overlap_events": _int(overlap_report.get("overlap_events")),
                "overlap_no_add_help": _int(overlap_report.get("overlap_no_add_help")),
                "overlap_no_add_hurt": _int(overlap_report.get("overlap_no_add_hurt")),
            },
            "No A21.20/A21.19 overlap where NO_ADD would help; overlapped events support reentry",
        ),
        _check(
            "hard_guards_not_overridden",
            str(replay.get("recommended_action")) == "BLOCKED_BY_HARD_GUARD"
            and str(replay.get("production_effect")) == "none"
            and bool(replay.get("hard_blockers")),
            {
                "raw_action": replay.get("raw_action"),
                "recommended_action": replay.get("recommended_action"),
                "production_effect": replay.get("production_effect"),
                "hard_blockers": replay.get("hard_blockers"),
            },
            "Replay remains advisory and blocked by hard guards when hard blockers exist",
        ),
    ]

    failed = [item for item in checks if not item["passed"] and item["severity"] == "fail"]
    if failed:
        shadow_decision = "fail"
        advisory_decision = "do_not_enable_daily_advisory"
    else:
        shadow_decision = "pass"
        advisory_decision = "enable_daily_advisory_shadow_only"

    production_blockers = [
        "research_only_shadow_candidate",
        "hard_guards_must_remain_precedence",
            "requires_daily_ops_integration",
            "requires_t_plus_1_execution_alignment_audit",
            "requires_rolling_window_shadow_monitoring_before_production",
        ]
    return {
        "schema_version": 1,
        "report_type": "a2120_letf_compounding_shadow_scorecard",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "strategy_id": "A21.20_LETF_COMPOUNDING_REGIME_SHADOW",
        "candidate": {
            "name": "score3_ar0_persist50_rev50__base40_mr0_trend100",
            "baseline_add_fraction": 0.40,
            "mean_reversion_add_fraction": 0.00,
            "trend_persistent_add_fraction": 1.00,
            "trend_score_min": 3,
            "ar1_trend_min": 0.00,
            "trend_persistence_min": 0.50,
            "reversal_speed_trend_max": 0.50,
        },
        "decision": {
            "shadow_gate": shadow_decision,
            "daily_advisory": advisory_decision,
            "production": "do_not_promote",
            "production_upgrade_pass": False,
            "reason": (
                "Preferred tuned candidate passes the current shadow evidence gate, "
                "but production remains blocked because it is research-only and hard guards must retain precedence."
                if not failed
                else "One or more required shadow evidence gates failed."
            ),
            "production_blockers": production_blockers,
        },
        "checks": checks,
        "summary": {
            "seven_window_delta_final_value_sum": _num(seven.get("delta_final_value_sum")),
            "cost20_delta_final_value_sum": _num(cost20.get("delta_final_value_sum")),
            "rolling_cost20_windows": _int(rolling_summary.get("windows")),
            "rolling_cost20_preferred_positive_rate": _num(rolling_pref.get("positive_rate")),
            "rolling_cost20_preferred_min": _num(rolling_pref.get("min")),
            "rolling_cost20_incremental_min": _num(rolling_incremental.get("min")),
            "turnover50_target_00631l": _int((shadow_plan.get("target_shares") or {}).get("00631L.TW")),
            "turnover50_ratio": _num(shadow_plan.get("turnover_ratio")),
            "a2119_overlap_no_add_help": _int(overlap_report.get("overlap_no_add_help")),
            "replay_raw_action": replay.get("raw_action"),
            "replay_recommended_action": replay.get("recommended_action"),
        },
    }


def _relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seven-window-report", default=str(DEFAULT_7WIN))
    parser.add_argument("--cost20-report", default=str(DEFAULT_COST20))
    parser.add_argument("--turnover-report", default=str(DEFAULT_TURNOVER))
    parser.add_argument("--overlap-report", default=str(DEFAULT_OVERLAP))
    parser.add_argument("--replay-report", default=str(DEFAULT_REPLAY))
    parser.add_argument("--rolling-report", default=str(DEFAULT_ROLLING))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    paths = {
        "seven_window_report": Path(args.seven_window_report),
        "cost20_report": Path(args.cost20_report),
        "turnover_report": Path(args.turnover_report),
        "overlap_report": Path(args.overlap_report),
        "replay_report": Path(args.replay_report),
        "rolling_report": Path(args.rolling_report),
    }
    payload = build_scorecard(
        seven_window_report=_load_json(paths["seven_window_report"]),
        cost20_report=_load_json(paths["cost20_report"]),
        turnover_report=_load_json(paths["turnover_report"]),
        overlap_report=_load_json(paths["overlap_report"]),
        replay_report=_load_json(paths["replay_report"]),
        rolling_report=_load_json(paths["rolling_report"]),
    )
    payload["inputs"] = {name: _relative(path) for name, path in paths.items()}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Shadow gate: {payload['decision']['shadow_gate']}")
    print(f"Daily advisory: {payload['decision']['daily_advisory']}")
    print(f"Production decision: {payload['decision']['production']}")
    print(f"Saved: {output.resolve()}")


if __name__ == "__main__":
    main()
