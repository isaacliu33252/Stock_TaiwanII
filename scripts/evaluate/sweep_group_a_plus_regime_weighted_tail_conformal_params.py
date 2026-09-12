#!/usr/bin/env python3
"""Parameter sweep for Group A+ 2602.03903 RWC tail-conformal shadow.

Research-only. It tunes warning/calibration diagnostics only; it does not
change live guards, target weights, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from itertools import product
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
    _summarize,
    _warning_cost,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/regime_weighted_tail_conformal_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/regime_weighted_tail_conformal_param_sweep/history"


def _parse_float_list(raw: str) -> list[float]:
    return [float(part.strip()) for part in str(raw).split(",") if part.strip()]


def _parse_int_list(raw: str) -> list[int]:
    return [int(part.strip()) for part in str(raw).split(",") if part.strip()]


def _safe(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(out):
        return default
    return out


def _candidate_metrics(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    summary = _summarize(rows, alpha=0.10)
    warning = _warning_cost(rows)
    h5 = summary.get(f"{method}:h5") or {}
    h10 = summary.get(f"{method}:h10") or {}
    w5 = warning.get(f"{method}:h5") or {}
    w10 = warning.get(f"{method}:h10") or {}
    calibration_error = (_safe(h5.get("absolute_calibration_error")) + _safe(h10.get("absolute_calibration_error"))) / 2.0
    tail_high_rate = (_safe(h5.get("tail_high_rate")) + _safe(h10.get("tail_high_rate"))) / 2.0
    severe_lift = (
        _safe(w5.get("tail_high_minus_normal_severe_mdd_8pct_rate"))
        + _safe(w10.get("tail_high_minus_normal_severe_mdd_8pct_rate"))
    ) / 2.0
    return_spread = (
        _safe(w5.get("tail_high_minus_normal_mean_forward_return"))
        + _safe(w10.get("tail_high_minus_normal_mean_forward_return"))
    ) / 2.0

    # Lower is better. Penalize calibration error and excessive warning rate;
    # reward warnings that select worse MDD windows and negative forward return.
    score = calibration_error + 0.15 * tail_high_rate - 0.20 * max(severe_lift, 0.0) + 0.10 * max(return_spread, 0.0)
    return {
        "summary": summary,
        "warning_cost": warning,
        "objective": {
            "score_lower_is_better": score,
            "mean_absolute_calibration_error": calibration_error,
            "mean_tail_high_rate": tail_high_rate,
            "mean_severe_mdd_lift": severe_lift,
            "mean_tail_high_return_spread": return_spread,
            "score_formula": (
                "calibration_error + 0.15*tail_high_rate - 0.20*positive_severe_mdd_lift "
                "+ 0.10*positive_return_spread"
            ),
        },
    }


def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    years = {int(part.strip()) for part in str(args.years).split(",") if part.strip()}
    close = _load_close(db_path, args.ticker, args.start, args.end)
    dates = _selected_dates(close, years, args.end)
    if args.max_dates and len(dates) > args.max_dates:
        step = max(1, len(dates) // int(args.max_dates))
        dates = dates[::step][: int(args.max_dates)]

    candidates: list[dict[str, Any]] = []
    for half_life, bandwidth, min_ess in product(
        _parse_float_list(args.half_lives),
        _parse_float_list(args.bandwidths),
        _parse_int_list(args.min_effective_sample_sizes),
    ):
        method = f"rwc_hl{half_life:g}_bw{bandwidth:g}_ess{min_ess}"
        rows: list[dict[str, Any]] = []
        _append_weighted_rows_fast(
            rows,
            close=close,
            dates=dates,
            method=method,
            use_regime_kernel=True,
            half_life=half_life,
            bandwidth=bandwidth,
            min_effective_sample_size=min_ess,
        )
        metrics = _candidate_metrics(rows, method)
        candidates.append(
            {
                "candidate": method,
                "params": {
                    "half_life": half_life,
                    "bandwidth": bandwidth,
                    "min_effective_sample_size": min_ess,
                },
                "row_count": int(len(rows)),
                **metrics,
            }
        )

    ranked = sorted(candidates, key=lambda item: item["objective"]["score_lower_is_better"])
    best = ranked[0] if ranked else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_regime_weighted_tail_conformal_param_sweep",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_param_sweep_only_no_weight_change_no_guard_promotion",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2602.03903.pdf",
            "title": "Taming Tail Risk in Financial Markets: Conformal Calibration for Nonstationary Portfolio VaR",
        },
        "inputs": {
            "db": str(db_path),
            "ticker": args.ticker,
            "start": args.start,
            "end": args.end,
            "years": sorted(years),
            "date_count": int(len(dates)),
            "sampled_max_dates": args.max_dates,
            "half_lives": _parse_float_list(args.half_lives),
            "bandwidths": _parse_float_list(args.bandwidths),
            "min_effective_sample_sizes": _parse_int_list(args.min_effective_sample_sizes),
        },
        "best_candidate": best,
        "top_candidates": ranked[:10],
        "candidate_count": int(len(candidates)),
        "decision": {
            "creates_orders": False,
            "changes_target_weights": False,
            "blocks_trades": False,
            "production_guard_changed": False,
            "promotion_ready": False,
            "promotion_blocker": "parameter_sweep_is_shadow_only_requires_trade_level_backtest",
        },
    }


def _write_report(report: dict[str, Any], output: Path, history_dir: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = history_dir / f"regime_weighted_tail_conformal_param_sweep_{stamp}.json"
    history_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", default=DEFAULT_TARGET_TICKER)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--years", default=DEFAULT_YEARS)
    parser.add_argument("--max-dates", type=int, default=0)
    parser.add_argument("--half-lives", default="63,126,252")
    parser.add_argument("--bandwidths", default="0.75,1.0,1.5")
    parser.add_argument("--min-effective-sample-sizes", default="60,100")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_sweep(args)
    _write_report(report, _resolve(args.output), _resolve(args.history_dir))
    best = report.get("best_candidate") or {}
    print(
        json.dumps(
            {
                "status": report["status"],
                "candidate_count": report["candidate_count"],
                "best_candidate": best.get("candidate"),
                "best_score": (best.get("objective") or {}).get("score_lower_is_better"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
