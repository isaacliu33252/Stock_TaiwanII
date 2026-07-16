#!/usr/bin/env python3
"""Replay a real execution plan with A21.20 00631L add-speed shadow rules.

Research-only.  This reads an existing execution plan and a compounding-regime
diagnostic, then computes what A21.20 would advise for 00631L add speed.  It
does not mutate the execution plan and does not write production pointers.
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

from group_a_plus.integrations.leveraged_compounding_regime import MEAN_REVERTING, TREND_PERSISTENT


DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_compounding_execution_replay_shadow_20260715.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap_standard_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _latest_compounding_report() -> Path | None:
    candidates = [
        path
        for path in (PROJECT_ROOT / "results").glob("00631l_leveraged_compounding_regime_*.json")
        if path.is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _load_compounding(path: Path | None) -> tuple[dict[str, Any], str | None]:
    candidate = _latest_compounding_report() if path is None else path
    if candidate is None or not candidate.exists():
        return {}, None
    payload = _read_json(candidate)
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else payload
    latest = dict(latest) if isinstance(latest, dict) else {}
    return latest, str(candidate)


def _as_int(mapping: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(mapping.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _blocked_guard_names(plan: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for guard in plan.get("pre_trade_guards") or []:
        if isinstance(guard, dict) and str(guard.get("status")) == "blocked":
            out.append(str(guard.get("name") or "unknown_guard"))
    return out


def _hard_blockers(plan: dict[str, Any], compounding: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(compounding.get("date") or "") != str(plan.get("actual_data_date") or ""):
        blockers.append(
            "compounding regime date does not align with execution_plan actual_data_date: "
            f"{compounding.get('date')} != {plan.get('actual_data_date')}"
        )
    if plan.get("execution_guard_reasons"):
        blockers.extend(str(reason) for reason in plan.get("execution_guard_reasons") or [])
    for guard_name in _blocked_guard_names(plan):
        blockers.append(f"blocked pre-trade guard: {guard_name}")
    risk_guard = plan.get("risk_add_pre_trade_guard") if isinstance(plan.get("risk_add_pre_trade_guard"), dict) else {}
    if str(risk_guard.get("status")) == "blocked":
        blockers.append("extreme risk add guard is blocking new risk exposure")
    graph = plan.get("cross_market_graph_advisory") if isinstance(plan.get("cross_market_graph_advisory"), dict) else {}
    if graph.get("no_add_active") is True:
        blockers.append("cross-market graph NO_ADD advisory is active")
    return blockers


def _weak_trend_edge_active(compounding: dict[str, Any], mode: str) -> bool:
    if mode == "none":
        return False
    if mode == "trend_score_eq_min":
        return int(compounding.get("trend_score") or 0) <= 3
    if mode == "relative_momentum_nonpositive":
        return float(compounding.get("00631L_vs_0050_relative_momentum") or 0.0) <= 0.0
    if mode == "ce20_negative":
        return float(compounding.get("compounding_effect_20d") or 0.0) < 0.0
    if mode == "any":
        return (
            _weak_trend_edge_active(compounding, "trend_score_eq_min")
            or _weak_trend_edge_active(compounding, "relative_momentum_nonpositive")
            or _weak_trend_edge_active(compounding, "ce20_negative")
        )
    raise ValueError(f"unknown weak trend edge gate: {mode}")


def replay_compounding_execution_plan(
    plan: dict[str, Any],
    compounding: dict[str, Any],
    *,
    baseline_add_fraction: float = 0.40,
    mean_reversion_add_fraction: float = 0.0,
    trend_persistent_add_fraction: float = 1.0,
    weak_trend_edge_gate: str = "none",
    weak_trend_add_fraction: float = 0.90,
    ticker: str = "00631L.TW",
) -> dict[str, Any]:
    """Return A21.20 replay advisory for a single real execution plan."""

    baseline_add_fraction = min(max(float(baseline_add_fraction), 0.0), 1.0)
    mean_reversion_add_fraction = min(max(float(mean_reversion_add_fraction), 0.0), 1.0)
    trend_persistent_add_fraction = min(max(float(trend_persistent_add_fraction), 0.0), 1.0)
    weak_trend_add_fraction = min(max(float(weak_trend_add_fraction), 0.0), 1.0)

    current = _as_int(plan.get("current_holdings") or {}, ticker)
    theoretical = _as_int(plan.get("theoretical_target_shares") or {}, ticker, current)
    staged = _as_int(plan.get("staged_target_shares_before_guards") or {}, ticker, current)
    final_target = _as_int(plan.get("target_shares") or {}, ticker, current)
    price = float((plan.get("current_prices") or {}).get(ticker) or 0.0)
    regime = str(compounding.get("compounding_regime") or "UNAVAILABLE").upper()
    requested_delta = max(theoretical - current, 0)
    staged_delta = max(staged - current, 0)
    final_delta = max(final_target - current, 0)

    if requested_delta <= 0:
        raw_action = "MAINTAIN"
        shadow_target = final_target
        allowed_fraction = 0.0
        weak_edge_active = False
    elif regime == TREND_PERSISTENT:
        raw_action = "FAST_REENTER_CANDIDATE"
        weak_edge_active = _weak_trend_edge_active(compounding, weak_trend_edge_gate)
        allowed_fraction = weak_trend_add_fraction if weak_edge_active else trend_persistent_add_fraction
        shadow_target = current + int(round(requested_delta * allowed_fraction))
    elif regime == MEAN_REVERTING:
        raw_action = "SLOW_ADD"
        allowed_fraction = mean_reversion_add_fraction
        weak_edge_active = False
        shadow_target = current + int(round(requested_delta * allowed_fraction))
    else:
        raw_action = "MAINTAIN"
        allowed_fraction = baseline_add_fraction
        weak_edge_active = False
        shadow_target = staged

    shadow_target = max(current, min(shadow_target, theoretical))
    hard_blockers = _hard_blockers(plan, compounding)
    blocked_guard_names = _blocked_guard_names(plan)
    action = "BLOCKED_BY_HARD_GUARD" if hard_blockers else raw_action

    shadow_delta = max(shadow_target - current, 0)
    return {
        "ticker": ticker,
        "date": plan.get("actual_data_date"),
        "execution_regime": plan.get("execution_regime"),
        "compounding_regime": regime,
        "raw_action": raw_action,
        "recommended_action": action,
        "production_effect": "none",
        "current_shares": current,
        "theoretical_target_shares": theoretical,
        "staged_target_shares_before_guards": staged,
        "final_execution_plan_target_shares": final_target,
        "requested_delta_shares": requested_delta,
        "staged_delta_shares": staged_delta,
        "final_delta_shares": final_delta,
        "shadow_target_shares_before_hard_guards": shadow_target,
        "shadow_delta_shares_before_hard_guards": shadow_delta,
        "shadow_notional_before_hard_guards": float(shadow_delta * price),
        "baseline_add_fraction": baseline_add_fraction,
        "mean_reversion_add_fraction": mean_reversion_add_fraction,
        "trend_persistent_add_fraction": trend_persistent_add_fraction,
        "weak_trend_edge_gate": weak_trend_edge_gate,
        "weak_trend_edge_active": weak_edge_active,
        "weak_trend_add_fraction": weak_trend_add_fraction,
        "allowed_fraction_for_regime": allowed_fraction,
        "blocked_guard_names": blocked_guard_names,
        "hard_blockers": hard_blockers,
        "interpretation": (
            "A21.20 replay is advisory only; hard blockers are not overridden."
            if hard_blockers
            else "A21.20 replay has no hard blocker in the supplied plan."
        ),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = Path(args.execution_plan)
    if not plan_path.is_absolute():
        plan_path = PROJECT_ROOT / plan_path
    compounding_path = Path(args.compounding_regime) if args.compounding_regime else None
    if compounding_path is not None and not compounding_path.is_absolute():
        compounding_path = PROJECT_ROOT / compounding_path

    plan = _unwrap_standard_payload(_read_json(plan_path))
    compounding, compounding_source = _load_compounding(compounding_path)
    replay = replay_compounding_execution_plan(
        plan,
        compounding,
        baseline_add_fraction=float(args.baseline_add_fraction),
        mean_reversion_add_fraction=float(args.mean_reversion_add_fraction),
        trend_persistent_add_fraction=float(args.trend_persistent_add_fraction),
        weak_trend_edge_gate=str(args.weak_trend_edge_gate),
        weak_trend_add_fraction=float(args.weak_trend_add_fraction),
    )
    return {
        "schema_version": 1,
        "experiment": "00631l_compounding_execution_replay_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "execution_plan_path": str(plan_path),
        "compounding_regime_path": compounding_source,
        "policy": "replay_real_execution_plan_00631l_add_speed_only",
        "replay": replay,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--compounding-regime", default=None, help="Default: latest results/00631l_leveraged_compounding_regime_*.json")
    parser.add_argument("--baseline-add-fraction", type=float, default=0.40)
    parser.add_argument("--mean-reversion-add-fraction", type=float, default=0.0)
    parser.add_argument("--trend-persistent-add-fraction", type=float, default=1.0)
    parser.add_argument(
        "--weak-trend-edge-gate",
        choices=("none", "trend_score_eq_min", "relative_momentum_nonpositive", "ce20_negative", "any"),
        default="none",
    )
    parser.add_argument("--weak-trend-add-fraction", type=float, default=0.90)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(report["replay"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
