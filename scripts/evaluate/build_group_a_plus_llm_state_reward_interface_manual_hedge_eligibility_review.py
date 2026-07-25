#!/usr/bin/env python3
"""Manual hedge eligibility checklist for the GIFT research import.

This consumes the windowed 00632R hedge-like evidence and existing GroupA+
readiness gates. It can only permit manual discussion; it never opens 00632R,
changes target weights, trains a model, or triggers rebalance.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WINDOWED_STABILITY = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_windowed_stability_review.json"
)
DEFAULT_LETF_TRACKING = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_RESEARCH_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/research_shadow_decision_snapshot.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_manual_hedge_eligibility_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_manual_hedge_eligibility/history"


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


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    return decision if isinstance(decision, dict) else {}


def _threshold_check(letf_tracking: dict[str, Any], name: str) -> dict[str, Any]:
    review = letf_tracking.get("parameter_threshold_review")
    checks = review.get("checks") if isinstance(review, dict) else {}
    check = checks.get(name) if isinstance(checks, dict) else {}
    return check if isinstance(check, dict) else {}


def _latest_rolling(windowed: dict[str, Any], ticker: str, window: str) -> dict[str, Any]:
    summary = windowed.get("summary")
    latest = (summary or {}).get("latest_rolling_by_target") if isinstance(summary, dict) else {}
    row = ((latest or {}).get(ticker) or {}).get(window)
    return row if isinstance(row, dict) else {}


def _recent_stress_relationship(windowed: dict[str, Any], ticker: str) -> dict[str, Any]:
    windows = windowed.get("stress_window_relationships")
    if not isinstance(windows, list):
        return {}
    recent = next((row for row in windows if isinstance(row, dict) and row.get("name") == "taiwan_2026_recent"), {})
    relationships = recent.get("relationships") if isinstance(recent, dict) else []
    if not isinstance(relationships, list):
        return {}
    row = next((item for item in relationships if isinstance(item, dict) and item.get("target") == ticker), {})
    return row if isinstance(row, dict) else {}


def _check(name: str, passed: bool, *, value: Any = None, threshold: Any = None, source: str = "", blocker: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "value": value,
        "threshold": threshold,
        "source": source,
        "blocking_reason_if_failed": blocker or name,
    }


def build_review(
    *,
    windowed_stability_path: Path = DEFAULT_WINDOWED_STABILITY,
    letf_tracking_path: Path = DEFAULT_LETF_TRACKING,
    market_impact_path: Path = DEFAULT_MARKET_IMPACT,
    research_shadow_path: Path = DEFAULT_RESEARCH_SHADOW,
    target_ticker: str = "00632R.TW",
    benchmark_ticker: str = "0050.TW",
    correlation_ceiling: float = -0.95,
    beta_abs_error_ceiling: float = 0.10,
    recent_extreme_days_ceiling: int = 1,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    windowed = _load(windowed_stability_path)
    letf_tracking = _load(letf_tracking_path)
    market_impact = _load(market_impact_path)
    research_shadow = _load(research_shadow_path)

    windowed_decision = _decision(windowed)
    letf_decision = _decision(letf_tracking)
    market_decision = _decision(market_impact)
    research_decision = _decision(research_shadow)

    latest_63 = _latest_rolling(windowed, target_ticker, "63")
    latest_126 = _latest_rolling(windowed, target_ticker, "126")
    latest_252 = _latest_rolling(windowed, target_ticker, "252")
    recent_stress = _recent_stress_relationship(windowed, target_ticker)
    summary = windowed.get("summary") if isinstance(windowed.get("summary"), dict) else {}

    rolling_corrs = [
        _finite(latest_63.get("latest_correlation")),
        _finite(latest_126.get("latest_correlation")),
        _finite(latest_252.get("latest_correlation")),
    ]
    rolling_betas = [
        _finite(latest_63.get("latest_beta")),
        _finite(latest_126.get("latest_beta")),
        _finite(latest_252.get("latest_beta")),
    ]
    recent_corr = _finite(recent_stress.get("correlation"))
    recent_beta = _finite(recent_stress.get("beta"))
    recent_drawdown_extreme_days = int(summary.get("recent_0050_drawdown_extreme_days") or 0)
    recent_reward_extreme_days = int(summary.get("recent_0050_reward_extreme_days") or 0)

    r32_beta_check = _threshold_check(letf_tracking, "00632r_60d_abs_beta_error_ceiling")
    r32_corr_check = _threshold_check(letf_tracking, "00632r_60d_correlation_ceiling")
    r32_p05_te_check = _threshold_check(letf_tracking, "00632r_30d_p05_tracking_error_floor")
    live_policy_check = _threshold_check(letf_tracking, "live_hedge_policy_validated")
    effective_fee_check = _threshold_check(letf_tracking, "effective_fee_proxy_independently_validated")

    hedge_evidence_checks = [
        _check(
            "windowed_stability_available",
            bool(windowed) and windowed.get("status") == "available_for_manual_offline_review",
            value=windowed.get("status"),
            threshold="available_for_manual_offline_review",
            source=str(windowed_stability_path),
            blocker="windowed_stability_unavailable",
        ),
        _check(
            "rolling_63_126_252_correlations_are_hedge_like",
            all(value is not None and value <= correlation_ceiling for value in rolling_corrs),
            value=rolling_corrs,
            threshold=f"all <= {correlation_ceiling}",
            source=str(windowed_stability_path),
            blocker="rolling_hedge_correlation_not_persistent",
        ),
        _check(
            "rolling_63_126_252_betas_are_near_inverse",
            all(value is not None and abs(value + 1.0) <= 0.10 for value in rolling_betas),
            value=rolling_betas,
            threshold="abs(beta + 1.0) <= 0.10",
            source=str(windowed_stability_path),
            blocker="rolling_inverse_beta_not_persistent",
        ),
        _check(
            "recent_stress_window_is_hedge_like",
            recent_corr is not None and recent_corr <= correlation_ceiling and recent_beta is not None and abs(recent_beta + 1.0) <= 0.10,
            value={"correlation": recent_corr, "beta": recent_beta},
            threshold={"correlation": f"<= {correlation_ceiling}", "beta": "abs(beta + 1.0) <= 0.10"},
            source=str(windowed_stability_path),
            blocker="recent_stress_window_not_hedge_like",
        ),
    ]

    manual_gate_checks = [
        _check(
            "recent_0050_extreme_days_within_manual_review_limit",
            recent_drawdown_extreme_days <= recent_extreme_days_ceiling
            and recent_reward_extreme_days <= recent_extreme_days_ceiling,
            value={
                "drawdown_extreme_days": recent_drawdown_extreme_days,
                "reward_extreme_days": recent_reward_extreme_days,
            },
            threshold=f"each <= {recent_extreme_days_ceiling}",
            source=str(windowed_stability_path),
            blocker="recent_0050_warning_too_persistent",
        ),
        _check(
            "letf_tracking_review_available",
            bool(letf_tracking),
            value=letf_tracking.get("status"),
            threshold="file_exists",
            source=str(letf_tracking_path),
            blocker="missing_letf_tracking_review",
        ),
        _check(
            "00632r_60d_beta_error_passes_tracking_gate",
            r32_beta_check.get("passed") is True,
            value=r32_beta_check.get("value"),
            threshold=r32_beta_check.get("threshold", beta_abs_error_ceiling),
            source=str(letf_tracking_path),
            blocker="00632r_beta_error_gate_failed",
        ),
        _check(
            "00632r_60d_correlation_passes_tracking_gate",
            r32_corr_check.get("passed") is True,
            value=r32_corr_check.get("value"),
            threshold=r32_corr_check.get("threshold", correlation_ceiling),
            source=str(letf_tracking_path),
            blocker="00632r_tracking_correlation_gate_failed",
        ),
        _check(
            "00632r_30d_tail_tracking_error_passes",
            r32_p05_te_check.get("passed") is True,
            value=r32_p05_te_check.get("value"),
            threshold=r32_p05_te_check.get("threshold"),
            source=str(letf_tracking_path),
            blocker="00632r_tail_tracking_error_gate_failed",
        ),
        _check(
            "effective_fee_proxy_independently_validated",
            effective_fee_check.get("passed") is True,
            value=effective_fee_check.get("value"),
            threshold=True,
            source=str(letf_tracking_path),
            blocker="effective_fee_proxy_not_validated",
        ),
        _check(
            "live_hedge_policy_validated",
            live_policy_check.get("passed") is True,
            value=live_policy_check.get("value"),
            threshold=True,
            source=str(letf_tracking_path),
            blocker="live_hedge_policy_not_validated",
        ),
        _check(
            "letf_readiness_allows_00632r_open",
            letf_decision.get("allow_00632r_open") is True,
            value=letf_decision.get("allow_00632r_open"),
            threshold=True,
            source=str(letf_tracking_path),
            blocker="letf_readiness_blocks_00632r_open",
        ),
        _check(
            "market_impact_allows_trade_or_manual_review",
            market_impact.get("status") in {"available_for_manual_review", "available_for_manual_offline_review"}
            and market_decision.get("target_weight_change_allowed") is True,
            value={
                "status": market_impact.get("status"),
                "target_weight_change_allowed": market_decision.get("target_weight_change_allowed"),
                "auto_rebalance_allowed": market_decision.get("auto_rebalance_allowed"),
            },
            threshold="market impact ready and target weight changes allowed",
            source=str(market_impact_path),
            blocker="market_impact_blocks_trade_or_weight_change",
        ),
        _check(
            "research_shadow_allows_00632r_open",
            research_decision.get("allow_00632r_open") is True,
            value=research_decision.get("allow_00632r_open"),
            threshold=True,
            source=str(research_shadow_path),
            blocker="research_shadow_blocks_00632r_open",
        ),
        _check(
            "windowed_review_does_not_output_actions",
            windowed_decision.get("outputs_actions") is False and windowed_decision.get("outputs_target_weights") is False,
            value={
                "outputs_actions": windowed_decision.get("outputs_actions"),
                "outputs_target_weights": windowed_decision.get("outputs_target_weights"),
            },
            threshold={"outputs_actions": False, "outputs_target_weights": False},
            source=str(windowed_stability_path),
            blocker="windowed_review_outputs_live_actions",
        ),
    ]

    hedge_evidence_available = all(check["passed"] for check in hedge_evidence_checks)
    failed_manual_gates = [check["blocking_reason_if_failed"] for check in manual_gate_checks if not check["passed"]]
    blockers = []
    if not hedge_evidence_available:
        blockers.extend(check["blocking_reason_if_failed"] for check in hedge_evidence_checks if not check["passed"])
    blockers.extend(failed_manual_gates)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "eligible_for_manual_hedge_discussion",
        "policy": "manual_hedge_eligibility_only_no_order_no_target_weight_no_rebalance",
        "target_ticker": target_ticker,
        "benchmark_ticker": benchmark_ticker,
        "inputs": {
            "windowed_stability_review": str(windowed_stability_path),
            "letf_tracking_error_effective_fee_readiness": str(letf_tracking_path),
            "market_impact_readiness": str(market_impact_path),
            "research_shadow_decision_snapshot": str(research_shadow_path),
        },
        "summary": {
            "hedge_evidence_available": hedge_evidence_available,
            "manual_hedge_discussion_allowed": not blockers,
            "failed_manual_gate_count": len(failed_manual_gates),
            "latest_rolling_correlations": {
                "63": rolling_corrs[0],
                "126": rolling_corrs[1],
                "252": rolling_corrs[2],
            },
            "latest_rolling_betas": {
                "63": rolling_betas[0],
                "126": rolling_betas[1],
                "252": rolling_betas[2],
            },
            "recent_stress_relationship": {
                "correlation": recent_corr,
                "beta": recent_beta,
                "relationship": recent_stress.get("relationship"),
            },
            "recent_0050_extreme_days": {
                "drawdown": recent_drawdown_extreme_days,
                "reward_proxy": recent_reward_extreme_days,
            },
        },
        "hedge_evidence_checks": hedge_evidence_checks,
        "manual_gate_checks": manual_gate_checks,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": [
            "hedge_like_evidence_is_not_live_authorization" if hedge_evidence_available else "hedge_like_evidence_incomplete",
            "manual_review_can_only_continue_after_live_gates_change" if blockers else "manual_discussion_only_no_order",
        ],
        "interpretation": [
            "00632R hedge-like rolling evidence exists, but it is insufficient without tracking-error, effective-fee, market-impact, and live policy gates.",
            "This checklist can at most permit manual discussion; it cannot output target weights or an order.",
            "00631L add remains separate and blocked because it increases benchmark beta.",
        ],
        "decision": {
            "hedge_evidence_available": hedge_evidence_available,
            "manual_hedge_discussion_allowed": not blockers,
            "manual_hedge_discussion_blocked": bool(blockers),
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
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
    return history_dir / f"llm_state_reward_interface_manual_hedge_eligibility_{stamp}.json"


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
    parser.add_argument("--windowed-stability", default=str(DEFAULT_WINDOWED_STABILITY))
    parser.add_argument("--letf-tracking", default=str(DEFAULT_LETF_TRACKING))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--research-shadow", default=str(DEFAULT_RESEARCH_SHADOW))
    parser.add_argument("--target-ticker", default="00632R.TW")
    parser.add_argument("--benchmark-ticker", default="0050.TW")
    parser.add_argument("--correlation-ceiling", type=float, default=-0.95)
    parser.add_argument("--beta-abs-error-ceiling", type=float, default=0.10)
    parser.add_argument("--recent-extreme-days-ceiling", type=int, default=1)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        windowed_stability_path=_resolve(args.windowed_stability),
        letf_tracking_path=_resolve(args.letf_tracking),
        market_impact_path=_resolve(args.market_impact),
        research_shadow_path=_resolve(args.research_shadow),
        target_ticker=args.target_ticker,
        benchmark_ticker=args.benchmark_ticker,
        correlation_ceiling=args.correlation_ceiling,
        beta_abs_error_ceiling=args.beta_abs_error_ceiling,
        recent_extreme_days_ceiling=args.recent_extreme_days_ceiling,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward manual hedge eligibility review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "hedge_evidence_available": review["summary"]["hedge_evidence_available"],
                "manual_hedge_discussion_allowed": review["summary"]["manual_hedge_discussion_allowed"],
                "failed_manual_gate_count": review["summary"]["failed_manual_gate_count"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
