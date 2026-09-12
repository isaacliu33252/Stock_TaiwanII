#!/usr/bin/env python3
"""Controlled test: does compounding_regime add lift beyond a naive trend filter?

Research-only diagnostic, follow-up to
evaluate_00631l_quadratic_bound_regime_crosscheck.py (see
results/00631l_quadratic_bound_regime_crosscheck_20260810.json). That
crosscheck found TREND_PERSISTENT has a higher forward actual_favorable_rate
than MEAN_REVERTING (0.671 vs 0.650) against the arXiv:2301.03186 bound, but
both are close to the unconditional base rate (0.656) -- raising the
question of whether the classifier's AR1/variance-ratio/reversal-speed
features carry information beyond simply "is 0050 currently in an uptrend."

Method: stratify the crosscheck rows by a naive, independent backward-looking
trend proxy (0050 close vs its own 200-day SMA, computed as of the same
date the regime label uses) and compare TREND_PERSISTENT vs MEAN_REVERTING
WITHIN each stratum. If the classifier's edge over MEAN_REVERTING survives
conditioning on the naive filter, that is incremental signal. If it
collapses or reverses within strata, the marginal crosscheck gap was
mostly/entirely proxying the naive filter.

Caveat handled explicitly: adjacent daily labels share ~(horizon-1)/horizon
of their forward window, so naive per-row significance tests overstate
independence. This script reports both the full overlapping-window sample
and a non-overlapping (stride = horizon) robustness subsample.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.leveraged_compounding_regime import (  # noqa: E402
    MEAN_REVERTING,
    TREND_PERSISTENT,
)

DEFAULT_CROSSCHECK_CSV = PROJECT_ROOT / "results" / "00631l_quadratic_bound_regime_crosscheck_20260810.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_regime_lift_vs_trend_baseline_20260810.json"


def _load_0050_close(db_path: Path, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float).sort_index()


def _proportion_ztest(k1: int, n1: int, k2: int, n2: int) -> float | None:
    if n1 == 0 or n2 == 0:
        return None
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    denom = np.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if denom == 0.0:
        return None
    z = (p1 - p2) / denom
    return float(2.0 * (1.0 - stats.norm.cdf(abs(z))))


def _stratum_comparison(rows: pd.DataFrame) -> dict[str, Any]:
    trend_rows = rows[rows["compounding_regime"] == TREND_PERSISTENT]
    revert_rows = rows[rows["compounding_regime"] == MEAN_REVERTING]
    if len(trend_rows) == 0 or len(revert_rows) == 0:
        return {
            "n_trend_persistent": int(len(trend_rows)),
            "n_mean_reverting": int(len(revert_rows)),
        }
    k1, n1 = int(trend_rows["actual_favorable"].sum()), int(len(trend_rows))
    k2, n2 = int(revert_rows["actual_favorable"].sum()), int(len(revert_rows))
    ttest = stats.ttest_ind(
        trend_rows["actual_margin"], revert_rows["actual_margin"], equal_var=False
    )
    return {
        "n_trend_persistent": n1,
        "n_mean_reverting": n2,
        "actual_favorable_rate_trend_persistent": k1 / n1,
        "actual_favorable_rate_mean_reverting": k2 / n2,
        "favorable_rate_lift_trend_minus_revert": k1 / n1 - k2 / n2,
        "favorable_rate_ztest_pvalue": _proportion_ztest(k1, n1, k2, n2),
        "mean_actual_margin_trend_persistent": float(trend_rows["actual_margin"].mean()),
        "mean_actual_margin_mean_reverting": float(revert_rows["actual_margin"].mean()),
        "actual_margin_ttest_pvalue": float(ttest.pvalue),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows = pd.read_csv(args.crosscheck_csv, parse_dates=["date"])
    close_0050 = _load_0050_close(
        Path(args.db), str(rows["date"].min().date() - pd.Timedelta(days=400)), str(rows["date"].max().date())
    )
    sma200 = close_0050.rolling(200, min_periods=200).mean()
    trend_up = (close_0050 > sma200).reindex(rows["date"]).to_numpy()
    rows["baseline_trend_up"] = trend_up
    rows = rows.dropna(subset=["baseline_trend_up"])
    rows["baseline_trend_up"] = rows["baseline_trend_up"].astype(bool)

    unconditional = _stratum_comparison(rows)
    bull_stratum = _stratum_comparison(rows[rows["baseline_trend_up"]])
    bear_stratum = _stratum_comparison(rows[~rows["baseline_trend_up"]])

    baseline_k = int(rows.loc[rows["baseline_trend_up"], "actual_favorable"].sum())
    baseline_n = int(rows["baseline_trend_up"].sum())
    baseline_k_bear = int(rows.loc[~rows["baseline_trend_up"], "actual_favorable"].sum())
    baseline_n_bear = int((~rows["baseline_trend_up"]).sum())
    baseline_effect = {
        "n_trend_up": baseline_n,
        "n_trend_down": baseline_n_bear,
        "actual_favorable_rate_trend_up": baseline_k / baseline_n if baseline_n else None,
        "actual_favorable_rate_trend_down": baseline_k_bear / baseline_n_bear if baseline_n_bear else None,
        "favorable_rate_lift_trend_up_minus_down": (
            (baseline_k / baseline_n - baseline_k_bear / baseline_n_bear)
            if baseline_n and baseline_n_bear
            else None
        ),
        "favorable_rate_ztest_pvalue": _proportion_ztest(baseline_k, baseline_n, baseline_k_bear, baseline_n_bear),
    }

    horizon = int(args.horizon)
    stride_rows = rows.iloc[::horizon].reset_index(drop=True)
    robustness = {
        "stride": horizon,
        "n_rows": int(len(stride_rows)),
        "unconditional": _stratum_comparison(stride_rows),
        "trend_up_stratum": _stratum_comparison(stride_rows[stride_rows["baseline_trend_up"]]),
        "trend_down_stratum": _stratum_comparison(stride_rows[~stride_rows["baseline_trend_up"]]),
    }

    report = {
        "schema_version": 1,
        "report_type": "00631l_regime_lift_vs_trend_baseline",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "method": (
            "Stratify the 2301.03186 crosscheck rows by a naive backward-looking "
            "trend proxy (0050 close vs its own 200d SMA) and compare "
            "TREND_PERSISTENT vs MEAN_REVERTING actual_favorable_rate/actual_margin "
            "within each stratum. Overlapping-window sample has pseudo-replication "
            "(adjacent daily labels share most of their forward window); a "
            "stride-sampled non-overlapping subsample is reported for robustness."
        ),
        "caveat": (
            "P-values on the overlapping sample understate true uncertainty due to "
            "serial dependence between adjacent rows -- treat the stride-sampled "
            "robustness block as the more trustworthy significance read."
        ),
        "naive_baseline_filter_effect": baseline_effect,
        "regime_lift_unconditional": unconditional,
        "regime_lift_within_trend_up_stratum": bull_stratum,
        "regime_lift_within_trend_down_stratum": bear_stratum,
        "non_overlapping_robustness_check": robustness,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crosscheck-csv", default=str(DEFAULT_CROSSCHECK_CSV))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"Naive baseline filter lift (trend_up - trend_down): {report['naive_baseline_filter_effect']['favorable_rate_lift_trend_up_minus_down']:.4f} "
          f"(p={report['naive_baseline_filter_effect']['favorable_rate_ztest_pvalue']:.4g})")
    print(f"Regime lift unconditional: {report['regime_lift_unconditional']['favorable_rate_lift_trend_minus_revert']:.4f} "
          f"(p={report['regime_lift_unconditional']['favorable_rate_ztest_pvalue']:.4g})")
    print(f"Regime lift within trend_up stratum: {report['regime_lift_within_trend_up_stratum'].get('favorable_rate_lift_trend_minus_revert')}")
    print(f"Regime lift within trend_down stratum: {report['regime_lift_within_trend_down_stratum'].get('favorable_rate_lift_trend_minus_revert')}")
    print(f"Non-overlapping robustness n={report['non_overlapping_robustness_check']['n_rows']}, "
          f"unconditional lift={report['non_overlapping_robustness_check']['unconditional'].get('favorable_rate_lift_trend_minus_revert')}")


if __name__ == "__main__":
    main()
