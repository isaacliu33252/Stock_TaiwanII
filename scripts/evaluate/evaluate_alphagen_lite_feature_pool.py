#!/usr/bin/env python3
"""Research-only test: can alphagen-lite's greedy mutual-IC pool selection
replace manual XGB feature-audit pruning?

Context: the 2026-06-30 XGBoost feature audit (scripts/misc/xgb_feature_audit.py)
flagged 7 features as "consensus D" (bottom-grade in both 00631L and 00632R):
n225_x_twii_ret, us_qqq_ret, twii_ret, vix_change, vix_change_x_return1d,
volume_ratio_5, above_ma20. Pruning them is currently a manual quarterly step.

This script feeds the FULL 00631L feature set (raw, not mined/expanded) into
the same greedy mutual-IC pool builder used in evaluate_alphagen_lite_shadow.py
and asks two questions, per TimeSeriesSplit fold:

1. Does the automatic pool selection avoid the 7 consensus-D features on its
   own (cross-validating the manual audit), or does it still pick some of them?
2. Does pre-pruning those 7 before running the pool builder change the
   resulting out-of-sample IC (i.e. is the manual pruning step redundant once
   the automated diversity+IC filter runs, or does it still add value)?

Does not affect live allocation.
"""

from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output

CONSENSUS_D_FEATURES = (
    "n225_x_twii_ret",
    "us_qqq_ret",
    "twii_ret",
    "vix_change",
    "vix_change_x_return1d",
    "volume_ratio_5",
    "above_ma20",
)

DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "alphagen_lite_feature_pool_latest_20260701.json"


def build_pruning_recommendation(
    folds: list[dict[str, Any]],
    consensus_d: list[str],
) -> dict[str, Any]:
    """Summarize how AlphaGen-lite should influence feature governance.

    The active A21.18 allocation must not consume this result directly. This
    report is intended for the next NCF retraining / feature-audit cycle.
    """
    selected_counts = {feature: 0 for feature in consensus_d}
    selected_when_helpful = {feature: 0 for feature in consensus_d}
    selected_when_harmful = {feature: 0 for feature in consensus_d}

    for fold in folds:
        selected = set(fold.get("consensus_d_features_selected_by_full_pool") or [])
        full_ic = fold.get("full_pool_test_ic")
        pruned_ic = fold.get("pre_pruned_pool_test_ic")
        for feature in selected:
            if feature not in selected_counts:
                continue
            selected_counts[feature] += 1
            if full_ic is None or pruned_ic is None:
                continue
            if full_ic > pruned_ic:
                selected_when_helpful[feature] += 1
            elif full_ic < pruned_ic:
                selected_when_harmful[feature] += 1

    prune_candidates: list[str] = []
    monitor_features: list[str] = []
    keep_features: list[str] = []
    feature_actions: dict[str, dict[str, Any]] = {}

    for feature in consensus_d:
        count = selected_counts[feature]
        helpful = selected_when_helpful[feature]
        harmful = selected_when_harmful[feature]
        if count == 0:
            action = "prune_candidate"
            rationale = "Never selected by the mutual-IC pool across folds."
            prune_candidates.append(feature)
        elif helpful > 0:
            action = "monitor"
            rationale = (
                "Selected in at least one fold where retaining the full feature "
                "pool improved out-of-sample IC versus pre-pruning."
            )
            monitor_features.append(feature)
        elif harmful > helpful:
            action = "prune_candidate"
            rationale = "Selected occasionally, but selection did not improve held-out IC."
            prune_candidates.append(feature)
        else:
            action = "keep_for_retest"
            rationale = "Selection evidence is mixed; retest after the next training refresh."
            keep_features.append(feature)

        feature_actions[feature] = {
            "action": action,
            "selected_folds": count,
            "selected_when_full_pool_helped": helpful,
            "selected_when_pre_pruning_helped": harmful,
            "rationale": rationale,
        }

    return {
        "status": "research_only",
        "active_allocation_impact": "none",
        "integration_target": "next_ncf_feature_governance_cycle",
        "prune_candidates": prune_candidates,
        "monitor_features": monitor_features,
        "keep_for_retest": keep_features,
        "feature_actions": feature_actions,
        "policy": (
            "Use AlphaGen-lite as a second-opinion feature governance tool only. "
            "Do not route these recommendations into live A21.18 allocation logic "
            "without a separate walk-forward retraining and backtest."
        ),
    }


