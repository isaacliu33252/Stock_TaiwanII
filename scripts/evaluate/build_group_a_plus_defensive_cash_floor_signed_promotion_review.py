#!/usr/bin/env python3
"""Build a manual signed-promotion review package for the cash-floor candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_SWEEP = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.json"
DEFAULT_VALIDATION = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_validation_latest.json"
DEFAULT_ABLATION = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_ablation_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json"
DEFAULT_MD = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.md"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "sha256": _sha256(path) if path.exists() else None}


def _best_sweep_summary(sweep: dict[str, Any]) -> dict[str, Any]:
    best = (sweep.get("top_variants") or [{}])[0]
    return {
        "variant": best.get("variant"),
        "cash_floor": best.get("cash_floor"),
        "total_risk_min": best.get("total_risk_min"),
        "tail_risk_min": best.get("tail_risk_min"),
        "changed_days": best.get("changed_days"),
        "active_days": best.get("active_days"),
        "total_return_delta": best.get("delta_total_return_delta"),
        "sharpe_delta": best.get("delta_sharpe_delta"),
        "max_drawdown_delta": best.get("delta_max_drawdown_delta"),
        "worst_day_delta": best.get("delta_worst_day_delta"),
    }


def build_review(
    *,
    sweep: dict[str, Any],
    validation: dict[str, Any],
    ablation: dict[str, Any],
    source_paths: dict[str, Path],
    as_of: str,
) -> dict[str, Any]:
    sweep_summary = _best_sweep_summary(sweep)
    variant = str(ablation.get("candidate") or validation.get("variant") or sweep_summary.get("variant"))
    validation_summary = validation.get("summary") or {}
    ablation_summary = ablation.get("summary") or {}
    ablation_decision = (ablation.get("decision") or {}).get("promotion_decision")
    evidence_ready = (
        sweep.get("status") == "ok"
        and validation.get("status") == "ok"
        and ablation.get("status") == "ok"
        and ablation_decision == "shadow_candidate_for_signed_review"
        and not validation_summary.get("fail_windows")
        and not ablation_summary.get("fail_folds")
    )
    status = "manual_signature_pending" if evidence_ready else "blocked"
    blockers = []
    if not evidence_ready:
        blockers.append("evidence_package_not_ready_for_signed_review")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_defensive_cash_floor_signed_promotion_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": status,
        "policy": "manual_signed_review_required_no_live_action_from_this_file",
        "sources": {name: _source(path) for name, path in source_paths.items()},
        "candidate": {
            "variant": variant,
            "rule": "Inside group_a_plus_defensive only, raise cash floor to 55% when total_risk_score >= 7 or tail_risk_score >= 1.",
            "cash_floor": 0.55,
            "total_risk_min": 7,
            "tail_risk_min": 1,
            "rebalance_mechanism": "reduce positive risky ETF weights pro-rata; add the released weight to cash",
            "scope": "group_a_plus_defensive_high_risk_cash_floor_only",
            "does_not_add_00631l": True,
            "does_not_open_00632r": True,
        },
        "evidence": {
            "sweep": sweep_summary,
            "window_validation": {
                "decision": (validation.get("decision") or {}).get("promotion_decision"),
                "evaluable_changed_window_count": validation_summary.get("evaluable_changed_window_count"),
                "pass_count": validation_summary.get("pass_count"),
                "fail_windows": validation_summary.get("fail_windows"),
            },
            "fold_ablation": {
                "decision": ablation_decision,
                "evaluable_changed_fold_count": ablation_summary.get("evaluable_changed_fold_count"),
                "candidate_pass_count": ablation_summary.get("candidate_pass_count"),
                "same_family_train_selection_count": ablation_summary.get("same_family_train_selection_count"),
                "fail_folds": ablation_summary.get("fail_folds"),
            },
        },
        "limitations": [
            "Only 27 changed days in the 607-row 2024-01-02 to 2026-08-05 frame.",
            "2024 has zero trigger days, so it is evidence-neutral rather than validated.",
            "The rule was validated as a shadow replay, not as broker-executed live trading.",
            "This review does not validate tax, liquidity, broker fill, or intraday slippage effects.",
            "The rule changes defensive cash posture, so it can lag if high-risk defensive days rebound immediately.",
        ],
        "manual_signature_required": {
            "reviewer": None,
            "reviewer_role": None,
            "signed_at": None,
            "expires_at": None,
            "required_acknowledgements": [
                "sparse_27_changed_day_evidence_acknowledged",
                "year_2024_no_trigger_limitation_acknowledged",
                "shadow_replay_not_live_execution_acknowledged",
                "no_00631l_add_and_no_00632r_open_acknowledged",
                "separate_execution_review_required_before_any_order_acknowledged",
            ],
        },
        "recommended_next_action_after_manual_signature": {
            "prepare_code_integration": True,
            "integration_mode": "guarded_formal_candidate",
            "default_enabled": False,
            "requires_daily_shadow_monitoring": True,
        },
        "rollback_monitor": {
            "disable_candidate_if_any_true": [
                "first_10_trigger_days_variant_underperforms_raw_by_more_than_0_50pct_cumulative",
                "variant_max_drawdown_worse_than_raw_by_more_than_0_25pct_on_trigger_window",
                "cash_floor_trigger_conflicts_with_execution_guard_or_freshness_block",
                "manual_reviewer_revokes_signed_review",
            ]
        },
        "blocking_reasons": blockers,
        "decision": {
            "signed_review_ready": evidence_ready,
            "manual_signature_valid": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
            "allow_prepare_guarded_integration_after_signature": evidence_ready,
        },
    }


def write_markdown(review: dict[str, Any], path: Path) -> None:
    evidence = review["evidence"]
    sweep = evidence["sweep"]
    validation = evidence["window_validation"]
    ablation = evidence["fold_ablation"]
    decision = review["decision"]
    lines = [
        "# GroupA+ Defensive Cash Floor Signed Promotion Review",
        "",
        f"- status: `{review['status']}`",
        f"- as_of: `{review['as_of']}`",
        f"- candidate: `{review['candidate']['variant']}`",
        f"- rule: {review['candidate']['rule']}",
        f"- signed_review_ready: `{decision['signed_review_ready']}`",
        f"- manual_signature_valid: `{decision['manual_signature_valid']}`",
        f"- target_weight_change_allowed: `{decision['target_weight_change_allowed']}`",
        f"- auto_rebalance_allowed: `{decision['auto_rebalance_allowed']}`",
        "",
        "## Evidence",
        "",
        f"- sweep total_return_delta: `{float(sweep['total_return_delta']):+.4%}`",
        f"- sweep max_drawdown_delta: `{float(sweep['max_drawdown_delta']):+.4%}`",
        f"- sweep worst_day_delta: `{float(sweep['worst_day_delta']):+.4%}`",
        f"- changed_days: `{sweep['changed_days']}`",
        f"- window validation: `{validation['pass_count']}/{validation['evaluable_changed_window_count']}` changed windows passed",
        f"- fold ablation: `{ablation['candidate_pass_count']}/{ablation['evaluable_changed_fold_count']}` changed folds passed",
        f"- same-family train reselection: `{ablation['same_family_train_selection_count']}/{ablation['evaluable_changed_fold_count']}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in review["limitations"])
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "This package is ready for manual signature review, but it does not itself authorize live trading, target-weight changes, or auto rebalance.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", default=str(DEFAULT_SWEEP))
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--ablation", default=str(DEFAULT_ABLATION))
    parser.add_argument("--as-of", default="2026-08-06")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD))
    args = parser.parse_args()

    source_paths = {
        "sweep": Path(args.sweep),
        "validation": Path(args.validation),
        "ablation": Path(args.ablation),
    }
    review = build_review(
        sweep=_load(source_paths["sweep"]),
        validation=_load(source_paths["validation"]),
        ablation=_load(source_paths["ablation"]),
        source_paths=source_paths,
        as_of=args.as_of,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(review, Path(args.md_output))
    print(
        "status={status} signed_ready={ready} target_weight_change_allowed={target} output={output}".format(
            status=review["status"],
            ready=review["decision"]["signed_review_ready"],
            target=review["decision"]["target_weight_change_allowed"],
            output=output,
        )
    )


if __name__ == "__main__":
    main()
