#!/usr/bin/env python3
"""Combine A21.19 and A21.20 shadow advisories.

Research-only.  A21.19 remains the higher-level action-regret gate; A21.20 can
only adjust 00631L reentry speed and never overrides hard guards.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_A2119 = PROJECT_ROOT / "results" / "a2119_reentry_regret_gate_7win_20260715.json"
DEFAULT_A2120 = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2120_letf_compounding_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "shadow" / "a2119_a2120_combined_policy_shadow_20260715.json"

VALID_A2119_ACTIONS = {"KEEP", "NO_ADD", "REENTER"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def latest_a2119_decision(report: dict[str, Any]) -> dict[str, Any]:
    latest: dict[str, Any] | None = None
    for window in report.get("windows") or []:
        for decision in window.get("recent_decisions") or []:
            if not isinstance(decision, dict) or not decision.get("date"):
                continue
            row = dict(decision)
            row["window_label"] = window.get("label")
            if latest is None or str(row["date"]) > str(latest.get("date")):
                latest = row
    if latest is not None:
        return latest
    action_counts = (report.get("summary") or {}).get("action_counts") or {}
    action = max(action_counts.items(), key=lambda item: int(item[1]))[0] if action_counts else "KEEP"
    return {"date": None, "action": action, "source": "summary_action_counts"}


def combine_policy(
    *,
    a2119_action: str,
    a2120_regime: str,
    a2120_raw_action: str,
    hard_blockers: list[str] | None = None,
    shadow_target_00631l: int | None = None,
    turnover50_target_00631l: int | None = None,
) -> dict[str, Any]:
    a2119_action = str(a2119_action or "KEEP").upper()
    if a2119_action not in VALID_A2119_ACTIONS:
        a2119_action = "KEEP"
    a2120_regime = str(a2120_regime or "UNAVAILABLE").upper()
    a2120_raw_action = str(a2120_raw_action or "MAINTAIN").upper()
    blockers = [str(item) for item in (hard_blockers or []) if str(item)]

    if blockers:
        combined = "BLOCKED_BY_HARD_GUARD"
        reason = "Hard guards have precedence over A21.19 and A21.20 shadow advisories."
    elif a2119_action == "NO_ADD":
        combined = "NO_ADD"
        reason = "A21.19 NO_ADD has precedence; A21.20 cannot override the action-regret gate."
    elif a2119_action == "REENTER" and a2120_regime == "TREND_PERSISTENT":
        combined = "FAST_REENTER_CANDIDATE"
        reason = "A21.19 allows reentry and A21.20 indicates favorable LETF compounding."
    elif a2119_action == "KEEP" and a2120_raw_action == "FAST_REENTER_CANDIDATE":
        combined = "FAST_REENTER_CANDIDATE"
        reason = "A21.19 does not block additions and A21.20 indicates favorable LETF compounding."
    elif a2120_regime == "MEAN_REVERTING":
        combined = "NO_ADD"
        reason = "A21.20 mean-reverting path diagnostic advises against incremental 00631L adds."
    else:
        combined = a2119_action if a2119_action != "KEEP" else "KEEP"
        reason = "No higher-priority blocker or A21.20 reentry acceleration is active."

    return {
        "combined_action": combined,
        "production_effect": "none",
        "a2119_action": a2119_action,
        "a2120_regime": a2120_regime,
        "a2120_raw_action": a2120_raw_action,
        "hard_blockers": blockers,
        "shadow_target_00631l": shadow_target_00631l,
        "turnover50_target_00631l": turnover50_target_00631l,
        "reason": reason,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    a2119_path = Path(args.a2119_report)
    a2120_path = Path(args.a2120_latest)
    if not a2119_path.is_absolute():
        a2119_path = PROJECT_ROOT / a2119_path
    if not a2120_path.is_absolute():
        a2120_path = PROJECT_ROOT / a2120_path
    a2119 = _read_json(a2119_path)
    a2120 = _read_json(a2120_path)
    a2119_latest = latest_a2119_decision(a2119)
    a2120_state = a2120.get("daily_state") if isinstance(a2120.get("daily_state"), dict) else {}
    forced_action = args.a2119_action.upper() if args.a2119_action else None
    combined = combine_policy(
        a2119_action=forced_action or str(a2119_latest.get("action") or "KEEP"),
        a2120_regime=str(a2120_state.get("compounding_regime") or ""),
        a2120_raw_action=str(a2120_state.get("raw_action") or ""),
        hard_blockers=a2120_state.get("hard_blockers") or [],
        shadow_target_00631l=a2120_state.get("shadow_target_00631l_before_hard_guards"),
        turnover50_target_00631l=a2120_state.get("turnover50_target_00631l"),
    )
    return {
        "schema_version": 1,
        "report_type": "a2119_a2120_combined_policy_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "inputs": {
            "a2119_report": str(a2119_path),
            "a2120_latest": str(a2120_path),
        },
        "policy_order": [
            "hard_guard",
            "A21.19 action-regret gate",
            "A21.20 LETF compounding reentry-speed advisory",
        ],
        "a2119_latest_decision": a2119_latest,
        "a2120_daily_state": a2120_state,
        "combined": combined,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a2119-report", default=str(DEFAULT_A2119))
    parser.add_argument("--a2120-latest", default=str(DEFAULT_A2120))
    parser.add_argument("--a2119-action", choices=sorted(VALID_A2119_ACTIONS), default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Combined action: {report['combined']['combined_action']}")
    print(f"Production effect: {report['production_effect']}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
