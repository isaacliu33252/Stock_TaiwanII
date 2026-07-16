#!/usr/bin/env python3
"""ncf_2330 TSMC_Leadership_Score ablation study (read-only w.r.t. production).

Compares direction (H1/H5/H20), forward-drawdown-risk (5%/8% @ 20d), and
forward-upside-reward (5% @ 20d) purged K-fold performance across leadership
feature-family variants:

  A  baseline_no_leadership   -- leadership_mode=none
  B  score_only               -- leadership_mode=score_only
  C  components_only          -- leadership_mode=components_only
  D1 full_after_close         -- leadership_mode=full, feature_mode=after_close (current shadow default)
  D2 full_pre_open            -- leadership_mode=full, feature_mode=pre_open
  E1 full_weight_050          -- leadership_mode=full, feature_mode=after_close, tsmc weight=0.50
  E2 full_weight_060          -- leadership_mode=full, feature_mode=after_close, tsmc weight=0.60

Writes only to results/ncf_2330_leadership_ablation_<date>.json.
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
    build_dataset, build_feature_matrix,
    forward_max_drawdown_label, forward_max_gain_label,
    purged_kfold_splits, train_classifier,
    evaluate_purged_kfold,
    TSMC_LEADERSHIP_FEATURES, TSMC_0050_WEIGHT_ASSUMPTION,
)

TRAIN_START = "2015-01-01"
VAL_START = "2025-01-02"
HORIZONS = [1, 5, 20]
LEADERSHIP_COMPONENTS = [f for f in TSMC_LEADERSHIP_FEATURES if f != "TSMC_Leadership_Score"]

# Variant name -> (leadership_mode, feature_mode, tsmc_weight)
VARIANTS: dict[str, tuple[str, str, float]] = {
    "A_baseline_no_leadership": ("none", "after_close", TSMC_0050_WEIGHT_ASSUMPTION),
    "B_score_only":             ("score_only", "after_close", TSMC_0050_WEIGHT_ASSUMPTION),
    "C_components_only":        ("components_only", "after_close", TSMC_0050_WEIGHT_ASSUMPTION),
    "D1_full_after_close":      ("full", "after_close", TSMC_0050_WEIGHT_ASSUMPTION),
    "D2_full_pre_open":         ("full", "pre_open", TSMC_0050_WEIGHT_ASSUMPTION),
    "E1_full_weight_050":       ("full", "after_close", 0.50),
    "E2_full_weight_060":       ("full", "after_close", 0.60),
}


def _leadership_ext_features(all_ext_features: list[str], leadership_mode: str) -> list[str]:
    if leadership_mode == "none":
        return [f for f in all_ext_features if f not in set(TSMC_LEADERSHIP_FEATURES)]
    if leadership_mode == "score_only":
        return [f for f in all_ext_features if f not in set(LEADERSHIP_COMPONENTS)]
    if leadership_mode == "components_only":
        return [f for f in all_ext_features if f != "TSMC_Leadership_Score"]
    return list(all_ext_features)


def _run_direction(X: pd.DataFrame, y_return: pd.Series, y_direction: pd.Series, horizon: int) -> dict:
    res = evaluate_purged_kfold(X, y_return, y_direction.values, horizon, n_splits=5, embargo_bars=horizon)
    return {"auc": round(res["avg_auc"]["ensemble"], 4), "accuracy": round(res["avg_acc"]["ensemble"], 4)}


def _run_binary_task(X: pd.DataFrame, y: pd.Series, horizon: int) -> dict:
    common_idx = X.index.intersection(y.dropna().index)
    X_task, y_task = X.loc[common_idx], y.loc[common_idx].astype(int)
    n = len(X_task)
    splits = purged_kfold_splits(n, 5, horizon, embargo_bars=horizon)
    fold_aucs, fold_briers = [], []
    for tr_idx, te_idx in splits:
        y_tr, y_te = y_task.values[tr_idx], y_task.values[te_idx]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2 or len(tr_idx) < 100:
            continue
        res = train_classifier(X_task.iloc[tr_idx], y_tr, X_task.iloc[te_idx], y_te)
        fold_aucs.append(float(res["ensemble"]["auc"]))
        fold_briers.append(float(res["ensemble"]["brier"]))
    return {
        "n_folds_used": len(fold_aucs),
        "auc": round(float(np.mean(fold_aucs)), 4) if fold_aucs else None,
        "brier": round(float(np.mean(fold_briers)), 4) if fold_briers else None,
        "positive_rate": round(float(y_task.mean()), 4),
    }


def evaluate_variant(raw: pd.DataFrame, ext_df: pd.DataFrame, all_ext_features: list[str],
                      leadership_mode: str) -> dict:
    ncf_2330.EXT_FEATURES[:] = _leadership_ext_features(all_ext_features, leadership_mode)
    out: dict = {"n_ext_features_used": len(ncf_2330.EXT_FEATURES)}

    direction: dict = {}
    for h in HORIZONS:
        labeling = "triple_barrier" if h == 5 else "simple"
        X, y_ret, y_dir, _ = build_dataset(raw, horizon=h, ext_df=ext_df, labeling=labeling, tbl_mult=1.0)
        direction[str(h)] = _run_direction(X, y_ret, y_dir, h)
    out["direction"] = direction

    X_task = build_feature_matrix(raw, ext_df)
    _, y_mdd5 = forward_max_drawdown_label(raw["close"], horizon=20, threshold=0.05)
    _, y_mdd8 = forward_max_drawdown_label(raw["close"], horizon=20, threshold=0.08)
    _, y_gain5 = forward_max_gain_label(raw["close"], horizon=20, threshold=0.05)
    out["forward_drawdown_risk_gt5_h20"] = _run_binary_task(X_task, y_mdd5, 20)
    out["forward_drawdown_risk_gt8_h20"] = _run_binary_task(X_task, y_mdd8, 20)
    out["forward_upside_reward_gt5_h20"] = _run_binary_task(X_task, y_gain5, 20)
    return out


def main() -> None:
    val_end = resolve_end_date(DB_PATH, TICKER, "latest")
    print(f"[ablation] Loading data through {val_end}")
    raw = load_data(DB_PATH, TICKER, TRAIN_START, val_end)
    print(f"[ablation] raw rows={len(raw)}")

    all_ext_features = list(ncf_2330.EXT_FEATURES)  # snapshot before any mutation

    # Only reload external data when feature_mode or tsmc weight actually changes.
    ext_cache: dict[tuple[str, float], pd.DataFrame] = {}

    def _get_ext_df(feature_mode: str, weight: float) -> pd.DataFrame:
        key = (feature_mode, weight)
        if key not in ext_cache:
            print(f"[ablation] Loading external features (feature_mode={feature_mode}, weight={weight})...")
            ncf_2330.EXT_FEATURES[:] = all_ext_features
            ext_cache[key] = load_external_df(raw, DB_PATH, feature_mode=feature_mode, tsmc_weight_in_0050=weight)
        return ext_cache[key]

    results: dict = {"generated_at": date.today().isoformat(), "train_start": TRAIN_START, "val_start": VAL_START,
                      "val_end": val_end, "variants": {}}

    for name, (leadership_mode, feature_mode, weight) in VARIANTS.items():
        print(f"\n=== Variant {name} (leadership_mode={leadership_mode}, feature_mode={feature_mode}, weight={weight}) ===")
        ext_df = _get_ext_df(feature_mode, weight)
        variant_result = evaluate_variant(raw, ext_df, all_ext_features, leadership_mode)
        variant_result["leadership_mode"] = leadership_mode
        variant_result["feature_mode"] = feature_mode
        variant_result["tsmc_0050_weight"] = weight
        results["variants"][name] = variant_result
        print(json.dumps(variant_result, indent=2))

    ncf_2330.EXT_FEATURES[:] = all_ext_features  # restore

    output_path = PROJECT_ROOT / "results" / f"ncf_2330_leadership_ablation_{date.today().strftime('%Y%m%d')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[ablation] Saved: {output_path}")


if __name__ == "__main__":
    main()
