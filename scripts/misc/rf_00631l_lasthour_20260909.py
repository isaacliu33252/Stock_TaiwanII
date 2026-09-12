#!/usr/bin/env python3
"""RF_0050: predict the 12:00-13:30 (Taipei) afternoon-session trend for
00631L.TW using features built from the 9:00-12:00 morning session, inspired
by arXiv:2608.29025's premarket-hour -> opening-hour hybrid correction idea
(desk-reviewed 2026-09-09 as not directly transferable due to asset
class/frequency mismatch, but the RF-on-summary-features structure is
adapted here for Taiwan's single continuous session, which has no premarket
analog).

Data source: yfinance 30-minute bars for 00631L.TW. Yahoo's own API limits
intraday history to ~60 days -- this is a hard external constraint, not
something this script can extend. Every trading day has 9 bars
(01:00-05:00 UTC = 09:00-13:30 Taipei): morning window is the first 6 bars
(09:00-12:00), afternoon window is the last 3 bars (12:00-13:30).

Read-only research prototype. Does not touch any production/live file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from scipy.stats import pearsonr

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MORNING_BARS = 7  # 09:00-12:30 in 30-min bars
AFTERNOON_BARS = 2  # 12:30-13:30 in 30-min bars
BARS_PER_DAY = MORNING_BARS + AFTERNOON_BARS


def fetch_data() -> pd.DataFrame:
    df = yf.download("00631L.TW", period="60d", interval="30m", progress=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = df.index.tz_convert("Asia/Taipei")
    return df


def build_daily_records(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["trade_date"] = df.index.date
    rows = []
    for d, g in df.groupby("trade_date"):
        g = g.sort_index()
        if len(g) != BARS_PER_DAY:
            continue  # skip half-days / holidays with irregular bar counts
        morning = g.iloc[:MORNING_BARS]
        afternoon = g.iloc[MORNING_BARS:]

        morning_open = float(morning["Open"].iloc[0])
        morning_close = float(morning["Close"].iloc[-1])
        afternoon_close = float(afternoon["Close"].iloc[-1])

        morning_ret = morning_close / morning_open - 1.0
        bar_rets = (morning["Close"] / morning["Open"] - 1.0).to_numpy()
        morning_vol = float(np.std(bar_rets))
        morning_range = float((morning["High"].max() - morning["Low"].min()) / morning_open)
        morning_vol_z = float(morning["Volume"].to_numpy().std() / (morning["Volume"].to_numpy().mean() + 1e-9))
        last_bar_ret = float(morning["Close"].iloc[-1] / morning["Open"].iloc[-1] - 1.0)
        momentum_accel = float(bar_rets[-1] - bar_rets[0]) if len(bar_rets) >= 2 else 0.0

        target_ret = afternoon_close / morning_close - 1.0

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
    print("Fetching 00631L.TW 30-minute bars (max ~60 days via yfinance)...")
    raw = fetch_data()
    daily = build_daily_records(raw)
    print(f"Usable trading days: {len(daily)}")
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
    pred_proba = clf.predict_proba(X_test)[:, 1]

    if len(np.unique(y_test_reg)) > 1 and np.std(pred_reg) > 0:
        corr, pval = pearsonr(pred_reg, y_test_reg)
    else:
        corr, pval = float("nan"), float("nan")

    directional_acc = float((pred_cls == y_test_cls.to_numpy()).mean())
    naive_baseline_acc = float(max(y_test_cls.mean(), 1 - y_test_cls.mean()))  # always-predict-majority-class

    print("\n=== Results (test set, n=%d) ===" % len(test))
    print(f"RF regressor:  corr(pred, actual) = {corr:.4f}  (p={pval:.4f})")
    print(f"RF classifier: directional accuracy = {directional_acc:.4f}")
    print(f"Naive baseline (always predict majority class): {naive_baseline_acc:.4f}")
    print(f"Test set base rate (fraction of up afternoons): {y_test_cls.mean():.4f}")

    print("\nFeature importances (classifier):")
    for feat, imp in sorted(zip(features, clf.feature_importances_), key=lambda x: -x[1]):
        print(f"  {feat:18s} {imp:.4f}")

    out_path = PROJECT_ROOT / "results" / "rf_00631l_lasthour_20260909.csv"
    test_out = test.copy()
    test_out["pred_ret"] = pred_reg
    test_out["pred_up"] = pred_cls
    test_out["pred_proba_up"] = pred_proba
    test_out.to_csv(out_path)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
