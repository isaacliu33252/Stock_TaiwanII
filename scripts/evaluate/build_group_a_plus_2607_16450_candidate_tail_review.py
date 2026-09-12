#!/usr/bin/env python3
"""Build candidate-level 2607.16450 tail review for GroupA+ improvements.

This report applies the 2607.16450 tail-sensitive review to current shadow
profit candidates. It is governance-only and never changes targets or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORECARD = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_tail_sensitive_scorecard.json"
DEFAULT_COST_ROBUSTNESS = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_turnover_cost_robustness.json"
DEFAULT_STAGED_REENTRY = PROJECT_ROOT / "report/group_a_plus/latest/staged_reentry_shadow.json"
DEFAULT_A2118 = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_shadow.json"
DEFAULT_A2118_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
DEFAULT_A2118_RISK_DOWN = PROJECT_ROOT / "report/group_a_plus/latest/a2118_risk_down_mapped_shadow.json"
DEFAULT_A2120 = PROJECT_ROOT / "report/group_a_plus/latest/a2120_small_00631l_reentry_shadow.json"
DEFAULT_GJR = PROJECT_ROOT / "report/group_a_plus/latest/gjr_post_trigger_severity_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_candidate_tail_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_candidate_tail_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _weights(payload: dict[str, Any], key: str) -> dict[str, float]:
    raw = payload.get(key)
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}


def _weight(raw: dict[str, float], key: str) -> float:
    return float(raw.get(key, 0.0))


def _ranked(scorecard: dict[str, Any], strategy: str) -> dict[str, Any]:
    for row in scorecard.get("ranked_references") or []:
        if isinstance(row, dict) and row.get("strategy") == strategy:
            return row
    return {}


def _cost_blockers(cost_robustness: dict[str, Any]) -> list[str]:
    return [
        f"turnover_cost_robustness:{item}"
        for item in (cost_robustness.get("blocking_reasons") or [])
    ]


def _review_staged(staged: dict[str, Any], scorecard: dict[str, Any]) -> dict[str, Any]:
    proposed = _weights(staged, "proposed_shadow_target_weights")
    defensive = _ranked(scorecard, "defensive_0050_70_cash30")
    exposure_ratio = None
    if _weight(proposed, "00631L.TW") == 0 and _weight(proposed, "0050.TW") >= 0:
        exposure_ratio = _weight(proposed, "0050.TW") / 0.70
    blockers = list(staged.get("blockers") or [])
    warnings = list(staged.get("warnings") or [])
    if _weight(proposed, "00631L.TW") > 0:
        blockers.append("staged_reentry_contains_00631l_despite_tail_review")
    return {
        "name": "staged_reentry",
        "source_status": staged.get("status"),
        "tail_review_status": "tail_acceptable_shadow_only" if not blockers else "blocked",
        "candidate_weights": proposed,
        "reference": "defensive_0050_70_cash30",
        "0050_exposure_vs_defensive_reference": exposure_ratio,
        "reference_score": defensive.get("score"),
        "tail_blockers": blockers,
        "tail_warnings": warnings,
        "decision": {
            "use_for_promotion_review": staged.get("status") == "active_shadow_candidate",
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "summary": "0050-only staged re-entry is compatible with the tail review as a shadow candidate, but still requires human promotion gates.",
        },
    }


def _review_a2118(
    a2118: dict[str, Any],
    monitor: dict[str, Any],
    cost_robustness: dict[str, Any],
    risk_down: dict[str, Any],
) -> dict[str, Any]:
    summary = (a2118.get("summary") or {}).get("preferred_full") or {}
    inference = monitor.get("ensemble_inference") if isinstance(monitor.get("ensemble_inference"), dict) else {}
    action_weights = inference.get("target_weights_for_action") if isinstance(inference.get("target_weights_for_action"), dict) else {}
    decision = a2118.get("decision") if isinstance(a2118.get("decision"), dict) else {}
    blockers = list(decision.get("production_blockers") or [])
    if _weight({k: float(v) for k, v in action_weights.items() if isinstance(v, (int, float))}, "00631L.TW") > 0:
        blockers.append("a2118_shadow_action_adds_00631l_against_current_tail_review")
    blockers.extend(_cost_blockers(cost_robustness))
    mapped_variants = risk_down.get("mapped_variants") if isinstance(risk_down.get("mapped_variants"), list) else []
    return {
        "name": "a2118_seed_averaging",
        "source_status": decision.get("shadow_gate") or a2118.get("status"),
        "tail_review_status": "blocked_for_live_promotion",
        "preferred_ensemble": a2118.get("preferred_ensemble"),
        "backtest_metrics": {
            "annual_return": summary.get("annual_return"),
            "sharpe": summary.get("sharpe"),
            "max_drawdown": summary.get("max_drawdown"),
        },
        "latest_shadow_action": inference.get("action"),
        "latest_shadow_action_weights": action_weights,
        "risk_down_mapping": {
            "status": risk_down.get("status") if risk_down else "missing",
            "variants": [
                {
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "weights": row.get("weights"),
                    "allow_00631l_add": row.get("allow_00631l_add"),
                }
                for row in mapped_variants
                if isinstance(row, dict)
            ],
            "blocking_reasons": risk_down.get("blocking_reasons") if risk_down else [],
        },
        "tail_blockers": sorted(set(blockers)),
        "tail_warnings": [],
        "decision": {
            "use_for_promotion_review": True,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "summary": "Backtest robustness is positive, but the latest shadow action adds 00631L and forward parity/cost-tail gates block live promotion.",
        },
    }


def _review_a2120(a2120: dict[str, Any]) -> dict[str, Any]:
    candidate = _weights(a2120, "candidate_target_weights_if_blockers_clear")
    blockers = list(a2120.get("blockers") or [])
    return {
        "name": "a2120_small_00631l",
        "source_status": a2120.get("status"),
        "tail_review_status": "inactive_blocked",
        "candidate_weights_if_blockers_clear": candidate,
        "tail_blockers": blockers + ["small_00631l_reentry_still_requires_non_bearish_tail_review"],
        "tail_warnings": list(a2120.get("warnings") or []),
        "decision": {
            "use_for_promotion_review": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "summary": "Small 00631L re-entry remains inactive; paper review does not override bearish direction or A21.20 blockers.",
        },
    }


def _review_gjr(gjr: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "gjr_post_trigger",
        "source_status": gjr.get("status"),
        "tail_review_status": "inactive_severity_only",
        "tail_blockers": list(gjr.get("blockers") or []),
        "tail_warnings": list(gjr.get("warnings") or []),
        "decision": {
            "use_for_promotion_review": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "summary": "GJR remains a post-trigger severity modifier only; it cannot create a new trade trigger.",
        },
    }


def build_candidate_tail_review(
    *,
    scorecard_path: Path,
    cost_robustness_path: Path,
    staged_reentry_path: Path,
    a2118_path: Path,
    a2118_monitor_path: Path,
    a2118_risk_down_path: Path,
    a2120_path: Path,
    gjr_path: Path,
) -> dict[str, Any]:
    scorecard = _load(scorecard_path)
    cost_robustness = _load(cost_robustness_path)
    staged = _load(staged_reentry_path)
    a2118 = _load(a2118_path)
    monitor = _load(a2118_monitor_path)
    risk_down = _load(a2118_risk_down_path)
    a2120 = _load(a2120_path)
    gjr = _load(gjr_path)

    blockers: list[str] = []
    for name, payload in {
        "tail_sensitive_scorecard": scorecard,
        "turnover_cost_robustness": cost_robustness,
        "staged_reentry": staged,
        "a2118_seed_averaging": a2118,
        "a2118_forward_monitor": monitor,
        "a2118_risk_down_mapped_shadow": risk_down,
        "a2120_small_00631l": a2120,
        "gjr_post_trigger": gjr,
    }.items():
        if not payload:
            blockers.append(f"missing_required_input:{name}")

    candidate_reviews = [
        _review_staged(staged, scorecard),
        _review_a2118(a2118, monitor, cost_robustness, risk_down),
        _review_a2120(a2120),
        _review_gjr(gjr),
    ]
    live_ready = [
        row["name"]
        for row in candidate_reviews
        if row.get("decision", {}).get("target_weight_change_allowed") is True
    ]
    as_of = (
        scorecard.get("latest_strategy_context", {}).get("actual_data_date")
        or cost_robustness.get("as_of")
        or staged.get("actual_data_date")
        or "unknown"
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_candidate_tail_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_no_target_weight_change",
        "status": "available" if not blockers else "blocked",
        "as_of": as_of,
        "tail_context": {
            "top_reference": (scorecard.get("ranked_references") or [{}])[0].get("strategy")
            if scorecard.get("ranked_references")
            else None,
            "cost_robustness_status": cost_robustness.get("status"),
            "promote_dynamic_cvar_optimizer": (cost_robustness.get("decision") or {}).get(
                "promote_dynamic_cvar_optimizer"
            ),
        },
        "candidate_reviews": candidate_reviews,
        "live_ready_candidates": live_ready,
        "decision": {
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_candidate_tail_review": False,
            "use_for_promotion_review": not blockers,
            "summary": "Candidate-level tail review supports staged 0050-only shadow review, but blocks 00631L-adding candidates from live promotion.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "inputs": {
            "tail_sensitive_scorecard": str(scorecard_path),
            "turnover_cost_robustness": str(cost_robustness_path),
            "staged_reentry": str(staged_reentry_path),
            "a2118_seed_averaging": str(a2118_path),
            "a2118_forward_monitor": str(a2118_monitor_path),
            "a2118_risk_down_mapped_shadow": str(a2118_risk_down_path),
            "a2120_small_00631l": str(a2120_path),
            "gjr_post_trigger": str(gjr_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_candidate_tail_review_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(review.get("as_of"))).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorecard", default=str(DEFAULT_SCORECARD))
    parser.add_argument("--cost-robustness", default=str(DEFAULT_COST_ROBUSTNESS))
    parser.add_argument("--staged-reentry", default=str(DEFAULT_STAGED_REENTRY))
    parser.add_argument("--a2118", default=str(DEFAULT_A2118))
    parser.add_argument("--a2118-monitor", default=str(DEFAULT_A2118_MONITOR))
    parser.add_argument("--a2118-risk-down", default=str(DEFAULT_A2118_RISK_DOWN))
    parser.add_argument("--a2120", default=str(DEFAULT_A2120))
    parser.add_argument("--gjr", default=str(DEFAULT_GJR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_candidate_tail_review(
        scorecard_path=_resolve(args.scorecard),
        cost_robustness_path=_resolve(args.cost_robustness),
        staged_reentry_path=_resolve(args.staged_reentry),
        a2118_path=_resolve(args.a2118),
        a2118_monitor_path=_resolve(args.a2118_monitor),
        a2118_risk_down_path=_resolve(args.a2118_risk_down),
        a2120_path=_resolve(args.a2120),
        gjr_path=_resolve(args.gjr),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_review(review, output, history_dir)
    print(f"2607.16450 candidate tail review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, str(review.get('as_of')))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "live_ready_candidates": review["live_ready_candidates"],
                "allow_00631l_add": review["decision"]["allow_00631l_add_from_candidate_tail_review"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
