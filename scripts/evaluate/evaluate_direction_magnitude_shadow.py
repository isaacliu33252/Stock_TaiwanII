#!/usr/bin/env python3
"""Direction/magnitude split shadow benchmark for Group A+.

This imports the useful idea from stock-prediction-deep-neural-learning:
separate direction classification from magnitude estimation, add clipping to
avoid unrealistic magnitude outputs, and publish a compact uncertainty band.
It is research-only and does not change live allocation.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, mean_absolute_error, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from scripts.evaluate.evaluate_stock_rnn_relative_window_shadow import (
    build_ohlcv_relative_window_features,
    load_ohlcv_panel,
    load_panel,
)
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "direction_magnitude_shadow_latest_20260701.json"


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


def _clip_by_train_percentile(values: np.ndarray, train_magnitude: pd.Series, percentile: float) -> np.ndarray:
    pct = min(max(float(percentile), 0.0), 100.0)
    if pct <= 0.0 or train_magnitude.empty:
        return np.maximum(values, 0.0)
    cap = float(np.percentile(train_magnitude.to_numpy(dtype=float), pct))
    if not np.isfinite(cap) or cap <= 0.0:
        return np.maximum(values, 0.0)
    return np.clip(np.maximum(values, 0.0), 0.0, cap)


def build_direction_magnitude_dataset(
    panel: pd.DataFrame,
    ohlcv: dict[str, pd.DataFrame],
    *,
    lookback: int = 30,
    tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Return features plus direction, magnitude, and signed H20 returns."""
    features, direction = build_ohlcv_relative_window_features(
        panel,
        ohlcv,
        lookback=lookback,
        tickers=tickers or list(TICKERS),
    )
    signed_return = panel["forward_gain_h20"].astype(float).reindex(features.index)
    magnitude = signed_return.abs()
    valid = signed_return.replace([np.inf, -np.inf], np.nan).notna()
    features = features.loc[valid]
    direction = direction.loc[features.index].astype(int)
    magnitude = magnitude.loc[features.index].astype(float)
    signed_return = signed_return.loc[features.index].astype(float)
    return features, direction, magnitude, signed_return


def evaluate_direction_magnitude_models(
    features: pd.DataFrame,
    direction_target: pd.Series,
    magnitude_target: pd.Series,
    signed_return: pd.Series,
    *,
    n_splits: int,
    gap: int,
    magnitude_clip_percentile: float = 90.0,
    include_baseline_feature: bool = False,
) -> dict[str, Any]:
    if len(features) < n_splits + 10:
        raise ValueError("Not enough rows for requested TimeSeriesSplit")

    train_cols = list(features.columns) if include_baseline_feature else [
        col for col in features.columns if col != "prob_up_h20"
    ]
    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    direction_probs: list[float] = []
    direction_truth: list[int] = []
    baseline_probs: list[float] = []
    magnitude_preds: list[float] = []
    magnitude_truth: list[float] = []
    signed_preds: list[float] = []
    signed_truth: list[float] = []
    clipped_count = 0
    folds: list[dict[str, Any]] = []

    for fold, (train_idx, test_idx) in enumerate(split.split(features), start=1):
        x_train = features.iloc[train_idx]
        x_test = features.iloc[test_idx]
        y_dir_train = direction_target.iloc[train_idx]
        y_dir_test = direction_target.iloc[test_idx]
        y_mag_train = magnitude_target.iloc[train_idx]
        y_mag_test = magnitude_target.iloc[test_idx]
        y_signed_test = signed_return.iloc[test_idx]

        direction_model = HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=0.035,
            max_leaf_nodes=15,
            l2_regularization=0.08,
            random_state=42,
        )
        magnitude_model = GradientBoostingRegressor(
            loss="huber",
            n_estimators=180,
            learning_rate=0.035,
            max_depth=2,
            random_state=42,
        )
        direction_model.fit(x_train[train_cols], y_dir_train)
        magnitude_model.fit(x_train[train_cols], y_mag_train)

        proba = direction_model.predict_proba(x_test[train_cols])[:, 1]
        raw_mag = magnitude_model.predict(x_test[train_cols])
        clipped_mag = _clip_by_train_percentile(raw_mag, y_mag_train, magnitude_clip_percentile)
        clipped_count += int(np.sum(np.asarray(raw_mag) != np.asarray(clipped_mag)))
        signed_pred = clipped_mag * np.where(proba >= 0.5, 1.0, -1.0)
        baseline = x_test["prob_up_h20"].clip(0.0, 1.0).to_numpy(dtype=float)

        direction_probs.extend(proba.tolist())
        direction_truth.extend(y_dir_test.tolist())
        baseline_probs.extend(baseline.tolist())
        magnitude_preds.extend(clipped_mag.tolist())
        magnitude_truth.extend(y_mag_test.tolist())
        signed_preds.extend(signed_pred.tolist())
        signed_truth.extend(y_signed_test.tolist())

        folds.append(
            {
                "fold": fold,
                "train_start": str(x_train.index[0].date()),
                "train_end": str(x_train.index[-1].date()),
                "test_start": str(x_test.index[0].date()),
                "test_end": str(x_test.index[-1].date()),
                "train_rows": int(len(x_train)),
                "test_rows": int(len(x_test)),
                "positive_rate_test": float(y_dir_test.mean()),
                "baseline_auc": _auc_or_none(y_dir_test, baseline),
                "direction_auc": _auc_or_none(y_dir_test, proba),
                "baseline_brier": _brier_or_none(y_dir_test, baseline),
                "direction_brier": _brier_or_none(y_dir_test, proba),
                "magnitude_mae": float(mean_absolute_error(y_mag_test, clipped_mag)),
                "signed_return_mae": float(mean_absolute_error(y_signed_test, signed_pred)),
            }
        )

    direction_auc = _auc_or_none(direction_truth, np.asarray(direction_probs))
    baseline_auc = _auc_or_none(direction_truth, np.asarray(baseline_probs))
    direction_brier = _brier_or_none(direction_truth, np.asarray(direction_probs))
    baseline_brier = _brier_or_none(direction_truth, np.asarray(baseline_probs))
    magnitude_mae = float(mean_absolute_error(magnitude_truth, magnitude_preds))
    signed_mae = float(mean_absolute_error(signed_truth, signed_preds))
    residuals = np.asarray(signed_truth, dtype=float) - np.asarray(signed_preds, dtype=float)
    residual_band = {
        "signed_return_residual_p10": float(np.percentile(residuals, 10)),
        "signed_return_residual_p50": float(np.percentile(residuals, 50)),
        "signed_return_residual_p90": float(np.percentile(residuals, 90)),
    }
    auc_delta = None if direction_auc is None or baseline_auc is None else float(direction_auc - baseline_auc)
    brier_delta = None if direction_brier is None or baseline_brier is None else float(direction_brier - baseline_brier)
    promotion_decision = (
        "candidate_for_deeper_ablation"
        if auc_delta is not None and auc_delta >= 0.02 and signed_mae <= float(np.mean(np.abs(signed_truth)))
        else "research_only"
    )
    return {
        "folds": folds,
        "aggregate": {
            "baseline": {
                "feature": "prob_up_h20",
                "auc": baseline_auc,
                "brier": baseline_brier,
            },
            "direction_model": {
                "model": "hist_gradient_boosting_classifier",
                "auc": direction_auc,
                "brier": direction_brier,
                "auc_delta_vs_baseline": auc_delta,
                "brier_delta_vs_baseline": brier_delta,
            },
            "magnitude_model": {
                "model": "gradient_boosting_regressor_huber",
                "mae": magnitude_mae,
                "clip_percentile": float(magnitude_clip_percentile),
                "clipped_prediction_count": int(clipped_count),
            },
            "combined_signed_return": {
                "mae": signed_mae,
                **residual_band,
            },
            "promotion_decision": promotion_decision,
            "active_allocation_impact": "none",
        },
    }


