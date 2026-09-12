#!/usr/bin/env python3
"""Backtest RWC no-add shadow economics for 00631L.

This answers a narrow question: if a tail-high signal pauses a hypothetical
new 00631L add, did that pause avoid losses or mostly miss gains? Research-only;
it never changes live guards, target weights, or orders.
"""

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

from scripts.evaluate.evaluate_group_a_plus_regime_weighted_tail_conformal_walk_forward import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_TARGET_TICKER,
    DEFAULT_YEARS,
    _append_weighted_rows_fast,
    _load_close,
    _resolve,
    _selected_dates,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/rwc_no_add_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/rwc_no_add_shadow_backtest/history"
DEFAULT_CANDIDATES = (
    ("default_calibration", 126.0, 1.0, 60),
    ("balanced_selectivity", 126.0, 1.25, 60),
    ("low_noise", 252.0, 1.5, 60),
)


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _candidate_rows(
    *,
    close: pd.Series,
    dates: list[pd.Timestamp],
    label: str,
    half_life: float,
    bandwidth: float,
    min_ess: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _append_weighted_rows_fast(
        rows,
        close=close,
        dates=dates,
        method=label,
        use_regime_kernel=True,
        half_life=half_life,
        bandwidth=bandwidth,
        min_effective_sample_size=min_ess,
    )
    return rows


def _event_summary(rows: list[dict[str, Any]], *, add_notional: float) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"status": "unavailable", "reason": "no_rows"}
    out: dict[str, Any] = {}
    for horizon, group in frame.groupby("horizon"):
        high = group[group["tail_high"]].copy()
        total_rows = int(len(group))
        high_rows = int(len(high))
        if high.empty:
            out[horizon] = {
                "total_rows": total_rows,
                "paused_add_rows": 0,
                "pause_rate": 0.0,
                "net_pause_benefit_per_event": None,
                "total_pause_benefit": 0.0,
            }
            continue
        high["pause_benefit"] = -float(add_notional) * high["actual_forward_return"].astype(float)
        avoided = high[high["pause_benefit"] > 0.0]
        missed = high[high["pause_benefit"] < 0.0]
        out[horizon] = {
            "total_rows": total_rows,
            "paused_add_rows": high_rows,
            "pause_rate": _safe_rate(high_rows, total_rows),
            "add_notional": float(add_notional),
            "total_pause_benefit": float(high["pause_benefit"].sum()),
            "net_pause_benefit_per_event": float(high["pause_benefit"].mean()),
            "median_pause_benefit_per_event": float(high["pause_benefit"].median()),
            "avoided_loss_rate": _safe_rate(int(len(avoided)), high_rows),
            "missed_gain_rate": _safe_rate(int(len(missed)), high_rows),
            "average_avoided_loss_when_positive": None if avoided.empty else float(avoided["pause_benefit"].mean()),
            "average_missed_gain_when_negative": None if missed.empty else float(missed["pause_benefit"].mean()),
            "severe_mdd_8pct_rate_on_paused_rows": _safe_rate(int(high["severe_mdd_8pct"].sum()), high_rows),
            "mean_forward_return_on_paused_rows": float(high["actual_forward_return"].mean()),
            "mean_forward_mdd_on_paused_rows": float(high["actual_forward_mdd"].mean()),
        }
    return out


def _rank_candidate(summary: dict[str, Any]) -> dict[str, Any]:
    h5 = summary.get("h5") or {}
    h10 = summary.get("h10") or {}
    total_benefit = float(h5.get("total_pause_benefit") or 0.0) + float(h10.get("total_pause_benefit") or 0.0)
    avg_pause_rate = (float(h5.get("pause_rate") or 0.0) + float(h10.get("pause_rate") or 0.0)) / 2.0
    severe_rate = (
        float(h5.get("severe_mdd_8pct_rate_on_paused_rows") or 0.0)
        + float(h10.get("severe_mdd_8pct_rate_on_paused_rows") or 0.0)
    ) / 2.0
    return {
        "combined_total_pause_benefit": total_benefit,
        "mean_pause_rate": avg_pause_rate,
        "mean_severe_mdd_8pct_rate_on_paused_rows": severe_rate,
        "promotion_hint": "negative_benefit_do_not_promote" if total_benefit < 0 else "positive_shadow_candidate",
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    years = {int(part.strip()) for part in str(args.years).split(",") if part.strip()}
    close = _load_close(db_path, args.ticker, args.start, args.end)
    dates = _selected_dates(close, years, args.end)
    if args.max_dates and len(dates) > args.max_dates:
        step = max(1, len(dates) // int(args.max_dates))
        dates = dates[::step][: int(args.max_dates)]

    candidates: list[dict[str, Any]] = []
    for label, half_life, bandwidth, min_ess in DEFAULT_CANDIDATES:
        rows = _candidate_rows(
            close=close,
            dates=dates,
            label=label,
            half_life=half_life,
            bandwidth=bandwidth,
            min_ess=min_ess,
        )
        summary = _event_summary(rows, add_notional=args.add_notional)
        candidates.append(
            {
                "candidate": label,
                "params": {
                    "half_life": half_life,
                    "bandwidth": bandwidth,
                    "min_effective_sample_size": min_ess,
                },
                "summary": summary,
                "ranking_metrics": _rank_candidate(summary),
            }
        )
    ranked = sorted(candidates, key=lambda item: item["ranking_metrics"]["combined_total_pause_benefit"], reverse=True)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_rwc_no_add_shadow_backtest",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "no_add_shadow_backtest_only_no_weight_change_no_guard_promotion",
        "inputs": {
            "db": str(db_path),
            "ticker": args.ticker,
            "start": args.start,
            "end": args.end,
            "years": sorted(years),
            "date_count": int(len(dates)),
            "sampled_max_dates": args.max_dates,
            "add_notional": float(args.add_notional),
        },
        "ranked_candidates": ranked,
        "best_candidate": ranked[0] if ranked else None,
        "interpretation": (
            "pause_benefit = -add_notional * forward_return. Positive means the no-add pause avoided a loss; "
            "negative means it missed a gain. This is event-level and does not model overlapping capital constraints."
        ),
        "decision": {
            "creates_orders": False,
            "changes_target_weights": False,
            "blocks_trades": False,
            "production_guard_changed": False,
            "promotion_ready": False,
            "promotion_blocker": "event_level_no_add_backtest_must_be_reconciled_with_actual_group_a_plus_add_attempts",
        },
    }


def _write_report(report: dict[str, Any], output: Path, history_dir: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = history_dir / f"rwc_no_add_shadow_backtest_{stamp}.json"
    history_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", default=DEFAULT_TARGET_TICKER)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--years", default=DEFAULT_YEARS)
    parser.add_argument("--max-dates", type=int, default=0)
    parser.add_argument("--add-notional", type=float, default=100000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    _write_report(report, _resolve(args.output), _resolve(args.history_dir))
    best = report.get("best_candidate") or {}
    print(
        json.dumps(
            {
                "status": report["status"],
                "best_candidate": best.get("candidate"),
                "combined_total_pause_benefit": (best.get("ranking_metrics") or {}).get("combined_total_pause_benefit"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
