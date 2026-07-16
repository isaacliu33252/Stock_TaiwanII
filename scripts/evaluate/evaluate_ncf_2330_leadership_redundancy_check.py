#!/usr/bin/env python3
"""Follow-up to results/ncf_2330_leadership_ablation_20260707.json.

The initial leadership ablation found a suspiciously large H1 direction AUC
jump (0.547 baseline -> 0.746 full leadership). Two of the leadership columns
(`tsmc_leadership_vs_0050_ex_tsmc`, `tsmc_leadership_0050_contribution`) are
algebraically just positive linear rescalings of quantities already derivable
from the stock's own same-day return (already present as `return_1d` in
FEATURES) and its excess vs the benchmark. This script isolates how much of
the H1 jump is attributable to those two columns alone, versus the genuinely
new information channels (ADR overnight, SOXX, peer semis, foreign net,
USD/TWD), and adds a strict single-split OOS check on the untouched
2025-2026 window (not just purged CV within the training years) since CV
folds can still share a broad regime.

Variants (H1 direction only, since that is where the suspicious jump is):
  baseline_no_leadership          -- leadership_mode=none
  full_leadership                 -- leadership_mode=full (current default)
  leadership_minus_redundant_pair -- full minus the two own-return-proxy columns
  only_redundant_pair             -- baseline + only the two own-return-proxy columns

Each variant is evaluated two ways:
  1. Purged 5-fold CV over the full 2015-latest sample (comparable to the
     original ablation numbers).
  2. A single strict OOS split: train < 2025-01-02, validate on
     2025-01-02..latest (the untouched, most-recent regime).

Writes only to results/ncf_2330_leadership_redundancy_check_<date>.json.
Does not modify ncf_2330.py further and does not touch any production/latest file.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import ncf_2330  # noqa: E402
from ncf_2330 import (  # noqa: E402
    DB_PATH, TICKER,
    load_data, load_external_df, resolve_end_date,
    build_dataset,
    purged_kfold_splits, train_classifier,
    evaluate_purged_kfold,
)

TRAIN_START = "2015-01-01"
VAL_START = "2025-01-02"
HORIZON = 1

REDUNDANT_PAIR = ["tsmc_leadership_vs_0050_ex_tsmc", "tsmc_leadership_0050_contribution"]

VARIANTS = {
    "baseline_no_leadership": "none",
    "full_leadership": "full",
    "leadership_minus_redundant_pair": "minus_redundant_pair",
    "only_redundant_pair": "only_redundant_pair",
}


def _feature_set(all_ext_features: list[str], mode: str) -> list[str]:
    leadership_all = set(ncf_2330.TSMC_LEADERSHIP_FEATURES)
    if mode == "none":
        return [f for f in all_ext_features if f not in leadership_all]
    if mode == "full":
        return list(all_ext_features)
    if mode == "minus_redundant_pair":
        return [f for f in all_ext_features if f not in set(REDUNDANT_PAIR)]
    if mode == "only_redundant_pair":
        return [f for f in all_ext_features if f not in leadership_all or f in set(REDUNDANT_PAIR)]
    raise ValueError(mode)


def _cv_auc(raw: pd.DataFrame, ext_df: pd.DataFrame) -> dict:
    X, y_ret, y_dir, _ = build_dataset(raw, horizon=HORIZON, ext_df=ext_df, labeling="simple")
    res = evaluate_purged_kfold(X, y_ret, y_dir.values, HORIZON, n_splits=5, embargo_bars=HORIZON)
    return {"auc": round(res["avg_auc"]["ensemble"], 4), "accuracy": round(res["avg_acc"]["ensemble"], 4)}


def _oos_single_split(raw: pd.DataFrame, ext_df: pd.DataFrame) -> dict:
    X, y_ret, y_dir, _ = build_dataset(raw, horizon=HORIZON, ext_df=ext_df, labeling="simple")
    train_mask = X.index < VAL_START
    X_tr, X_val = X[train_mask], X[~train_mask]
    y_tr, y_val = y_dir[train_mask], y_dir[~train_mask]
    if X_tr.empty or X_val.empty or y_tr.nunique() < 2 or y_val.nunique() < 2:
        return {"auc": None, "brier": None, "train_rows": int(len(X_tr)), "val_rows": int(len(X_val))}
    clf = train_classifier(X_tr, y_tr, X_val, y_val)
    return {
        "auc": round(float(clf["ensemble"]["auc"]), 4),
        "brier": round(float(clf["ensemble"]["brier"]), 4),
        "train_rows": int(len(X_tr)),
        "val_rows": int(len(X_val)),
        "val_positive_rate": round(float(y_val.mean()), 4),
    }


def main() -> None:
    val_end = resolve_end_date(DB_PATH, TICKER, "latest")
    print(f"[redundancy-check] Loading data through {val_end}")
    raw = load_data(DB_PATH, TICKER, TRAIN_START, val_end)
    ext_df = load_external_df(raw, DB_PATH, feature_mode="after_close")
    all_ext_features = list(ncf_2330.EXT_FEATURES)

    results: dict = {
        "generated_at": date.today().isoformat(),
        "train_start": TRAIN_START, "val_start": VAL_START, "val_end": val_end,
        "horizon": HORIZON, "redundant_pair": REDUNDANT_PAIR,
        "variants": {},
    }

    for name, mode in VARIANTS.items():
        print(f"\n=== {name} (mode={mode}) ===")
        ncf_2330.EXT_FEATURES[:] = _feature_set(all_ext_features, mode)
        n_used = len(ncf_2330.EXT_FEATURES)
        cv = _cv_auc(raw, ext_df)
        oos = _oos_single_split(raw, ext_df)
        print(f"  n_ext_features_used={n_used}  cv_auc={cv['auc']}  oos_auc={oos['auc']}")
        results["variants"][name] = {"n_ext_features_used": n_used, "purged_cv": cv, "oos_single_split": oos}

    ncf_2330.EXT_FEATURES[:] = all_ext_features  # restore

    output_path = PROJECT_ROOT / "results" / f"ncf_2330_leadership_redundancy_check_{date.today().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[redundancy-check] Saved: {output_path}")


if __name__ == "__main__":
    main()
