#!/usr/bin/env python3
"""Parameter sweep for v3 high-dividend active-pain reward redesign."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (  # noqa: E402
    DEFAULT_EXCLUDED_TICKERS,
    _aggregate_folds,
    _finite_float,
    _load_panel,
    _metrics,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_high_dividend_active_pain_offline_smoke import (  # noqa: E402
    DEFAULT_BASELINE,
    DEFAULT_DGR,
    DEFAULT_PANEL_OUTPUT,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import (  # noqa: E402
    HIGH_DIVIDEND_BUCKET,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _resolve  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _load_json  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_high_dividend_active_pain_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_param_sweep/history"


def _score(row: dict[str, Any]) -> tuple[int, int, int, float, float, float, bool]:
    return (
        int(row.get("non_worse_drawdown_folds", 0) or 0),
        int(row.get("positive_final_value_folds", 0) or 0),
        int(row.get("positive_sharpe_folds", 0) or 0),
        float(row.get("mean_delta_max_drawdown") or -999.0),
        float(row.get("mean_delta_sharpe_ratio") or -999.0),
        float(row.get("mean_delta_final_value") or -999.0),
        bool(row.get("event_probe_active_drag_improved")),
    )


def _validate_inputs(panel_path: Path, baseline_path: Path, dgr_path: Path) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    panel = _load_panel(panel_path)
    baseline = _load_json(baseline_path)
    dgr = _load_json(dgr_path)
    blockers: list[str] = []
    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not baseline:
        blockers.append("missing_baseline_shadow_backtest")
    elif baseline.get("status") != "available_for_manual_offline_review":
        blockers.append(f"baseline_shadow_backtest_not_available:{baseline.get('status')}")
    if not dgr:
        blockers.append("missing_high_dividend_active_pain_dgr")
    elif dgr.get("status") != "available_for_manual_offline_review":
        blockers.append(f"dgr_not_available:{dgr.get('status')}")
    if dgr and dgr.get("decision", {}).get("high_dividend_active_pain_dgr_passed") is not True:
        blockers.append("high_dividend_active_pain_dgr_not_green")
    expected_hash = baseline.get("inputs", {}).get("panel_sha256") if baseline else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("frozen_panel_hash_mismatch")
    return panel, baseline, sorted(set(blockers))


def _build_wide_inputs(panel: pd.DataFrame, eligible_tickers: list[str]) -> dict[str, pd.DataFrame]:
    eligible = panel[panel["ticker"].isin(eligible_tickers)]
    return {
        "reward": eligible.pivot(index="date", columns="ticker", values="reward_proxy").sort_index().reindex(columns=eligible_tickers),
        "return": eligible.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers),
        "drawdown": eligible.pivot(index="date", columns="ticker", values="drawdown_depth").sort_index().reindex(columns=eligible_tickers),
    }


def _positive_hhi(weight: pd.Series) -> float:
    positive = pd.to_numeric(weight, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(positive.sum())
    if total <= 0:
        return 0.0
    share = positive / total
    return float((share**2).sum())


def _weights_wide_from_signal(
    signal: pd.DataFrame,
    *,
    low_threshold: float,
    high_threshold: float,
    low_score: float,
    mid_score: float,
    high_score: float,
) -> pd.DataFrame:
    numeric = signal.apply(pd.to_numeric, errors="coerce")
    scores = pd.DataFrame(mid_score, index=numeric.index, columns=numeric.columns, dtype=float)
    scores = scores.mask(numeric <= low_threshold, low_score)
    scores = scores.mask(numeric >= high_threshold, high_score)
    scores = scores.where(numeric.notna(), mid_score).clip(lower=0.0)
    row_sum = scores.sum(axis=1)
    equal = pd.DataFrame(1.0 / len(scores.columns), index=scores.index, columns=scores.columns, dtype=float)
    return scores.div(row_sum.replace(0.0, np.nan), axis=0).fillna(equal)


def _prepare_fold_cache(
    panel: pd.DataFrame,
    fold: dict[str, Any],
    *,
    eligible_tickers: list[str],
    wide_inputs: dict[str, pd.DataFrame],
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    cost_bps: float,
) -> dict[str, Any]:
    train = panel[
        (panel["date"] >= pd.Timestamp(fold["train_start"]))
        & (panel["date"] <= pd.Timestamp(fold["train_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ]
    train_reward = pd.to_numeric(train["reward_proxy"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    test_returns = (
        wide_inputs["return"]
        .loc[fold["test_start"] : fold["test_end"]]
        .reindex(columns=eligible_tickers)
        .fillna(0.0)
    )
    if train_reward.empty or test_returns.empty:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_reward_or_test_frame"}

    original_low = float(train_reward.quantile(low_quantile))
    original_high = float(train_reward.quantile(high_quantile))
    train_dates = wide_inputs["return"].loc[fold["train_start"] : fold["train_end"]].index
    test_dates = test_returns.index
    signal_dates = train_dates.union(test_dates)
    signal = (
        wide_inputs["reward"]
        .shift(1)
        .reindex(signal_dates)
        .reindex(columns=eligible_tickers)
    )
    lag_return = (
        wide_inputs["return"]
        .shift(1)
        .reindex(signal_dates)
        .reindex(columns=eligible_tickers)
    )
    lag_drawdown = (
        wide_inputs["drawdown"]
        .shift(1)
        .reindex(signal_dates)
        .reindex(columns=eligible_tickers)
    )
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    high_dividend = [ticker for ticker in HIGH_DIVIDEND_BUCKET if ticker in eligible_tickers]
    original_weight_wide = _weights_wide_from_signal(
        signal,
        low_threshold=original_low,
        high_threshold=original_high,
        low_score=low_score,
        mid_score=mid_score,
        high_score=high_score,
    )
    active = original_weight_wide.sub(equal_weight, axis=1)
    hd_active = active.reindex(columns=high_dividend).fillna(0.0)
    positive_hd = hd_active.clip(lower=0.0)
    positive_hd_total = positive_hd.sum(axis=1)
    if high_dividend:
        allocations = positive_hd.div(positive_hd_total.replace(0.0, np.nan), axis=0).fillna(1.0 / len(high_dividend))
    else:
        allocations = pd.DataFrame(index=signal.index)
    positive_active = active.clip(lower=0.0)
    positive_active_total = positive_active.sum(axis=1)
    hhi = (positive_active.pow(2).sum(axis=1) / positive_active_total.pow(2).replace(0.0, np.nan)).fillna(0.0)

    diag = pd.DataFrame(
        {
            "positive_high_dividend_active_weight": hd_active.sum(axis=1).clip(lower=0.0),
            "lag_high_dividend_return": lag_return.reindex(columns=high_dividend).fillna(0.0).mean(axis=1),
            "lag_high_dividend_drawdown": lag_drawdown.reindex(columns=high_dividend).fillna(0.0).mean(axis=1),
            "reward_signal_concentration_hhi": hhi,
        },
        index=signal.index,
    )
    original_test_weights = original_weight_wide.reindex(test_returns.index).reindex(columns=eligible_tickers)
    previous_original = original_test_weights.shift(1)
    if not previous_original.empty:
        previous_original.iloc[0] = equal_weight
    original_turnovers = (original_test_weights - previous_original).abs().sum(axis=1)
    cost_rate = cost_bps / 10_000.0
    baseline_returns = test_returns.mul(equal_weight, axis=1).sum(axis=1)
    original_returns = original_test_weights.mul(test_returns, axis=0).sum(axis=1) - original_turnovers * cost_rate

    index = test_returns.index
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "test_days": int(len(index)),
        "eligible_tickers": eligible_tickers,
        "high_dividend": high_dividend,
        "signal": signal,
        "test_returns": test_returns,
        "diag": diag,
        "allocations": allocations,
        "original_low": original_low,
        "original_high": original_high,
        "low_quantile": low_quantile,
        "high_quantile": high_quantile,
        "low_score": low_score,
        "mid_score": mid_score,
        "high_score": high_score,
        "cost_rate": cost_rate,
        "equal_weight": equal_weight,
        "baseline_series": pd.Series(baseline_returns, index=index, dtype=float),
        "original_series": pd.Series(original_returns, index=index, dtype=float),
        "original_turnovers": pd.Series(original_turnovers, index=index, dtype=float),
    }


def _simulate_cached_fold(
    cache: dict[str, Any],
    *,
    active_penalty_scale: float,
    drawdown_scale: float,
    return_pain_scale: float,
    concentration_scale: float,
) -> dict[str, Any]:
    if cache.get("status") != "available_for_manual_offline_review":
        return cache

    signal = cache["signal"].copy()
    diag = cache["diag"].copy()
    high_dividend = cache["high_dividend"]
    pain = diag["positive_high_dividend_active_weight"] * (
        drawdown_scale * diag["lag_high_dividend_drawdown"].clip(lower=0.0)
        + return_pain_scale * (-diag["lag_high_dividend_return"]).clip(lower=0.0)
        + concentration_scale * diag["reward_signal_concentration_hhi"]
    )
    penalty = active_penalty_scale * pain
    if high_dividend:
        signal.loc[:, high_dividend] = signal.loc[:, high_dividend] - cache["allocations"].mul(penalty, axis=0)

    train_signal = signal.loc[cache["train_start"] : cache["train_end"]].stack().dropna()
    if train_signal.empty:
        return {"fold": cache["fold"], "status": "blocked", "blocking_reason": "empty_train_redesigned_signal"}
    redesigned_low = float(train_signal.quantile(cache["low_quantile"]))
    redesigned_high = float(train_signal.quantile(cache["high_quantile"]))

    test_signal = signal.loc[cache["test_start"] : cache["test_end"]].reindex(columns=cache["eligible_tickers"])
    redesigned_weights = _weights_wide_from_signal(
        test_signal,
        low_threshold=redesigned_low,
        high_threshold=redesigned_high,
        low_score=cache["low_score"],
        mid_score=cache["mid_score"],
        high_score=cache["high_score"],
    )
    previous = redesigned_weights.shift(1)
    if not previous.empty:
        previous.iloc[0] = cache["equal_weight"]
    turnovers = (redesigned_weights - previous).abs().sum(axis=1)
    redesigned_series = redesigned_weights.mul(cache["test_returns"], axis=0).sum(axis=1) - turnovers * cache["cost_rate"]
    event_rows: list[dict[str, Any]] = []
    event_date = pd.Timestamp("2024-08-05")
    if event_date in redesigned_series.index:
        baseline_return = float(cache["baseline_series"].loc[event_date])
        original_return = float(cache["original_series"].loc[event_date])
        redesigned_return = float(redesigned_series.loc[event_date])
        event_rows.append(
            {
                "date": event_date.date().isoformat(),
                "original_active_return": _finite_float(original_return - baseline_return),
                "redesigned_active_return": _finite_float(redesigned_return - baseline_return),
                "active_return_improvement": _finite_float((redesigned_return - baseline_return) - (original_return - baseline_return)),
                "active_bucket_drawdown_penalty": _finite_float(float(penalty.loc[event_date])),
                "high_dividend_active_pain": _finite_float(float(pain.loc[event_date])),
            }
        )

    index = cache["test_returns"].index
    baseline_metrics = _metrics(cache["baseline_series"])
    original_metrics = _metrics(cache["original_series"], turnover=cache["original_turnovers"])
    redesigned_metrics = _metrics(pd.Series(redesigned_series, index=index, dtype=float), turnover=pd.Series(turnovers, index=index, dtype=float))
    return {
        "fold": cache["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": cache["train_start"],
        "train_end": cache["train_end"],
        "test_start": cache["test_start"],
        "test_end": cache["test_end"],
        "test_days": cache["test_days"],
        "thresholds": {
            "original_low_reward_threshold": _finite_float(cache["original_low"]),
            "original_high_reward_threshold": _finite_float(cache["original_high"]),
            "redesigned_low_reward_threshold": _finite_float(redesigned_low),
            "redesigned_high_reward_threshold": _finite_float(redesigned_high),
        },
        "original_reward_tilt": original_metrics,
        "redesigned_reward_tilt": redesigned_metrics,
        "equal_weight_baseline": baseline_metrics,
        "delta_vs_equal_weight": {
            "final_value": _finite_float((redesigned_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((redesigned_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((redesigned_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
        "delta_redesigned_minus_original": {
            "final_value": _finite_float((redesigned_metrics["final_value"] or 0.0) - (original_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((redesigned_metrics["sharpe_ratio"] or 0.0) - (original_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((redesigned_metrics["max_drawdown"] or 0.0) - (original_metrics["max_drawdown"] or 0.0)),
        },
        "event_probes": event_rows,
    }


def _row_from_folds(
    fold_rows: list[dict[str, Any]],
    *,
    active_scale: float,
    drawdown_scale: float,
    return_scale: float,
    concentration_scale: float,
    min_positive_final_folds: int,
    min_positive_sharpe_folds: int,
    min_non_worse_drawdown_folds: int,
) -> dict[str, Any]:
    blockers = [
        f"fold_not_available:{row.get('fold')}:{row.get('blocking_reason')}"
        for row in fold_rows
        if row.get("status") != "available_for_manual_offline_review"
    ]
    aggregate = _aggregate_folds(fold_rows)
    warnings: list[str] = []
    if aggregate["available_fold_count"]:
        if aggregate["positive_final_value_folds"] < min_positive_final_folds:
            warnings.append(f"positive_final_value_folds_below_threshold:{aggregate['positive_final_value_folds']}<{min_positive_final_folds}")
        if aggregate["positive_sharpe_folds"] < min_positive_sharpe_folds:
            warnings.append(f"positive_sharpe_folds_below_threshold:{aggregate['positive_sharpe_folds']}<{min_positive_sharpe_folds}")
        if aggregate["non_worse_drawdown_folds"] < min_non_worse_drawdown_folds:
            warnings.append(
                f"non_worse_drawdown_folds_below_threshold:{aggregate['non_worse_drawdown_folds']}<{min_non_worse_drawdown_folds}"
            )
    event_probes = [probe for row in fold_rows for probe in row.get("event_probes", [])]
    event_improved = bool(event_probes and all((probe.get("active_return_improvement") or 0.0) > 0 for probe in event_probes))
    if not event_improved:
        warnings.append("event_probe_2024_08_05_active_drag_not_improved")
    passed = bool(
        not blockers
        and aggregate["positive_final_value_folds"] >= min_positive_final_folds
        and aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds
        and aggregate["non_worse_drawdown_folds"] >= min_non_worse_drawdown_folds
        and event_improved
    )
    event = event_probes[0] if event_probes else {}
    return {
        "active_penalty_scale": active_scale,
        "drawdown_scale": drawdown_scale,
        "return_pain_scale": return_scale,
        "concentration_scale": concentration_scale,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "passed": passed,
        "positive_final_value_folds": aggregate["positive_final_value_folds"],
        "positive_sharpe_folds": aggregate["positive_sharpe_folds"],
        "non_worse_drawdown_folds": aggregate["non_worse_drawdown_folds"],
        "mean_delta_final_value": aggregate["mean_delta_final_value"],
        "mean_delta_sharpe_ratio": aggregate["mean_delta_sharpe_ratio"],
        "mean_delta_max_drawdown": aggregate["mean_delta_max_drawdown"],
        "event_probe_active_drag_improved": event_improved,
        "event_active_return_improvement": event.get("active_return_improvement"),
        "warning_reasons": sorted(set(warnings)),
        "blocking_reasons": sorted(set(blockers)),
    }


def build_sweep(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    dgr_path: Path = DEFAULT_DGR,
    active_penalty_scales: list[float] | None = None,
    return_pain_scales: list[float] | None = None,
    concentration_scales: list[float] | None = None,
    drawdown_scale: float = 1.0,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    min_passed_candidates: int = 3,
    as_of: str = "2026-07-21",
) -> dict[str, Any]:
    active_grid = active_penalty_scales or [10.0, 15.0, 20.0, 25.0, 30.0]
    return_grid = return_pain_scales or [2.0, 4.0, 6.0]
    concentration_grid = concentration_scales or [0.05, 0.10, 0.20]
    panel, baseline, input_blockers = _validate_inputs(panel_path, baseline_path, dgr_path)
    inputs = baseline.get("inputs", {}) if baseline else {}
    eligible_tickers = list(inputs.get("eligible_tickers") or [])
    if len(eligible_tickers) < 2:
        input_blockers.append("too_few_eligible_tickers")
    if {"00631L.TW", "00632R.TW"} & set(eligible_tickers):
        input_blockers.append("leveraged_or_inverse_ticker_not_excluded")
    folds = baseline.get("fold_results") if isinstance(baseline.get("fold_results"), list) else []
    if not folds:
        input_blockers.append("missing_baseline_folds")

    rows: list[dict[str, Any]] = []
    input_blockers = sorted(set(input_blockers))
    if not input_blockers:
        wide_inputs = _build_wide_inputs(panel, eligible_tickers)
        fold_cache = [
            _prepare_fold_cache(
                panel,
                fold,
                eligible_tickers=eligible_tickers,
                wide_inputs=wide_inputs,
                low_quantile=float(inputs.get("low_quantile", 0.30)),
                high_quantile=float(inputs.get("high_quantile", 0.70)),
                low_score=float(inputs.get("low_score", 0.50)),
                mid_score=float(inputs.get("mid_score", 1.00)),
                high_score=float(inputs.get("high_score", 1.50)),
                cost_bps=float(inputs.get("cost_bps", 5.0)),
            )
            for fold in folds
        ]
        for active_scale, return_scale, concentration_scale in product(active_grid, return_grid, concentration_grid):
            fold_rows = [
                _simulate_cached_fold(
                    cache,
                    active_penalty_scale=active_scale,
                    drawdown_scale=drawdown_scale,
                    return_pain_scale=return_scale,
                    concentration_scale=concentration_scale,
                )
                for cache in fold_cache
            ]
            rows.append(
                _row_from_folds(
                    fold_rows,
                    active_scale=active_scale,
                    drawdown_scale=drawdown_scale,
                    return_scale=return_scale,
                    concentration_scale=concentration_scale,
                    min_positive_final_folds=min_positive_final_folds,
                    min_positive_sharpe_folds=min_positive_sharpe_folds,
                    min_non_worse_drawdown_folds=min_non_worse_drawdown_folds,
                )
            )
    else:
        for active_scale, return_scale, concentration_scale in product(active_grid, return_grid, concentration_grid):
            rows.append(
                {
                    "active_penalty_scale": active_scale,
                    "drawdown_scale": drawdown_scale,
                    "return_pain_scale": return_scale,
                    "concentration_scale": concentration_scale,
                    "status": "blocked",
                    "passed": False,
                    "positive_final_value_folds": 0,
                    "positive_sharpe_folds": 0,
                    "non_worse_drawdown_folds": 0,
                    "mean_delta_final_value": None,
                    "mean_delta_sharpe_ratio": None,
                    "mean_delta_max_drawdown": None,
                    "event_probe_active_drag_improved": False,
                    "event_active_return_improvement": None,
                    "warning_reasons": [],
                    "blocking_reasons": input_blockers,
                }
            )
    ranked = sorted(rows, key=_score, reverse=True)
    passed = [row for row in ranked if row["passed"]]
    robustness_passed = len(passed) >= min_passed_candidates
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "available_for_manual_offline_review",
        "policy": "v3_active_pain_param_sweep_shadow_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "baseline_shadow_backtest": str(baseline_path),
            "dgr_review": str(dgr_path),
            "active_penalty_scales": active_grid,
            "return_pain_scales": return_grid,
            "concentration_scales": concentration_grid,
            "drawdown_scale": drawdown_scale,
            "min_positive_final_folds": min_positive_final_folds,
            "min_positive_sharpe_folds": min_positive_sharpe_folds,
            "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            "min_passed_candidates": min_passed_candidates,
            "execution_mode": "cached_fold_fast_sweep",
        },
        "summary": {
            "evaluated_count": len(rows),
            "passed_count": len(passed),
            "robustness_passed": robustness_passed,
            "best_candidate": ranked[0] if ranked else None,
            "recommended_candidate": passed[0] if passed else None,
            "passed_candidates": passed[:10],
        },
        "results": ranked,
        "decision": {
            "available_for_manual_offline_review": True,
            "v3_active_pain_param_robustness_passed": robustness_passed,
            "next_shadow_scorecard_allowed": robustness_passed,
            "next_shadow_model_design_allowed": False,
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
    return history_dir / f"llm_state_reward_interface_high_dividend_active_pain_param_sweep_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _float_list(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-21")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--dgr", default=str(DEFAULT_DGR))
    parser.add_argument("--active-penalty-scales", default="10,15,20,25,30")
    parser.add_argument("--return-pain-scales", default="2,4,6")
    parser.add_argument("--concentration-scales", default="0.05,0.1,0.2")
    parser.add_argument("--drawdown-scale", type=float, default=1.0)
    parser.add_argument("--min-passed-candidates", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    review = build_sweep(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        dgr_path=_resolve(args.dgr),
        active_penalty_scales=_float_list(args.active_penalty_scales),
        return_pain_scales=_float_list(args.return_pain_scales),
        concentration_scales=_float_list(args.concentration_scales),
        drawdown_scale=args.drawdown_scale,
        min_passed_candidates=args.min_passed_candidates,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward high-dividend active-pain param sweep: {_resolve(args.output)}")
    print(json.dumps(review["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
