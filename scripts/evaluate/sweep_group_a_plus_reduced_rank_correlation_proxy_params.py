#!/usr/bin/env python3
"""Sweep weak reduced-rank correlation proxy parameters for GroupA+."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_reduced_rank_correlation_proxy import (  # noqa: E402
    DEFAULT_DB,
    build_proxy,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/reduced_rank_correlation_proxy_param_sweep/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _parse_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _score_candidate(proxy: dict[str, Any]) -> dict[str, Any]:
    latest = proxy.get("latest") or {}
    state = latest.get("state")
    state_penalty = {"normal": 0.0, "watch": 0.25, "elevated_fragility": 0.5, "unavailable": 1.0}.get(
        str(state), 0.75
    )
    usable = int((proxy.get("coverage") or {}).get("usable_ticker_count") or 0)
    snapshots = int((proxy.get("coverage") or {}).get("snapshot_count") or 0)
    distance_percentile = float(latest.get("distance_percentile") or 0.0)
    objective = usable / 100.0 + snapshots / 1000.0 - state_penalty - abs(distance_percentile - 0.5) * 0.1
    return {
        "objective": round(objective, 6),
        "state": state,
        "usable_ticker_count": usable,
        "snapshot_count": snapshots,
        "distance_percentile": latest.get("distance_percentile"),
        "reduced_rank_mean_corr": latest.get("reduced_rank_mean_corr"),
        "manual_review_required": latest.get("manual_review_required"),
    }


def run_sweep(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = "2026-07-20",
    windows: list[int] | None = None,
    min_histories: list[int] | None = None,
    analysis_lookbacks: list[int] | None = None,
    min_tickers_values: list[int] | None = None,
    max_stale_days: int = 10,
) -> dict[str, Any]:
    windows = windows or [21, 42, 63]
    min_histories = min_histories or [63, 84]
    analysis_lookbacks = analysis_lookbacks or [252, 504]
    min_tickers_values = min_tickers_values or [12, 20]

    candidates: list[dict[str, Any]] = []
    for window in windows:
        for min_history in min_histories:
            for analysis_lookback in analysis_lookbacks:
                if analysis_lookback < window + 1 or min_history < window:
                    continue
                for min_tickers in min_tickers_values:
                    proxy = build_proxy(
                        db_path=db_path,
                        as_of=as_of,
                        window=window,
                        min_history=min_history,
                        analysis_lookback=analysis_lookback,
                        min_tickers=min_tickers,
                        max_stale_days=max_stale_days,
                    )
                    score = _score_candidate(proxy)
                    candidates.append(
                        {
                            "params": {
                                "window": window,
                                "min_history": min_history,
                                "analysis_lookback": analysis_lookback,
                                "min_tickers": min_tickers,
                                "max_stale_days": max_stale_days,
                            },
                            "status": proxy.get("status"),
                            "blocking_reasons": proxy.get("blocking_reasons"),
                            "warning_reasons": proxy.get("warning_reasons"),
                            "score": score,
                            "decision": {
                                "promote_to_live": False,
                                "target_weight_change_allowed": False,
                                "allow_00631l_add": False,
                                "allow_00632r_open": False,
                            },
                        }
                    )

    candidates = sorted(candidates, key=lambda item: item["score"]["objective"], reverse=True)
    available = [item for item in candidates if item["status"] == "available_for_manual_review"]
    states = Counter(str((item.get("score") or {}).get("state")) for item in available)
    manual_review_count = sum(1 for item in available if (item.get("score") or {}).get("manual_review_required"))
    best = available[0] if available else (candidates[0] if candidates else {})
    blockers = ["reduced_rank_proxy_sweep_research_only", "no_live_weight_change_allowed"]
    if not available:
        blockers.append("no_available_reduced_rank_proxy_candidates")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_reduced_rank_correlation_proxy_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked",
        "policy": "research_only_parameter_sweep_no_live_weight_change",
        "grid": {
            "windows": windows,
            "min_histories": min_histories,
            "analysis_lookbacks": analysis_lookbacks,
            "min_tickers_values": min_tickers_values,
            "max_stale_days": max_stale_days,
            "candidate_count": len(candidates),
            "available_candidate_count": len(available),
        },
        "aggregate": {
            "available_state_counts": dict(sorted(states.items())),
            "manual_review_candidate_count": manual_review_count,
            "normal_candidate_count": int(states.get("normal", 0)),
            "watch_or_elevated_candidate_count": int(states.get("watch", 0) + states.get("elevated_fragility", 0)),
        },
        "best_candidate": best,
        "candidates": candidates,
        "blocking_reasons": blockers,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"reduced_rank_correlation_proxy_param_sweep_{stamp}.json"


def write_sweep(payload: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload.get("as_of")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--windows", default="21,42,63")
    parser.add_argument("--min-histories", default="63,84")
    parser.add_argument("--analysis-lookbacks", default="252,504")
    parser.add_argument("--min-tickers-values", default="12,20")
    parser.add_argument("--max-stale-days", type=int, default=10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = run_sweep(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        windows=_parse_ints(args.windows),
        min_histories=_parse_ints(args.min_histories),
        analysis_lookbacks=_parse_ints(args.analysis_lookbacks),
        min_tickers_values=_parse_ints(args.min_tickers_values),
        max_stale_days=int(args.max_stale_days),
    )
    write_sweep(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"Reduced-rank correlation proxy parameter sweep: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "available_candidate_count": payload["grid"]["available_candidate_count"],
                "available_state_counts": payload["aggregate"]["available_state_counts"],
                "allow_00631l_add": payload["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
