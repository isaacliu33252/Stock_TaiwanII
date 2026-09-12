#!/usr/bin/env python3
"""Build bootstrap promotion gate for 2607.16450 GroupA+ candidates.

The paper notes that portfolio-ranking differences were not formally tested.
This report adds a conservative bootstrap gate for shadow candidates. It never
changes target weights; promotion requires enough forward rows and a positive
bootstrap lower confidence bound.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGED_EVENT_STUDY = PROJECT_ROOT / "report/group_a_plus/latest/staged_reentry_shadow_event_study.json"
DEFAULT_A2118_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
DEFAULT_CANDIDATE_TAIL = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_candidate_tail_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_bootstrap_promotion_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_bootstrap_promotion_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _bootstrap_mean_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.choice(arr, size=(samples, len(arr)), replace=True).mean(axis=1)
    lower = float(np.quantile(draws, alpha / 2.0))
    upper = float(np.quantile(draws, 1.0 - alpha / 2.0))
    return {
        "mean": float(arr.mean()),
        "ci_lower": lower,
        "ci_upper": upper,
        "positive_rate": float((arr > 0.0).mean()),
        "sample_count": int(len(arr)),
    }


def _staged_edges(staged_event_study: dict[str, Any]) -> dict[str, list[float]]:
    out = {"edge_5d": [], "edge_10d": [], "edge_20d": []}
    for event in staged_event_study.get("events") or []:
        if not isinstance(event, dict):
            continue
        forward = event.get("forward") if isinstance(event.get("forward"), dict) else {}
        for key in out:
            value = _as_float(forward.get(key))
            if value is not None:
                out[key].append(value)
    return out


def _candidate_statuses(candidate_tail: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in candidate_tail.get("candidate_reviews") or []:
        if isinstance(row, dict) and row.get("name"):
            out[str(row["name"])] = str(row.get("tail_review_status") or "unknown")
    return out


def _review_staged(
    staged_event_study: dict[str, Any],
    *,
    min_rows: int,
    bootstrap_samples: int,
    seed: int,
    alpha: float,
) -> dict[str, Any]:
    edges_by_horizon = _staged_edges(staged_event_study)
    horizon_reviews: dict[str, Any] = {}
    blockers: list[str] = []
    for horizon, values in edges_by_horizon.items():
        if len(values) < min_rows:
            horizon_reviews[horizon] = {
                "status": "insufficient_forward_rows",
                "sample_count": len(values),
                "required_min_rows": min_rows,
            }
            blockers.append(f"staged_reentry_{horizon}_bootstrap_rows_below_minimum")
            continue
        ci = _bootstrap_mean_ci(values, samples=bootstrap_samples, seed=seed, alpha=alpha)
        status = "passed" if ci["ci_lower"] > 0.0 else "failed_ci_lower_not_positive"
        if status != "passed":
            blockers.append(f"staged_reentry_{horizon}_bootstrap_ci_lower_not_positive")
        horizon_reviews[horizon] = {"status": status, **ci}
    return {
        "name": "staged_reentry",
        "source_status": staged_event_study.get("status"),
        "active_event_count": staged_event_study.get("active_event_count"),
        "horizon_reviews": horizon_reviews,
        "statistical_status": "passed" if not blockers else "blocked",
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "summary": "Staged re-entry requires enough realized forward edge rows and positive bootstrap lower bounds before promotion.",
        },
    }


def _review_a2118(a2118_monitor: dict[str, Any], *, min_rows: int) -> dict[str, Any]:
    requirements = a2118_monitor.get("monitoring_requirements")
    if not isinstance(requirements, dict):
        requirements = {}
    count = int(requirements.get("current_forward_rows_counted_by_log") or 0)
    parity = a2118_monitor.get("latest_live_action_parity")
    parity_validated = isinstance(parity, dict) and parity.get("validated") is True
    blockers: list[str] = []
    if count < min_rows:
        blockers.append("a2118_forward_rows_below_bootstrap_minimum")
    if not parity_validated:
        blockers.append("a2118_latest_live_action_parity_not_validated")
    return {
        "name": "a2118_seed_averaging",
        "source_status": a2118_monitor.get("status"),
        "forward_rows": count,
        "required_min_rows": min_rows,
        "latest_live_action_parity_validated": parity_validated,
        "statistical_status": "blocked" if blockers else "ready_for_return_series_bootstrap",
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "summary": "A21.18 needs enough forward rows and live-action parity before bootstrap return testing is meaningful.",
        },
    }


def build_bootstrap_gate(
    *,
    staged_event_study_path: Path = DEFAULT_STAGED_EVENT_STUDY,
    a2118_monitor_path: Path = DEFAULT_A2118_MONITOR,
    candidate_tail_path: Path = DEFAULT_CANDIDATE_TAIL,
    min_rows: int = 20,
    bootstrap_samples: int = 2000,
    seed: int = 260716450,
    alpha: float = 0.05,
) -> dict[str, Any]:
    staged = _load(staged_event_study_path)
    a2118 = _load(a2118_monitor_path)
    candidate_tail = _load(candidate_tail_path)
    blockers: list[str] = []
    for name, payload in {
        "staged_reentry_event_study": staged,
        "a2118_forward_monitor": a2118,
        "candidate_tail_review": candidate_tail,
    }.items():
        if not payload:
            blockers.append(f"missing_required_input:{name}")

    candidate_reviews = [
        _review_staged(
            staged,
            min_rows=min_rows,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
            alpha=alpha,
        ),
        _review_a2118(a2118, min_rows=min_rows),
    ]
    candidate_statuses = _candidate_statuses(candidate_tail)
    for review in candidate_reviews:
        review["candidate_tail_status"] = candidate_statuses.get(review["name"], "missing")
        blockers.extend(f"{review['name']}:{item}" for item in review.get("blocking_reasons") or [])

    live_ready = [
        row["name"]
        for row in candidate_reviews
        if row.get("statistical_status") == "passed"
        and row.get("candidate_tail_status") not in {"blocked_for_live_promotion", "inactive_blocked"}
    ]
    as_of = staged.get("events", [{}])[-1].get("actual_data_date") if staged.get("events") else None
    as_of = as_of or a2118.get("as_of") or candidate_tail.get("as_of") or "unknown"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_bootstrap_promotion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "statistical_gate_only_no_live_weight_change",
        "status": "blocked_for_live_promotion" if blockers or not live_ready else "passed_shadow_statistical_gate",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.16450.pdf",
            "limitation_addressed": "portfolio_ranking_differences_not_formally_tested",
            "implemented_as": "bootstrap_forward_edge_promotion_gate",
        },
        "parameters": {
            "min_rows": min_rows,
            "bootstrap_samples": bootstrap_samples,
            "seed": seed,
            "alpha": alpha,
        },
        "candidate_reviews": candidate_reviews,
        "live_ready_candidates": live_ready,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_bootstrap_gate": False,
            "summary": "No candidate can be promoted until forward rows are sufficient and bootstrap evidence is positive after tail/cost gates.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "inputs": {
            "staged_reentry_event_study": str(staged_event_study_path),
            "a2118_forward_monitor": str(a2118_monitor_path),
            "candidate_tail_review": str(candidate_tail_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_bootstrap_promotion_gate_{stamp}.json"


def write_gate(gate: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(gate.get("as_of"))).write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-event-study", default=str(DEFAULT_STAGED_EVENT_STUDY))
    parser.add_argument("--a2118-monitor", default=str(DEFAULT_A2118_MONITOR))
    parser.add_argument("--candidate-tail", default=str(DEFAULT_CANDIDATE_TAIL))
    parser.add_argument("--min-rows", type=int, default=20)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=260716450)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    gate = build_bootstrap_gate(
        staged_event_study_path=_resolve(args.staged_event_study),
        a2118_monitor_path=_resolve(args.a2118_monitor),
        candidate_tail_path=_resolve(args.candidate_tail),
        min_rows=int(args.min_rows),
        bootstrap_samples=int(args.bootstrap_samples),
        seed=int(args.seed),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_gate(gate, output, history_dir)
    print(f"2607.16450 bootstrap promotion gate: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, str(gate.get('as_of')))}")
    print(
        json.dumps(
            {
                "status": gate["status"],
                "live_ready_candidates": gate["live_ready_candidates"],
                "blocking_reasons": gate["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
