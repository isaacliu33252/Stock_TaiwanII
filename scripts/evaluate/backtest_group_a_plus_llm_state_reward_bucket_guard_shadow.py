#!/usr/bin/env python3
"""Bucket guard shadow for frozen GroupA+ GIFT reward tilt.

This no-model OOS check suppresses active overweight only in buckets that show
lagged bucket-specific stress. It is a shadow diagnostic and never emits live
target weights, actions, PPO training instructions, or rebalance decisions.
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (  # noqa: E402
    DEFAULT_EXCLUDED_TICKERS,
    DEFAULT_OUTPUT as DEFAULT_BASELINE,
    _aggregate_folds,
    _finite_float,
    _load_panel,
    _metrics,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import (  # noqa: E402
    BOND_BUCKET,
    HIGH_DIVIDEND_BUCKET,
    _apply_bucket_cap,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_bucket_guard_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_bucket_guard_shadow_backtest/history"
BUCKETS = {
    "high_dividend": HIGH_DIVIDEND_BUCKET,
    "bond": BOND_BUCKET,
}


def _normalize(weights: pd.Series) -> pd.Series:
    clean = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(clean.sum())
    if total <= 0:
        return pd.Series(1.0 / len(clean), index=clean.index, dtype=float)
    return clean / total


def _bucket_stress_frame(panel: pd.DataFrame, tickers: list[str], *, lookback: int = 5) -> pd.DataFrame:
    present = [ticker for ticker in tickers if ticker in set(panel["ticker"])]
    if not present:
        return pd.DataFrame()
    bucket = panel[panel["ticker"].isin(present)].copy()
    wide_close = bucket.pivot(index="date", columns="ticker", values="close").sort_index().reindex(columns=present)
    close_5d_return = wide_close / wide_close.shift(lookback) - 1.0
    vol = bucket.pivot(index="date", columns="ticker", values="realized_volatility").sort_index().reindex(columns=present)
    drawdown = bucket.pivot(index="date", columns="ticker", values="drawdown_depth").sort_index().reindex(columns=present)
    out = pd.DataFrame(index=wide_close.index)
    out["bucket_return_5d"] = close_5d_return.mean(axis=1)
    out["bucket_realized_volatility"] = vol.apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["bucket_drawdown_depth"] = drawdown.apply(pd.to_numeric, errors="coerce").mean(axis=1)
    return out.sort_index()


def _bucket_thresholds(
    panel: pd.DataFrame,
    *,
    train_start: str,
    train_end: str,
    bucket_return_quantile: float,
    bucket_vol_quantile: float,
    bucket_drawdown_quantile: float,
) -> dict[str, dict[str, float]]:
    thresholds: dict[str, dict[str, float]] = {}
    for name, tickers in BUCKETS.items():
        frame = _bucket_stress_frame(panel, tickers).loc[train_start:train_end]
        if frame.empty:
            continue
        thresholds[name] = {
            "bucket_return_5d_max": float(frame["bucket_return_5d"].quantile(bucket_return_quantile)),
            "bucket_realized_volatility_min": float(frame["bucket_realized_volatility"].quantile(bucket_vol_quantile)),
            "bucket_drawdown_depth_min": float(frame["bucket_drawdown_depth"].quantile(bucket_drawdown_quantile)),
        }
    return thresholds


def _stressed_buckets(
    panel: pd.DataFrame,
    dt: pd.Timestamp,
    *,
    thresholds: dict[str, dict[str, float]],
    lagged_frames: dict[str, pd.DataFrame],
) -> list[str]:
    stressed: list[str] = []
    for name, frame in lagged_frames.items():
        if name not in thresholds or dt not in frame.index:
            continue
        row = frame.loc[dt]
        threshold = thresholds[name]
        if bool(
            pd.notna(row["bucket_return_5d"])
            and pd.notna(row["bucket_realized_volatility"])
            and pd.notna(row["bucket_drawdown_depth"])
            and (
                float(row["bucket_return_5d"]) <= threshold["bucket_return_5d_max"]
                or float(row["bucket_realized_volatility"]) >= threshold["bucket_realized_volatility_min"]
                or float(row["bucket_drawdown_depth"]) >= threshold["bucket_drawdown_depth_min"]
            )
        ):
            stressed.append(name)
    return stressed


def _apply_bucket_guard(weight: pd.Series, stressed: list[str]) -> pd.Series:
    guarded = _normalize(weight)
    equal = pd.Series(1.0 / len(guarded), index=guarded.index, dtype=float)
    for name in stressed:
        present = [ticker for ticker in BUCKETS[name] if ticker in guarded.index]
        if not present:
            continue
        equal_bucket_weight = float(equal[present].sum())
        if float(guarded[present].sum()) > equal_bucket_weight:
            guarded = _apply_bucket_cap(guarded, present, equal_bucket_weight)
    return _normalize(guarded)


def _fold_bucket_guard_backtest(
    panel: pd.DataFrame,
    fold: dict[str, Any],
    *,
    eligible_tickers: list[str],
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    cost_bps: float,
    bucket_return_quantile: float,
    bucket_vol_quantile: float,
    bucket_drawdown_quantile: float,
) -> dict[str, Any]:
    train = panel[
        (panel["date"] >= pd.Timestamp(fold["train_start"]))
        & (panel["date"] <= pd.Timestamp(fold["train_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ]
    test = panel[
        (panel["date"] >= pd.Timestamp(fold["test_start"]))
        & (panel["date"] <= pd.Timestamp(fold["test_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ]
    train_reward = pd.to_numeric(train["reward_proxy"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    thresholds = _bucket_thresholds(
        panel,
        train_start=fold["train_start"],
        train_end=fold["train_end"],
        bucket_return_quantile=bucket_return_quantile,
        bucket_vol_quantile=bucket_vol_quantile,
        bucket_drawdown_quantile=bucket_drawdown_quantile,
    )
    if train_reward.empty or test.empty or not thresholds:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_test_or_bucket_thresholds"}

    low_threshold = float(train_reward.quantile(low_quantile))
    high_threshold = float(train_reward.quantile(high_quantile))
    wide_returns = test.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers)
    wide_signal = (
        panel[panel["ticker"].isin(eligible_tickers)]
        .pivot(index="date", columns="ticker", values="reward_proxy")
        .sort_index()
        .shift(1)
        .reindex(wide_returns.index)
        .reindex(columns=eligible_tickers)
    )
    lagged_frames = {
        name: _bucket_stress_frame(panel, tickers).shift(1).reindex(wide_returns.index)
        for name, tickers in BUCKETS.items()
    }
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_weight = equal_weight.copy()
    guarded_returns: list[float] = []
    baseline_returns: list[float] = []
    turnovers: list[float] = []
    guard_counts = {name: 0 for name in BUCKETS}
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in wide_returns.iterrows():
        usable_returns = pd.to_numeric(return_row, errors="coerce").fillna(0.0)
        raw_weight = _weights_from_signal(
            wide_signal.loc[dt],
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        stressed = _stressed_buckets(panel, dt, thresholds=thresholds, lagged_frames=lagged_frames)
        for name in stressed:
            guard_counts[name] += 1
        guarded = _apply_bucket_guard(raw_weight, stressed)
        turnover = float((guarded - previous_weight).abs().sum())
        guarded_returns.append(float((guarded * usable_returns).sum() - turnover * cost_rate))
        baseline_returns.append(float((equal_weight * usable_returns).sum()))
        turnovers.append(turnover)
        previous_weight = guarded

    guarded_series = pd.Series(guarded_returns, index=wide_returns.index, dtype=float)
    baseline_series = pd.Series(baseline_returns, index=wide_returns.index, dtype=float)
    turnover_series = pd.Series(turnovers, index=wide_returns.index, dtype=float)
    guarded_metrics = _metrics(guarded_series, turnover=turnover_series)
    baseline_metrics = _metrics(baseline_series)
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "test_days": int(len(guarded_series)),
        "bucket_guard_days": {name: int(count) for name, count in guard_counts.items()},
        "bucket_guard_rates": {
            name: _finite_float(count / len(guarded_series)) if len(guarded_series) else None
            for name, count in guard_counts.items()
        },
        "thresholds": {
            name: {key: _finite_float(value) for key, value in values.items()}
            for name, values in thresholds.items()
        },
        "bucket_guard": guarded_metrics,
        "equal_weight_baseline": baseline_metrics,
        "delta_vs_equal_weight": {
            "final_value": _finite_float((guarded_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((guarded_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((guarded_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    bucket_return_quantile: float = 0.15,
    bucket_vol_quantile: float = 0.85,
    bucket_drawdown_quantile: float = 0.85,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    baseline = _load_json(baseline_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not baseline:
        blockers.append("missing_baseline_shadow_backtest")
    elif baseline.get("status") != "available_for_manual_offline_review":
        blockers.append(f"baseline_shadow_backtest_not_available:{baseline.get('status')}")
    expected_hash = baseline.get("inputs", {}).get("panel_sha256") if baseline else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("frozen_panel_hash_mismatch")

    inputs = baseline.get("inputs", {}) if baseline else {}
    eligible_tickers = list(inputs.get("eligible_tickers") or [])
    if len(eligible_tickers) < 2:
        blockers.append("too_few_eligible_tickers")
    if {"00631L.TW", "00632R.TW"} & set(eligible_tickers):
        blockers.append("leveraged_or_inverse_ticker_not_excluded")
    folds = baseline.get("fold_results") if isinstance(baseline.get("fold_results"), list) else []
    if not folds:
        blockers.append("missing_baseline_folds")

    fold_rows = [
        _fold_bucket_guard_backtest(
            panel,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=float(inputs.get("low_quantile", 0.30)),
            high_quantile=float(inputs.get("high_quantile", 0.70)),
            low_score=float(inputs.get("low_score", 0.50)),
            mid_score=float(inputs.get("mid_score", 1.00)),
            high_score=float(inputs.get("high_score", 1.50)),
            cost_bps=float(inputs.get("cost_bps", 5.0)),
            bucket_return_quantile=bucket_return_quantile,
            bucket_vol_quantile=bucket_vol_quantile,
            bucket_drawdown_quantile=bucket_drawdown_quantile,
        )
        for fold in folds
    ] if not blockers else []
    for row in fold_rows:
        if row.get("status") != "available_for_manual_offline_review":
            blockers.append(f"fold_not_available:{row.get('fold')}:{row.get('blocking_reason')}")

    guarded_aggregate = _aggregate_folds(fold_rows)
    baseline_aggregate = baseline.get("summary", {}) if baseline else {}
    if guarded_aggregate["available_fold_count"]:
        if guarded_aggregate["positive_final_value_folds"] < min_positive_final_folds:
            warnings.append(
                f"positive_final_value_folds_below_threshold:{guarded_aggregate['positive_final_value_folds']}<{min_positive_final_folds}"
            )
        if guarded_aggregate["positive_sharpe_folds"] < min_positive_sharpe_folds:
            warnings.append(
                f"positive_sharpe_folds_below_threshold:{guarded_aggregate['positive_sharpe_folds']}<{min_positive_sharpe_folds}"
            )
        if guarded_aggregate["non_worse_drawdown_folds"] < min_non_worse_drawdown_folds:
            warnings.append(
                "non_worse_drawdown_folds_below_threshold:"
                f"{guarded_aggregate['non_worse_drawdown_folds']}<{min_non_worse_drawdown_folds}"
            )

    pass_gate = bool(
        not blockers
        and guarded_aggregate["positive_final_value_folds"] >= min_positive_final_folds
        and guarded_aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds
        and guarded_aggregate["non_worse_drawdown_folds"] >= min_non_worse_drawdown_folds
    )
    guard_rates = {
        name: _finite_float(np.mean([row["bucket_guard_rates"][name] for row in fold_rows if row.get("bucket_guard_rates")]))
        if fold_rows
        else None
        for name in BUCKETS
    }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_bucket_guard_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "bucket_guard_shadow_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "bucket_return_quantile": bucket_return_quantile,
            "bucket_vol_quantile": bucket_vol_quantile,
            "bucket_drawdown_quantile": bucket_drawdown_quantile,
            "buckets": BUCKETS,
        },
        "summary": {
            "baseline_positive_final_value_folds": baseline_aggregate.get("positive_final_value_folds"),
            "baseline_positive_sharpe_folds": baseline_aggregate.get("positive_sharpe_folds"),
            "baseline_non_worse_drawdown_folds": baseline_aggregate.get("non_worse_drawdown_folds"),
            "bucket_guard": guarded_aggregate,
            "delta_bucket_guard_minus_baseline": {
                "positive_final_value_folds": (
                    guarded_aggregate["positive_final_value_folds"]
                    - int(baseline_aggregate.get("positive_final_value_folds", 0) or 0)
                ),
                "positive_sharpe_folds": (
                    guarded_aggregate["positive_sharpe_folds"]
                    - int(baseline_aggregate.get("positive_sharpe_folds", 0) or 0)
                ),
                "non_worse_drawdown_folds": (
                    guarded_aggregate["non_worse_drawdown_folds"]
                    - int(baseline_aggregate.get("non_worse_drawdown_folds", 0) or 0)
                ),
            },
            "mean_bucket_guard_rates": guard_rates,
            "pass_bucket_guard_gate": pass_gate,
        },
        "fold_results": fold_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The bucket guard suppresses active overweight only for lagged stressed high-dividend or bond buckets.",
            "Bucket thresholds are computed per fold from the training window to avoid OOS leakage.",
            "This report is a shadow diagnostic only and does not authorize live weights.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "bucket_guard_ready_for_review": not blockers,
            "bucket_guard_passed_shadow_gate": pass_gate,
            "next_shadow_model_design_allowed": pass_gate,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_bucket_guard_shadow_backtest_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--bucket-return-quantile", type=float, default=0.15)
    parser.add_argument("--bucket-vol-quantile", type=float, default=0.85)
    parser.add_argument("--bucket-drawdown-quantile", type=float, default=0.85)
    parser.add_argument("--min-positive-final-folds", type=int, default=4)
    parser.add_argument("--min-positive-sharpe-folds", type=int, default=4)
    parser.add_argument("--min-non-worse-drawdown-folds", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        bucket_return_quantile=args.bucket_return_quantile,
        bucket_vol_quantile=args.bucket_vol_quantile,
        bucket_drawdown_quantile=args.bucket_drawdown_quantile,
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        min_non_worse_drawdown_folds=args.min_non_worse_drawdown_folds,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward bucket guard shadow backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "bucket_guard": review["summary"]["bucket_guard"],
                "mean_bucket_guard_rates": review["summary"]["mean_bucket_guard_rates"],
                "bucket_guard_passed_shadow_gate": review["decision"]["bucket_guard_passed_shadow_gate"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
