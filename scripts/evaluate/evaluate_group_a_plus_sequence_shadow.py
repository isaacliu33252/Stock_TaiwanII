#!/usr/bin/env python3
"""Shadow sequence benchmark for Group A+ NCF signal outputs.

This research-only tool tests whether lagged/rolling NCF signal features add
incremental H20 direction information versus the raw latest H20 probability.
It does not change live allocation logic.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_sequence_shadow_latest_20260630.json"

BASE_SIGNAL_COLUMNS = [
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "ensemble_prob_up",
    "prob_magnitude",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "tail_reward_risk_score_h20",
    "confidence",
]


def load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        raise ValueError("NCF panel is missing date column")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").set_index("date")
    if "is_live" in frame.columns:
        frame = frame[~frame["is_live"].astype(bool)]
    return frame


def build_sequence_features(panel: pd.DataFrame, horizon: int = 20) -> tuple[pd.DataFrame, pd.Series]:
    if "forward_gain_h20" not in panel.columns:
        raise ValueError("NCF panel is missing forward_gain_h20")
    available = [col for col in BASE_SIGNAL_COLUMNS if col in panel.columns]
    if not available:
        raise ValueError("NCF panel has no usable signal columns")

    features = pd.DataFrame(index=panel.index)
    for col in available:
        series = panel[col].astype(float)
        features[col] = series
        for lag in (1, 2, 3, 5):
            features[f"{col}_lag{lag}"] = series.shift(lag)
        features[f"{col}_roll5_mean"] = series.rolling(5, min_periods=3).mean()
        features[f"{col}_roll10_mean"] = series.rolling(10, min_periods=5).mean()
        features[f"{col}_roll5_std"] = series.rolling(5, min_periods=3).std()

    if {"prob_up_h1", "prob_up_h20"}.issubset(panel.columns):
        features["h1_minus_h20"] = panel["prob_up_h1"].astype(float) - panel["prob_up_h20"].astype(float)
        features["h1_minus_h20_lag1"] = features["h1_minus_h20"].shift(1)
    if {"prob_fwd_gain_gt5_h20", "prob_fwd_mdd_gt5_h20"}.issubset(panel.columns):
        features["gain_minus_mdd_tail"] = (
            panel["prob_fwd_gain_gt5_h20"].astype(float) - panel["prob_fwd_mdd_gt5_h20"].astype(float)
        )
        features["gain_minus_mdd_tail_lag1"] = features["gain_minus_mdd_tail"].shift(1)

    target = (panel["forward_gain_h20"].astype(float) > 0.0).astype(int)
    valid = features.replace([np.inf, -np.inf], np.nan).notna().all(axis=1) & target.notna()
    return features.loc[valid].astype(float), target.loc[valid].astype(int)


def _auc_or_none(y_true: pd.Series | np.ndarray, proba: np.ndarray) -> float | None:
    values = np.asarray(y_true)
    if len(np.unique(values)) < 2:
        return None
    return float(roc_auc_score(values, proba))


def _brier_or_none(y_true: pd.Series | np.ndarray, proba: np.ndarray) -> float | None:
    values = np.asarray(y_true)
    if len(values) == 0:
        return None
    return float(brier_score_loss(values, proba))


def _delta_or_none(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return float(value - baseline)


def evaluate_shadow_models(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    n_splits: int = 4,
    gap: int = 5,
) -> dict[str, Any]:
    if len(features) < n_splits + 10:
        raise ValueError("Not enough rows for requested TimeSeriesSplit")

    models = {
        "lagged_logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
        ),
        "lagged_hgb": HistGradientBoostingClassifier(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=15,
            l2_regularization=0.05,
            random_state=42,
        ),
    }
    baseline_col = "prob_up_h20" if "prob_up_h20" in features.columns else features.columns[0]
    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)

    fold_rows: list[dict[str, Any]] = []
    model_probs = {name: [] for name in models}
    model_truth = {name: [] for name in models}
    baseline_probs: list[float] = []
    baseline_truth: list[int] = []

    for fold, (train_idx, test_idx) in enumerate(split.split(features), start=1):
        x_train = features.iloc[train_idx]
        y_train = target.iloc[train_idx]
        x_test = features.iloc[test_idx]
        y_test = target.iloc[test_idx]
        baseline = x_test[baseline_col].clip(0.0, 1.0).to_numpy(dtype=float)
        baseline_probs.extend(baseline.tolist())
        baseline_truth.extend(y_test.tolist())

        row: dict[str, Any] = {
            "fold": fold,
            "train_start": str(x_train.index[0].date()),
            "train_end": str(x_train.index[-1].date()),
            "test_start": str(x_test.index[0].date()),
            "test_end": str(x_test.index[-1].date()),
            "train_rows": int(len(x_train)),
            "test_rows": int(len(x_test)),
            "positive_rate_test": float(y_test.mean()),
            "baseline_auc": _auc_or_none(y_test, baseline),
            "baseline_brier": _brier_or_none(y_test, baseline),
        }
        for name, model in models.items():
            model.fit(x_train, y_train)
            proba = model.predict_proba(x_test)[:, 1]
            model_probs[name].extend(proba.tolist())
            model_truth[name].extend(y_test.tolist())
            row[f"{name}_auc"] = _auc_or_none(y_test, proba)
            row[f"{name}_brier"] = _brier_or_none(y_test, proba)
        fold_rows.append(row)

    baseline_auc = _auc_or_none(baseline_truth, np.asarray(baseline_probs))
    baseline_brier = _brier_or_none(baseline_truth, np.asarray(baseline_probs))
    aggregate: dict[str, Any] = {
        "baseline": {
            "feature": baseline_col,
            "auc": baseline_auc,
            "brier": baseline_brier,
        }
    }
    for name in models:
        proba = np.asarray(model_probs[name], dtype=float)
        truth = np.asarray(model_truth[name], dtype=int)
        auc = _auc_or_none(truth, proba)
        brier = _brier_or_none(truth, proba)
        aggregate[name] = {
            "auc": auc,
            "brier": brier,
            "auc_delta_vs_baseline": _delta_or_none(auc, baseline_auc),
            "brier_delta_vs_baseline": _delta_or_none(brier, baseline_brier),
        }

    best_name = max(models, key=lambda name: aggregate[name]["auc"] or float("-inf"))
    aggregate["best_shadow_model"] = best_name
    aggregate["promotion_decision"] = (
        "research_only"
        if (aggregate[best_name]["auc_delta_vs_baseline"] is None or aggregate[best_name]["auc_delta_vs_baseline"] < 0.02)
        else "candidate_for_deeper_ablation"
    )
    return {"folds": fold_rows, "aggregate": aggregate}


def build_report(panel_path: Path, n_splits: int, gap: int) -> dict[str, Any]:
    panel = load_panel(panel_path)
    features, target = build_sequence_features(panel)
    evaluation = evaluate_shadow_models(features, target, n_splits=n_splits, gap=gap)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_sequence_shadow_benchmark",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "panel": str(panel_path),
            "rows_after_live_filter": int(len(panel)),
            "feature_rows": int(len(features)),
            "feature_count": int(features.shape[1]),
            "target": "forward_gain_h20 > 0",
        },
        "evaluation": evaluation,
        "method_note": (
            "Research-only TimeSeriesSplit benchmark using lagged and rolling NCF signal outputs. "
            "It does not use raw future labels as features and does not change active allocation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_group_a_plus_sequence_shadow")
    try:
        report = build_report(Path(args.panel), args.n_splits, args.gap)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Sequence shadow benchmark: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
