#!/usr/bin/env python3
"""CSM-lite sign-on-magnitude shadow evaluator for 00631L.

Research-only implementation inspired by Brou and Luger (2026),
"A new decomposition approach to modeling financial returns: Conditioning
sign on magnitude". The paper's full CSM model is monthly and uses a
multiplicative-error magnitude model plus a probit sign model. This script
keeps the transferable idea only: predict return magnitude first, then feed
the predicted magnitude into a sign model.

No live allocation, target weight, or strategy manifest is changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, mean_absolute_error, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT as GROUP_A_PLUS_ROOT
from scripts.evaluate.evaluate_direction_magnitude_shadow import build_direction_magnitude_dataset
from scripts.evaluate.evaluate_stock_rnn_relative_window_shadow import load_ohlcv_panel, load_panel

DEFAULT_PANEL = GROUP_A_PLUS_ROOT / "results" / "ncf_00631l_panel_latest_20260716.csv"
DEFAULT_OUTPUT = GROUP_A_PLUS_ROOT / "results" / "csm_lite_00631l_shadow_20250102_20260716.json"


def _auc_or_none(y_true: pd.Series | np.ndarray, proba: np.ndarray) -> float | None:
    values = np.asarray(y_true)
    if len(values) == 0 or len(np.unique(values)) < 2:
        return None
    return float(roc_auc_score(values, proba))


def _brier_or_none(y_true: pd.Series | np.ndarray, proba: np.ndarray) -> float | None:
    values = np.asarray(y_true)
    if len(values) == 0:
        return None
    return float(brier_score_loss(values, proba))


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _confusion(pred: pd.Series, label: pd.Series) -> dict[str, Any]:
    valid = pred.notna() & label.notna()
    p = pred[valid].astype(bool)
    y = label[valid].astype(bool)
    tp = int((p & y).sum())
    fp = int((p & ~y).sum())
    tn = int((~p & ~y).sum())
    fn = int((~p & y).sum())
    return {
        "rows": int(valid.sum()),
        "active_days": int(p.sum()),
        "event_days": int(y.sum()),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": _safe_rate(tp, tp + fp),
        "recall": _safe_rate(tp, tp + fn),
        "false_positive_rate": _safe_rate(fp, fp + tn),
    }


def _clip_by_train_percentile(values: np.ndarray, train_magnitude: pd.Series, percentile: float) -> np.ndarray:
    pct = min(max(float(percentile), 0.0), 100.0)
    raw = np.maximum(np.asarray(values, dtype=float), 0.0)
    if pct <= 0.0 or train_magnitude.empty:
        return raw
    cap = float(np.percentile(train_magnitude.to_numpy(dtype=float), pct))
    if not np.isfinite(cap) or cap <= 0.0:
        return raw
    return np.clip(raw, 0.0, cap)


def _fit_predict_direction_proba(model: Any, x_train: pd.DataFrame, y_train: pd.Series, x_test: pd.DataFrame) -> tuple[np.ndarray, bool]:
    """Fit a probabilistic direction model, falling back to base-rate if one-class."""
    if y_train.nunique() < 2:
        base_rate = float(y_train.mean()) if len(y_train) else 0.5
        return np.full(len(x_test), base_rate, dtype=float), True
    model.fit(x_train, y_train)
    return model.predict_proba(x_test)[:, 1], False


def _signal_summary(frame: pd.DataFrame, prob_col: str, threshold: float) -> dict[str, Any]:
    prob = frame[prob_col].astype(float)
    signal = prob <= threshold
    nonpositive_label = frame["signed_return_h20"] <= 0.0
    adverse_label = frame["signed_return_h20"] <= -0.03
    return {
        "threshold": float(threshold),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "nonpositive_forward_return": _confusion(signal, nonpositive_label),
        "adverse_forward_return_le_neg3pct": _confusion(signal, adverse_label),
        "active_mean_forward_return": float(frame.loc[signal, "signed_return_h20"].mean()) if signal.any() else None,
        "inactive_mean_forward_return": float(frame.loc[~signal, "signed_return_h20"].mean()) if (~signal).any() else None,
        "active_mean_predicted_magnitude": float(frame.loc[signal, "csm_lite_predicted_magnitude"].mean()) if signal.any() else None,
        "inactive_mean_predicted_magnitude": float(frame.loc[~signal, "csm_lite_predicted_magnitude"].mean()) if (~signal).any() else None,
    }


def evaluate_csm_lite(
    features: pd.DataFrame,
    direction_target: pd.Series,
    magnitude_target: pd.Series,
    signed_return: pd.Series,
    *,
    n_splits: int,
    gap: int,
    magnitude_clip_percentile: float,
    include_baseline_feature: bool,
    no_add_thresholds: tuple[float, ...],
) -> tuple[dict[str, Any], pd.DataFrame]:
    if len(features) < n_splits + 10:
        raise ValueError("Not enough rows for requested TimeSeriesSplit")

    train_cols = list(features.columns) if include_baseline_feature else [
        col for col in features.columns if col != "prob_up_h20"
    ]
    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    rows: list[pd.DataFrame] = []
    folds: list[dict[str, Any]] = []

    for fold, (train_idx, test_idx) in enumerate(split.split(features), start=1):
        x_train = features.iloc[train_idx]
        x_test = features.iloc[test_idx]
        y_dir_train = direction_target.iloc[train_idx]
        y_dir_test = direction_target.iloc[test_idx]
        y_mag_train = magnitude_target.iloc[train_idx]
        y_mag_test = magnitude_target.iloc[test_idx]
        signed_test = signed_return.iloc[test_idx]

        magnitude_model = HistGradientBoostingRegressor(
            max_iter=180,
            learning_rate=0.035,
            max_leaf_nodes=15,
            l2_regularization=0.08,
            random_state=42,
        )
        direction_only = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42),
        )
        csm_lite = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42),
        )
        hgb_csm_lite = HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=0.035,
            max_leaf_nodes=15,
            l2_regularization=0.08,
            random_state=42,
        )

        magnitude_model.fit(x_train[train_cols], y_mag_train)
        pred_mag_train = _clip_by_train_percentile(
            magnitude_model.predict(x_train[train_cols]), y_mag_train, magnitude_clip_percentile
        )
        pred_mag_test = _clip_by_train_percentile(
            magnitude_model.predict(x_test[train_cols]), y_mag_train, magnitude_clip_percentile
        )
        x_train_csm = x_train[train_cols].copy()
        x_test_csm = x_test[train_cols].copy()
        train_mag_series = pd.Series(pred_mag_train, index=x_train.index, dtype=float)
        test_mag_series = pd.Series(pred_mag_test, index=x_test.index, dtype=float)
        train_mag_scale = float(train_mag_series.rolling(252, min_periods=60).median().iloc[-1])
        if not np.isfinite(train_mag_scale) or train_mag_scale <= 0.0:
            train_mag_scale = float(max(train_mag_series.median(), 1e-9))
        x_train_csm["csm_predicted_magnitude"] = train_mag_series
        x_train_csm["csm_predicted_magnitude_ratio"] = train_mag_series / train_mag_scale
        x_test_csm["csm_predicted_magnitude"] = test_mag_series
        x_test_csm["csm_predicted_magnitude_ratio"] = test_mag_series / train_mag_scale

        baseline_prob = x_test["prob_up_h20"].clip(0.0, 1.0).to_numpy(dtype=float)
        direction_prob, direction_one_class = _fit_predict_direction_proba(
            direction_only, x_train[train_cols], y_dir_train, x_test[train_cols]
        )
        csm_prob, csm_one_class = _fit_predict_direction_proba(csm_lite, x_train_csm, y_dir_train, x_test_csm)
        hgb_csm_prob, hgb_one_class = _fit_predict_direction_proba(
            hgb_csm_lite, x_train_csm, y_dir_train, x_test_csm
        )

        fold_frame = pd.DataFrame(
            {
                "fold": fold,
                "baseline_prob_up_h20": baseline_prob,
                "direction_only_prob_up_h20": direction_prob,
                "csm_lite_prob_up_h20": csm_prob,
                "hgb_csm_lite_prob_up_h20": hgb_csm_prob,
                "csm_lite_predicted_magnitude": pred_mag_test,
                "true_magnitude_h20": y_mag_test.to_numpy(dtype=float),
                "signed_return_h20": signed_test.to_numpy(dtype=float),
                "direction_target_h20": y_dir_test.to_numpy(dtype=int),
            },
            index=x_test.index,
        )
        rows.append(fold_frame)
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
                "magnitude_mae": float(mean_absolute_error(y_mag_test, pred_mag_test)),
                "baseline_auc": _auc_or_none(y_dir_test, baseline_prob),
                "direction_only_auc": _auc_or_none(y_dir_test, direction_prob),
                "csm_lite_auc": _auc_or_none(y_dir_test, csm_prob),
                "hgb_csm_lite_auc": _auc_or_none(y_dir_test, hgb_csm_prob),
                "baseline_brier": _brier_or_none(y_dir_test, baseline_prob),
                "direction_only_brier": _brier_or_none(y_dir_test, direction_prob),
                "csm_lite_brier": _brier_or_none(y_dir_test, csm_prob),
                "hgb_csm_lite_brier": _brier_or_none(y_dir_test, hgb_csm_prob),
                "one_class_fallback": {
                    "direction_only": bool(direction_one_class),
                    "csm_lite": bool(csm_one_class),
                    "hgb_csm_lite": bool(hgb_one_class),
                },
            }
        )

    frame = pd.concat(rows).sort_index()
    y = frame["direction_target_h20"].astype(int)
    aggregate: dict[str, Any] = {
        "baseline": {
            "feature": "prob_up_h20",
            "auc": _auc_or_none(y, frame["baseline_prob_up_h20"].to_numpy(dtype=float)),
            "brier": _brier_or_none(y, frame["baseline_prob_up_h20"].to_numpy(dtype=float)),
        },
        "direction_only_logistic": {
            "auc": _auc_or_none(y, frame["direction_only_prob_up_h20"].to_numpy(dtype=float)),
            "brier": _brier_or_none(y, frame["direction_only_prob_up_h20"].to_numpy(dtype=float)),
        },
        "csm_lite_logistic": {
            "auc": _auc_or_none(y, frame["csm_lite_prob_up_h20"].to_numpy(dtype=float)),
            "brier": _brier_or_none(y, frame["csm_lite_prob_up_h20"].to_numpy(dtype=float)),
        },
        "csm_lite_hgb": {
            "auc": _auc_or_none(y, frame["hgb_csm_lite_prob_up_h20"].to_numpy(dtype=float)),
            "brier": _brier_or_none(y, frame["hgb_csm_lite_prob_up_h20"].to_numpy(dtype=float)),
        },
        "magnitude_model": {
            "model": "hist_gradient_boosting_regressor",
            "mae": float(mean_absolute_error(frame["true_magnitude_h20"], frame["csm_lite_predicted_magnitude"])),
            "clip_percentile": float(magnitude_clip_percentile),
        },
    }
    baseline_auc = aggregate["baseline"]["auc"]
    baseline_brier = aggregate["baseline"]["brier"]
    for key in ("direction_only_logistic", "csm_lite_logistic", "csm_lite_hgb"):
        auc = aggregate[key]["auc"]
        brier = aggregate[key]["brier"]
        aggregate[key]["auc_delta_vs_baseline"] = None if auc is None or baseline_auc is None else float(auc - baseline_auc)
        aggregate[key]["brier_delta_vs_baseline"] = None if brier is None or baseline_brier is None else float(brier - baseline_brier)

    signal_quality = {
        "baseline": {
            f"prob_le_{threshold:.2f}": _signal_summary(frame, "baseline_prob_up_h20", threshold)
            for threshold in no_add_thresholds
        },
        "direction_only_logistic": {
            f"prob_le_{threshold:.2f}": _signal_summary(frame, "direction_only_prob_up_h20", threshold)
            for threshold in no_add_thresholds
        },
        "csm_lite_logistic": {
            f"prob_le_{threshold:.2f}": _signal_summary(frame, "csm_lite_prob_up_h20", threshold)
            for threshold in no_add_thresholds
        },
        "csm_lite_hgb": {
            f"prob_le_{threshold:.2f}": _signal_summary(frame, "hgb_csm_lite_prob_up_h20", threshold)
            for threshold in no_add_thresholds
        },
    }
    csm_auc_delta = aggregate["csm_lite_logistic"]["auc_delta_vs_baseline"]
    best_no_add = signal_quality["csm_lite_logistic"][f"prob_le_{no_add_thresholds[0]:.2f}"][
        "nonpositive_forward_return"
    ]
    promotion_decision = (
        "candidate_for_deeper_ablation"
        if csm_auc_delta is not None and csm_auc_delta >= 0.02 and (best_no_add["precision"] or 0.0) >= 0.60
        else "research_only"
    )
    return {
        "folds": folds,
        "aggregate": aggregate,
        "no_add_signal_quality": signal_quality,
        "promotion_decision": promotion_decision,
        "active_allocation_impact": "none",
    }, frame


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
    no_add_thresholds: tuple[float, ...],
) -> tuple[dict[str, Any], pd.DataFrame]:
    panel = load_panel(panel_path)
    ohlcv = load_ohlcv_panel(db_path, list(TICKERS), start, end)
    features, direction, magnitude, signed_return = build_direction_magnitude_dataset(
        panel,
        ohlcv,
        lookback=lookback,
        tickers=list(TICKERS),
    )
    evaluation, frame = evaluate_csm_lite(
        features,
        direction,
        magnitude,
        signed_return,
        n_splits=n_splits,
        gap=gap,
        magnitude_clip_percentile=magnitude_clip_percentile,
        include_baseline_feature=include_baseline_feature,
        no_add_thresholds=no_add_thresholds,
    )
    report = {
        "report_type": "csm_lite_00631l_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.04153v1.pdf",
            "title": "A new decomposition approach to modeling financial returns: Conditioning sign on magnitude",
            "implementation_note": (
                "CSM-lite uses predicted H20 magnitude as a sign-model feature. It does not use "
                "realized contemporaneous magnitude at prediction time."
            ),
        },
        "policy": "shadow_only_no_weight_change",
        "parameters": {
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
            "n_splits": int(n_splits),
            "gap": int(gap),
            "magnitude_clip_percentile": float(magnitude_clip_percentile),
            "include_baseline_feature": bool(include_baseline_feature),
            "no_add_thresholds": list(no_add_thresholds),
            "feature_rows": int(len(features)),
            "feature_count": int(features.shape[1]),
            "direction_target": "forward_gain_h20 > 0",
            "magnitude_target": "abs(forward_gain_h20)",
            "tickers": list(TICKERS),
        },
        "evaluation": evaluation,
        "interpretation": (
            "A useful CSM-lite shadow should improve direction AUC/Brier versus the existing "
            "prob_up_h20 baseline and produce low-probability no-add days with poor realized "
            "00631L forward returns. This report is diagnostic only."
        ),
    }
    return report, frame


def _parse_thresholds(raw: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError("At least one no-add threshold is required")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=20)
    parser.add_argument("--magnitude-clip-percentile", type=float, default=90.0)
    parser.add_argument("--include-baseline-feature", action="store_true")
    parser.add_argument("--no-add-thresholds", default="0.45,0.40,0.35")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_report(
        panel_path=Path(args.panel),
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        lookback=int(args.lookback),
        n_splits=int(args.n_splits),
        gap=int(args.gap),
        magnitude_clip_percentile=float(args.magnitude_clip_percentile),
        include_baseline_feature=bool(args.include_baseline_feature),
        no_add_thresholds=_parse_thresholds(args.no_add_thresholds),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {
        "aggregate": report["evaluation"]["aggregate"],
        "promotion_decision": report["evaluation"]["promotion_decision"],
    }
    print(f"Saved: {output}")
    print(f"Frame: {frame_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
