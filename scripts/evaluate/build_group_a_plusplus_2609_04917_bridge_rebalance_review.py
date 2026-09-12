#!/usr/bin/env python3
"""Review the 2609.04917 turnover bridge against rebalance blockers.

The output is shadow-only. It can show whether a bridge plan resolves stale
date and leveraged-add blockers, but it never enables automatic rebalancing.
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

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_BRIDGE_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow.json"
DEFAULT_HETEROGENEOUS_VOL = PROJECT_ROOT / "report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_rebalance_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_rebalance_review.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _int_map(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if str(k) != "cash"}


def _has_leveraged_add(plan: dict[str, Any], ticker: str = "00631L.TW") -> bool:
    current = _int_map(plan.get("current_holdings"))
    target = _int_map(plan.get("target_shares") or plan.get("bridge_target_shares"))
    return int(target.get(ticker, 0)) > int(current.get(ticker, 0))


def build_review(
    *,
    live_signal: dict[str, Any],
    bridge_plan: dict[str, Any],
    heterogeneous_vol: dict[str, Any],
) -> dict[str, Any]:
    live_date = live_signal.get("actual_data_date")
    plan_date = bridge_plan.get("actual_data_date")
    date_aligned = bool(live_date and plan_date and str(live_date) == str(plan_date))
    hetero_advisory = heterogeneous_vol.get("advisory") if isinstance(heterogeneous_vol.get("advisory"), dict) else {}
    hetero_blocks_add = bool(hetero_advisory.get("active")) and str(
        hetero_advisory.get("suggested_review")
    ) == "avoid_adding_00631l_until_manual_review"
    bridge_adds_00631l = _has_leveraged_add(bridge_plan)
    turnover = (bridge_plan.get("computed") or {}).get("bridge_turnover")
    blockers: list[str] = []
    warnings: list[str] = []
    if not date_aligned:
        blockers.append("bridge_plan_date_not_aligned_with_live_signal")
    if hetero_blocks_add and bridge_adds_00631l:
        blockers.append("heterogeneous_vol_blocks_00631l_add_and_bridge_adds_00631l")
    if turnover is None:
        warnings.append("bridge_turnover_missing")
    elif float(turnover) > 0.50:
        blockers.append("bridge_turnover_exceeds_50pct")
    if bridge_plan.get("status") != "shadow_bridge_available_for_manual_review":
        blockers.append(f"bridge_plan_status={bridge_plan.get('status') or 'missing'}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_bridge_rebalance_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_bridge_rebalance_review_no_auto_rebalance",
        "status": "ready_for_human_rebalance_review" if not blockers else "blocked",
        "as_of": live_signal.get("requested_as_of_date") or live_date,
        "checks": {
            "live_signal_actual_data_date": live_date,
            "bridge_plan_actual_data_date": plan_date,
            "date_aligned": date_aligned,
            "heterogeneous_vol_blocks_00631l_add": hetero_blocks_add,
            "bridge_adds_00631l": bridge_adds_00631l,
            "bridge_turnover": turnover,
            "bridge_execution_allowed": bridge_plan.get("execution_allowed"),
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "auto_rebalance_allowed": False,
            "manual_review_required": True,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "summary": (
                "Bridge resolves the stale-date and 00631L-add rebalance blockers for manual review only."
                if not blockers
                else "Bridge is not ready even for manual rebalance review."
            ),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    return "\n".join(
        [
            "# 2609.04917 Bridge Rebalance Review",
            "",
            f"- status: {report['status']}",
            f"- date_aligned: {checks['date_aligned']}",
            f"- bridge_turnover: {checks['bridge_turnover']}",
            f"- bridge_adds_00631l: {checks['bridge_adds_00631l']}",
            f"- manual_review_required: {report['decision']['manual_review_required']}",
            f"- auto_rebalance_allowed: {report['decision']['auto_rebalance_allowed']}",
            f"- blocking_reasons: {', '.join(report['blocking_reasons']) or 'none'}",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--bridge-plan", default=str(DEFAULT_BRIDGE_PLAN))
    parser.add_argument("--heterogeneous-vol", default=str(DEFAULT_HETEROGENEOUS_VOL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    live_signal_path = _resolve(args.live_signal)
    bridge_plan_path = _resolve(args.bridge_plan)
    heterogeneous_vol_path = _resolve(args.heterogeneous_vol)
    report = build_review(
        live_signal=_load(live_signal_path),
        bridge_plan=_load(bridge_plan_path),
        heterogeneous_vol=_load(heterogeneous_vol_path),
    )
    report["inputs"] = {
        "live_signal": str(live_signal_path),
        "bridge_plan": str(bridge_plan_path),
        "heterogeneous_vol": str(heterogeneous_vol_path),
    }
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"], "checks": report["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
