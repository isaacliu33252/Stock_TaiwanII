#!/usr/bin/env python3
"""
Fast parameter sweep for ncf_00632r.
Varies direction_threshold × tbl_mult.
Uses RF + ET only (n=100) to finish in ~8 minutes.
Usage: python3 -u sweep_ncf_00632r.py
"""
import json
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.metrics import roc_auc_score, accuracy_score

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from ncf_00632r import (
    load_data, load_external_df, build_dataset, resolve_end_date, TICKER,
)
from FinRL.data.stock_db import DB_PATH

TRAIN_START = "2015-01-01"
VAL_START   = "2025-01-02"
VAL_END     = "latest"
HORIZONS    = [1, 5, 20]

HORIZON_DROP: dict[int, list[str]] = {
    1: ["close_open_ratio"],
    5: ["rsi_14"],
}

# Grid: 9 configs
SWEEPS = [
    ("thr=0.005 tbl=0.75", 0.005, 0.75),   # Base
    ("thr=0.003 tbl=0.75", 0.003, 0.75),
    ("thr=0.002 tbl=0.75", 0.002, 0.75),
    ("thr=0.000 tbl=0.75", 0.000, 0.75),
    ("thr=0.005 tbl=0.50", 0.005, 0.50),
    ("thr=0.005 tbl=1.00", 0.005, 1.00),
    ("thr=0.002 tbl=0.50", 0.002, 0.50),
    ("thr=0.002 tbl=1.00", 0.002, 1.00),
    ("thr=0.003 tbl=1.00", 0.003, 1.00),
]

RF_KW = dict(n_estimators=150, max_depth=10, min_samples_leaf=5,
             max_features="sqrt", n_jobs=-1, random_state=42)
ET_KW = dict(n_estimators=150, max_depth=10, min_samples_leaf=5,
             max_features="sqrt", n_jobs=-1, random_state=42)


def fast_eval(X_tr, y_tr_dir, X_val, y_val_dir) -> dict:
    """RF + ET only — fast, no calibration."""
    rf = RandomForestClassifier(**RF_KW)
    et = ExtraTreesClassifier(**ET_KW)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rf.fit(X_tr, y_tr_dir)
        et.fit(X_tr, y_tr_dir)
    prob_rf = rf.predict_proba(X_val)[:, 1]
    prob_et = et.predict_proba(X_val)[:, 1]
    prob_ens = (prob_rf + prob_et) / 2
    return {
        "rf_auc":  float(roc_auc_score(y_val_dir, prob_rf)),
        "et_auc":  float(roc_auc_score(y_val_dir, prob_et)),
        "ens_auc": float(roc_auc_score(y_val_dir, prob_ens)),
        "ens_acc": float(accuracy_score(y_val_dir, (prob_ens >= 0.5).astype(int))),
    }


