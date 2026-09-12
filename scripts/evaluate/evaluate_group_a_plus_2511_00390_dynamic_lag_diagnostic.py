#!/usr/bin/env python3
"""Dynamic vs. fixed lead-lag diagnostic for NCF's US-overnight features (arXiv 2511.00390).

Research-only. DeltaLag's core critique of traditional lead-lag methods is
that a single fixed lag between a leader and a lagger series is often wrong,
because the true optimal lag drifts over time; it proposes learning a
time-varying, pair-specific lag with a neural cross-attention model. That
full architecture needs a broad stock cross-section to be worth building
(GroupA+ does not have one -- same limitation as several other papers
reviewed this session). But the underlying question is testable at small
scale without any neural network: NCF's production feature pipeline
(scripts/misc/ncf_0050.py::load_external_df) hard-codes shift=1 for every
US-overnight leader (QQQ, SOXX, TSM ADR, VIX) against 0050.TW/2330.TW. This
script checks, with a plain rolling cross-correlation, whether lag=1 is in
fact the consistently-best lag, or whether the optimal lag drifts across
history the way DeltaLag's motivation claims.

Never modifies ncf_0050.py or any production feature file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH
from ncf_external_cache import fetch_yf_close_cached

LEADERS = ("QQQ", "SOXX", "TSM")
LAGGERS = ("0050.TW", "2330.TW")
CANDIDATE_LAGS = (0, 1, 2, 3)
CURRENT_PRODUCTION_LAG = 1
ROLLING_WINDOW_DAYS = 126
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2511_00390_dynamic_lag_diagnostic.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2511_00390_dynamic_lag_diagnostic.md"


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _load_taiwan_close(db_path: Path, ticker: str, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        # Not every constituent (e.g. 2330.TW) is mirrored into the local
        # ohlcv table; fall back to the same yfinance cache ncf_0050.py uses
        # for its same-day Taiwan-market features (tsmc_ret etc.).
        return fetch_yf_close_cached(ticker, start, end, db_path, allow_download=False)
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float).sort_index()


def rolling_optimal_lag(
    leader_ret: pd.Series,
    lagger_ret: pd.Series,
    window: int,
) -> pd.DataFrame:
    """For each rolling window ending at t, find which candidate lag (leader
    return at t-lag vs lagger return at t) has the highest absolute
    correlation over that window. lag=0 means same-day (no true lead)."""
    idx = lagger_ret.index
    lagged = {lag: leader_ret.shift(lag).reindex(idx) for lag in CANDIDATE_LAGS}
    lagged_df = pd.DataFrame(lagged)
    joined = lagged_df.join(lagger_ret.rename("lagger"))

    records = []
    for end_i in range(window, len(joined)):
        block = joined.iloc[end_i - window : end_i]
        block = block.dropna()
        if len(block) < window // 2:
            continue
        corrs = {lag: block[lag].corr(block["lagger"]) for lag in CANDIDATE_LAGS}
        best_lag = max(corrs, key=lambda k: abs(corrs[k]) if corrs[k] == corrs[k] else -1.0)
        records.append(
            {
                "date": joined.index[end_i - 1],
                "best_lag": best_lag,
                "best_corr": _finite(corrs[best_lag]),
                "lag1_corr": _finite(corrs.get(CURRENT_PRODUCTION_LAG)),
            }
        )
    if not records:
        return pd.DataFrame(columns=["best_lag", "best_corr", "lag1_corr"])
    return pd.DataFrame(records).set_index("date")


def build_report(*, db_path: Path, start: str, end: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for leader in LEADERS:
        leader_close = fetch_yf_close_cached(leader, start, end, db_path, allow_download=False)
        leader_ret = leader_close.pct_change()
        for lagger in LAGGERS:
            lagger_close = _load_taiwan_close(db_path, lagger, start, end)
            lagger_ret = lagger_close.pct_change()
            rolling = rolling_optimal_lag(leader_ret, lagger_ret, ROLLING_WINDOW_DAYS)
            if rolling.empty:
                continue
            lag_counts = Counter(rolling["best_lag"])
            total = len(rolling)
            share_lag1_is_best = float(lag_counts.get(CURRENT_PRODUCTION_LAG, 0)) / total if total else None
            mean_best_corr = _finite(rolling["best_corr"].abs().mean())
            mean_lag1_corr = _finite(rolling["lag1_corr"].abs().mean())
            key = f"{leader}_vs_{lagger}"
            results[key] = {
                "n_windows": total,
                "share_windows_lag1_is_best": share_lag1_is_best,
                "lag_frequency": {str(k): int(v) for k, v in sorted(lag_counts.items())},
                "mean_abs_corr_best_lag": mean_best_corr,
                "mean_abs_corr_fixed_lag1": mean_lag1_corr,
                "best_lag_over_fixed_lag1_corr_gap": (
                    None if mean_best_corr is None or mean_lag1_corr is None else mean_best_corr - mean_lag1_corr
                ),
            }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2511_00390_dynamic_lag_diagnostic",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2511.00390.pdf",
            "title": "DeltaLag: Learning Dynamic Lead-Lag Patterns in Financial Markets",
            "adapted_concepts": [
                "test whether a single fixed lag (NCF's shift=1) is consistently optimal, or drifts, via rolling cross-correlation",
            ],
            "not_replicated": "the full cross-attention neural architecture (needs a broad cross-section GroupA+ does not have)",
        },
        "policy": "research_only_lag_stability_diagnostic_no_model_change",
        "status": "diagnostic_available",
        "parameters": {
            "start": start,
            "end": end,
            "candidate_lags": list(CANDIDATE_LAGS),
            "current_production_lag": CURRENT_PRODUCTION_LAG,
            "rolling_window_days": ROLLING_WINDOW_DAYS,
        },
        "results": results,
        "decision": {"review_complete": True, "changes_ncf_production_model": False, "changes_target_weights": False},
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2511.00390 Dynamic vs Fixed Lag Diagnostic",
        "",
        f"- Status: `{report['status']}`",
        "",
        "| pair | windows | share lag=1 best | mean|corr| best-lag | mean|corr| fixed lag=1 | gap |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, row in report["results"].items():
        lines.append(
            "| {k} | {n} | {s} | {b} | {f} | {g} |".format(
                k=key,
                n=row["n_windows"],
                s=_fmt(row["share_windows_lag1_is_best"]),
                b=_fmt(row["mean_abs_corr_best_lag"]),
                f=_fmt(row["mean_abs_corr_fixed_lag1"]),
                g=_fmt(row["best_lag_over_fixed_lag1_corr_gap"]),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Diagnostic only: rolling cross-correlation, not a trained model.",
            "- Does not modify ncf_0050.py or any production feature.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(db_path=Path(args.db), start=args.start, end=args.end)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"2511.00390 dynamic lag diagnostic: {output}")
    for key, row in report["results"].items():
        print(key, json.dumps({k: v for k, v in row.items() if k != "lag_frequency"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
