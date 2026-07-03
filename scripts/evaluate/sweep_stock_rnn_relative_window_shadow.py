#!/usr/bin/env python3
"""Small grid sweep for stock-rnn relative-window shadow features."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from scripts.evaluate.evaluate_stock_rnn_relative_window_shadow import (
    DEFAULT_PANEL,
    build_ohlcv_relative_window_features,
    build_relative_window_features,
    load_close_prices,
    load_ohlcv_panel,
    load_panel,
)
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "stock_rnn_relative_window_sweep_20260630.json"


def _auc_or_none(y_true: list[int], proba: list[float]) -> float | None:
    values = np.asarray(y_true)
    if len(np.unique(values)) < 2:
        return None
    return float(roc_auc_score(values, np.asarray(proba, dtype=float)))


def _brier_or_none(y_true: list[int], proba: list[float]) -> float | None:
    if not y_true:
        return None
    return float(brier_score_loss(np.asarray(y_true), np.asarray(proba, dtype=float)))


def evaluate_hgb_combo(
    features,
    target,
    *,
    include_baseline_feature: bool,
    n_splits: int,
    gap: int,
    max_leaf_nodes: int,
    learning_rate: float,
    l2_regularization: float,
) -> dict[str, Any]:
    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    train_cols = list(features.columns) if include_baseline_feature else [
        col for col in features.columns if col != "prob_up_h20"
    ]
    baseline_probs: list[float] = []
    baseline_truth: list[int] = []
    model_probs: list[float] = []
    model_truth: list[int] = []
    fold_positive_rates: list[float] = []

    for train_idx, test_idx in split.split(features):
        x_train = features.iloc[train_idx]
        y_train = target.iloc[train_idx]
        x_test = features.iloc[test_idx]
        y_test = target.iloc[test_idx]
        baseline = x_test["prob_up_h20"].clip(0.0, 1.0).to_numpy(dtype=float)
        baseline_probs.extend(baseline.tolist())
        baseline_truth.extend(y_test.astype(int).tolist())
        fold_positive_rates.append(float(y_test.mean()))

        model = HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=learning_rate,
            max_leaf_nodes=max_leaf_nodes,
            l2_regularization=l2_regularization,
            random_state=42,
        )
        model.fit(x_train[train_cols], y_train)
        proba = model.predict_proba(x_test[train_cols])[:, 1]
        model_probs.extend(proba.tolist())
        model_truth.extend(y_test.astype(int).tolist())

    baseline_auc = _auc_or_none(baseline_truth, baseline_probs)
    baseline_brier = _brier_or_none(baseline_truth, baseline_probs)
    model_auc = _auc_or_none(model_truth, model_probs)
    model_brier = _brier_or_none(model_truth, model_probs)
    return {
        "baseline_auc": baseline_auc,
        "baseline_brier": baseline_brier,
        "model_auc": model_auc,
        "model_brier": model_brier,
        "auc_delta_vs_baseline": None if model_auc is None or baseline_auc is None else float(model_auc - baseline_auc),
        "brier_delta_vs_baseline": None if model_brier is None or baseline_brier is None else float(model_brier - baseline_brier),
        "fold_positive_rates": fold_positive_rates,
    }


def run_sweep(
    *,
    panel_path: Path,
    db_path: Path,
    start: str,
    end: str,
    lookbacks: list[int],
    feature_sets: list[str],
    include_baseline_options: list[bool],
    n_splits: int,
    gap: int,
    fast: bool = False,
) -> dict[str, Any]:
    panel = load_panel(panel_path)
    close_prices = load_close_prices(db_path, list(TICKERS), start, end)
    ohlcv = load_ohlcv_panel(db_path, list(TICKERS), start, end)
    if fast:
        hgb_grid = [
            {"max_leaf_nodes": 7, "learning_rate": 0.02, "l2_regularization": 0.20},
            {"max_leaf_nodes": 15, "learning_rate": 0.035, "l2_regularization": 0.08},
            {"max_leaf_nodes": 31, "learning_rate": 0.05, "l2_regularization": 0.02},
        ]
    else:
        hgb_grid = [
            {"max_leaf_nodes": leaf, "learning_rate": lr, "l2_regularization": l2}
            for leaf in (7, 15, 31)
            for lr in (0.02, 0.035, 0.05)
            for l2 in (0.02, 0.08, 0.20)
        ]

    rows: list[dict[str, Any]] = []
    for lookback in lookbacks:
        for feature_set in feature_sets:
            if feature_set == "close":
                features, target = build_relative_window_features(panel, close_prices, lookback=lookback, tickers=list(TICKERS))
            elif feature_set == "ohlcv":
                features, target = build_ohlcv_relative_window_features(panel, ohlcv, lookback=lookback, tickers=list(TICKERS))
            else:
                raise ValueError(f"Unsupported feature_set: {feature_set}")
            for include_baseline in include_baseline_options:
                for params in hgb_grid:
                    metrics = evaluate_hgb_combo(
                        features,
                        target,
                        include_baseline_feature=include_baseline,
                        n_splits=n_splits,
                        gap=gap,
                        **params,
                    )
                    rows.append(
                        {
                            "lookback": lookback,
                            "feature_set": feature_set,
                            "include_baseline_feature": include_baseline,
                            "feature_rows": int(len(features)),
                            "feature_count": int(features.shape[1]),
                            **params,
                            **metrics,
                        }
                    )

    ranked = sorted(
        rows,
        key=lambda row: (
            row["auc_delta_vs_baseline"] if row["auc_delta_vs_baseline"] is not None else -999.0,
            -(row["model_brier"] if row["model_brier"] is not None else 999.0),
        ),
        reverse=True,
    )
    calibration_ranked = sorted(
        rows,
        key=lambda row: (
            row["brier_delta_vs_baseline"] if row["brier_delta_vs_baseline"] is not None else 999.0,
            row["model_auc"] if row["model_auc"] is not None else -999.0,
        ),
    )
    best_auc = ranked[0] if ranked else None
    best_brier = calibration_ranked[0] if calibration_ranked else None
    return {
        "schema_version": 1,
        "report_type": "stock_rnn_relative_window_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "panel": str(panel_path),
            "db_path": str(db_path),
            "start": start,
            "end": end,
            "lookbacks": lookbacks,
            "feature_sets": feature_sets,
            "include_baseline_options": include_baseline_options,
            "n_splits": n_splits,
            "gap": gap,
            "combo_count": len(rows),
            "fast": bool(fast),
        },
        "best_auc_combo": best_auc,
        "best_brier_combo": best_brier,
        "top_auc_combos": ranked[:10],
        "top_brier_combos": calibration_ranked[:10],
        "promotion_decision": (
            "candidate_for_deeper_ablation"
            if best_auc and best_auc.get("auc_delta_vs_baseline") is not None and best_auc["auc_delta_vs_baseline"] >= -0.03
            else "research_only"
        ),
        "all_results": rows,
    }


def _parse_int_list(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_feature_sets(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    allowed = {"close", "ohlcv"}
    bad = [value for value in values if value not in allowed]
    if bad:
        raise ValueError(f"Unsupported feature sets: {bad}")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--lookbacks", default="10,20,30,45,60")
    parser.add_argument("--feature-sets", default="close,ohlcv")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=5)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("sweep_stock_rnn_relative_window_shadow")
    try:
        report = run_sweep(
            panel_path=Path(args.panel),
            db_path=Path(args.db),
            start=args.start,
            end=args.end,
            lookbacks=_parse_int_list(args.lookbacks),
            feature_sets=_parse_feature_sets(args.feature_sets),
            include_baseline_options=[False, True],
            n_splits=args.n_splits,
            gap=args.gap,
            fast=args.fast,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"stock-rnn relative-window sweep: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
