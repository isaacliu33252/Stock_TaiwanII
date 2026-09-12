#!/usr/bin/env python3
"""Direct hit-rate comparison: adaptive window vs each individual fixed
window, decoupled from the sparse ADD_0050_INSTEAD trigger condition.

Follow-up to evaluate_adaptive_lookback_narrow_lead_shadow.py (2026-08-09),
same day. That test's backtest comparison was inconclusive because it only
evaluated days where BOTH narrow_lead fired AND 00631L's target was
increasing -- only 15 such events across 6+ years. This script removes that
gating: every trading day is scored, using the same causal
concentration_divergence(window) sign vs realized next-day 00631L-vs-0050
relative-return sign as the underlying signal, for each individual fixed
window in {5, 20, 40, 60, 120, 252} and for the adaptively-selected window
(select_adaptive_window(), reused unmodified). This gives a much larger
sample (every day, not just guard-trigger days) to test the adaptive-window
CONCEPT directly: does causal window selection produce a higher hit-rate
than any single fixed window over the same period?

Research-only, read-only diagnostic. Does not touch any live weight,
guard, or execution plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.tsmc_concentration_divergence import TSMC_0050_WEIGHT_ASSUMPTION
from scripts.evaluate.evaluate_adaptive_lookback_narrow_lead_shadow import (
    CANDIDATE_WINDOWS,
    DEFAULT_EVAL_LOOKBACK,
    _divergence_series_for_window,
    _load_2330_0050_closes,
    select_adaptive_window,
)
from tw_output_standard import OutputStandardizer, write_standard_output

FIXED_WINDOWS_TO_COMPARE = (5, 20, 40, 60, 120, 252)
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "adaptive_window_hit_rate_comparison_latest.json"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_631l_close(db_path: Path, index: pd.DatetimeIndex) -> pd.Series:
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = '00631L.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [str(index[0].date()), str(index[-1].date())],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].reindex(index).ffill()


def _hit_rate(sign_pred: np.ndarray, sign_true: np.ndarray, valid_start: int) -> dict[str, Any]:
    p = sign_pred[valid_start:]
    t = sign_true[valid_start:]
    valid = np.isfinite(p) & np.isfinite(t) & (t != 0.0) & (p != 0.0)
    n = int(valid.sum())
    if n == 0:
        return {"n": 0, "hit_rate": None}
    hits = float((np.sign(p[valid]) == np.sign(t[valid])).mean())
    # two-sided binomial test vs 50% null, normal approximation
    se = float(np.sqrt(0.25 / n))
    z = (hits - 0.5) / se if se > 0 else None
    return {
        "n": n,
        "hit_rate": hits,
        "z_vs_50pct": z,
        "significant_at_5pct": bool(z is not None and abs(z) >= 1.96),
    }


def build_report(*, db_path: Path, start: str, end: str, eval_lookback: int) -> dict[str, Any]:
    dummy_index = pd.date_range(start, end, freq="B")
    close_2330, close_0050 = _load_2330_0050_closes(db_path, dummy_index)
    close_631l = _load_631l_close(db_path, dummy_index)
    valid_dates = close_2330.dropna().index.intersection(close_0050.dropna().index).intersection(
        close_631l.dropna().index
    )
    close_2330 = close_2330.loc[valid_dates]
    close_0050 = close_0050.loc[valid_dates]
    close_631l = close_631l.loc[valid_dates]
    index = close_2330.index

    ret_631l_1d_fwd = (close_631l.shift(-1) / close_631l - 1.0).to_numpy()
    ret_0050_1d_fwd = (close_0050.shift(-1) / close_0050 - 1.0).to_numpy()
    realized_rel_1d_fwd = ret_631l_1d_fwd - ret_0050_1d_fwd

    warmup = max(FIXED_WINDOWS_TO_COMPARE) + eval_lookback + 10

    results: dict[str, Any] = {}
    for w in FIXED_WINDOWS_TO_COMPARE:
        div, _ret2330 = _divergence_series_for_window(close_2330, close_0050, w, TSMC_0050_WEIGHT_ASSUMPTION)
        results[f"fixed_{w}d"] = _hit_rate(div.to_numpy(), realized_rel_1d_fwd, warmup)

    chosen_window, div_adaptive, _ret2330_adaptive = select_adaptive_window(
        close_2330, close_631l, close_0050, index,
        candidate_windows=CANDIDATE_WINDOWS, eval_lookback=eval_lookback,
    )
    results["adaptive"] = _hit_rate(div_adaptive.to_numpy(), realized_rel_1d_fwd, warmup)
    results["adaptive"]["window_usage_counts"] = {
        str(k): int(v) for k, v in chosen_window.iloc[warmup:].value_counts().to_dict().items()
    }

    best_fixed = max(
        (k for k in results if k.startswith("fixed_")),
        key=lambda k: (results[k]["hit_rate"] or 0.0),
    )

    return {
        "report_type": "adaptive_window_hit_rate_comparison",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "research_only_diagnostic_no_live_weight_change",
        "params": {
            "start": start,
            "end": end,
            "eval_lookback": int(eval_lookback),
            "fixed_windows_compared": list(FIXED_WINDOWS_TO_COMPARE),
            "adaptive_candidate_windows": list(CANDIDATE_WINDOWS),
        },
        "results": results,
        "best_single_fixed_window": best_fixed,
        "adaptive_beats_best_fixed": bool(
            (results["adaptive"]["hit_rate"] or 0.0) > (results[best_fixed]["hit_rate"] or 0.0)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2019-01-02")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--eval-lookback", type=int, default=DEFAULT_EVAL_LOOKBACK)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.evaluate_adaptive_window_hit_rate_comparison")
    try:
        report = build_report(
            db_path=_resolve(args.db), start=args.start, end=args.end, eval_lookback=int(args.eval_lookback)
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Adaptive window hit-rate comparison: {_resolve(args.output)}")
    if payload.get("success"):
        for key, value in payload["data"]["results"].items():
            print(key, json.dumps({k: v for k, v in value.items() if k != "window_usage_counts"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
