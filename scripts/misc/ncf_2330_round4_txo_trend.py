#!/usr/bin/env python3
"""Round-4 ncf_2330 diagnostics (read-only w.r.t. production).

Task 1: TXO option-market features — data coverage check, and with/without purged-CV
        comparison on the best (8%,20d) tail-risk combo.
Task 2: Revenue-signal trend-confound diagnostic — direct correlation with a time-trend
        proxy, plus with/without-trend-control importance-rank comparison.

Writes only to results/ncf_2330_round4_<date>.json.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ncf_2330 import (  # noqa: E402
    DB_PATH, TICKER,
    load_data, load_external_df, resolve_end_date,
    build_feature_matrix,
    forward_max_drawdown_label,
    purged_kfold_splits, train_classifier,
)

TRAIN_START = "2015-01-01"
BEST_THRESHOLD, BEST_HORIZON = 0.08, 20
TXO_COLS = [
    "txo_foreign_put_oi", "txo_foreign_call_oi", "txo_foreign_pc_spread",
    "txo_total_pcr", "txo_foreign_pc_spread_ma5", "txo_pcr_x_ma_gap", "txo_foreign_pc_x_vix",
]


def run_purged(X: pd.DataFrame, y: pd.Series, horizon: int, label: str) -> dict:
    n = len(X)
    splits = purged_kfold_splits(n, 5, horizon, embargo_bars=horizon)
    fold_aucs, fold_briers = [], []
    for fi, (tr_idx, te_idx) in enumerate(splits):
        y_tr_f, y_te_f = y.values[tr_idx], y.values[te_idx]
        if len(np.unique(y_tr_f)) < 2 or len(np.unique(y_te_f)) < 2 or len(tr_idx) < 100:
            print(f"  [{label}] fold {fi+1}: skipped (train={len(tr_idx)})")
            continue
        res = train_classifier(X.iloc[tr_idx], y_tr_f, X.iloc[te_idx], y_te_f)
        fold_aucs.append(float(res["ensemble"]["auc"]))
        fold_briers.append(float(res["ensemble"]["brier"]))
        print(f"  [{label}] fold {fi+1}: train={len(tr_idx)} test={len(te_idx)} AUC={fold_aucs[-1]:.4f}")
    out = {
        "n_folds_used": len(fold_aucs),
        "avg_auc": float(np.mean(fold_aucs)) if fold_aucs else None,
        "avg_brier": float(np.mean(fold_briers)) if fold_briers else None,
    }
    print(f"  [{label}] purged-CV avg AUC={out['avg_auc']} (folds={out['n_folds_used']})")
    return out


def main() -> None:
    val_end = resolve_end_date(DB_PATH, TICKER, "latest")
    print(f"[round4] Loading data through {val_end}")
    raw = load_data(DB_PATH, TICKER, TRAIN_START, val_end)
    ext_df = load_external_df(raw, DB_PATH)
    X = build_feature_matrix(raw, ext_df)
    print(f"[round4] feature matrix: {X.shape}")

    result: dict = {"generated_at": date.today().isoformat()}

    # ---------- Task 1: TXO coverage + with/without comparison ----------
    con = duckdb.connect(str(DB_PATH), read_only=True)
    txo_cov = con.execute(
        "SELECT MIN(dt), MAX(dt), COUNT(DISTINCT dt) FROM derivative_institutional_data WHERE product_id='TXO'"
    ).fetchdf()
    con.close()
    txo_min, txo_max, txo_days = txo_cov.iloc[0].tolist()
    total_days = len(X)
    coverage_pct = float(txo_days) / total_days if total_days else None
    print(f"\n[round4] TXO coverage: {txo_min} ~ {txo_max}, {txo_days} days "
          f"({coverage_pct:.1%} of {total_days} model rows)")
    result["txo_coverage"] = {
        "min_date": str(txo_min), "max_date": str(txo_max),
        "n_days": int(txo_days), "total_model_rows": int(total_days),
        "coverage_pct": coverage_pct,
        "note": "Outside this window, all txo_* EXT_FEATURES are fillna(0.0) in build_dataset/build_feature_matrix — not NaN-dropped, silently imputed to zero.",
    }

    forward_mdd, y_risk = forward_max_drawdown_label(raw["close"], horizon=BEST_HORIZON, threshold=BEST_THRESHOLD)
    common_idx = X.index.intersection(y_risk.dropna().index)
    X_full = X.loc[common_idx]
    y_full = y_risk.loc[common_idx].astype(int)

    print(f"\n=== Task 1: with vs without TXO features, full window, ({BEST_THRESHOLD:.0%},{BEST_HORIZON}d) ===")
    with_txo = run_purged(X_full, y_full, BEST_HORIZON, "with_txo (full window)")
    txo_present = [c for c in TXO_COLS if c in X_full.columns]
    X_no_txo = X_full.drop(columns=txo_present)
    without_txo = run_purged(X_no_txo, y_full, BEST_HORIZON, "without_txo (full window)")

    # Supplementary: recent-window-only test where TXO actually has non-zero data,
    # to check whether TXO carries signal at all when not diluted by zero-fill.
    recent_mask = X_full.index >= pd.Timestamp(str(txo_min))
    X_recent, y_recent = X_full.loc[recent_mask], y_full.loc[recent_mask]
    print(f"\n=== Task 1 supplementary: recent-window-only ({len(X_recent)} rows, TXO non-zero) ===")
    recent_with = run_purged(X_recent, y_recent, BEST_HORIZON, "with_txo (recent-only)")
    X_recent_no_txo = X_recent.drop(columns=[c for c in TXO_COLS if c in X_recent.columns])
    recent_without = run_purged(X_recent_no_txo, y_recent, BEST_HORIZON, "without_txo (recent-only)")

    result["task1_txo"] = {
        "full_window": {"with_txo": with_txo, "without_txo": without_txo},
        "recent_window_only": {
            "n_rows": int(len(X_recent)),
            "with_txo": recent_with, "without_txo": recent_without,
        },
    }

    # ---------- Task 2: revenue trend-confound diagnostic ----------
    print("\n=== Task 2: revenue signal vs time-trend diagnostic ===")
    trend_idx = pd.Series(np.arange(len(X_full)), index=X_full.index, name="trend_idx")
    diag = {}
    for col in ["revenue_ytd_yoy", "revenue_yoy", "revenue_yoy_accel", "revenue_mom"]:
        if col in X_full.columns:
            corr = float(X_full[col].corr(trend_idx))
            diag[col] = corr
            print(f"  corr({col}, trading_day_index) = {corr:.4f}")
    result["task2_revenue_trend_correlation"] = diag

    # Importance rank without vs with an explicit trend-control feature
    rf_no_trend = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                                          max_features="sqrt", n_jobs=2, random_state=42)
    rf_no_trend.fit(X_full, y_full)
    imp_no_trend = pd.Series(rf_no_trend.feature_importances_, index=X_full.columns).sort_values(ascending=False)
    rank_no_trend = {f: i + 1 for i, f in enumerate(imp_no_trend.index)}

    X_with_trend = X_full.copy()
    X_with_trend["trend_idx_control"] = trend_idx.values
    rf_with_trend = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                                            max_features="sqrt", n_jobs=2, random_state=42)
    rf_with_trend.fit(X_with_trend, y_full)
    imp_with_trend = pd.Series(rf_with_trend.feature_importances_, index=X_with_trend.columns).sort_values(ascending=False)
    rank_with_trend = {f: i + 1 for i, f in enumerate(imp_with_trend.index)}

    revenue_cols = ["revenue_ytd_yoy", "revenue_yoy", "revenue_yoy_accel", "revenue_mom"]
    rank_comparison = {}
    for col in revenue_cols:
        if col in rank_no_trend:
            rank_comparison[col] = {
                "rank_without_trend_control": rank_no_trend[col],
                "rank_with_trend_control": rank_with_trend.get(col),
                "imp_without": float(imp_no_trend.get(col, 0.0)),
                "imp_with": float(imp_with_trend.get(col, 0.0)),
            }
    trend_control_rank = rank_with_trend.get("trend_idx_control")
    print(f"  trend_idx_control rank (of {len(imp_with_trend)}): {trend_control_rank}")
    for col, v in rank_comparison.items():
        print(f"  {col}: rank {v['rank_without_trend_control']} -> {v['rank_with_trend_control']}  "
              f"(imp {v['imp_without']:.4f} -> {v['imp_with']:.4f})")

    result["task2_trend_control_experiment"] = {
        "trend_idx_control_rank": trend_control_rank,
        "n_features_with_trend": int(len(imp_with_trend)),
        "revenue_feature_rank_shift": rank_comparison,
    }

    out_path = PROJECT_ROOT / "results" / f"ncf_2330_round4_{date.today().strftime('%Y%m%d')}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[round4] Saved: {out_path}")


if __name__ == "__main__":
    main()
