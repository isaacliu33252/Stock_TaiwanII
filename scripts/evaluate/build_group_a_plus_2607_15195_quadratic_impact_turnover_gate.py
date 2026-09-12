#!/usr/bin/env python3
"""Build a 2607.15195 quadratic-impact / turnover promotion gate.

This gate imports the paper's explicit cost discipline, not its oracle-signal
optimizer. It checks whether target-holding proposals survive linear cost,
quadratic impact, turnover, and real-signal economic sample requirements.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COST_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_cost_aware_target_holding_shadow.json"
DEFAULT_SIGNAL_GATE = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_quadratic_impact_turnover_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_15195_quadratic_impact_turnover_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _scenario(report: dict[str, Any], name: str) -> dict[str, Any]:
    rows = report.get("scenarios") if isinstance(report.get("scenarios"), list) else []
    return next((row for row in rows if isinstance(row, dict) and row.get("scenario") == name), {})


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def build_gate(
    *,
    cost_shadow_path: Path = DEFAULT_COST_SHADOW,
    signal_gate_path: Path = DEFAULT_SIGNAL_GATE,
    market_impact_path: Path = DEFAULT_MARKET_IMPACT,
    max_turnover: float = 0.10,
    max_cost_bps_assets: float = 2.0,
    max_quadratic_share_of_total_cost: float = 0.25,
    max_raw_vs_guarded_turnover_ratio: float = 5.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    cost_shadow = _load(_resolve(cost_shadow_path))
    signal_gate = _load(_resolve(signal_gate_path))
    market_impact = _load(_resolve(market_impact_path))

    if not cost_shadow:
        blockers.append("cost_aware_target_holding_shadow_missing")
    if not signal_gate:
        blockers.append("real_signal_quality_gate_missing")
    if not market_impact:
        warnings.append("market_impact_readiness_review_missing")

    guarded = _scenario(cost_shadow, "guarded_live_target")
    raw = _scenario(cost_shadow, "raw_a2118_seed_ensemble_target")
    reviewed_scenarios: list[dict[str, Any]] = []
    for row in [guarded, raw]:
        if not row:
            continue
        total_cost = float(row.get("total_estimated_cost") or 0.0)
        quadratic_cost = float(row.get("quadratic_impact_cost") or 0.0)
        quadratic_share = quadratic_cost / total_cost if total_cost > 0 else 0.0
        scenario_blockers: list[str] = []
        if isinstance(row.get("turnover"), (int, float)) and float(row["turnover"]) > max_turnover:
            scenario_blockers.append("turnover_exceeds_limit")
        if (
            isinstance(row.get("total_estimated_cost_bps_of_assets"), (int, float))
            and float(row["total_estimated_cost_bps_of_assets"]) > max_cost_bps_assets
        ):
            scenario_blockers.append("cost_bps_assets_exceeds_limit")
        if quadratic_share > max_quadratic_share_of_total_cost:
            scenario_blockers.append("quadratic_impact_share_exceeds_limit")
        reviewed_scenarios.append(
            {
                "scenario": row.get("scenario"),
                "turnover": row.get("turnover"),
                "total_estimated_cost_bps_of_assets": row.get("total_estimated_cost_bps_of_assets"),
                "linear_cost": row.get("linear_cost"),
                "quadratic_impact_cost": row.get("quadratic_impact_cost"),
                "quadratic_share_of_total_cost": _float(quadratic_share),
                "execution_cost_state": row.get("execution_cost_state"),
                "scenario_passes_cost_gate": not scenario_blockers,
                "scenario_blocking_reasons": scenario_blockers,
            }
        )
        if row.get("scenario") == "guarded_live_target":
            blockers.extend(f"guarded_live_target:{reason}" for reason in scenario_blockers)

    if guarded and raw:
        guarded_turnover = float(guarded.get("turnover") or 0.0)
        raw_turnover = float(raw.get("turnover") or 0.0)
        ratio = raw_turnover / guarded_turnover if guarded_turnover > 0 else np.inf
        if ratio > max_raw_vs_guarded_turnover_ratio:
            warnings.append("raw_a2118_target_turnover_materially_exceeds_guarded_target")
    else:
        ratio = None

    signal_decision = _decision(signal_gate)
    if signal_gate.get("status") != "pass":
        blockers.append("real_signal_quality_gate_not_passed")
    if signal_decision.get("real_signal_quality_sufficient_for_sciphyrl_optimizer_research") is not True:
        blockers.append("real_signal_quality_insufficient_for_optimizer_research")

    market_decision = _decision(market_impact)
    if market_impact and market_impact.get("status") == "blocked":
        blockers.append("market_impact_readiness_blocked")
    if market_decision and market_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("market_impact_disallows_auto_rebalance")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_15195_quadratic_impact_turnover_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_governance_gate_no_live_weight_change",
        "status": "pass" if not blockers else "blocked",
        "as_of": cost_shadow.get("as_of") or signal_gate.get("as_of") or market_impact.get("as_of"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.15195.pdf",
            "paper_title": "SciPhy Reinforcement Learning for Portfolio Optimization",
            "imported_concept": "quadratic_execution_impact_and_turnover_penalty_as_promotion_gate",
            "not_imported": ["oracle_signal", "pinn_hjb_optimizer", "automatic_target_holding_policy"],
        },
        "parameters": {
            "max_turnover": max_turnover,
            "max_cost_bps_assets": max_cost_bps_assets,
            "max_quadratic_share_of_total_cost": max_quadratic_share_of_total_cost,
            "max_raw_vs_guarded_turnover_ratio": max_raw_vs_guarded_turnover_ratio,
        },
        "scenario_cost_reviews": reviewed_scenarios,
        "raw_vs_guarded_turnover_ratio": _float(ratio),
        "upstream_status": {
            "cost_aware_target_holding_shadow": cost_shadow.get("status"),
            "real_signal_quality_gate": signal_gate.get("status"),
            "market_impact_readiness_review": market_impact.get("status"),
        },
        "decision": {
            "quadratic_impact_turnover_gate_passed": not blockers,
            "allow_sciphyrl_optimizer_research": False if blockers else True,
            "allow_raw_a2118_target_to_override_guarded_target": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "Turnover/impact gate is governance only; proposals must pass cost and real-signal gates before optimizer research.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {
            "cost_shadow": str(cost_shadow_path),
            "signal_gate": str(signal_gate_path),
            "market_impact": str(market_impact_path),
        },
    }


def write_gate(gate: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(gate.get("as_of") or datetime.now().date())
    (history_dir / f"2607_15195_quadratic_impact_turnover_gate_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cost-shadow", default=str(DEFAULT_COST_SHADOW))
    parser.add_argument("--signal-gate", default=str(DEFAULT_SIGNAL_GATE))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--max-turnover", type=float, default=0.10)
    parser.add_argument("--max-cost-bps-assets", type=float, default=2.0)
    parser.add_argument("--max-quadratic-share-of-total-cost", type=float, default=0.25)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gate = build_gate(
        cost_shadow_path=_resolve(args.cost_shadow),
        signal_gate_path=_resolve(args.signal_gate),
        market_impact_path=_resolve(args.market_impact),
        max_turnover=args.max_turnover,
        max_cost_bps_assets=args.max_cost_bps_assets,
        max_quadratic_share_of_total_cost=args.max_quadratic_share_of_total_cost,
    )
    write_gate(gate, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(gate["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
