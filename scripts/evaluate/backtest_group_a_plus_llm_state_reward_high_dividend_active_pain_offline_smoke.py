#!/usr/bin/env python3
"""Offline smoke backtest for the high-dividend active-pain GIFT redesign.

This converts the DGR-green high-dividend active-pain idea into a no-model OOS
reward-tilt smoke test. It compares redesigned reward signals against equal
weight and the original frozen reward tilt. It does not train models or output
live target weights.
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
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import HIGH_DIVIDEND_BUCKET  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_high_dividend_active_pain_dgr import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_DGR,
    PROPOSAL_ID,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _load_json, _resolve  # noqa: E402
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_high_dividend_active_pain_offline_smoke.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_offline_smoke/history"


def _positive_hhi(active_weight: pd.Series) -> float:
    positive = pd.to_numeric(active_weight, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(positive.sum())
    if total <= 0:
        return 0.0
    share = positive / total
    return float((share**2).sum())


def _redesigned_signal_row(
    *,
    signal_row: pd.Series,
    lag_return_row: pd.Series,
    lag_drawdown_row: pd.Series,
    original_low_threshold: float,
    original_high_threshold: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    active_penalty_scale: float,
    drawdown_scale: float,
    return_pain_scale: float,
    concentration_scale: float,
    eligible_tickers: list[str],
) -> tuple[pd.Series, dict[str, Any]]:
    signal = pd.to_numeric(signal_row.reindex(eligible_tickers), errors="coerce")
    raw_weight = _weights_from_signal(
        signal,
        low_threshold=original_low_threshold,
        high_threshold=original_high_threshold,
        low_score=low_score,
        mid_score=mid_score,
        high_score=high_score,
    )
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    active_weight = raw_weight - equal_weight
    high_dividend = [ticker for ticker in HIGH_DIVIDEND_BUCKET if ticker in eligible_tickers]
    hd_active = active_weight.reindex(high_dividend).fillna(0.0)
    positive_hd_active_weight = max(float(hd_active.sum()), 0.0)
    lag_hd_return = float(pd.to_numeric(lag_return_row.reindex(high_dividend), errors="coerce").fillna(0.0).mean())
    lag_hd_drawdown = float(pd.to_numeric(lag_drawdown_row.reindex(high_dividend), errors="coerce").fillna(0.0).mean())
    concentration_hhi = _positive_hhi(active_weight)
    high_dividend_active_pain = positive_hd_active_weight * (
        drawdown_scale * max(lag_hd_drawdown, 0.0)
        + return_pain_scale * max(-lag_hd_return, 0.0)
        + concentration_scale * concentration_hhi
    )
    penalty = active_penalty_scale * high_dividend_active_pain
    redesigned = signal.copy()
    positive_hd = hd_active.clip(lower=0.0)
    if penalty > 0 and high_dividend:
        if float(positive_hd.sum()) > 0:
            allocation = positive_hd / float(positive_hd.sum()) * penalty
        else:
            allocation = pd.Series(penalty / len(high_dividend), index=high_dividend, dtype=float)
        redesigned.loc[allocation.index] = redesigned.loc[allocation.index] - allocation
    return redesigned, {
        "high_dividend_active_weight": _finite_float(float(hd_active.sum())),
        "high_dividend_active_pain": _finite_float(high_dividend_active_pain),
        "active_bucket_drawdown_penalty": _finite_float(penalty),
        "reward_signal_concentration_hhi": _finite_float(concentration_hhi),
    }


def _redesigned_signal_wide(
    *,
    eligible_tickers: list[str],
    reward_wide: pd.DataFrame,
    return_wide: pd.DataFrame,
    drawdown_wide: pd.DataFrame,
    dates: pd.Index,
    original_low_threshold: float,
    original_high_threshold: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    active_penalty_scale: float,
    drawdown_scale: float,
    return_pain_scale: float,
    concentration_scale: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal = (
        reward_wide
        .shift(1)
        .reindex(dates)
        .reindex(columns=eligible_tickers)
    )
    returns = return_wide.shift(1).reindex(dates).reindex(columns=eligible_tickers)
    drawdown = (
        drawdown_wide
        .shift(1)
        .reindex(dates)
        .reindex(columns=eligible_tickers)
    )
    redesigned_rows: list[pd.Series] = []
    diagnostics: list[dict[str, Any]] = []
    for dt, signal_row in signal.iterrows():
        redesigned, diag = _redesigned_signal_row(
            signal_row=signal_row,
            lag_return_row=returns.loc[dt],
            lag_drawdown_row=drawdown.loc[dt],
            original_low_threshold=original_low_threshold,
            original_high_threshold=original_high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
            active_penalty_scale=active_penalty_scale,
            drawdown_scale=drawdown_scale,
            return_pain_scale=return_pain_scale,
            concentration_scale=concentration_scale,
            eligible_tickers=eligible_tickers,
        )
        redesigned.name = dt
        redesigned_rows.append(redesigned)
        diagnostics.append({"date": pd.Timestamp(dt), **diag})
    return pd.DataFrame(redesigned_rows).sort_index(), pd.DataFrame(diagnostics)


def _fold_smoke(
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
    active_penalty_scale: float,
    drawdown_scale: float,
    return_pain_scale: float,
    concentration_scale: float,
    wide_inputs: dict[str, pd.DataFrame] | None = None,
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
    if train_reward.empty or test.empty:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_reward_or_test_frame"}

    original_low = float(train_reward.quantile(low_quantile))
    original_high = float(train_reward.quantile(high_quantile))
    if wide_inputs is None:
        eligible = panel[panel["ticker"].isin(eligible_tickers)]
        wide_inputs = {
            "reward": eligible.pivot(index="date", columns="ticker", values="reward_proxy").sort_index().reindex(columns=eligible_tickers),
            "return": eligible.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers),
            "drawdown": eligible.pivot(index="date", columns="ticker", values="drawdown_depth").sort_index().reindex(columns=eligible_tickers),
        }
    train_dates = wide_inputs["return"].loc[fold["train_start"] : fold["train_end"]].index
    test_dates = wide_inputs["return"].loc[fold["test_start"] : fold["test_end"]].index
    signal_dates = train_dates.union(test_dates)
    redesigned_signal, diagnostics = _redesigned_signal_wide(
        eligible_tickers=eligible_tickers,
        reward_wide=wide_inputs["reward"],
        return_wide=wide_inputs["return"],
        drawdown_wide=wide_inputs["drawdown"],
        dates=signal_dates,
        original_low_threshold=original_low,
        original_high_threshold=original_high,
        low_score=low_score,
        mid_score=mid_score,
        high_score=high_score,
        active_penalty_scale=active_penalty_scale,
        drawdown_scale=drawdown_scale,
        return_pain_scale=return_pain_scale,
        concentration_scale=concentration_scale,
    )
    train_redesigned = redesigned_signal.loc[fold["train_start"] : fold["train_end"]].stack().dropna()
    if train_redesigned.empty:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_redesigned_signal"}
    redesigned_low = float(train_redesigned.quantile(low_quantile))
    redesigned_high = float(train_redesigned.quantile(high_quantile))

    wide_returns = wide_inputs["return"].loc[fold["test_start"] : fold["test_end"]].reindex(columns=eligible_tickers)
    original_signal = (
        wide_inputs["reward"]
        .shift(1)
        .reindex(wide_returns.index)
        .reindex(columns=eligible_tickers)
    )
    redesigned_test_signal = redesigned_signal.reindex(wide_returns.index).reindex(columns=eligible_tickers)
    diagnostics = diagnostics.set_index("date").reindex(wide_returns.index)
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_original = equal_weight.copy()
    previous_redesigned = equal_weight.copy()
    original_returns: list[float] = []
    redesigned_returns: list[float] = []
    baseline_returns: list[float] = []
    original_turnovers: list[float] = []
    redesigned_turnovers: list[float] = []
    event_rows: list[dict[str, Any]] = []
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in wide_returns.iterrows():
        usable_returns = pd.to_numeric(return_row, errors="coerce").fillna(0.0)
        original_weight = _weights_from_signal(
            original_signal.loc[dt],
            low_threshold=original_low,
            high_threshold=original_high,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        redesigned_weight = _weights_from_signal(
            redesigned_test_signal.loc[dt],
            low_threshold=redesigned_low,
            high_threshold=redesigned_high,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        original_turnover = float((original_weight - previous_original).abs().sum())
        redesigned_turnover = float((redesigned_weight - previous_redesigned).abs().sum())
        baseline_return = float((equal_weight * usable_returns).sum())
        original_return = float((original_weight * usable_returns).sum() - original_turnover * cost_rate)
        redesigned_return = float((redesigned_weight * usable_returns).sum() - redesigned_turnover * cost_rate)
        original_returns.append(original_return)
        redesigned_returns.append(redesigned_return)
        baseline_returns.append(baseline_return)
        original_turnovers.append(original_turnover)
        redesigned_turnovers.append(redesigned_turnover)
        if dt == pd.Timestamp("2024-08-05"):
            diag = diagnostics.loc[dt].to_dict() if dt in diagnostics.index else {}
            event_rows.append(
                {
                    "date": dt.date().isoformat(),
                    "original_active_return": _finite_float(original_return - baseline_return),
                    "redesigned_active_return": _finite_float(redesigned_return - baseline_return),
                    "active_return_improvement": _finite_float((redesigned_return - baseline_return) - (original_return - baseline_return)),
                    "original_high_dividend_active_weight": _finite_float(
                        float((original_weight - equal_weight).reindex(HIGH_DIVIDEND_BUCKET).fillna(0.0).sum())
                    ),
                    "redesigned_high_dividend_active_weight": _finite_float(
                        float((redesigned_weight - equal_weight).reindex(HIGH_DIVIDEND_BUCKET).fillna(0.0).sum())
                    ),
                    "high_dividend_active_pain": diag.get("high_dividend_active_pain"),
                    "active_bucket_drawdown_penalty": diag.get("active_bucket_drawdown_penalty"),
                }
            )
        previous_original = original_weight
        previous_redesigned = redesigned_weight

    index = wide_returns.index
    baseline_series = pd.Series(baseline_returns, index=index, dtype=float)
    original_series = pd.Series(original_returns, index=index, dtype=float)
    redesigned_series = pd.Series(redesigned_returns, index=index, dtype=float)
    original_metrics = _metrics(original_series, turnover=pd.Series(original_turnovers, index=index, dtype=float))
    redesigned_metrics = _metrics(redesigned_series, turnover=pd.Series(redesigned_turnovers, index=index, dtype=float))
    baseline_metrics = _metrics(baseline_series)
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "test_days": int(len(index)),
        "thresholds": {
            "original_low_reward_threshold": _finite_float(original_low),
            "original_high_reward_threshold": _finite_float(original_high),
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


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    dgr_path: Path = DEFAULT_DGR,
    active_penalty_scale: float | None = None,
    drawdown_scale: float | None = None,
    return_pain_scale: float | None = None,
    concentration_scale: float | None = None,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    require_event_improvement: bool = True,
    as_of: str = "2026-07-21",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    baseline = _load_json(baseline_path)
    dgr = _load_json(dgr_path)
    blockers: list[str] = []
    warnings: list[str] = []
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
    if _load_json(dgr_path).get("decision", {}).get("high_dividend_active_pain_dgr_passed") is not True:
        blockers.append("high_dividend_active_pain_dgr_not_green")
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

    dgr_inputs = dgr.get("inputs", {}) if dgr else {}
    active_penalty = float(active_penalty_scale if active_penalty_scale is not None else dgr_inputs.get("active_penalty_scale", 20.0))
    drawdown = float(drawdown_scale if drawdown_scale is not None else dgr_inputs.get("drawdown_scale", 1.0))
    return_pain = float(return_pain_scale if return_pain_scale is not None else dgr_inputs.get("return_pain_scale", 4.0))
    concentration = float(concentration_scale if concentration_scale is not None else dgr_inputs.get("concentration_scale", 0.1))
    wide_inputs = None
    if not blockers:
        eligible = panel[panel["ticker"].isin(eligible_tickers)]
        wide_inputs = {
            "reward": eligible.pivot(index="date", columns="ticker", values="reward_proxy").sort_index().reindex(columns=eligible_tickers),
            "return": eligible.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers),
            "drawdown": eligible.pivot(index="date", columns="ticker", values="drawdown_depth").sort_index().reindex(columns=eligible_tickers),
        }

    fold_rows = [
        _fold_smoke(
            panel,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=float(inputs.get("low_quantile", 0.30)),
            high_quantile=float(inputs.get("high_quantile", 0.70)),
            low_score=float(inputs.get("low_score", 0.50)),
            mid_score=float(inputs.get("mid_score", 1.00)),
            high_score=float(inputs.get("high_score", 1.50)),
            cost_bps=float(inputs.get("cost_bps", 5.0)),
            active_penalty_scale=active_penalty,
            drawdown_scale=drawdown,
            return_pain_scale=return_pain,
            concentration_scale=concentration,
            wide_inputs=wide_inputs,
        )
        for fold in folds
    ] if not blockers else []
    for row in fold_rows:
        if row.get("status") != "available_for_manual_offline_review":
            blockers.append(f"fold_not_available:{row.get('fold')}:{row.get('blocking_reason')}")

    aggregate = _aggregate_folds(fold_rows)
    if aggregate["available_fold_count"]:
        if aggregate["positive_final_value_folds"] < min_positive_final_folds:
            warnings.append(f"positive_final_value_folds_below_threshold:{aggregate['positive_final_value_folds']}<{min_positive_final_folds}")
        if aggregate["positive_sharpe_folds"] < min_positive_sharpe_folds:
            warnings.append(f"positive_sharpe_folds_below_threshold:{aggregate['positive_sharpe_folds']}<{min_positive_sharpe_folds}")
        if aggregate["non_worse_drawdown_folds"] < min_non_worse_drawdown_folds:
            warnings.append(f"non_worse_drawdown_folds_below_threshold:{aggregate['non_worse_drawdown_folds']}<{min_non_worse_drawdown_folds}")

    event_probes = [probe for row in fold_rows for probe in row.get("event_probes", [])]
    event_improved = bool(event_probes and all((probe.get("active_return_improvement") or 0.0) > 0 for probe in event_probes))
    if require_event_improvement and not event_improved:
        warnings.append("event_probe_2024_08_05_active_drag_not_improved")

    pass_gate = bool(
        not blockers
        and aggregate["positive_final_value_folds"] >= min_positive_final_folds
        and aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds
        and aggregate["non_worse_drawdown_folds"] >= min_non_worse_drawdown_folds
        and (event_improved or not require_event_improvement)
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_offline_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "offline_smoke_only_no_model_training_no_live_action",
        "proposal_id": PROPOSAL_ID,
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "dgr_review": str(dgr_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "active_penalty_scale": active_penalty,
            "drawdown_scale": drawdown,
            "return_pain_scale": return_pain,
            "concentration_scale": concentration,
            "min_positive_final_folds": min_positive_final_folds,
            "min_positive_sharpe_folds": min_positive_sharpe_folds,
            "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
        },
        "summary": {
            "baseline_positive_final_value_folds": (baseline.get("summary", {}) if baseline else {}).get("positive_final_value_folds"),
            "baseline_positive_sharpe_folds": (baseline.get("summary", {}) if baseline else {}).get("positive_sharpe_folds"),
            "baseline_non_worse_drawdown_folds": (baseline.get("summary", {}) if baseline else {}).get("non_worse_drawdown_folds"),
            "high_dividend_active_pain_offline_smoke": aggregate,
            "event_probe_2024_08_05": event_probes[0] if event_probes else {"available": False},
            "event_probe_active_drag_improved": event_improved,
            "pass_high_dividend_active_pain_offline_smoke": pass_gate,
        },
        "fold_results": fold_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "high_dividend_active_pain_offline_smoke_passed": pass_gate,
            "next_frozen_manifest_design_allowed": pass_gate,
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
    return history_dir / f"llm_state_reward_interface_high_dividend_active_pain_offline_smoke_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-21")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--dgr", default=str(DEFAULT_DGR))
    parser.add_argument("--active-penalty-scale", type=float)
    parser.add_argument("--drawdown-scale", type=float)
    parser.add_argument("--return-pain-scale", type=float)
    parser.add_argument("--concentration-scale", type=float)
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
        dgr_path=_resolve(args.dgr),
        active_penalty_scale=args.active_penalty_scale,
        drawdown_scale=args.drawdown_scale,
        return_pain_scale=args.return_pain_scale,
        concentration_scale=args.concentration_scale,
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        min_non_worse_drawdown_folds=args.min_non_worse_drawdown_folds,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward high-dividend active-pain offline smoke: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "smoke": review["summary"]["high_dividend_active_pain_offline_smoke"],
                "event_improved": review["summary"]["event_probe_active_drag_improved"],
                "pass_smoke": review["decision"]["high_dividend_active_pain_offline_smoke_passed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
