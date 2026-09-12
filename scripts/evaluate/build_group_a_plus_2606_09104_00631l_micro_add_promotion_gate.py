#!/usr/bin/env python3
"""Build a promotion gate for the 2606.09104 00631L micro-add candidate.

This consolidates the fixed cap sweep, current risk-aversion gate, BLED tail
review, and current portfolio drift/cost estimate. Passing this gate can only
create a manual promotion-review candidate; it cannot change live weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR,
    DEFAULT_LIVE_SNAPSHOT,
    DEFAULT_TICKERS,
    _load_json,
)


DEFAULT_CAP_SWEEP = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_micro_add_cap_sweep.json"
DEFAULT_RISK_GATE = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_dynamic_risk_aversion_gate.json"
DEFAULT_BLED_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_bled_tail_adjustment_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_micro_add_promotion_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_micro_add_promotion_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _weights(raw: Any) -> dict[str, float]:
    src = raw if isinstance(raw, dict) else {}
    return {key: float(src.get(key, 0.0) or 0.0) for key in [*DEFAULT_TICKERS, "cash"]}


def _current_weights(live_snapshot: dict[str, Any]) -> tuple[dict[str, float], bool, str]:
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    if isinstance(live_snapshot.get("current_weights"), dict):
        return _weights(live_snapshot.get("current_weights")), True, "top_level_current_weights"
    if isinstance(portfolio.get("weights"), dict):
        current = _weights(portfolio.get("weights"))
        if "cash_weight" in portfolio:
            current["cash"] = float(portfolio.get("cash_weight") or 0.0)
        return current, True, "portfolio_state_weights"
    if "cash_weight" in portfolio:
        current = _weights({})
        current["cash"] = float(portfolio.get("cash_weight") or 0.0)
        return current, True, "portfolio_state_cash_weight_only"
    reason = str(live_snapshot.get("state_basis") or "current_weights_missing")
    return _weights({}), False, reason


def _turnover_review(current: dict[str, float], target: dict[str, float], *, linear_cost_bps: float) -> dict[str, Any]:
    keys = [*DEFAULT_TICKERS, "cash"]
    turnover = 0.5 * sum(abs(float(target.get(key, 0.0) or 0.0) - float(current.get(key, 0.0) or 0.0)) for key in keys)
    return {
        "turnover_l1_half": _float(turnover),
        "estimated_linear_cost_bps_of_assets": _float(turnover * linear_cost_bps),
        "execution_cost_state": "LOW_COST" if turnover <= 0.05 and turnover * linear_cost_bps <= 0.5 else "REVIEW_REQUIRED",
    }


def _find_guarded_es_ratio(bled_review: dict[str, Any], target_es: float | None) -> float | None:
    rows = bled_review.get("target_tail_reviews") if isinstance(bled_review.get("target_tail_reviews"), list) else []
    guarded = next((row for row in rows if isinstance(row, dict) and row.get("target_name") == "guarded_live_target"), {})
    guarded_es = abs(float(guarded.get("student_t_adjusted_daily_es95") or 0.0))
    if guarded_es <= 0 or target_es is None:
        return None
    return abs(target_es) / guarded_es


def build_gate(
    *,
    cap_sweep_path: Path = DEFAULT_CAP_SWEEP,
    risk_gate_path: Path = DEFAULT_RISK_GATE,
    bled_review_path: Path = DEFAULT_BLED_REVIEW,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
    preferred_cap: float = 0.04,
    max_turnover: float = 0.05,
    max_cost_bps: float = 0.5,
    linear_cost_bps: float = 5.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    cap_sweep = _load_json(_resolve(cap_sweep_path))
    risk_gate = _load_json(_resolve(risk_gate_path))
    bled_review = _load_json(_resolve(bled_review_path))
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    for name, payload in {
        "cap_sweep": cap_sweep,
        "risk_gate": risk_gate,
        "bled_review": bled_review,
        "live_snapshot": live_snapshot,
        "forward_monitor": forward_monitor,
    }.items():
        if not payload:
            blockers.append(f"{name}_missing")
    cap_reviews = cap_sweep.get("cap_reviews") if isinstance(cap_sweep.get("cap_reviews"), list) else []
    preferred = next((row for row in cap_reviews if abs(float(row.get("cap_00631l") or -1.0) - preferred_cap) < 1e-9), {})
    best_cap = cap_sweep.get("decision", {}).get("best_cap_for_promotion_review")
    if not preferred:
        blockers.append("preferred_cap_review_missing")
    elif preferred.get("passes_high_extreme_gate") is not True:
        blockers.append("preferred_cap_does_not_pass_high_extreme_gate")
    if best_cap is not None and abs(float(best_cap) - preferred_cap) > 1e-9:
        warnings.append("preferred_cap_differs_from_best_cap_for_promotion_review")
    risk_state = (risk_gate.get("risk_aversion") or {}).get("state")
    if risk_state in {"HIGH", "EXTREME"}:
        warnings.append("current_risk_aversion_high_or_extreme_manual_review_required")
    current, current_weights_reliable, current_weight_source_status = _current_weights(live_snapshot)
    if not current_weights_reliable:
        blockers.append("current_weights_missing_or_stale")
    target = _weights({"0050.TW": 0.30, "00631L.TW": preferred_cap, "cash": 0.70 - preferred_cap})
    turnover = _turnover_review(current, target, linear_cost_bps=linear_cost_bps)
    if current_weights_reliable and (turnover.get("turnover_l1_half") or 999.0) > max_turnover:
        blockers.append("micro_add_turnover_exceeds_limit")
    if current_weights_reliable and (turnover.get("estimated_linear_cost_bps_of_assets") or 999.0) > max_cost_bps:
        blockers.append("micro_add_cost_bps_exceeds_limit")
    high_summary = preferred.get("high_extreme_summary") if isinstance(preferred.get("high_extreme_summary"), dict) else {}
    es_ratio = _find_guarded_es_ratio(bled_review, high_summary.get("mean_micro_es_20d"))
    as_of = str(cap_sweep.get("as_of") or live_snapshot.get("as_of") or forward_monitor.get("as_of") or datetime.now().date())
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    candidate_ready = bool(not blockers and preferred.get("passes_high_extreme_gate") is True and turnover["execution_cost_state"] == "LOW_COST")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_micro_add_promotion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "promotion_review_gate_only_no_live_weight_change",
        "status": "manual_review_candidate_ready" if candidate_ready else "blocked",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "constrained_micro_add_promotion_gate",
            "not_imported": ["unconstrained_BLED_optimizer", "short_selling", "auto_rebalance"],
        },
        "latest_a2118_context": {
            "strategy_id": live_signal.get("strategy_id"),
            "target_weights": live_signal.get("target_weights"),
            "market_state": live_signal.get("market_state"),
            "execution_regime": live_signal.get("execution_regime"),
        },
        "candidate": {
            "candidate_id": "00631l_micro_add_cap_4pct",
            "target_weights": target,
            "current_weights": current,
            "current_weights_reliable": current_weights_reliable,
            "current_weight_source_status": current_weight_source_status,
            "preferred_cap": preferred_cap,
            "cap_sweep_high_extreme_summary": high_summary,
            "micro_es_vs_guarded_latest_tail_review_ratio": _float(es_ratio),
            "turnover_review": turnover,
        },
        "decision": {
            "candidate_ready_for_manual_promotion_review": candidate_ready,
            "allow_00631l_micro_add": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "requires_signed_manual_approval": candidate_ready,
            "replace_a2118": False,
            "summary": "4pct 00631L micro-add can be reviewed manually if unblocked; this gate never authorizes live orders.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_gate(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_micro_add_promotion_gate_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap-sweep", default=str(DEFAULT_CAP_SWEEP))
    parser.add_argument("--risk-gate", default=str(DEFAULT_RISK_GATE))
    parser.add_argument("--bled-review", default=str(DEFAULT_BLED_REVIEW))
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--preferred-cap", type=float, default=0.04)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_gate(
        cap_sweep_path=_resolve(args.cap_sweep),
        risk_gate_path=_resolve(args.risk_gate),
        bled_review_path=_resolve(args.bled_review),
        live_snapshot_path=_resolve(args.live_snapshot),
        forward_monitor_path=_resolve(args.forward_monitor),
        preferred_cap=args.preferred_cap,
    )
    write_gate(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
