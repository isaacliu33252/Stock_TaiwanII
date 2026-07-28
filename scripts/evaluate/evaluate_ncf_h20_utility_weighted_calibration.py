#!/usr/bin/env python3
"""Diagnose whether ncf_00631l's h20_prob_up (the production trigger signal) is
miscalibrated specifically in the decision-relevant regions: near the 0.5
action threshold, and during high-volatility (high-friction) regimes.

Research-only, read-only diagnostic. Does not change any production signal,
weight, or threshold. Motivated by arXiv:2601.07852v1 (Wright, 2026), whose
central claim -- generic global calibration can look fine while calibration
error concentrates in the regions that actually drive trading decisions -- is
untested for Group A+'s NCF panel. An earlier attempt (2026-07-01,
docs candidate "ncf_ensemble_calibration") applied *uniform* Brier-weighted
calibration and was rejected because it degraded AUC; this script checks the
narrower, decision-weighted claim instead of re-testing the rejected uniform
approach.

Data source: results/ncf_00631l_panel_latest_<date>.csv, which already
contains walk-forward (no-leakage, expanding-window) h20_prob_up predictions
and resolved actual_up_h20 labels for ~357 trading days (2025-01-02 onward).
Volatility regime is computed from 00631L.TW's own trailing 20-day realized
volatility (backward-looking only, no leakage), read from
FinRL/data/stock_data.db.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"


def _load_realized_vol(ticker: str, db_path: Path, window: int = 20) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]
        ).fetchdf()
    finally:
        con.close()
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.set_index("dt").sort_index()
    ret = df["close"].pct_change()
    vol = ret.rolling(window, min_periods=window).std()
    return vol.rename("realized_vol_20d")


def _reliability_summary(prob: pd.Series, actual: pd.Series, n_bins: int = 5) -> pd.DataFrame:
    """Bin by predicted probability, compare mean predicted vs realized frequency."""
    df = pd.DataFrame({"prob": prob, "actual": actual}).dropna()
    if df.empty:
        return pd.DataFrame()
    try:
        df["bin"] = pd.qcut(df["prob"], q=min(n_bins, df["prob"].nunique()), duplicates="drop")
    except ValueError:
        return pd.DataFrame()
    grouped = df.groupby("bin", observed=True).agg(
        n=("actual", "size"),
        mean_predicted=("prob", "mean"),
        realized_freq=("actual", "mean"),
    )
    grouped["gap"] = grouped["mean_predicted"] - grouped["realized_freq"]
    return grouped


def _brier(prob: pd.Series, actual: pd.Series) -> float:
    df = pd.DataFrame({"prob": prob, "actual": actual}).dropna()
    if df.empty:
        return float("nan")
    return float(np.mean((df["prob"] - df["actual"]) ** 2))


def _calibration_bias(prob: pd.Series, actual: pd.Series) -> float:
    df = pd.DataFrame({"prob": prob, "actual": actual}).dropna()
    if df.empty:
        return float("nan")
    return float(df["prob"].mean() - df["actual"].mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True, help="Path to ncf_00631l_panel_latest_*.csv")
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--vol-window", type=int, default=20)
    args = parser.parse_args()

    panel = pd.read_csv(args.panel, parse_dates=["date"])
    panel = panel[panel["is_live"] == False].copy()  # noqa: E712 -- only resolved labels
    panel = panel.dropna(subset=["h20_prob_up", "actual_up_h20"])
    panel = panel.set_index("date").sort_index()

    print(f"Resolved rows: {len(panel)}")

    vol = _load_realized_vol(args.ticker, DB_PATH, args.vol_window)
    panel["realized_vol_20d"] = vol.reindex(panel.index)
    panel = panel.dropna(subset=["realized_vol_20d"])
    print(f"Rows with volatility joined: {len(panel)}")

    # --- Overall calibration (the paper's "global" baseline) ---
    print("\n=== Overall (unconditional) calibration ===")
    print(f"Brier score:        {_brier(panel['h20_prob_up'], panel['actual_up_h20']):.4f}")
    print(f"Mean predicted - realized (bias): {_calibration_bias(panel['h20_prob_up'], panel['actual_up_h20']):+.4f}")
    rel = _reliability_summary(panel["h20_prob_up"], panel["actual_up_h20"])
    print(rel.to_string())

    # --- Dimension 1: distance to the 0.5 decision threshold ---
    panel["dist_to_threshold"] = (panel["h20_prob_up"] - 0.5).abs()
    near_mask = panel["dist_to_threshold"] <= panel["dist_to_threshold"].median()
    print("\n=== Near vs far from 0.5 decision threshold ===")
    for label, mask in [("NEAR threshold (decision-sensitive)", near_mask), ("FAR from threshold (confident)", ~near_mask)]:
        sub = panel[mask]
        print(
            f"{label}: n={len(sub)}, Brier={_brier(sub['h20_prob_up'], sub['actual_up_h20']):.4f}, "
            f"bias={_calibration_bias(sub['h20_prob_up'], sub['actual_up_h20']):+.4f}"
        )

    # --- Dimension 2: volatility (friction) regime terciles ---
    print("\n=== Volatility regime terciles (low/med/high realized_vol_20d) ===")
    panel["vol_tercile"] = pd.qcut(panel["realized_vol_20d"], 3, labels=["low", "medium", "high"])
    for tercile in ["low", "medium", "high"]:
        sub = panel[panel["vol_tercile"] == tercile]
        print(
            f"{tercile:>6}: n={len(sub)}, Brier={_brier(sub['h20_prob_up'], sub['actual_up_h20']):.4f}, "
            f"bias={_calibration_bias(sub['h20_prob_up'], sub['actual_up_h20']):+.4f}"
        )

    # --- Combined: near-threshold AND high-vol (the paper's economically decisive cell) ---
    print("\n=== Combined: near-threshold + high-vol (economically decisive per UWC theory) ===")
    decisive_mask = near_mask & (panel["vol_tercile"] == "high")
    other_mask = ~decisive_mask
    for label, mask in [("Decisive cell (near-threshold & high-vol)", decisive_mask), ("Everything else", other_mask)]:
        sub = panel[mask]
        if len(sub) < 5:
            print(f"{label}: n={len(sub)} (too few for a reliable estimate)")
            continue
        print(
            f"{label}: n={len(sub)}, Brier={_brier(sub['h20_prob_up'], sub['actual_up_h20']):.4f}, "
            f"bias={_calibration_bias(sub['h20_prob_up'], sub['actual_up_h20']):+.4f}"
        )


if __name__ == "__main__":
    main()
