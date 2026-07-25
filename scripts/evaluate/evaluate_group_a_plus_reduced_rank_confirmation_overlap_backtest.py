#!/usr/bin/env python3
"""Backtest confirmation-gated reduced-rank proxy warnings."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_group_a_plus_reduced_rank_correlation_crash_window_backtest import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_WINDOWS,
    _at_or_above,
    build_daily_scores as build_reduced_rank_daily_scores,
)
from scripts.evaluate.evaluate_group_a_plus_sin_lite_crash_window_backtest import (  # noqa: E402
    build_daily_scores as build_sin_lite_daily_scores,
)
from scripts.evaluate.evaluate_group_a_plus_systemic_bubble_srr_overlap import (  # noqa: E402
    DEFAULT_TICKERS,
    _load_panel,
    build_systemic_daily_frame,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/reduced_rank_confirmation_overlap_backtest/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return round(out, 6) if pd.notna(out) else None


def _load_sin_scores(db_path: Path, as_of: str | None) -> pd.DataFrame:
    scores = build_sin_lite_daily_scores(
        db_path=db_path,
        as_of=as_of,
        lookback=120,
        min_history=80,
        min_tickers=8,
        edge_threshold=0.35,
    )
    if scores.empty:
        return pd.DataFrame()
    scores = scores.copy()
    scores["dt"] = pd.to_datetime(scores["dt"]).dt.normalize()
    return scores.set_index("dt").sort_index()


def _load_systemic_scores(db_path: Path, as_of: str | None, start: str) -> pd.DataFrame:
    try:
        panel = _load_panel(db_path, DEFAULT_TICKERS, start, as_of or datetime.now().strftime("%Y-%m-%d"))
        frame = build_systemic_daily_frame(panel)
    except Exception:
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()
    frame["dt"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame.set_index("dt").sort_index()


def _window_mask(index: pd.Index, windows: list[dict[str, str]]) -> pd.Series:
    mask = pd.Series(False, index=index)
    for window in windows:
        mask |= (index >= pd.Timestamp(window["start"])) & (index <= pd.Timestamp(window["end"]))
    return mask


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series, stress_mask: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    stress = stress_mask.reindex(frame.index).fillna(False).astype(bool)
    non = ~stress
    stress_active = signal & stress
    non_active = signal & non
    return {
        "active_days": int(signal.sum()),
        "active_rate": _safe_rate(int(signal.sum()), int(len(signal))),
        "stress_active_days": int(stress_active.sum()),
        "non_window_active_days": int(non_active.sum()),
        "stress_window_days": int(stress.sum()),
        "non_window_days": int(non.sum()),
        "stress_watch_or_worse_rate": _safe_rate(int(stress_active.sum()), int(stress.sum())),
        "non_window_watch_or_worse_rate": _safe_rate(int(non_active.sum()), int(non.sum())),
        "stress_to_non_rate_ratio": (
            None
            if int(non_active.sum()) == 0 or int(non.sum()) == 0 or int(stress.sum()) == 0
            else float((int(stress_active.sum()) / int(stress.sum())) / (int(non_active.sum()) / int(non.sum())))
        ),
        "active_dates_tail": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal][-20:]],
    }


def _window_summaries(frame: pd.DataFrame, signal: pd.Series, windows: list[dict[str, str]]) -> list[dict[str, Any]]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    out: list[dict[str, Any]] = []
    for window in windows:
        subset = signal[(frame.index >= pd.Timestamp(window["start"])) & (frame.index <= pd.Timestamp(window["end"]))]
        if subset.empty:
            out.append({**window, "status": "no_data", "available_days": 0})
            continue
        out.append(
            {
                **window,
                "status": "available",
                "available_days": int(len(subset)),
                "active_days": int(subset.sum()),
                "active_rate": _safe_rate(int(subset.sum()), int(len(subset))),
            }
        )
    return out


def build_backtest(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = "2026-07-20",
    start: str = "2015-01-05",
    windows: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    windows = windows or DEFAULT_WINDOWS
    reduced = build_reduced_rank_daily_scores(
        db_path=db_path,
        as_of=as_of,
        window=42,
        min_history=63,
        min_tickers=12,
        max_stale_days=10,
        baseline_lookback=252,
    )
    if reduced.empty:
        payload = {
            "schema_version": 1,
            "report_type": "group_a_plus_reduced_rank_confirmation_overlap_backtest",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "status": "blocked",
            "policy": "research_only_confirmation_overlap_no_weight_change",
            "blocking_reasons": ["reduced_rank_daily_scores_unavailable"],
            "decision": {
                "promotion_allowed": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        }
        return payload, pd.DataFrame()

    reduced = reduced.copy()
    reduced["dt"] = pd.to_datetime(reduced["dt"]).dt.normalize()
    frame = reduced.set_index("dt").sort_index().add_prefix("reduced_")
    frame["reduced_watch_or_worse"] = frame["reduced_state"].isin(["watch", "elevated_fragility"])
    frame["reduced_elevated"] = frame["reduced_state"].eq("elevated_fragility")

    sin = _load_sin_scores(db_path, as_of)
    confirmation_sources: list[str] = []
    if not sin.empty:
        frame = frame.join(sin[["state", "sin_lite_score"]].add_prefix("sin_"), how="left")
        frame["sin_watch_or_worse"] = frame["sin_state"].isin(["watch", "elevated", "blocked_for_leverage_add"])
        frame["sin_available"] = frame["sin_state"].notna()
        confirmation_sources.append("sin_lite_watch_or_worse")
    else:
        frame["sin_watch_or_worse"] = False
        frame["sin_available"] = False

    systemic = _load_systemic_scores(db_path, as_of, start)
    if not systemic.empty:
        frame = frame.join(systemic[["systemic_score", "overall_state"]].add_prefix("systemic_"), how="left")
        frame["systemic_watch_or_worse"] = pd.to_numeric(
            frame["systemic_systemic_score"], errors="coerce"
        ).fillna(0) >= 1
        frame["systemic_available"] = frame["systemic_systemic_score"].notna()
        confirmation_sources.append("systemic_bubble_watch_or_worse")
    else:
        frame["systemic_watch_or_worse"] = False
        frame["systemic_available"] = False

    frame["any_confirmation"] = frame["sin_watch_or_worse"] | frame["systemic_watch_or_worse"]
    frame["both_confirmations"] = frame["sin_watch_or_worse"] & frame["systemic_watch_or_worse"]
    frame["confirmed_reduced_rank"] = frame["reduced_watch_or_worse"] & frame["any_confirmation"]
    frame["strict_confirmed_reduced_rank"] = frame["reduced_watch_or_worse"] & frame["both_confirmations"]
    stress_mask = _window_mask(frame.index, windows)

    signals = {
        "reduced_watch_or_worse": frame["reduced_watch_or_worse"],
        "reduced_elevated": frame["reduced_elevated"],
        "sin_watch_or_worse": frame["sin_watch_or_worse"],
        "systemic_watch_or_worse": frame["systemic_watch_or_worse"],
        "any_confirmation": frame["any_confirmation"],
        "confirmed_reduced_rank": frame["confirmed_reduced_rank"],
        "strict_confirmed_reduced_rank": frame["strict_confirmed_reduced_rank"],
    }
    summary = {name: _summarize_signal(frame, signal, stress_mask) for name, signal in signals.items()}
    base = summary["reduced_watch_or_worse"]
    confirmed = summary["confirmed_reduced_rank"]
    blockers = [
        "confirmation_overlap_research_only",
        "reduced_rank_proxy_not_paper_equivalent",
        "no_live_weight_change_allowed",
    ]
    if not confirmation_sources:
        blockers.append("no_historical_confirmation_sources_available")
    if (confirmed.get("active_days") or 0) < 20:
        blockers.append("confirmed_sample_too_small")
    if (confirmed.get("stress_watch_or_worse_rate") or 0.0) <= (base.get("stress_watch_or_worse_rate") or 0.0) * 0.5:
        blockers.append("confirmation_gate_cuts_too_much_stress_recall")
    if (confirmed.get("non_window_watch_or_worse_rate") or 0.0) >= (base.get("non_window_watch_or_worse_rate") or 0.0):
        blockers.append("confirmation_gate_does_not_reduce_non_window_false_positive_rate")

    return (
        {
            "schema_version": 1,
            "report_type": "group_a_plus_reduced_rank_confirmation_overlap_backtest",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "actual_data_start": str(frame.index.min().date()),
            "actual_data_end": str(frame.index.max().date()),
            "status": "blocked",
            "policy": "research_only_confirmation_overlap_no_weight_change",
            "confirmation_sources": confirmation_sources,
            "summary": summary,
            "windows_confirmed_reduced_rank": _window_summaries(
                frame, frame["confirmed_reduced_rank"], windows
            ),
            "blocking_reasons": sorted(set(blockers)),
            "decision": {
                "confirmation_gate_promotable": False,
                "promotion_allowed": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
                "keep_golden1_0531_unchanged": True,
            },
        },
        frame,
    )


def _history_path(history_dir: Path, as_of: str | None, actual_data_end: str | None) -> Path:
    stamp = str(as_of or actual_data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"reduced_rank_confirmation_overlap_backtest_{stamp}.json"


def write_backtest(
    payload: dict[str, Any],
    frame: pd.DataFrame,
    output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not frame.empty:
        frame_output = output_path.with_name(output_path.stem + "_frame.csv")
        frame.to_csv(frame_output, encoding="utf-8-sig")
        payload["frame_output"] = str(frame_output)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload.get("as_of"), payload.get("actual_data_end")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    payload, frame = build_backtest(db_path=_resolve(args.db), as_of=args.as_of, start=args.start)
    write_backtest(payload, frame, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"Reduced-rank confirmation overlap backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "sources": payload.get("confirmation_sources"),
                "base_non_window_rate": (payload.get("summary") or {})
                .get("reduced_watch_or_worse", {})
                .get("non_window_watch_or_worse_rate"),
                "confirmed_non_window_rate": (payload.get("summary") or {})
                .get("confirmed_reduced_rank", {})
                .get("non_window_watch_or_worse_rate"),
                "allow_00631l_add": payload["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