def eval_config(raw, ext_df, thr: float, tbl: float, val_end: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for h in HORIZONS:
        labeling = "triple_barrier" if h == 5 else "simple"
        X, y_ret, y_dir, _ = build_dataset(
            raw, horizon=h, ext_df=ext_df,
            direction_threshold=thr, labeling=labeling, tbl_mult=tbl,
        )
        train_mask = X.index < VAL_START
        val_mask   = (X.index >= VAL_START) & (X.index <= val_end)
        y_train_dir = y_dir[train_mask].values
        y_val_dir   = (y_ret[val_mask] > 0).astype(int).values
        X_tr = X[train_mask]
        X_val = X[val_mask]

        clf_mask   = y_train_dir != -1
        neutral_pct = float((~clf_mask).mean())
        X_tr_clf   = X_tr[clf_mask]
        y_tr_clf   = y_train_dir[clf_mask]

        drop = [c for c in HORIZON_DROP.get(h, []) if c in X_tr_clf.columns]
        if drop:
            X_tr_clf = X_tr_clf.drop(columns=drop)
            X_val    = X_val.drop(columns=drop, errors="ignore")

        if (len(X_val) < 20 or len(np.unique(y_val_dir)) < 2
                or X_tr_clf.shape[0] < 50 or len(np.unique(y_tr_clf)) < 2):
            out[h] = {"ens_auc": 0.5, "rf_auc": 0.5, "et_auc": 0.5,
                      "neutral_pct": neutral_pct, "note": "tiny/skip"}
        else:
            m = fast_eval(X_tr_clf, y_tr_clf, X_val, y_val_dir)
            m["neutral_pct"] = neutral_pct
            m["n_train"] = int(X_tr_clf.shape[0])
            out[h] = m
        print(f"    H={h} auc={out[h]['ens_auc']:.4f} neu={out[h]['neutral_pct']:.1%}", flush=True)
    return out


def main() -> None:
    print(f"[sweep] Loading {TICKER}...", flush=True)
    val_end = resolve_end_date(DB_PATH, TICKER, VAL_END)
    raw = load_data(DB_PATH, TICKER, TRAIN_START, val_end)
    print(f"  {len(raw)} rows  ({raw.index[0].date()} ~ {raw.index[-1].date()})", flush=True)

    print("[sweep] Ext features...", flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ext_df = load_external_df(raw, DB_PATH)
    print(f"  {len(ext_df.columns)} features ready\n", flush=True)

    hdr = f"{'Config':<24} {'H1_AUC':>8} {'H5_AUC':>8} {'H20_AUC':>9} {'Score':>7} {'H1_neu':>8}"
    print("=" * len(hdr), flush=True)
    print(hdr, flush=True)
    print("=" * len(hdr), flush=True)

    all_rows = []
    for label, thr, tbl in SWEEPS:
        print(f"\n>> {label}  (thr={thr} tbl={tbl})", flush=True)
        t0 = time.time()
        try:
            res = eval_config(raw, ext_df, thr, tbl, val_end)
            h1  = res[1]["ens_auc"]
            h5  = res[5]["ens_auc"]
            h20 = res[20]["ens_auc"]
            neu = res[1].get("neutral_pct", 0)
            score = h1*0.2 + h5*0.3 + h20*0.5
            print(f"   {label:<24} {h1:>8.4f} {h5:>8.4f} {h20:>9.4f} {score:>7.4f} {neu:>7.1%}  "
                  f"({time.time()-t0:.0f}s)", flush=True)
            all_rows.append({"label": label, "thr": thr, "tbl": tbl,
                             "H1_auc": h1, "H5_auc": h5, "H20_auc": h20,
                             "score": score, "H1_neutral": neu})
        except Exception:
            print(f"   ERROR: {traceback.format_exc(limit=3)}", flush=True)

    if not all_rows:
        print("[sweep] No results collected.", flush=True)
        return

    all_rows.sort(key=lambda r: -r["score"])
    best = all_rows[0]

    print(f"\n{'='*65}", flush=True)
    print("RANKING (by weighted score  H1×0.2 + H5×0.3 + H20×0.5):", flush=True)
    print(f"{'Rk':<4} {'Config':<24} {'H1':>8} {'H5':>8} {'H20':>9} {'Score':>7}", flush=True)
    for i, r in enumerate(all_rows):
        tag = " *** BEST" if i == 0 else ""
        print(f"#{i+1:<3} {r['label']:<24} {r['H1_auc']:>8.4f} "
              f"{r['H5_auc']:>8.4f} {r['H20_auc']:>9.4f} {r['score']:>7.4f}{tag}", flush=True)

    print(f"\nBEST → direction_threshold={best['thr']}  tbl_mult={best['tbl']}", flush=True)

    out = PROJECT_ROOT / "results" / "ncf_00632r_sweep_summary.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w") as f:
        json.dump({"results": all_rows, "best": best}, f, indent=2)
    print(f"Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
