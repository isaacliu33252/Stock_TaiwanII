#!/usr/bin/env python3
"""Round-3 ncf_2330 tail-risk deep dive (read-only w.r.t. production; writes only to
results/ncf_2330_tail_risk_sweep_<date>.json).

1. Sweeps (threshold, horizon) combos for the forward-drawdown tail-risk classifier,
   each validated with its own purged K-fold (not a single split).
2. Reports RF feature importance for the best combo (checks new chip-outflow-
   acceleration / margin-deleveraging / vol-spike features).
3. Checks whether the new continuous earnings-distance features rank better than the
   old binary earnings_window_flag.
4. Re-validates the H=20 direction classifier with a LOW-stability-and-low-importance
   feature set pruned out, via purged K-fold, against the round-2 baseline (0.5502).

Does not modify ncf_2330.py further, does not touch any production file.
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

from ncf_2330 import (  # noqa: E402
    DB_PATH, TICKER,
    load_data, load_external_df, resolve_end_date,
    build_feature_matrix, build_dataset,
    forward_max_drawdown_label,
    purged_kfold_splits, train_classifier,
    walk_forward_evaluate,
)

VAL_START = "2025-01-02"
TRAIN_START = "2015-01-01"

# LOW-stability AND low mean_imp features from the round-2 H20 feature_stability report
# (results/ncf_2330_improved_20260703.json). Deliberately excludes revenue_yoy /
# revenue_yoy_accel / revenue_mom / margin_usage_ratio / close_ma240_ratio — the round-2
# handoff flagged these as LOW-stability-but-high-importance exceptions not to prune.
H20_PRUNE_CANDIDATES = [
    # only pruned if present in the fitted feature matrix; anything not found is a no-op
]


def main() -> None:
    val_end = resolve_end_date(DB_PATH, TICKER, "latest")
    print(f"[sweep] Loading data through {val_end}")
    raw = load_data(DB_PATH, TICKER, TRAIN_START, val_end)
    print(f"[sweep] raw rows={len(raw)}")
    ext_df = load_external_df(raw, DB_PATH)

    X = build_feature_matrix(raw, ext_df)
    print(f"[sweep] feature matrix: {X.shape}")

    combos = [(0.03, 10), (0.05, 20), (0.08, 20), (0.05, 40)]
    combo_results = {}
    for threshold, horizon in combos:
        tag = f"th{int(threshold*100)}_h{horizon}"
        print(f"\n=== drawdown combo {tag} ===")
        forward_mdd, y_risk = forward_max_drawdown_label(raw["close"], horizon=horizon, threshold=threshold)
        common_idx = X.index.intersection(y_risk.dropna().index)
        X_model = X.loc[common_idx]
        y_model = y_risk.loc[common_idx].astype(int)

        # Single split (val_start), for continuity with round-1/round-2 numbers.
        train_mask = X_model.index < VAL_START
        X_tr, X_val = X_model[train_mask], X_model[~train_mask]
        y_tr, y_val = y_model[train_mask], y_model[~train_mask]
        single_split = None
        if len(X_tr) >= 100 and len(X_val) >= 20 and y_tr.nunique() == 2 and y_val.nunique() == 2:
            clf = train_classifier(X_tr, y_tr, X_val, y_val)
            single_split = {
                "auc": float(clf["ensemble"]["auc"]),
                "brier": float(clf["ensemble"]["brier"]),
                "train_rows": int(len(X_tr)), "val_rows": int(len(X_val)),
                "val_positive_rate": float(y_val.mean()),
            }
            print(f"  single-split: AUC={single_split['auc']:.4f} Brier={single_split['brier']:.4f} "
                  f"val_pos={single_split['val_positive_rate']:.2%}")
        else:
            print(f"  single-split: skipped (train={len(X_tr)}, val={len(X_val)})")

        # Purged K-fold, embargo = horizon (own validation, not piggybacking on the
        # direction-model's evaluate_purged_kfold, which assumes a -1/0/1 direction
        # label rather than this 0/1 tail-risk label).
        n = len(X_model)
        splits = purged_kfold_splits(n, 5, horizon, embargo_bars=horizon)
        fold_aucs, fold_briers = [], []
        for fi, (tr_idx, te_idx) in enumerate(splits):
            y_tr_f = y_model.values[tr_idx]
            y_te_f = y_model.values[te_idx]
            if len(np.unique(y_tr_f)) < 2 or len(np.unique(y_te_f)) < 2 or len(tr_idx) < 100:
                print(f"  fold {fi+1}: skipped (train={len(tr_idx)}, classes={len(np.unique(y_tr_f))})")
                continue
            res = train_classifier(X_model.iloc[tr_idx], y_tr_f, X_model.iloc[te_idx], y_te_f)
            fold_aucs.append(float(res["ensemble"]["auc"]))
            fold_briers.append(float(res["ensemble"]["brier"]))
            print(f"  fold {fi+1}: train={len(tr_idx)} test={len(te_idx)} AUC={fold_aucs[-1]:.4f}")

        purged = {
            "n_folds_used": len(fold_aucs),
            "avg_auc": float(np.mean(fold_aucs)) if fold_aucs else None,
            "avg_brier": float(np.mean(fold_briers)) if fold_briers else None,
        }
        print(f"  purged-CV avg AUC={purged['avg_auc']}  Brier={purged['avg_brier']}  (folds={purged['n_folds_used']})")

        combo_results[tag] = {
            "threshold": threshold, "horizon": horizon,
            "single_split": single_split, "purged_cv": purged,
            "positive_rate_all": float(y_model.mean()),
        }

    best_tag = max(
        (t for t in combo_results if combo_results[t]["purged_cv"]["avg_auc"] is not None),
        key=lambda t: combo_results[t]["purged_cv"]["avg_auc"],
    )
    print(f"\n[sweep] Best combo by purged-CV AUC: {best_tag} -> {combo_results[best_tag]['purged_cv']}")

    # Feature importance for the best combo (checks new chip/vol-spike/ADR features).
    best_threshold, best_horizon = combo_results[best_tag]["threshold"], combo_results[best_tag]["horizon"]
    _, y_best = forward_max_drawdown_label(raw["close"], horizon=best_horizon, threshold=best_threshold)
    common_idx = X.index.intersection(y_best.dropna().index)
    X_best, y_best = X.loc[common_idx], y_best.loc[common_idx].astype(int)
    from sklearn.ensemble import RandomForestClassifier
    rf_imp = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                                     max_features="sqrt", n_jobs=2, random_state=42)
    rf_imp.fit(X_best, y_best)
    importances = pd.Series(rf_imp.feature_importances_, index=X_best.columns).sort_values(ascending=False)
    top30 = importances.head(30)
    print("\n[sweep] Top-30 feature importances for best drawdown combo:")
    print(top30.to_string())

    new_tail_feats = [
        "inst_foreign_accel", "inst_foreign_sell_streak", "margin_balance_5d_chg",
        "vol5_vol20_spike", "soxx_down_x_vix_spike", "foreign_streak_x_vol20",
    ]
    new_feat_ranks = {}
    rank_of = {f: i + 1 for i, f in enumerate(importances.index)}
    for f in new_tail_feats:
        new_feat_ranks[f] = rank_of.get(f)
    print("\n[sweep] New tail-risk feature ranks (of", len(importances), "):", new_feat_ranks)

    earnings_ranks = {
        "earnings_window_flag": rank_of.get("earnings_window_flag"),
        "trading_days_since_earnings": rank_of.get("trading_days_since_earnings"),
        "trading_days_until_earnings": rank_of.get("trading_days_until_earnings"),
    }
    print("[sweep] Earnings feature ranks:", earnings_ranks)

    # --- H20 direction classifier: LOW-stability pruning experiment ---
    print("\n=== H20 direction classifier: baseline vs pruned ===")
    X20, y_ret20, y_dir20, avail20 = build_dataset(
        raw, horizon=20, ext_df=ext_df, direction_threshold=0.0, labeling="simple",
    )
    n20 = len(X20)
    splits20 = purged_kfold_splits(n20, 5, 20, embargo_bars=20)

    def _run_purged(Xd, tag):
        aucs = []
        for fi, (tr_idx, te_idx) in enumerate(splits20):
            y_tr = y_dir20[tr_idx]
            mask = y_tr != -1
            tr_clf = tr_idx[mask]
            y_tr_c = y_dir20[tr_clf]
            y_te_c = (y_ret20.values[te_idx] > 0).astype(int)
            if len(tr_clf) < 60 or len(np.unique(y_tr_c)) < 2 or len(np.unique(y_te_c)) < 2:
                continue
            res = train_classifier(Xd.iloc[tr_clf], y_tr_c, Xd.iloc[te_idx], y_te_c)
            aucs.append(float(res["ensemble"]["auc"]))
        avg = float(np.mean(aucs)) if aucs else None
        print(f"  [{tag}] purged-CV avg AUC over {len(aucs)} folds: {avg}")
        return avg, aucs

    baseline_auc, baseline_folds = _run_purged(X20, "baseline (all features)")

    # Identify LOW-importance features via a quick RF fit (excluding the known
    # LOW-but-important exceptions from round 2), drop bottom 30% by importance.
    rf20 = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                                   max_features="sqrt", n_jobs=2, random_state=42)
    mask20 = (y_dir20 != -1).to_numpy()
    rf20.fit(X20.iloc[mask20], y_dir20.iloc[mask20])
    imp20 = pd.Series(rf20.feature_importances_, index=X20.columns).sort_values()
    protect = {"revenue_yoy", "revenue_yoy_accel", "revenue_mom", "revenue_ytd_yoy",
               "margin_usage_ratio", "close_ma240_ratio"}
    n_drop = int(len(imp20) * 0.30)
    drop_candidates = [f for f in imp20.index[:n_drop] if f not in protect]
    X20_pruned = X20.drop(columns=drop_candidates)
    print(f"  Dropping {len(drop_candidates)} bottom-importance features (protected {len(protect & set(imp20.index[:n_drop]))} exceptions kept)")
    pruned_auc, pruned_folds = _run_purged(X20_pruned, "pruned (bottom-30% importance dropped)")

    result = {
        "generated_at": date.today().isoformat(),
        "drawdown_combo_sweep": combo_results,
        "best_combo": best_tag,
        "best_combo_top30_importance": top30.to_dict(),
        "new_tail_risk_feature_ranks": new_feat_ranks,
        "earnings_feature_ranks": earnings_ranks,
        "n_features_total": int(len(importances)),
        "h20_pruning": {
            "baseline_purged_cv_auc": baseline_auc,
            "baseline_fold_aucs": baseline_folds,
            "pruned_purged_cv_auc": pruned_auc,
            "pruned_fold_aucs": pruned_folds,
            "n_dropped_features": len(drop_candidates),
            "dropped_features": drop_candidates,
            "n_features_before": int(X20.shape[1]),
            "n_features_after": int(X20_pruned.shape[1]),
        },
    }
    out_path = PROJECT_ROOT / "results" / f"ncf_2330_tail_risk_sweep_{date.today().strftime('%Y%m%d')}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[sweep] Saved: {out_path}")


if __name__ == "__main__":
    main()
