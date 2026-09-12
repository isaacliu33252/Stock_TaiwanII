#!/usr/bin/env python3
"""RF_<ticker>: predict the final 30-minute bar (13:00-13:30 Taipei) of
0050.TW/00631L.TW/00713.TW using features built from the morning session
(09:00-12:00), inspired by arXiv:2608.29025 (desk-reviewed 2026-09-09).

Reads from ohlcv_intraday_30m (populated by
scripts/fetch/fetch_intraday_30m_ohlcv.py), which accumulates daily going
forward -- yfinance's own 60-day intraday history limit means today's run
still only has ~60 days available, but this will grow over time instead of
being re-fetched from scratch (and losing everything past 60 days) on every
run.

Read-only research prototype. Does not touch any production/live file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from scipy.stats import pearsonr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"

MORNING_BARS = 6  # 09:00-12:00 in 30-min bars
BARS_PER_DAY = 9  # 09:00-13:30 in 30-min bars


def load_data(db_path: str, ticker: str) -> pd.DataFrame:
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute(
        "SELECT dt, bar_start, open, high, low, close, volume FROM ohlcv_intraday_30m "
        "WHERE ticker = ? ORDER BY bar_start",
        [ticker],
    ).fetchdf()
    con.close()
    return df


def build_daily_records(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d, g in df.groupby("dt"):
        g = g.sort_values("bar_start")
        if len(g) != BARS_PER_DAY:
            continue
        morning = g.iloc[:MORNING_BARS]
        last_bar = g.iloc[-1]

        morning_open = float(morning["open"].iloc[0])
        morning_close = float(morning["close"].iloc[-1])

        morning_ret = morning_close / morning_open - 1.0
        bar_rets = (morning["close"] / morning["open"] - 1.0).to_numpy()
        morning_vol = float(np.std(bar_rets))
        morning_range = float((morning["high"].max() - morning["low"].min()) / morning_open)
        morning_vol_z = float(morning["volume"].to_numpy().std() / (morning["volume"].to_numpy().mean() + 1e-9))
        last_bar_ret = float(morning["close"].iloc[-1] / morning["open"].iloc[-1] - 1.0)
        momentum_accel = float(bar_rets[-1] - bar_rets[0]) if len(bar_rets) >= 2 else 0.0

        target_ret = float(last_bar["close"]) / morning_close - 1.0

        rows.append(
            {
                "date": d,
                "morning_ret": morning_ret,
                "morning_vol": morning_vol,
                "morning_range": morning_range,
                "morning_vol_z": morning_vol_z,
                "last_bar_ret": last_bar_ret,
                "momentum_accel": momentum_accel,
                "target_ret": target_ret,
                "target_up": int(target_ret > 0),
            }
        )
    return pd.DataFrame(rows).set_index("date")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    raw = load_data(args.db, args.ticker)
    if raw.empty:
        print(f"No data in ohlcv_intraday_30m for {args.ticker}. Run fetch_intraday_30m_ohlcv.py first.")
        return
    daily = build_daily_records(raw)
    print(f"{args.ticker}: usable trading days = {len(daily)}")
    if len(daily) < 30:
        print("Too few usable days for a meaningful train/test split. Stopping.")
        return

    features = ["morning_ret", "morning_vol", "morning_range", "morning_vol_z", "last_bar_ret", "momentum_accel"]
    n = len(daily)
    split = int(n * 0.7)
    train, test = daily.iloc[:split], daily.iloc[split:]
    print(f"Train days: {len(train)}  Test days: {len(test)}")
    print(f"Train date range: {train.index.min()} .. {train.index.max()}")
    print(f"Test date range:  {test.index.min()} .. {test.index.max()}")

    X_train, y_train_reg, y_train_cls = train[features], train["target_ret"], train["target_up"]
    X_test, y_test_reg, y_test_cls = test[features], test["target_ret"], test["target_up"]

    reg = RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=3, random_state=42)
    reg.fit(X_train, y_train_reg)
    pred_reg = reg.predict(X_test)

    clf = RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=3, random_state=42)
    clf.fit(X_train, y_train_cls)
    pred_cls = clf.predict(X_test)

    if len(np.unique(y_test_reg)) > 1 and np.std(pred_reg) > 0:
        corr, pval = pearsonr(pred_reg, y_test_reg)
    else:
        corr, pval = float("nan"), float("nan")

    directional_acc = float((pred_cls == y_test_cls.to_numpy()).mean())
    naive_baseline_acc = float(max(y_test_cls.mean(), 1 - y_test_cls.mean()))

    print(f"\n=== Results (test set, n={len(test)}) ===")
    print(f"RF regressor:  corr(pred, actual) = {corr:.4f}  (p={pval:.4f})")
    print(f"RF classifier: directional accuracy = {directional_acc:.4f}")
    print(f"Naive baseline (always predict majority class): {naive_baseline_acc:.4f}")
    print(f"Test set base rate (fraction of up last-bars): {y_test_cls.mean():.4f}")

    print("\nFeature importances (classifier):")
    for feat, imp in sorted(zip(features, clf.feature_importances_), key=lambda x: -x[1]):
        print(f"  {feat:18s} {imp:.4f}")

    out_path = PROJECT_ROOT / "results" / f"rf_{args.ticker.replace('.', '_')}_lastbar_20260909.csv"
    test_out = test.copy()
    test_out["pred_ret"] = pred_reg
    test_out["pred_up"] = pred_cls
    test_out.to_csv(out_path)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
