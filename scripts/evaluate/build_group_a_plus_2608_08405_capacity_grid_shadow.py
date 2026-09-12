#!/usr/bin/env python3
"""Build finite-grid capacity interval shadow report for GroupA+.

arXiv 2608.08405 argues that finite deployment grids should report capacity
intervals with simultaneous bands, not point estimates. GroupA+ does not have a
randomized sleeve experiment, so this report creates the grid specification and
readiness audit only. It cannot change live weights or scale capital.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_ASSIGNED_REALIZED = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_capacity_grid_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_capacity_grid_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_08405_capacity_grid_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _float_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _date_key(payload: dict[str, Any]) -> str | None:
    value = payload.get("requested_as_of_date") or payload.get("actual_data_date") or payload.get("as_of")
    return str(value) if value else None


def _grid_rows(*, weights: dict[str, float], capital: float, arms: list[float], max_pov: float | None) -> list[dict[str, Any]]:
    risky_weight = sum(value for key, value in weights.items() if key != "cash")
    rows: list[dict[str, Any]] = []
    for arm in arms:
        deployed = capital * arm * risky_weight
        rows.append(
            {
                "deployment_arm_beta": float(arm),
                "scaled_risky_notional": round(float(deployed), 6),
                "scaled_cash_weight_reference": float(max(0.0, 1.0 - arm * risky_weight)),
                "one_sided_impact_proxy_max_pov": None if max_pov is None else round(float(max_pov * arm), 12),
                "observed_edge_erosion": None,
                "simultaneous_band_lower": None,
                "simultaneous_band_upper": None,
            }
        )
    return rows


def build_report(
    *,
    live_signal_path: Path,
    market_impact_path: Path,
    assigned_realized_path: Path,
    capital: float,
    arms: list[float],
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    market = _unwrap(_load(market_impact_path))
    assigned_realized = _load(assigned_realized_path)

    weights = _float_map(live.get("target_weights"))
    market_computed = market.get("computed") if isinstance(market.get("computed"), dict) else {}
    try:
        max_pov = float(market_computed.get("max_participation_of_volume"))
    except (TypeError, ValueError):
        max_pov = None

    rows = _grid_rows(weights=weights, capital=capital, arms=arms, max_pov=max_pov)
    assigned_ready = assigned_realized.get("status") == "ready_for_capacity_shadow_review"
    market_ready = market.get("status") not in {None, "blocked"} and market.get("decision", {}).get("target_weight_change_allowed") is True

    blockers: list[str] = []
    if not weights:
        blockers.append("live_target_weights_missing")
    if len(arms) < 3:
        blockers.append("finite_grid_has_too_few_arms")
    if not assigned_ready:
        blockers.append("assigned_realized_deployment_not_ready")
    if not market_ready:
        blockers.append("market_impact_not_ready_for_capacity_grid")
    blockers.extend(
        [
            "randomized_parallel_sleeve_observations_missing",
            "edge_erosion_by_deployment_arm_missing",
            "simultaneous_band_not_estimable",
        ]
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_08405_capacity_grid_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "not_identified_shadow_only",
        "policy": "finite_grid_capacity_interval_shadow_no_weight_change",
        "as_of": _date_key(live),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf",
            "concept": "finite_arm_grids_should_report_capacity_intervals_not_point_estimates",
        },
        "grid_specification": {
            "capital": float(capital),
            "arms": [float(item) for item in arms],
            "arm_count": len(arms),
            "target_weights": weights,
            "simultaneous_band_required": True,
            "point_estimate_allowed": False,
            "capacity_interval_identified": False,
            "capacity_interval": {"lower_beta": None, "upper_beta_open": None},
        },
        "grid_rows": rows,
        "upstream_status": {
            "market_impact_status": market.get("status"),
            "market_impact_target_weight_change_allowed": market.get("decision", {}).get("target_weight_change_allowed"),
            "assigned_realized_status": assigned_realized.get("status"),
        },
        "blocking_reasons": blockers,
        "decision": {
            "capacity_interval_reported": False,
            "capacity_point_estimate_reported": False,
            "capacity_claim_allowed": False,
            "capacity_scaling_allowed": False,
            "latest_strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "summary": (
                "A finite deployment grid can be specified, but no capacity interval is identified "
                "without randomized sleeve observations, realized deployment, and observed edge "
                "erosion by arm. Keep this as shadow governance only."
            ),
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "market_impact": str(market_impact_path),
            "assigned_realized": str(assigned_realized_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    spec = report["grid_specification"]
    decision = report["decision"]
    lines = [
        "# 2608.08405 Capacity Grid Shadow",
        "",
        f"- status: {report['status']}",
        f"- as_of: {report.get('as_of')}",
        f"- policy: {report['policy']}",
        f"- capital: {spec['capital']:.2f}",
        f"- arm_count: {spec['arm_count']}",
        f"- simultaneous_band_required: {spec['simultaneous_band_required']}",
        f"- capacity_interval_identified: {spec['capacity_interval_identified']}",
        f"- point_estimate_allowed: {spec['point_estimate_allowed']}",
        f"- capacity_scaling_allowed: {decision['capacity_scaling_allowed']}",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Grid Rows"])
    for row in report["grid_rows"]:
        lines.append(
            "- beta={beta}: scaled_risky_notional={notional:.2f}, impact_proxy_max_pov={pov}".format(
                beta=row["deployment_arm_beta"],
                notional=row["scaled_risky_notional"],
                pov=row["one_sided_impact_proxy_max_pov"],
            )
        )
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    date = str(report.get("as_of") or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2608_08405_capacity_grid_shadow_{date}.json"


def write_report(report: dict[str, Any], *, output_path: Path, markdown_path: Path | None, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--assigned-realized", default=str(DEFAULT_ASSIGNED_REALIZED))
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--arms", type=float, nargs="+", default=[0.0, 0.5, 1.0, 1.5, 2.0])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=_resolve(args.live_signal),
        market_impact_path=_resolve(args.market_impact),
        assigned_realized_path=_resolve(args.assigned_realized),
        capital=float(args.capital),
        arms=[float(item) for item in args.arms],
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown) if args.markdown else None
    history = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output_path=output, markdown_path=markdown, history_dir=history)
    print(f"2608.08405 capacity grid shadow: {output}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
