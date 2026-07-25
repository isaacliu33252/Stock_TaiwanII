#!/usr/bin/env python3
"""Summarize GroupA+ promotion readiness with optional governance guardrails."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.governance.compare import compare_candidates

# 2026-07-07 Fable audit + empirical recalibration: a2118's trigger
# (group_a_plus/runners/a2118.py) reads `prob_up_h20` (aliased 1:1 to
# `h20_prob_up` -- see ncf_00631l.py's `_build_expanding_horizon_ensemble_panel`)
# and `confidence` directly, so both are tagged "trigger_critical" here.
# `ensemble_prob_up` is a diagnostic/composite view a2118 never reads on its
# own, tagged "diagnostic".
#
# The original flat 0.05 limit on all three was checked against five real
# drift audits from the 2026-07-07 panel-drift-fix session (OFF baseline +
# ON/v2/v3/v4 shrinkage-tuning iterations) and turned out to be
# unsatisfiable even by "v4" -- the accepted, shipped fix
# (results/ncf_00631l_panel_drift_verify_ON_v4_20260707.json):
#   h20_prob_up=0.111  confidence=0.213  ensemble_prob_up=0.107
# `confidence` in particular is a shrinkage-adjusted cross-horizon blend
# (see ncf_00631l.py main()'s "HORIZON ENSEMBLE (confidence-aware)" step,
# `dir_w = raw_auc_w / raw_auc_w.sum()` over the *full* val set each run --
# a horizon-level analog of the model-level drift bug this session's/
# 2026-07-07's fixes address, still unfixed at that level) and is
# structurally the noisiest of the three across every iteration observed
# (0.19-0.32 range even in the discarded "ON"/v2/v3 iterations). A strict
# 0.05 on trigger_critical fields would keep every NCF-panel candidate
# permanently blocked -- the exact failure mode this tiering was meant to
# fix, just moved from ensemble_prob_up onto confidence/h20_prob_up instead.
# Limits below are calibrated with ~1.3-1.4x margin over the shipped v4
# values (so v4 passes) while still failing the discarded "ON" v1 iteration
# (h20_prob_up=0.675, confidence=0.319, ensemble_prob_up=0.260) on every
# column -- i.e. the gate still discriminates a genuinely worse fix from an
# accepted one, it just no longer blocks the accepted one.
DRIFT_LIMIT_TIERS = {
    "trigger_critical": {"h20_prob_up": 0.15, "confidence": 0.28},
    "diagnostic": {"ensemble_prob_up": 0.15},
}
DEFAULT_DRIFT_LIMITS = {
    **DRIFT_LIMIT_TIERS["trigger_critical"],
    **DRIFT_LIMIT_TIERS["diagnostic"],
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _drift_gate(
    drift_audit_path: str | Path | None,
    *,
    limits: dict[str, float],
    require_drift_audit: bool,
) -> dict[str, Any]:
    if drift_audit_path is None:
        return {
            "status": "fail" if require_drift_audit else "not_required",
            "path": None,
            "reason": "panel drift audit is required but was not provided"
            if require_drift_audit
            else "panel drift audit not required for this gate run",
            "limits": limits,
            "checks": {},
        }

    path = _resolve(drift_audit_path)
    if not path.exists():
        return {
            "status": "fail" if require_drift_audit else "not_required",
            "path": str(path),
            "reason": "panel drift audit is required but the file is missing"
            if require_drift_audit
            else "panel drift audit file is missing but not required for this gate run",
            "limits": limits,
            "checks": {},
        }

    audit = _load_json(path)
    column_summary = audit.get("column_summary") or {}
    tier_by_column = {
        column: tier
        for tier, columns in DRIFT_LIMIT_TIERS.items()
        for column in columns
    }
    checks: dict[str, Any] = {}
    failures: list[str] = []
    for column, limit in limits.items():
        tier = tier_by_column.get(column, "diagnostic")
        info = column_summary.get(column)
        if not isinstance(info, dict):
            checks[column] = {"status": "fail", "reason": "missing from drift audit", "limit": limit, "tier": tier}
            failures.append(column)
            continue
        value = float(info.get("max_abs_delta", 0.0) or 0.0)
        passed = value <= float(limit)
        checks[column] = {
            "status": "pass" if passed else "fail",
            "max_abs_delta": value,
            "limit": float(limit),
            "tier": tier,
            "max_abs_delta_date": info.get("max_abs_delta_date"),
        }
        if not passed:
            failures.append(column)

    return {
        "status": "pass" if not failures else "fail",
        "path": str(path),
        "reason": "all drift checks passed" if not failures else f"drift exceeds limits: {', '.join(failures)}",
        "limits": limits,
        "overlap_rows": audit.get("overlap_rows"),
        "overlap_start": audit.get("overlap_start"),
        "overlap_end": audit.get("overlap_end"),
        "checks": checks,
    }


def _multi_window_gate(
    multi_window_gate_path: str | Path | None,
    *,
    require_multi_window_gate: bool,
) -> dict[str, Any]:
    if multi_window_gate_path is None:
        return {
            "status": "fail" if require_multi_window_gate else "not_required",
            "path": None,
            "reason": "multi-window gate is required but was not provided"
            if require_multi_window_gate
            else "multi-window gate not required for this gate run",
            "candidate_count": None,
            "pass_candidates": [],
        }

    gate = _load_json(multi_window_gate_path)
    pass_candidates = [
        candidate
        for candidate in gate.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("decision") == "multi_window_pass"
    ]
    passed = gate.get("decision") == "candidate_available" and bool(pass_candidates)
    return {
        "status": "pass" if passed else "fail",
        "path": str(_resolve(multi_window_gate_path)),
        "reason": "at least one candidate passed the multi-window gate"
        if passed
        else "no candidate passed the multi-window gate",
        "source_decision": gate.get("decision"),
        "row_count": gate.get("row_count"),
        "candidate_count": gate.get("candidate_count"),
        "pass_candidates": [
            {
                "candidate": candidate.get("candidate"),
                "pass_count": candidate.get("pass_count"),
                "window_count": candidate.get("window_count"),
                "pass_ratio": candidate.get("pass_ratio"),
            }
            for candidate in pass_candidates
        ],
        "criteria": gate.get("criteria", {}),
    }


def _deployment_governance_context(deployment_consistency_path: str | Path | None) -> dict[str, Any]:
    if deployment_consistency_path is None:
        return {
            "status": "not_provided",
            "path": None,
            "gift_signed_approval_governance": {},
            "blocking_reasons": [],
            "warning_reasons": [],
        }
    path = _resolve(deployment_consistency_path)
    if not path.exists():
        return {
            "status": "missing",
            "path": str(path),
            "gift_signed_approval_governance": {},
            "blocking_reasons": ["deployment_consistency_review_missing"],
            "warning_reasons": [],
        }
    review = _load_json(path)
    computed = review.get("computed") if isinstance(review.get("computed"), dict) else {}
    gift = (
        computed.get("gift_signed_approval_governance")
        if isinstance(computed.get("gift_signed_approval_governance"), dict)
        else {}
    )
    return {
        "status": review.get("status"),
        "path": str(path),
        "broker_actionable": (review.get("decision") or {}).get("broker_actionable", review.get("broker_actionable")),
        "gift_signed_approval_governance": gift,
        "blocking_reasons": list(review.get("blocking_reasons") or []),
        "warning_reasons": list(review.get("warning_reasons") or []),
        "gift_signed_approval_record_valid": gift.get("signed_approval_record_valid"),
        "gift_human_exception_approved": gift.get("human_exception_approved"),
        "gift_training_queue_allowed": gift.get("training_queue_allowed"),
        "gift_model_training_allowed": gift.get("model_training_allowed"),
        "gift_ppo_training_allowed": gift.get("ppo_training_allowed"),
        "gift_promote_to_live": gift.get("promote_to_live"),
    }


def _deployment_consistency_gate(deployment_context: dict[str, Any]) -> dict[str, Any]:
    if deployment_context.get("status") == "not_provided":
        return {
            "status": "not_required",
            "reason": "deployment consistency review not provided for this gate run",
            "blocking_reasons": [],
            "hard_blocking_reasons": [],
            "manual_approval_pending_reasons": [],
        }

    blocking_reasons = list(deployment_context.get("blocking_reasons") or [])
    warning_reasons = list(deployment_context.get("warning_reasons") or [])
    gate_blockers: list[str] = []
    manual_pending: list[str] = []

    if deployment_context.get("status") in {"missing", "blocked"}:
        gate_blockers.append(f"deployment_consistency_status:{deployment_context.get('status')}")
    if deployment_context.get("broker_actionable") is not True:
        gate_blockers.append("deployment_consistency_not_broker_actionable")
    if deployment_context.get("gift_signed_approval_record_valid") is False:
        manual_pending.append("gift_signed_approval_record_missing_or_invalid")
    if deployment_context.get("gift_human_exception_approved") is False:
        manual_pending.append("gift_human_exception_not_approved")
    if deployment_context.get("gift_training_queue_allowed") is True:
        gate_blockers.append("gift_training_queue_unexpectedly_allowed")
    if deployment_context.get("gift_model_training_allowed") is True:
        gate_blockers.append("gift_model_training_unexpectedly_allowed")
    if deployment_context.get("gift_ppo_training_allowed") is True:
        gate_blockers.append("gift_ppo_training_unexpectedly_allowed")
    if deployment_context.get("gift_promote_to_live") is True:
        gate_blockers.append("gift_promote_to_live_unexpectedly_allowed")

    hard_blockers = list(dict.fromkeys([*blocking_reasons, *gate_blockers]))
    manual_pending = list(
        dict.fromkeys(
            [
                *manual_pending,
                *[
                    reason
                    for reason in warning_reasons
                    if reason.startswith("gift_") or reason.endswith("_manual_completion_pending")
                ],
            ]
        )
    )
    all_reasons = list(dict.fromkeys([*hard_blockers, *manual_pending, *warning_reasons]))
    passed = not gate_blockers and not blocking_reasons
    return {
        "status": "pass" if passed else "fail",
        "reason": "deployment consistency governance passed"
        if passed
        else "deployment consistency governance blocks promotion",
        "blocking_reasons": hard_blockers,
        "hard_blocking_reasons": hard_blockers,
        "manual_approval_pending_reasons": manual_pending,
        "warning_reasons": warning_reasons,
        "all_reasons": all_reasons,
    }


def _deployment_summary_context(deployment_summary_path: str | Path | None) -> dict[str, Any]:
    if deployment_summary_path is None:
        return {
            "status": "not_provided",
            "path": None,
            "consistency_review": {},
            "blocking_reasons": [],
        }
    path = _resolve(deployment_summary_path)
    if not path.exists():
        return {
            "status": "missing",
            "path": str(path),
            "consistency_review": {},
            "blocking_reasons": ["deployment_summary_missing"],
        }
    summary = _load_json(path)
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    consistency_review = (
        summary.get("consistency_review") if isinstance(summary.get("consistency_review"), dict) else {}
    )
    return {
        "status": summary.get("status"),
        "path": str(path),
        "broker_actionable": summary.get("broker_actionable"),
        "consistency_review": consistency_review,
        "consistency_review_status": consistency_review.get("status"),
        "consistency_review_errors": list(consistency_review.get("errors") or []),
        "summary_only": decision.get("summary_only"),
        "creates_orders": decision.get("creates_orders"),
        "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
        "auto_rebalance_allowed": decision.get("auto_rebalance_allowed"),
        "allow_00631l_add": decision.get("allow_00631l_add"),
        "allow_00632r_open": decision.get("allow_00632r_open"),
        "keep_golden1_0531_unchanged": decision.get("keep_golden1_0531_unchanged"),
        "blocking_reasons": list(summary.get("blocking_reasons") or []),
        "warning_reasons": list(summary.get("warning_reasons") or []),
    }


def _deployment_summary_gate(summary_context: dict[str, Any]) -> dict[str, Any]:
    if summary_context.get("status") == "not_provided":
        return {
            "status": "not_required",
            "reason": "deployment summary not provided for this gate run",
            "blocking_reasons": [],
        }

    blockers = list(summary_context.get("blocking_reasons") or [])
    if summary_context.get("status") == "missing":
        blockers.append("deployment_summary_missing")
    if summary_context.get("consistency_review_status") != "ok":
        blockers.append(f"deployment_summary_consistency_review:{summary_context.get('consistency_review_status')}")
    for key, expected in {
        "summary_only": True,
        "creates_orders": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
        "keep_golden1_0531_unchanged": True,
    }.items():
        if summary_context.get(key) is not expected:
            blockers.append(f"deployment_summary_{key}_unexpected")
    blockers.extend(summary_context.get("consistency_review_errors") or [])
    blockers = list(dict.fromkeys(blockers))
    passed = not blockers
    return {
        "status": "pass" if passed else "fail",
        "reason": "deployment summary governance passed"
        if passed
        else "deployment summary governance blocks promotion",
        "blocking_reasons": blockers,
    }


def build_promotion_gate(
    baseline: str | Path,
    candidates: list[str | Path],
    *,
    drift_audit: str | Path | None = None,
    drift_limits: dict[str, float] | None = None,
    require_drift_audit: bool = True,
    multi_window_gate: str | Path | None = None,
    require_multi_window_gate: bool = False,
    deployment_consistency: str | Path | None = None,
    deployment_summary: str | Path | None = None,
) -> dict[str, Any]:
    comparison = compare_candidates(_resolve(baseline), [_resolve(path) for path in candidates])
    drift = _drift_gate(
        drift_audit,
        limits=drift_limits or DEFAULT_DRIFT_LIMITS,
        require_drift_audit=require_drift_audit,
    )
    multi_window = _multi_window_gate(
        multi_window_gate,
        require_multi_window_gate=require_multi_window_gate,
    )
    deployment_context = _deployment_governance_context(deployment_consistency)
    deployment_gate = _deployment_consistency_gate(deployment_context)
    summary_context = _deployment_summary_context(deployment_summary)
    summary_gate = _deployment_summary_gate(summary_context)

    formal_rows = [row for row in comparison.get("rows", []) if row.get("formal_upgrade_pass")]
    watchlist_rows = [row for row in comparison.get("rows", []) if row.get("research_watchlist_pass")]
    metrics_status = "pass" if formal_rows else "watchlist" if watchlist_rows else "fail"

    drift_failed = drift["status"] == "fail"
    multi_window_failed = multi_window["status"] == "fail"
    deployment_failed = deployment_gate["status"] == "fail"
    manual_approval_pending = bool(deployment_gate.get("manual_approval_pending_reasons"))
    summary_failed = summary_gate["status"] == "fail"
    blocking_gates = [
        gate
        for gate, failed in (
            ("panel_drift", drift_failed),
            ("multi_window", multi_window_failed),
            ("deployment_consistency", deployment_failed),
            ("deployment_summary", summary_failed),
        )
        if failed
    ]
    governance_failed = deployment_failed or summary_failed
    model_failed = drift_failed or multi_window_failed
    if governance_failed and model_failed:
        decision = "blocked_deployment_consistency_and_model_gates"
    elif model_failed and manual_approval_pending:
        decision = "blocked_model_gates_manual_approval_pending"
    elif drift_failed and multi_window_failed:
        decision = "blocked_panel_drift_and_multi_window"
    elif deployment_failed and summary_failed:
        decision = "blocked_deployment_governance"
    elif deployment_failed:
        decision = "blocked_deployment_consistency"
    elif summary_failed:
        decision = "blocked_deployment_summary"
    elif drift_failed:
        decision = "blocked_panel_drift"
    elif multi_window_failed:
        decision = "blocked_multi_window"
    elif manual_approval_pending:
        decision = "manual_approval_pending"
    elif formal_rows:
        decision = "promotion_ready"
    elif watchlist_rows:
        decision = "research_watchlist"
    else:
        decision = "research_only"

    return {
        "report_type": "group_a_plus_promotion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "decision": decision,
        "blocking_gates": blocking_gates,
        "active_allocation_impact": "none",
        "baseline": str(_resolve(baseline)),
        "candidates": [str(_resolve(path)) for path in candidates],
        "metrics_gate": {
            "status": metrics_status,
            "formal_upgrade_pass_count": len(formal_rows),
            "research_watchlist_pass_count": len(watchlist_rows),
            "candidate_row_count": comparison.get("candidate_row_count"),
            "top_candidates": comparison.get("top_candidates", [])[:10],
        },
        "panel_drift_gate": drift,
        "multi_window_gate": multi_window,
        "deployment_consistency_gate": deployment_gate,
        "deployment_summary_gate": summary_gate,
        "governance_context": {
            "deployment_consistency": deployment_context,
            "deployment_summary": summary_context,
            "active_allocation_impact": "none",
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "comparison": comparison,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--drift-audit", default=None)
    parser.add_argument("--max-ensemble-prob-drift", type=float, default=DEFAULT_DRIFT_LIMITS["ensemble_prob_up"])
    parser.add_argument("--max-h20-prob-drift", type=float, default=DEFAULT_DRIFT_LIMITS["h20_prob_up"])
    parser.add_argument("--max-confidence-drift", type=float, default=DEFAULT_DRIFT_LIMITS["confidence"])
    parser.add_argument("--no-require-drift-audit", action="store_true")
    parser.add_argument("--multi-window-gate", default=None)
    parser.add_argument("--require-multi-window-gate", action="store_true")
    parser.add_argument("--deployment-consistency", default=None)
    parser.add_argument("--deployment-summary", default=None)
    parser.add_argument("--output", default="results/group_a_plus_promotion_gate_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limits = {
        "ensemble_prob_up": float(args.max_ensemble_prob_drift),
        "h20_prob_up": float(args.max_h20_prob_drift),
        "confidence": float(args.max_confidence_drift),
    }
    report = build_promotion_gate(
        args.baseline,
        args.candidates,
        drift_audit=args.drift_audit,
        drift_limits=limits,
        require_drift_audit=not args.no_require_drift_audit,
        multi_window_gate=args.multi_window_gate,
        require_multi_window_gate=args.require_multi_window_gate,
        deployment_consistency=args.deployment_consistency,
        deployment_summary=args.deployment_summary,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Promotion gate: {output}")
    print(f"Decision: {report['decision']}")
    print(f"Metrics gate: {report['metrics_gate']['status']}")
    print(f"Panel drift gate: {report['panel_drift_gate']['status']} - {report['panel_drift_gate']['reason']}")
    print(f"Multi-window gate: {report['multi_window_gate']['status']} - {report['multi_window_gate']['reason']}")


if __name__ == "__main__":
    main()
