#!/usr/bin/env python3
"""Review the 00632R 30d tail tracking-error gate.

This explains whether the failing 30d p05 tracking-error gate is a persistent
near-term issue or a conservative full-sample auto-trading blocker. It does not
open 00632R, change target weights, or permit rebalance.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LETF_TRACKING = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_MANUAL_HEDGE = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_manual_hedge_eligibility_review.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/00632r_tail_tracking_error_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _horizon_metric(letf_tracking: dict[str, Any], horizon: str = "30") -> dict[str, Any]:
    summary = letf_tracking.get("tracking_error_summary")
    ticker = (summary or {}).get("00632R.TW") if isinstance(summary, dict) else {}
    metrics = (ticker or {}).get("horizon_metrics") if isinstance(ticker, dict) else {}
    row = (metrics or {}).get(horizon) if isinstance(metrics, dict) else {}
    return row if isinstance(row, dict) else {}


def _threshold_check(letf_tracking: dict[str, Any], name: str) -> dict[str, Any]:
    threshold_review = letf_tracking.get("parameter_threshold_review")
    checks = threshold_review.get("checks") if isinstance(threshold_review, dict) else {}
    row = checks.get(name) if isinstance(checks, dict) else {}
    return row if isinstance(row, dict) else {}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    return decision if isinstance(decision, dict) else {}


def build_review(
    *,
    letf_tracking_path: Path = DEFAULT_LETF_TRACKING,
    manual_hedge_path: Path = DEFAULT_MANUAL_HEDGE,
    full_sample_floor: float = -0.03,
    manual_recent_p05_floor: float = -0.02,
    manual_latest_floor: float = -0.02,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    letf_tracking = _load(letf_tracking_path)
    manual_hedge = _load(manual_hedge_path)
    letf_decision = _decision(letf_tracking)
    manual_decision = _decision(manual_hedge)

    h30 = _horizon_metric(letf_tracking, "30")
    tracking_error = h30.get("tracking_error") if isinstance(h30.get("tracking_error"), dict) else {}
    recent = h30.get("recent_60_observations") if isinstance(h30.get("recent_60_observations"), dict) else {}
    effective_drag = h30.get("effective_drag_proxy") if isinstance(h30.get("effective_drag_proxy"), dict) else {}
    realized_variance = h30.get("realized_variance") if isinstance(h30.get("realized_variance"), dict) else {}
    threshold_check = _threshold_check(letf_tracking, "00632r_30d_p05_tracking_error_floor")

    full_p05 = _finite(tracking_error.get("p05"))
    full_latest = _finite(tracking_error.get("latest"))
    full_mean = _finite(tracking_error.get("mean"))
    full_p50 = _finite(tracking_error.get("p50"))
    full_p95 = _finite(tracking_error.get("p95"))
    recent_p05 = _finite(recent.get("p05_tracking_error"))
    recent_mean = _finite(recent.get("mean_tracking_error"))
    recent_drag_mean = _finite(recent.get("mean_effective_drag_proxy"))
    drag_p05 = _finite(effective_drag.get("p05"))
    drag_latest = _finite(effective_drag.get("latest"))
    rv_latest = _finite(realized_variance.get("latest"))

    full_sample_tail_gate_passed = full_p05 is not None and full_p05 >= full_sample_floor
    manual_recent_tail_gate_passed = (
        recent_p05 is not None
        and recent_p05 >= manual_recent_p05_floor
        and full_latest is not None
        and full_latest >= manual_latest_floor
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if not letf_tracking:
        blockers.append("missing_letf_tracking_review")
    if not manual_hedge:
        blockers.append("missing_manual_hedge_eligibility_review")
    if not full_sample_tail_gate_passed:
        blockers.append("full_sample_00632r_tail_tracking_error_gate_failed")
    if not manual_recent_tail_gate_passed:
        blockers.append("recent_manual_tail_tracking_error_gate_failed")
    if manual_decision.get("manual_hedge_discussion_allowed") is not True:
        blockers.append("manual_hedge_eligibility_still_blocked")
    if letf_decision.get("allow_00632r_open") is not True:
        blockers.append("letf_readiness_still_blocks_00632r_open")

    if manual_recent_tail_gate_passed and not full_sample_tail_gate_passed:
        warnings.append("recent_tail_tracking_error_is_better_than_full_sample_auto_gate")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_00632r_tail_tracking_error_gate_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked",
        "policy": "tail_tracking_error_gate_review_only_no_hedge_open_no_weight_change",
        "inputs": {
            "letf_tracking_error_effective_fee_readiness": str(letf_tracking_path),
            "manual_hedge_eligibility": str(manual_hedge_path),
        },
        "thresholds": {
            "full_sample_30d_p05_floor_for_auto_gate": full_sample_floor,
            "manual_recent_60_30d_p05_floor": manual_recent_p05_floor,
            "manual_latest_30d_tracking_error_floor": manual_latest_floor,
        },
        "metrics": {
            "full_sample_30d": {
                "count": tracking_error.get("count"),
                "mean": full_mean,
                "p05": full_p05,
                "p50": full_p50,
                "p95": full_p95,
                "latest": full_latest,
                "effective_drag_p05": drag_p05,
                "effective_drag_latest": drag_latest,
                "realized_variance_latest": rv_latest,
            },
            "recent_60_observations": {
                "mean_tracking_error": recent_mean,
                "p05_tracking_error": recent_p05,
                "mean_effective_drag_proxy": recent_drag_mean,
            },
            "source_threshold_check": threshold_check,
        },
        "assessment": {
            "full_sample_tail_gate_passed": full_sample_tail_gate_passed,
            "manual_recent_tail_gate_passed": manual_recent_tail_gate_passed,
            "gate_split_recommended": manual_recent_tail_gate_passed and not full_sample_tail_gate_passed,
            "full_sample_failure_magnitude": _finite(full_p05 - full_sample_floor)
            if full_p05 is not None
            else None,
            "recent_p05_margin_to_manual_floor": _finite(recent_p05 - manual_recent_p05_floor)
            if recent_p05 is not None
            else None,
            "latest_margin_to_manual_floor": _finite(full_latest - manual_latest_floor)
            if full_latest is not None
            else None,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The original full-sample p05 gate remains a valid conservative blocker for automatic 00632R trading.",
            "Recent 60-observation tail tracking error is less severe than the full-sample p05, so a manual-discussion tier can be tracked separately.",
            "This review does not override effective-fee, live hedge policy, market-impact, or research-shadow blockers.",
        ],
        "decision": {
            "tail_gate_review_complete": bool(letf_tracking),
            "gate_split_recommended": manual_recent_tail_gate_passed and not full_sample_tail_gate_passed,
            "full_sample_auto_trade_tail_gate_passed": full_sample_tail_gate_passed,
            "manual_discussion_tail_gate_passed": manual_recent_tail_gate_passed,
            "manual_hedge_discussion_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"00632r_tail_tracking_error_gate_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--letf-tracking", default=str(DEFAULT_LETF_TRACKING))
    parser.add_argument("--manual-hedge", default=str(DEFAULT_MANUAL_HEDGE))
    parser.add_argument("--full-sample-floor", type=float, default=-0.03)
    parser.add_argument("--manual-recent-p05-floor", type=float, default=-0.02)
    parser.add_argument("--manual-latest-floor", type=float, default=-0.02)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        letf_tracking_path=_resolve(args.letf_tracking),
        manual_hedge_path=_resolve(args.manual_hedge),
        full_sample_floor=args.full_sample_floor,
        manual_recent_p05_floor=args.manual_recent_p05_floor,
        manual_latest_floor=args.manual_latest_floor,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"00632R tail tracking-error gate review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "gate_split_recommended": review["assessment"]["gate_split_recommended"],
                "full_sample_tail_gate_passed": review["assessment"]["full_sample_tail_gate_passed"],
                "manual_recent_tail_gate_passed": review["assessment"]["manual_recent_tail_gate_passed"],
                "manual_hedge_discussion_allowed": review["decision"]["manual_hedge_discussion_allowed"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