def _load_module(relative_path: str, name: str):
    path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_feature_matrix(
    ticker: str,
    horizon: int,
    train_start: str,
    train_end: str,
    db_path: Path,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    audit = _load_module("scripts/misc/xgb_feature_audit.py", "_alphagen_pool_xgb_audit")
    mod = audit._load_ncf_module(ticker)
    resolved_end = train_end
    if train_end.lower() == "latest":
        resolved_end = mod.resolve_end_date(db_path, f"{ticker}.TW", "latest")
    X, y_ret, _y_dir, feature_list = audit._build_feature_matrix(
        mod, ticker, train_start, resolved_end, db_path, horizon,
        use_external=True, use_fourier=True, use_global=True, use_tbrain=False,
    )
    return X[feature_list].astype(float), y_ret.astype(float), feature_list


def evaluate_pool_vs_manual_pruning(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    n_splits: int,
    gap: int,
    capacity: int,
    ic_lower_bound: float,
    mutual_ic_threshold: float,
) -> dict[str, Any]:
    pool_module = _load_module(
        "scripts/evaluate/evaluate_alphagen_lite_shadow.py", "_alphagen_pool_shadow"
    )
    consensus_d = [c for c in CONSENSUS_D_FEATURES if c in features.columns]
    pruned_columns = [c for c in features.columns if c not in consensus_d]

    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    folds: list[dict[str, Any]] = []
    full_ics: list[float] = []
    pruned_ics: list[float] = []

    for fold, (train_idx, test_idx) in enumerate(split.split(features), start=1):
        x_train, x_test = features.iloc[train_idx], features.iloc[test_idx]
        y_train, y_test = target.iloc[train_idx], target.iloc[test_idx]

        full_selected, full_weights, full_means, full_stds = pool_module.greedy_pool_select(
            x_train, y_train, capacity=capacity,
            ic_lower_bound=ic_lower_bound, mutual_ic_threshold=mutual_ic_threshold,
        )
        pruned_selected, pruned_weights, pruned_means, pruned_stds = pool_module.greedy_pool_select(
            x_train[pruned_columns], y_train, capacity=capacity,
            ic_lower_bound=ic_lower_bound, mutual_ic_threshold=mutual_ic_threshold,
        )

        full_ic = pruned_ic = None
        if full_selected:
            score = ((x_test[full_selected] - full_means) / full_stds * full_weights).sum(axis=1)
            full_ic = pool_module._ic(score, y_test)
        if pruned_selected:
            score = ((x_test[pruned_selected] - pruned_means) / pruned_stds * pruned_weights).sum(axis=1)
            pruned_ic = pool_module._ic(score, y_test)

        if full_ic is not None:
            full_ics.append(full_ic)
        if pruned_ic is not None:
            pruned_ics.append(pruned_ic)

        consensus_d_selected = [f for f in full_selected if f in consensus_d]
        folds.append({
            "fold": fold,
            "train_rows": int(len(x_train)),
            "test_rows": int(len(x_test)),
            "full_pool_size": len(full_selected),
            "full_pool_features": full_selected,
            "full_pool_test_ic": full_ic,
            "consensus_d_features_selected_by_full_pool": consensus_d_selected,
            "pre_pruned_pool_size": len(pruned_selected),
            "pre_pruned_pool_features": pruned_selected,
            "pre_pruned_pool_test_ic": pruned_ic,
        })

    full_mean = sum(full_ics) / len(full_ics) if full_ics else None
    pruned_mean = sum(pruned_ics) / len(pruned_ics) if pruned_ics else None
    total_d_selections = sum(len(f["consensus_d_features_selected_by_full_pool"]) for f in folds)

    return {
        "folds": folds,
        "aggregate": {
            "consensus_d_features_checked": consensus_d,
            "consensus_d_selections_across_folds": total_d_selections,
            "consensus_d_selection_rate": (
                total_d_selections / (len(folds) * len(consensus_d)) if consensus_d else None
            ),
            "full_candidate_pool_mean_test_ic": full_mean,
            "pre_pruned_candidate_pool_mean_test_ic": pruned_mean,
            "manual_pruning_ic_delta": (
                pruned_mean - full_mean if full_mean is not None and pruned_mean is not None else None
            ),
        },
        "pruning_recommendation": build_pruning_recommendation(folds, consensus_d),
    }


def build_report(
    *,
    ticker: str,
    horizon: int,
    train_start: str,
    train_end: str,
    db_path: Path,
    n_splits: int,
    gap: int,
    capacity: int,
    ic_lower_bound: float,
    mutual_ic_threshold: float,
) -> dict[str, Any]:
    features, target, feature_list = build_feature_matrix(ticker, horizon, train_start, train_end, db_path)
    evaluation = evaluate_pool_vs_manual_pruning(
        features, target,
        n_splits=n_splits, gap=gap, capacity=capacity,
        ic_lower_bound=ic_lower_bound, mutual_ic_threshold=mutual_ic_threshold,
    )
    return {
        "schema_version": 1,
        "report_type": "alphagen_lite_feature_pool_vs_manual_pruning",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "alphagen_source": "C:\\Users\\isaac\\Downloads\\alphagen-master\\alphagen-master",
            "audit_reference": "results/xgb_audit_00631l_20260630.json",
            "ticker": ticker,
            "horizon": horizon,
            "train_start": train_start,
            "train_end": train_end,
            "db_path": str(db_path),
            "total_feature_count": len(feature_list),
            "consensus_d_features": list(CONSENSUS_D_FEATURES),
            "pool_capacity": capacity,
            "ic_lower_bound": ic_lower_bound,
            "mutual_ic_threshold": mutual_ic_threshold,
        },
        "evaluation": evaluation,
        "method_note": (
            "Research-only test of whether alphagen-lite's greedy mutual-IC pool "
            "selection (from ALPHAGEN_IMPORT_REVIEW_20260701.md) can replace the "
            "manual quarterly XGB feature-audit pruning step. Runs the pool "
            "builder over the raw hand-crafted feature set (no formula mining) "
            "with and without the 7 known consensus-D features pre-removed. "
            "The output is intentionally limited to feature governance and has "
            "no direct active-allocation impact."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", choices=["00631L", "00632R"], default="00631L")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end", default="latest")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--gap", type=int, default=5)
    parser.add_argument("--capacity", type=int, default=12)
    parser.add_argument("--ic-lower-bound", type=float, default=0.03)
    parser.add_argument("--mutual-ic-threshold", type=float, default=0.7)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_alphagen_lite_feature_pool")
    try:
        report = build_report(
            ticker=args.ticker,
            horizon=args.horizon,
            train_start=args.train_start,
            train_end=args.train_end,
            db_path=Path(args.db),
            n_splits=args.n_splits,
            gap=args.gap,
            capacity=args.capacity,
            ic_lower_bound=args.ic_lower_bound,
            mutual_ic_threshold=args.mutual_ic_threshold,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"alphagen-lite feature pool vs manual pruning: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