def build_report(
    *,
    panel_path: Path,
    db_path: Path,
    start: str,
    end: str,
    lookback: int,
    n_splits: int,
    gap: int,
    magnitude_clip_percentile: float,
    include_baseline_feature: bool,
) -> dict[str, Any]:
    panel = load_panel(panel_path)
    ohlcv = load_ohlcv_panel(db_path, list(TICKERS), start, end)
    features, direction, magnitude, signed_return = build_direction_magnitude_dataset(
        panel,
        ohlcv,
        lookback=lookback,
        tickers=list(TICKERS),
    )
    evaluation = evaluate_direction_magnitude_models(
        features,
        direction,
        magnitude,
        signed_return,
        n_splits=n_splits,
        gap=gap,
        magnitude_clip_percentile=magnitude_clip_percentile,
        include_baseline_feature=include_baseline_feature,
    )
    return {
        "schema_version": 1,
        "report_type": "direction_magnitude_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "inspiration_source": (
                "C:\\Users\\isaac\\Downloads\\stock-prediction-deep-neural-learning-master"
                "\\stock-prediction-deep-neural-learning-master"
            ),
            "panel": str(panel_path),
            "db_path": str(db_path),
            "price_window": {
                "requested_start": start,
                "requested_end": end,
                "actual_start": str(ohlcv["close"].index[0].date()),
                "actual_end": str(ohlcv["close"].index[-1].date()),
                "price_rows": int(len(ohlcv["close"])),
            },
            "lookback_days": int(lookback),
            "feature_rows": int(len(features)),
            "feature_count": int(features.shape[1]),
            "direction_target": "forward_gain_h20 > 0",
            "magnitude_target": "abs(forward_gain_h20)",
            "tickers": list(TICKERS),
            "include_baseline_feature": bool(include_baseline_feature),
        },
        "evaluation": evaluation,
        "method_note": (
            "Research-only import of direction/magnitude split, Huber-style "
            "magnitude regression, clipping, and uncertainty-band diagnostics. "
            "This report does not affect live allocation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=5)
    parser.add_argument("--magnitude-clip-percentile", type=float, default=90.0)
    parser.add_argument("--include-baseline-feature", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_direction_magnitude_shadow")
    try:
        report = build_report(
            panel_path=Path(args.panel),
            db_path=Path(args.db),
            start=args.start,
            end=args.end,
            lookback=args.lookback,
            n_splits=args.n_splits,
            gap=args.gap,
            magnitude_clip_percentile=args.magnitude_clip_percentile,
            include_baseline_feature=args.include_baseline_feature,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"direction/magnitude shadow: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
