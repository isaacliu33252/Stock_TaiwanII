#!/usr/bin/env python3
"""Optuna hyperparameter tuning for NCF 00631L direction classifiers.

Tunes LGB, XGB, HGB, RF for H=20 direction prediction using TimeSeriesSplit
on the training period. Saves best params to results/ncf_optuna_best_params.json.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/misc/ncf_optuna_tune.py
    PYTHONPATH=. .venv/bin/python scripts/misc/ncf_optuna_tune.py --trials 100 --horizon 20
    PYTHONPATH=. .venv/bin/python scripts/misc/ncf_optuna_tune.py --trials 50 --models lgb xgb
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
    ExtraTreesClassifier,
)
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.misc.ncf_00631l import (
    DB_PATH,
    load_data,
    load_external_df,
    build_dataset,
)

try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

RESULTS_DIR = ROOT / "results"
DEFAULT_OUTPUT = RESULTS_DIR / "ncf_optuna_best_params.json"

N_CV_SPLITS = 4
MIN_TRAIN_SIZE = 200


def _cv_auc(model_cls, params: dict, X: pd.DataFrame, y: np.ndarray, n_splits: int) -> float:
    """TimeSeriesSplit CV AUC, using only binary labels."""
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=5)
    aucs = []
    for train_idx, val_idx in tscv.split(X):
        if len(train_idx) < MIN_TRAIN_SIZE:
            continue
        Xt, Xv = X.iloc[train_idx], X.iloc[val_idx]
        yt, yv = y[train_idx], y[val_idx]
        # only binary labels in training
        mask = yt != -1
        if mask.sum() < 50:
            continue
        clf = model_cls(**params)
        clf.fit(Xt[mask], yt[mask])
        try:
            proba = clf.predict_proba(Xv)[:, 1]
            yv_bin = (yv != 0).astype(int) if -1 in np.unique(yv) else yv
            if len(np.unique(yv_bin)) < 2:
                continue
            aucs.append(roc_auc_score(yv_bin, proba))
        except Exception:
            continue
    return float(np.mean(aucs)) if aucs else 0.5


def make_objective_lgb(X: pd.DataFrame, y: np.ndarray):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1000, step=100),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 30),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 1.0, log=True),
            "n_jobs": -1,
            "random_state": 42,
            "verbose": -1,
        }
        return _cv_auc(lgb.LGBMClassifier, params, X, y, N_CV_SPLITS)
    return objective


def make_objective_xgb(X: pd.DataFrame, y: np.ndarray):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1000, step=100),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 5.0, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0.0, 0.5),
            "eval_metric": "logloss",
            "n_jobs": -1,
            "random_state": 42,
            "verbosity": 0,
        }
        return _cv_auc(xgb.XGBClassifier, params, X, y, N_CV_SPLITS)
    return objective


def make_objective_hgb(X: pd.DataFrame, y: np.ndarray):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "max_iter": trial.suggest_int("max_iter", 200, 800, step=100),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 30),
            "l2_regularization": trial.suggest_float("l2_regularization", 1e-4, 1.0, log=True),
            "max_features": trial.suggest_float("max_features", 0.5, 1.0),
            "random_state": 42,
        }
        return _cv_auc(HistGradientBoostingClassifier, params, X, y, N_CV_SPLITS)
    return objective


def make_objective_rf(X: pd.DataFrame, y: np.ndarray):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
            "max_depth": trial.suggest_int("max_depth", 5, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 2, 15),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5, 0.7]),
            "n_jobs": -1,
            "random_state": 42,
        }
        return _cv_auc(RandomForestClassifier, params, X, y, N_CV_SPLITS)
    return objective


def make_objective_et(X: pd.DataFrame, y: np.ndarray):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
            "max_depth": trial.suggest_int("max_depth", 5, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 2, 15),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5, 0.7]),
            "n_jobs": -1,
            "random_state": 42,
        }
        return _cv_auc(ExtraTreesClassifier, params, X, y, N_CV_SPLITS)
    return objective


MODEL_OBJECTIVES = {
    "lgb": (make_objective_lgb, _HAS_LGB),
    "xgb": (make_objective_xgb, _HAS_XGB),
    "hgb": (make_objective_hgb, True),
    "rf":  (make_objective_rf,  True),
    "et":  (make_objective_et,  True),
}


def tune_model(
    name: str,
    objective_fn,
    X: pd.DataFrame,
    y: np.ndarray,
    n_trials: int,
) -> dict:
    print(f"\n[Optuna] Tuning {name.upper()}  ({n_trials} trials, {N_CV_SPLITS}-fold TSS)...")
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective_fn(X, y), n_trials=n_trials, show_progress_bar=False)
    best = study.best_trial
    print(f"  Best AUC: {best.value:.4f}  params: {best.params}")
    return {"best_auc": best.value, "best_params": best.params}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--horizon", type=int, default=20,
                        help="Which horizon to optimize for (default 20)")
    parser.add_argument("--trials", type=int, default=75,
                        help="Number of Optuna trials per model (default 75)")
    parser.add_argument("--models", nargs="+",
                        default=["lgb", "xgb", "hgb", "rf", "et"],
                        help="Models to tune (default: lgb xgb hgb rf et)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    print(f"[NCF Optuna] Loading data {args.train_start} ~ {args.train_end}...")
    raw = load_data(DB_PATH, args.ticker, args.train_start, args.train_end)
    print(f"  Raw rows: {len(raw)}")

    print("\n[ExtFeat] Loading external features...")
    ext_df = load_external_df(raw, DB_PATH)

    labeling = "triple_barrier" if args.horizon == 5 else "simple"
    print(f"\n[NCF Optuna] Building H={args.horizon} dataset (labeling={labeling})...")
    X, y_return, y_direction, features = build_dataset(
        raw, horizon=args.horizon, ext_df=ext_df,
        direction_threshold=0.005, labeling=labeling, tbl_mult=0.75,
    )
    y = y_direction.values
    print(f"  Features: {len(features)}  Rows: {len(X)}")
    print(f"  Direction dist: {(y==1).sum()} up / {(y==0).sum()} down / {(y==-1).sum()} neutral")

    results: dict = {
        "ticker": args.ticker,
        "horizon": args.horizon,
        "train_start": args.train_start,
        "train_end": args.train_end,
        "n_trials": args.trials,
        "n_features": len(features),
        "n_rows": len(X),
        "models": {},
    }

    for model_name in args.models:
        if model_name not in MODEL_OBJECTIVES:
            print(f"  [skip] unknown model: {model_name}")
            continue
        obj_fn, available = MODEL_OBJECTIVES[model_name]
        if not available:
            print(f"  [skip] {model_name}: not installed")
            continue
        result = tune_model(model_name, obj_fn, X, y, args.trials)
        results["models"][model_name] = result

    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[Optuna] Best params saved → {output_path}")
    print("\n=== Summary ===")
    for name, r in results["models"].items():
        print(f"  {name.upper():>5}  best CV AUC = {r['best_auc']:.4f}")


if __name__ == "__main__":
    main()
