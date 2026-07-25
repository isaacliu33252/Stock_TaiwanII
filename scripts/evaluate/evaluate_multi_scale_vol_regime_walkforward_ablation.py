#!/usr/bin/env python3
"""Walk-forward feature ablation for multi-scale volatility regime shadow.

This is a research-only evaluator. It tests whether the 2606.06190v1-inspired
multi-scale volatility features add out-of-sample value for 00631L no-add risk.
It does not connect any signal to live allocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from group_a_plus.validation import PurgedWalkForwardSplit
from scripts.evaluate.evaluate_multi_scale_vol_regime_shadow import (
    DB_PATH,
    _add_forward_labels,
    _build_vol_frame,
    _confusion,
    _load_close_panel,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "multi_scale_vol_regime_walkforward_ablation_20180102_20260716.json"


FEATURE_SETS: dict[str, list[str]] = {
    "short_vol_only": ["short_vol_percentile"],
    "medium_vol_only": ["medium_vol_percentile"],
    "long_vol_only": ["long_vol_percentile"],
    "scale_percentiles": ["short_vol_percentile", "medium_vol_percentile", "long_vol_percentile"],
    "regime_codes": ["short_regime_code", "medium_regime_code", "long_regime_code"],
    "uncertainty": ["regime_entropy", "cross_scale_disagreement", "crisis_probability_proxy"],
    "signal_flags": [
        "all_crisis_active",
        "synchronized_turbulence_active",
        "micro_shock_active",
        "macro_stress_divergence_active",
        "high_uncertainty_active",
    ],
    "all_vol_features": [
        "short_vol_percentile",
        "medium_vol_percentile",
        "long_vol_percentile",
        "short_regime_code",
        "medium_regime_code",
        "long_regime_code",
        "regime_entropy",
        "cross_scale_disagreement",
        "crisis_probability_proxy",
        "all_crisis_active",
        "synchronized_turbulence_active",
        "micro_shock_active",
        "macro_stress_divergence_active",
        "high_uncertainty_active",
    ],
}


def _auc_or_none(y_true: pd.Series | np.ndarray, score: pd.Series | np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=int)
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, np.asarray(score, dtype=float)))


def _ap_or_none(y_true: pd.Series | np.ndarray, score: pd.Series | np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=int)
    if len(np.unique(y)) < 2:
        return None
    return float(average_precision_score(y, np.asarray(score, dtype=float)))


def _brier_or_none(y_true: pd.Series | np.ndarray, prob: pd.Series | np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=int)
    if len(np.unique(y)) < 2:
        return None
    return float(brier_score_loss(y, np.asarray(prob, dtype=float)))


def _delta(value: float | None, baseline: float | None) -> float | None:
    return None if value is None or baseline is None else float(value - baseline)


def _build_frame(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    percentile_window: int,
    horizon: int,
    underperform_threshold: float,
    mdd_threshold: float,
) -> pd.DataFrame:
    prices = _load_close_panel(db_path, ("0050.TW", "00631L.TW"), start, end, warmup_days)
    frame = _build_vol_frame(
        prices,
        start=start,
        end=end,
        vol_symbol="00631L.TW",
        percentile_window=percentile_window,
    )
    frame = _add_forward_labels(
        frame,
        prices,
        underperform_threshold=underperform_threshold,
        mdd_threshold=mdd_threshold,
    )
    label_col = f"no_add_label_h{horizon}"
    needed = sorted({label_col, "vol_no_add_active", *[col for cols in FEATURE_SETS.values() for col in cols]})
    return frame[needed].dropna(subset=[label_col]).copy()


def _fit_predict_prob(x_train: pd.DataFrame, y_train: pd.Series, x_test: pd.DataFrame) -> np.ndarray:
    if y_train.nunique() < 2:
        return np.repeat(float(y_train.mean()), len(x_test))
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42),
    )
    model.fit(x_train, y_train.astype(int))
    return model.predict_proba(x_test)[:, 1]


def _top_quantile_signal(
    *,
    train_score: pd.Series,
    test_score: pd.Series,
    quantile: float,
) -> pd.Series:
    threshold = float(train_score.quantile(quantile))
    return test_score >= threshold


def _evaluate_feature_set(
    frame: pd.DataFrame,
    *,
    feature_cols: list[str],
    label_col: str,
    splitter: PurgedWalkForwardSplit,
    alert_quantile: float,
    feature_set_name: str,
) -> tuple[dict[str, Any], pd.DataFrame]:
    data = frame[feature_cols + [label_col]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    y = data[label_col].astype(int)
    fold_rows: list[dict[str, Any]] = []
    pred_rows: list[pd.DataFrame] = []

    for fold, (train_idx, test_idx) in enumerate(splitter.split(data), start=1):
        x_train = data.iloc[train_idx][feature_cols].astype(float)
        y_train = y.iloc[train_idx]
        x_test = data.iloc[test_idx][feature_cols].astype(float)
        y_test = y.iloc[test_idx]
        prob = _fit_predict_prob(x_train, y_train, x_test)
        train_prob = _fit_predict_prob(x_train, y_train, x_train)
        base_prob = np.repeat(float(y_train.mean()), len(y_test))
        alert = _top_quantile_signal(
            train_score=pd.Series(train_prob, index=x_train.index),
            test_score=pd.Series(prob, index=x_test.index),
            quantile=alert_quantile,
        )
        base_alert = np.repeat(False, len(y_test))

        fold_rows.append(
            {
                "fold": fold,
                "train_start": str(x_train.index[0].date()),
                "train_end": str(x_train.index[-1].date()),
                "test_start": str(x_test.index[0].date()),
                "test_end": str(x_test.index[-1].date()),
                "train_rows": int(len(x_train)),
                "test_rows": int(len(x_test)),
                "train_event_rate": float(y_train.mean()),
                "test_event_rate": float(y_test.mean()),
                "auc": _auc_or_none(y_test, prob),
                "average_precision": _ap_or_none(y_test, prob),
                "brier": _brier_or_none(y_test, prob),
                "base_rate_brier": _brier_or_none(y_test, base_prob),
                "alert_confusion": _confusion(alert, y_test.astype(bool)),
                "base_rate_confusion": _confusion(pd.Series(base_alert, index=y_test.index), y_test.astype(bool)),
            }
        )
        pred_rows.append(
            pd.DataFrame(
                {
                    "date": x_test.index,
                    "fold": fold,
                    "feature_set": feature_set_name,
                    "label": y_test.to_numpy(dtype=int),
                    "prob_no_add_horizon": prob,
                    "alert_active": alert.to_numpy(dtype=bool),
                }
            )
        )

    pred = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    if pred.empty:
        aggregate = {
            "rows": 0,
            "auc": None,
            "average_precision": None,
            "brier": None,
            "base_rate_brier": None,
            "brier_delta_vs_base_rate": None,
            "alert_confusion": None,
        }
    else:
        yy = pred["label"].astype(int)
        pp = pred["prob_no_add_horizon"].astype(float)
        base_rates = []
        for row in fold_rows:
            mask = pred["fold"].eq(row["fold"])
            base_rates.extend([row["train_event_rate"]] * int(mask.sum()))
        base = np.asarray(base_rates, dtype=float)
        aggregate = {
            "rows": int(len(pred)),
            "auc": _auc_or_none(yy, pp),
            "average_precision": _ap_or_none(yy, pp),
            "brier": _brier_or_none(yy, pp),
            "base_rate_brier": _brier_or_none(yy, base),
            "brier_delta_vs_base_rate": _delta(_brier_or_none(yy, pp), _brier_or_none(yy, base)),
            "alert_confusion": _confusion(pred["alert_active"].astype(bool), yy.astype(bool)),
        }
    return {"features": feature_cols, "folds": fold_rows, "aggregate": aggregate}, pred


def _evaluate_raw_scores(
    frame: pd.DataFrame,
    *,
    label_col: str,
    alert_quantile: float,
) -> dict[str, Any]:
    y = frame[label_col].astype(bool)
    out: dict[str, Any] = {}
    for name, score_col in {
        "raw_crisis_probability_proxy": "crisis_probability_proxy",
        "raw_regime_entropy": "regime_entropy",
        "raw_cross_scale_disagreement": "cross_scale_disagreement",
    }.items():
        score = frame[score_col].astype(float)
        active = score >= float(score.quantile(alert_quantile))
        out[name] = {
            "score_col": score_col,
            "auc": _auc_or_none(y.astype(int), score),
            "average_precision": _ap_or_none(y.astype(int), score),
            "alert_confusion": _confusion(active, y),
        }
    out["rule_vol_no_add_active"] = {
        "score_col": "vol_no_add_active",
        "auc": _auc_or_none(y.astype(int), frame["vol_no_add_active"].astype(int)),
        "average_precision": _ap_or_none(y.astype(int), frame["vol_no_add_active"].astype(int)),
        "alert_confusion": _confusion(frame["vol_no_add_active"].astype(bool), y),
    }
    return out


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    percentile_window: int,
    horizon: int,
    n_splits: int,
    test_size: int,
    min_train_size: int,
    alert_quantile: float,
    underperform_threshold: float,
    mdd_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    frame = _build_frame(
        db_path=db_path,
        start=start,
        end=end,
        warmup_days=warmup_days,
        percentile_window=percentile_window,
        horizon=horizon,
        underperform_threshold=underperform_threshold,
        mdd_threshold=mdd_threshold,
    )
    label_col = f"no_add_label_h{horizon}"
    splitter = PurgedWalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        purge=horizon,
        min_train_size=min_train_size,
    )
    results: dict[str, Any] = {}
    predictions: list[pd.DataFrame] = []
    for name, cols in FEATURE_SETS.items():
        result, pred = _evaluate_feature_set(
            frame,
            feature_cols=cols,
            label_col=label_col,
            splitter=splitter,
            alert_quantile=alert_quantile,
            feature_set_name=name,
        )
        results[name] = result
        predictions.append(pred)
    aggregate_rank = sorted(
        (
            {
                "feature_set": name,
                "auc": value["aggregate"]["auc"],
                "average_precision": value["aggregate"]["average_precision"],
                "brier_delta_vs_base_rate": value["aggregate"]["brier_delta_vs_base_rate"],
                "alert_precision": (value["aggregate"]["alert_confusion"] or {}).get("precision"),
                "alert_recall": (value["aggregate"]["alert_confusion"] or {}).get("recall"),
                "alert_fpr": (value["aggregate"]["alert_confusion"] or {}).get("false_positive_rate"),
            }
            for name, value in results.items()
        ),
        key=lambda row: (
            row["auc"] if row["auc"] is not None else -1.0,
            -(row["brier_delta_vs_base_rate"] if row["brier_delta_vs_base_rate"] is not None else 999.0),
        ),
        reverse=True,
    )
    pred_frame = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    raw_scores = _evaluate_raw_scores(frame, label_col=label_col, alert_quantile=alert_quantile)
    best = aggregate_rank[0] if aggregate_rank else {}
    promotion_decision = "research_only"
    if (
        best.get("auc") is not None
        and best.get("auc", 0.0) >= 0.60
        and best.get("brier_delta_vs_base_rate") is not None
        and best.get("brier_delta_vs_base_rate") < 0
        and best.get("alert_fpr") is not None
        and best.get("alert_fpr") <= 0.20
    ):
        promotion_decision = "candidate_for_deeper_out_of_sample_review"
    report = {
        "report_type": "multi_scale_vol_regime_walkforward_ablation",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "C:/Users/isaac/Downloads/2606.06190v1.pdf",
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
            "rows": int(len(frame)),
            "event_rate": float(frame[label_col].mean()),
        },
        "parameters": {
            "horizon": horizon,
            "n_splits": n_splits,
            "test_size": test_size,
            "min_train_size": min_train_size,
            "purge": horizon,
            "alert_quantile": alert_quantile,
            "percentile_window": percentile_window,
            "underperform_threshold": underperform_threshold,
            "mdd_threshold": mdd_threshold,
        },
        "feature_set_results": results,
        "aggregate_rank": aggregate_rank,
        "raw_score_results": raw_scores,
        "promotion_decision": promotion_decision,
        "interpretation": (
            "Purged walk-forward ablation of transparent multi-scale volatility features. "
            "A candidate still requires separate crash-window and live-shadow review."
        ),
    }
    return report, pred_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--warmup-days", type=int, default=500)
    parser.add_argument("--percentile-window", type=int, default=252)
    parser.add_argument("--horizon", type=int, default=10, choices=[5, 10])
    parser.add_argument("--n-splits", type=int, default=8)
    parser.add_argument("--test-size", type=int, default=63)
    parser.add_argument("--min-train-size", type=int, default=252)
    parser.add_argument("--alert-quantile", type=float, default=0.80)
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, pred = build_report(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        warmup_days=int(args.warmup_days),
        percentile_window=int(args.percentile_window),
        horizon=int(args.horizon),
        n_splits=int(args.n_splits),
        test_size=int(args.test_size),
        min_train_size=int(args.min_train_size),
        alert_quantile=float(args.alert_quantile),
        underperform_threshold=float(args.underperform_threshold),
        mdd_threshold=float(args.mdd_threshold),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pred_output = output.with_name(output.stem + "_predictions.csv")
    pred.to_csv(pred_output, index=False, encoding="utf-8-sig")
    report["prediction_output"] = str(pred_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"Predictions: {pred_output}")
    print(json.dumps(report["aggregate_rank"][:8], ensure_ascii=False, indent=2))
    print(f"Promotion decision: {report['promotion_decision']}")


if __name__ == "__main__":
    main()
