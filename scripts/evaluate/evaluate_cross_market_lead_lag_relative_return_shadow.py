#!/usr/bin/env python3
"""Sparse US->Taiwan lead-lag graph, narrowed to 1-day relative-return targets.

User-proposed research line, 2026-08-09. The bulk of this mechanism already
exists (`docs/cross_market_graph_shadow_20260715.md`,
`scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py`): same
source nodes (TSM/SOXX/QQQ/TWD=X/NVDA/AMD/AVGO/ASML/^TNX), same target
universe (2330/0050/00631L/2454/2317/2308/2382), same strict source-close-
before-target-date timing, same rolling-window t-stat edge-stability
selection (`select_directed_edges`, reused unmodified from that module).
That prior work found the existing 5-day-horizon binary NO_ADD/REENTER
targets: NO_ADD weakly-but-repeatably predictable (AUC 0.532), REENTER
unusable (AUC 0.485).

This script tests two DIFFERENT, narrower targets the prior work never
built, both continuous and 1-day horizon (not 5-day binary classification):
- `rel_00631L_vs_0050`: 00631L's 1-day forward return minus 0050's 1-day
  forward return.
- `rel_2330_vs_0050_ex_tsmc`: TSMC's 1-day forward return minus the
  ex-TSMC-proxy's 1-day forward return (reuses
  group_a_plus/integrations/tsmc_concentration_divergence.py's formula),
  i.e. does US information lead a divergence between TSMC and the rest of
  the 0050 basket specifically, not just 0050's overall move.

Research-only. Does not change any live weight, guard, or execution plan.
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
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.tsmc_concentration_divergence import TSMC_0050_WEIGHT_ASSUMPTION
from scripts.evaluate.evaluate_cross_market_directed_graph_shadow import (
    DEFAULT_SOURCE_TICKERS,
    DEFAULT_TARGET_TICKERS,
    add_composite_source_features,
    align_source_returns_to_taiwan_dates,
    load_source_closes,
    load_target_closes,
    select_directed_edges,
)
from tw_output_standard import OutputStandardizer, write_standard_output

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "cross_market_lead_lag_relative_return_shadow_latest.json"
RELATIVE_TARGET_COLS = ("target_rel_00631l_vs_0050_ret1d_fwd", "target_rel_2330_vs_0050_ex_tsmc_ret1d_fwd")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def build_relative_return_targets(
    target_close: pd.DataFrame, *, tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION
) -> pd.DataFrame:
    """1-day forward relative-return targets (continuous, no lookahead).

    Column names deliberately match `target_*_ret1d_fwd` so they can be fed
    directly into `select_directed_edges()` (reused unmodified) without any
    change to that function.
    """

    out = pd.DataFrame(index=target_close.index)
    if "00631L.TW" in target_close and "0050.TW" in target_close:
        fwd_631l = target_close["00631L.TW"].shift(-1) / target_close["00631L.TW"] - 1.0
        fwd_0050 = target_close["0050.TW"].shift(-1) / target_close["0050.TW"] - 1.0
        out["target_rel_00631l_vs_0050_ret1d_fwd"] = fwd_631l - fwd_0050
    if "2330.TW" in target_close and "0050.TW" in target_close and tsmc_weight < 1.0:
        fwd_2330 = target_close["2330.TW"].shift(-1) / target_close["2330.TW"] - 1.0
        fwd_0050 = target_close["0050.TW"].shift(-1) / target_close["0050.TW"] - 1.0
        fwd_ex_tsmc = (fwd_0050 - tsmc_weight * fwd_2330) / (1.0 - tsmc_weight)
        out["target_rel_2330_vs_0050_ex_tsmc_ret1d_fwd"] = fwd_2330 - fwd_ex_tsmc
    return out


def _directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    nonzero = y_true != 0.0
    if int(nonzero.sum()) == 0:
        return None
    return float((np.sign(y_true[nonzero]) == np.sign(y_pred[nonzero])).mean())


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    if len(y_true) < 2:
        return None
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    if ss_tot <= 0.0:
        return None
    return 1.0 - ss_res / ss_tot


def walk_forward_relative_return_model(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    target_col: str,
    *,
    edge_window: int,
    tstat_threshold: float,
    min_windows: int,
    stability_threshold: float,
    min_train_days: int,
    retrain_step: int,
) -> dict[str, Any]:
    """Regression analogue of evaluate_cross_market_directed_graph_shadow.py's
    walk_forward_graph_action_models(), for one continuous relative-return
    target instead of the REENTER/NO_ADD binary labels.
    """

    edge_scan_outcomes = outcomes[[target_col]]
    data = features.join(outcomes[[target_col]], how="inner").replace([np.inf, -np.inf], np.nan).dropna()
    feature_cols = list(features.columns)
    if len(data) <= min_train_days + retrain_step:
        return {"status": "skipped", "reason": "insufficient_rows", "rows": int(len(data)), "target": target_col}

    predictions: list[float] = []
    truth: list[float] = []
    dates: list[str] = []
    selected_history: list[dict[str, Any]] = []
    latest_selected_features: list[str] = []

    for block_start in range(min_train_days, len(data), retrain_step):
        block_end = min(block_start + retrain_step, len(data))
        train = data.iloc[:block_start]
        test = data.iloc[block_start:block_end]
        train_features = train[feature_cols].fillna(0.0)
        edges, selected = select_directed_edges(
            train_features,
            edge_scan_outcomes.loc[train.index],
            window=min(edge_window, max(40, len(train_features) - 1)),
            tstat_threshold=tstat_threshold,
            min_windows=min_windows,
            stability_threshold=stability_threshold,
        )
        selected_features = [item["feature"] for item in selected]
        latest_selected_features = selected_features
        selected_history.append(
            {
                "train_end": str(train.index[-1].date()),
                "test_start": str(test.index[0].date()),
                "test_end": str(test.index[-1].date()),
                "selected_features": selected_features,
                "stable_edge_count": int(edges["stable"].sum()) if not edges.empty else 0,
            }
        )
        for _dt, test_row in test.iterrows():
            dates.append(str(pd.Timestamp(_dt).date()))
            truth.append(float(test_row[target_col]))

        if not selected_features:
            mean_target = float(train[target_col].mean())
            predictions.extend([mean_target] * len(test))
            continue

        x_train = train[selected_features].fillna(0.0)
        y_train = train[target_col].astype(float)
        x_test = test[selected_features].fillna(0.0)
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0, random_state=42))
        model.fit(x_train, y_train)
        predictions.extend(model.predict(x_test).astype(float).tolist())

    y_arr = np.asarray(truth, dtype=float)
    p_arr = np.asarray(predictions, dtype=float)
    correlation = float(np.corrcoef(y_arr, p_arr)[0, 1]) if len(y_arr) >= 2 and np.std(p_arr) > 0 else None
    feature_counts: dict[str, int] = {}
    for item in selected_history:
        for feature in item["selected_features"]:
            feature_counts[feature] = feature_counts.get(feature, 0) + 1

    return {
        "status": "ok",
        "target": target_col,
        "rows": int(len(data)),
        "oos_rows": int(len(dates)),
        "retrain_step": int(retrain_step),
        "min_train_days": int(min_train_days),
        "latest_selected_features": latest_selected_features,
        "most_frequent_selected_features": [
            {"feature": feature, "count": count}
            for feature, count in sorted(feature_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        "selection_history_tail": selected_history[-10:],
        "metrics": {
            "r2_oos": _r2(y_arr, p_arr),
            "correlation_oos": correlation,
            "directional_accuracy_oos": _directional_accuracy(y_arr, p_arr),
            "mean_abs_target": float(np.mean(np.abs(y_arr))) if len(y_arr) else None,
            "mean_abs_prediction": float(np.mean(np.abs(p_arr))) if len(p_arr) else None,
            "target_std": float(np.std(y_arr)) if len(y_arr) else None,
        },
        "metrics_by_realized_side": _metrics_by_realized_side(dates, y_arr, p_arr),
        "policy": "shadow_only_no_weight_change",
    }


def _metrics_by_realized_side(dates: list[str], y_arr: np.ndarray, p_arr: np.ndarray) -> dict[str, Any]:
    """Post-hoc conditional breakdown: does prediction quality differ on days
    the FIRST asset in the target name actually won vs days the SECOND did?

    Uses realized truth only to stratify evaluation after the fact -- never
    to select features or fit the model (that stays walk-forward/past-only
    as in walk_forward_relative_return_model). This is the same category of
    technique as the existing cross-market graph module's
    _metrics_by_condition(), applied here to answer the user's asymmetry
    question: is next-day lead-lag predictability different depending on
    which side of the pair is actually outperforming?
    """

    out: dict[str, Any] = {}
    for label, mask in (
        ("first_asset_wins", y_arr > 0.0),
        ("second_asset_wins", y_arr < 0.0),
    ):
        if int(mask.sum()) < 2:
            out[label] = {"rows": int(mask.sum()), "status": "insufficient_rows"}
            continue
        y_sub = y_arr[mask]
        p_sub = p_arr[mask]
        correlation = float(np.corrcoef(y_sub, p_sub)[0, 1]) if np.std(p_sub) > 0 else None
        out[label] = {
            "rows": int(mask.sum()),
            "r2_oos": _r2(y_sub, p_sub),
            "correlation_oos": correlation,
            "directional_accuracy_oos": _directional_accuracy(y_sub, p_sub),
            "mean_abs_target": float(np.mean(np.abs(y_sub))),
        }
    del dates
    return out


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    source_tickers: tuple[str, ...],
    target_tickers: tuple[str, ...],
    edge_window: int,
    tstat_threshold: float,
    min_windows: int,
    stability_threshold: float,
    use_composite_features: bool,
    min_train_days: int,
    retrain_step: int,
) -> dict[str, Any]:
    source_close = load_source_closes(db_path, source_tickers, start, end)
    target_close = load_target_closes(db_path, target_tickers, start, end)
    if source_close.empty or target_close.empty:
        raise ValueError("Missing source or target close data")
    target_close = target_close.dropna(how="all")
    features = align_source_returns_to_taiwan_dates(source_close, target_close.index)
    if use_composite_features:
        features = add_composite_source_features(features)
    outcomes = build_relative_return_targets(target_close)

    valid_features = features.dropna(axis=1, thresh=max(edge_window, 40))
    valid = valid_features.join(outcomes, how="inner").dropna(subset=list(RELATIVE_TARGET_COLS), how="all")
    features = valid[valid_features.columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    outcomes = valid[list(RELATIVE_TARGET_COLS)]

    results = {}
    for target_col in RELATIVE_TARGET_COLS:
        if target_col not in outcomes.columns:
            continue
        target_data = outcomes[[target_col]].dropna()
        aligned_features = features.loc[target_data.index]
        results[target_col] = walk_forward_relative_return_model(
            aligned_features,
            target_data,
            target_col,
            edge_window=edge_window,
            tstat_threshold=tstat_threshold,
            min_windows=min_windows,
            stability_threshold=stability_threshold,
            min_train_days=min_train_days,
            retrain_step=retrain_step,
        )

    return {
        "schema_version": 1,
        "report_type": "cross_market_lead_lag_relative_return_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "db_path": str(db_path),
            "start": start,
            "end": end,
            "source_tickers_requested": list(source_tickers),
            "source_tickers_available": list(source_close.columns),
            "target_tickers_requested": list(target_tickers),
            "timing": "source close date must be strictly earlier than Taiwan target date",
            "edge_window": int(edge_window),
            "tstat_threshold": float(tstat_threshold),
            "min_windows": int(min_windows),
            "stability_threshold": float(stability_threshold),
            "min_train_days": int(min_train_days),
            "retrain_step": int(retrain_step),
        },
        "targets": results,
        "method_note": (
            "Reuses select_directed_edges() from "
            "evaluate_cross_market_directed_graph_shadow.py unmodified. Only "
            "the target definition changed: 1-day continuous relative-return "
            "regression instead of 5-day binary REENTER/NO_ADD classification."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2019-01-02")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--source-tickers", default=",".join(DEFAULT_SOURCE_TICKERS))
    parser.add_argument("--target-tickers", default=",".join(DEFAULT_TARGET_TICKERS))
    parser.add_argument("--edge-window", type=int, default=250)
    parser.add_argument("--tstat-threshold", type=float, default=2.0)
    parser.add_argument("--min-windows", type=int, default=3)
    parser.add_argument("--stability-threshold", type=float, default=0.20)
    parser.add_argument("--no-composite-features", action="store_true")
    parser.add_argument("--min-train-days", type=int, default=504)
    parser.add_argument("--retrain-step", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_cross_market_lead_lag_relative_return_shadow")
    try:
        report = build_report(
            db_path=_resolve(args.db_path),
            start=args.start,
            end=args.end,
            source_tickers=tuple(item.strip() for item in args.source_tickers.split(",") if item.strip()),
            target_tickers=tuple(item.strip() for item in args.target_tickers.split(",") if item.strip()),
            edge_window=args.edge_window,
            tstat_threshold=float(args.tstat_threshold),
            min_windows=int(args.min_windows),
            stability_threshold=float(args.stability_threshold),
            use_composite_features=not args.no_composite_features,
            min_train_days=int(args.min_train_days),
            retrain_step=int(args.retrain_step),
        )
        payload = std.success(report, run_id=datetime.now().strftime("%Y%m%d_%H%M%S"))
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Cross-market lead-lag relative-return shadow: {_resolve(args.output)}")
    if payload.get("success"):
        for target_col, result in payload["data"]["targets"].items():
            print(target_col, json.dumps(result.get("metrics"), ensure_ascii=False))


if __name__ == "__main__":
    main()
