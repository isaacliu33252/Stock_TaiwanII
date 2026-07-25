#!/usr/bin/env python3
"""Regime-filtered micro-tilt shadow backtest for the frozen GIFT panel.

This tests whether the 5 bps cost warning can be improved by activating the
micro-tilt only in simple train-window regimes. It is no-model, research-only,
and never emits target weights or live rebalance actions.
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

from scripts.evaluate.audit_group_a_plus_llm_state_reward_frozen_panel_walk_forward import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_WF_AUDIT,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (  # noqa: E402
    DEFAULT_EXCLUDED_TICKERS,
    _aggregate_folds,
    _finite_float,
    _load_panel,
    _metrics,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.sweep_group_a_plus_llm_state_reward_frozen_panel_baseline_params import (  # noqa: E402
    _score_candidate,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_regime_filtered_micro_tilt_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_regime_filtered_micro_tilt_shadow_backtest/history"
REGIME_RULES = [
    "trend_above_train_median",
    "vol_below_train_70q",
    "downside_below_train_70q",
    "drawdown_below_train_70q",
    "trend_and_vol",
    "trend_and_downside",
    "trend_vol_downside",
]


def _float_list(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _daily_regime(panel: pd.DataFrame, eligible_tickers: list[str]) -> pd.DataFrame:
    cols = ["realized_volatility", "downside_deviation", "drawdown_depth", "ema_cross_strength"]
    frame = panel[panel["ticker"].isin(eligible_tickers)].copy()
    daily = frame.groupby("date", sort=True)[cols].mean(numeric_only=True)
    return daily.replace([np.inf, -np.inf], np.nan).sort_index()


def _regime_thresholds(daily: pd.DataFrame, fold: dict[str, Any]) -> dict[str, float]:
    train = daily.loc[pd.Timestamp(fold["train_start"]) : pd.Timestamp(fold["train_end"])]
    return {
        "trend_median": float(train["ema_cross_strength"].dropna().quantile(0.50)),
        "vol_70q": float(train["realized_volatility"].dropna().quantile(0.70)),
        "downside_70q": float(train["downside_deviation"].dropna().quantile(0.70)),
        "drawdown_70q": float(train["drawdown_depth"].dropna().quantile(0.70)),
    }


def _active_regime(row: pd.Series, thresholds: dict[str, float], rule: str) -> bool:
    trend = float(row.get("ema_cross_strength") or 0.0) > thresholds["trend_median"]
    vol = float(row.get("realized_volatility") or 0.0) <= thresholds["vol_70q"]
    downside = float(row.get("downside_deviation") or 0.0) <= thresholds["downside_70q"]
    drawdown = float(row.get("drawdown_depth") or 0.0) <= thresholds["drawdown_70q"]
    if rule == "trend_above_train_median":
        return trend
    if rule == "vol_below_train_70q":
        return vol
    if rule == "downside_below_train_70q":
        return downside
    if rule == "drawdown_below_train_70q":
        return drawdown
    if rule == "trend_and_vol":
        return trend and vol
    if rule == "trend_and_downside":
        return trend and downside
    if rule == "trend_vol_downside":
        return trend and vol and downside
    raise ValueError(f"unknown regime rule: {rule}")


def _fold_backtest_regime_filtered(
    panel: pd.DataFrame,
    fold: dict[str, Any],
    *,
    eligible_tickers: list[str],
    daily_regime: pd.DataFrame,
    regime_rule: str,
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    high_score: float,
    cost_bps: float,
) -> dict[str, Any]:
    train = panel[
        (panel["date"] >= pd.Timestamp(fold["train_start"]))
        & (panel["date"] <= pd.Timestamp(fold["train_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ].copy()
    test = panel[
        (panel["date"] >= pd.Timestamp(fold["test_start"]))
        & (panel["date"] <= pd.Timestamp(fold["test_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ].copy()
    train_reward = pd.to_numeric(train["reward_proxy"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if train_reward.empty or test.empty:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_reward_or_test_frame"}

    thresholds = _regime_thresholds(daily_regime, fold)
    low_threshold = float(train_reward.quantile(low_quantile))
    high_threshold = float(train_reward.quantile(high_quantile))
    wide_returns = test.pivot(index="date", columns="ticker", values="return").sort_index()
    wide_signal = (
        panel[panel["ticker"].isin(eligible_tickers)]
        .pivot(index="date", columns="ticker", values="reward_proxy")
        .sort_index()
        .shift(1)
        .reindex(wide_returns.index)
    )
    shifted_regime = daily_regime.shift(1).reindex(wide_returns.index)
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_candidate = equal_weight.copy()
    candidate_returns: list[float] = []
    baseline_returns: list[float] = []
    turnovers: list[float] = []
    active_days = 0
    dates: list[pd.Timestamp] = []
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in wide_returns.iterrows():
        usable_returns = pd.to_numeric(return_row.reindex(eligible_tickers), errors="coerce").fillna(0.0)
        active = (
            shifted_regime.loc[dt].notna().all()
            and _active_regime(shifted_regime.loc[dt], thresholds, regime_rule)
        )
        if active:
            candidate_weight = _weights_from_signal(
                wide_signal.loc[dt].reindex(eligible_tickers),
                low_threshold=low_threshold,
                high_threshold=high_threshold,
                low_score=low_score,
                mid_score=1.0,
                high_score=high_score,
            )
            active_days += 1
        else:
            candidate_weight = equal_weight.copy()
        turnover = float((candidate_weight - previous_candidate).abs().sum())
        candidate_returns.append(float((candidate_weight * usable_returns).sum() - turnover * cost_rate))
        baseline_returns.append(float((equal_weight * usable_returns).sum()))
        turnovers.append(turnover)
        dates.append(dt)
        previous_candidate = candidate_weight

    candidate_series = pd.Series(candidate_returns, index=dates, dtype=float)
    baseline_series = pd.Series(baseline_returns, index=dates, dtype=float)
    turnover_series = pd.Series(turnovers, index=dates, dtype=float)
    candidate_metrics = _metrics(candidate_series, turnover=turnover_series)
    baseline_metrics = _metrics(baseline_series, turnover=pd.Series(0.0, index=dates))
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "test_days": int(len(candidate_series)),
        "active_days": int(active_days),
        "active_day_ratio": _finite_float(active_days / len(candidate_series)) if len(candidate_series) else None,
        "thresholds": {
            "low_reward_threshold": _finite_float(low_threshold),
            "high_reward_threshold": _finite_float(high_threshold),
            **{key: _finite_float(value) for key, value in thresholds.items()},
        },
        "candidate": candidate_metrics,
        "equal_weight_baseline": baseline_metrics,
        "delta_vs_equal_weight": {
            "final_value": _finite_float((candidate_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((candidate_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((candidate_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    excluded_tickers: list[str] | None = None,
    high_scores: list[float] | None = None,
    regime_rules: list[str] | None = None,
    cost_bps: float = 5.0,
    low_quantile: float = 0.30,
    high_quantile: float = 0.70,
    low_score: float = 1.00,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    audit = _load_json(walk_forward_audit_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not audit:
        blockers.append("missing_walk_forward_audit")
    elif audit.get("status") != "available_for_manual_offline_review":
        blockers.append(f"walk_forward_audit_not_available:{audit.get('status')}")

    expected_hash = audit.get("inputs", {}).get("actual_panel_sha256") if audit else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("frozen_panel_hash_mismatch")

    excluded = set(excluded_tickers or DEFAULT_EXCLUDED_TICKERS)
    all_tickers = sorted(panel["ticker"].dropna().unique()) if "ticker" in panel.columns else []
    eligible_tickers = [ticker for ticker in all_tickers if ticker not in excluded]
    if len(eligible_tickers) < 2:
        blockers.append("too_few_eligible_tickers")
    if {"00631L.TW", "00632R.TW"} & set(eligible_tickers):
        blockers.append("leveraged_or_inverse_ticker_not_excluded")

    folds = audit.get("folds") if isinstance(audit.get("folds"), list) else []
    if not folds:
        blockers.append("missing_walk_forward_folds")

    high_scores = high_scores or [1.01, 1.02, 1.03]
    regime_rules = regime_rules or REGIME_RULES
    unknown_rules = sorted(set(regime_rules) - set(REGIME_RULES))
    if unknown_rules:
        blockers.extend(f"unknown_regime_rule:{rule}" for rule in unknown_rules)

    daily = _daily_regime(panel, eligible_tickers) if not blockers else pd.DataFrame()
    candidate_rows: list[dict[str, Any]] = []
    for regime_rule in regime_rules:
        for high_score in high_scores:
            fold_rows = [
                _fold_backtest_regime_filtered(
                    panel,
                    fold,
                    eligible_tickers=eligible_tickers,
                    daily_regime=daily,
                    regime_rule=regime_rule,
                    low_quantile=low_quantile,
                    high_quantile=high_quantile,
                    low_score=low_score,
                    high_score=high_score,
                    cost_bps=cost_bps,
                )
                for fold in folds
            ] if not blockers else []
            aggregate = _aggregate_folds(fold_rows)
            passed = bool(
                aggregate.get("positive_final_value_folds", 0) >= min_positive_final_folds
                and aggregate.get("positive_sharpe_folds", 0) >= min_positive_sharpe_folds
                and aggregate.get("non_worse_drawdown_folds", 0) >= min_non_worse_drawdown_folds
            )
            active_ratios = [row.get("active_day_ratio") for row in fold_rows if row.get("active_day_ratio") is not None]
            if active_ratios and max(active_ratios) == 0:
                warnings.append(f"regime_rule_never_active:{regime_rule}")
            candidate_rows.append(
                {
                    "regime_rule": regime_rule,
                    "high_score": high_score,
                    "cost_bps": cost_bps,
                    "aggregate": aggregate,
                    "rank_score": _finite_float(_score_candidate(aggregate)),
                    "mean_active_day_ratio": _finite_float(float(np.mean(active_ratios))) if active_ratios else None,
                    "fold_results": fold_rows,
                    "passes_required_thresholds": passed,
                }
            )

    ranked = sorted(
        candidate_rows,
        key=lambda row: row["rank_score"] if row["rank_score"] is not None else -1e9,
        reverse=True,
    )
    recommended = [row for row in ranked if row["passes_required_thresholds"]]
    best = ranked[0] if ranked else None
    best_recommended = recommended[0] if recommended else None

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_regime_filtered_micro_tilt_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "regime_filtered_micro_tilt_shadow_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "walk_forward_audit": str(walk_forward_audit_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": sorted(excluded),
            "high_scores": high_scores,
            "regime_rules": regime_rules,
            "cost_bps": cost_bps,
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_score": low_score,
            "thresholds": {
                "min_positive_final_folds": min_positive_final_folds,
                "min_positive_sharpe_folds": min_positive_sharpe_folds,
                "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            },
        },
        "summary": {
            "evaluated_count": len(candidate_rows),
            "passed_count": len(recommended),
            "best_candidate": {
                key: best[key]
                for key in ["regime_rule", "high_score", "cost_bps", "aggregate", "rank_score", "mean_active_day_ratio"]
            } if best else None,
            "recommended_candidate": {
                key: best_recommended[key]
                for key in ["regime_rule", "high_score", "cost_bps", "aggregate", "rank_score", "mean_active_day_ratio"]
            } if best_recommended else None,
            "regime_filter_resolves_5bps_warning": bool(best_recommended),
        },
        "top_candidates": ranked[:10],
        "candidate_results": candidate_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "Regime filters are derived only from each training window and applied with one-day-lagged test signals.",
            "Passing this shadow check would only resolve a research blocker; it does not authorize training or live action.",
            "The filter is deliberately simple so any improvement can be audited fold by fold.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "regime_filter_resolves_5bps_warning": bool(best_recommended),
            "shadow_training_ready": False,
            "shadow_training_request_allowed": False,
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
    return history_dir / f"llm_state_reward_regime_filtered_micro_tilt_shadow_backtest_{stamp}.json"


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
    parser.add_argument("--walk-forward-audit", default=str(DEFAULT_WF_AUDIT))
    parser.add_argument("--exclude-ticker", action="append", default=[])
    parser.add_argument("--high-scores", default="1.01,1.02,1.03")
    parser.add_argument("--regime-rule", action="append", default=[])
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        excluded_tickers=args.exclude_ticker or None,
        high_scores=_float_list(args.high_scores),
        regime_rules=args.regime_rule or None,
        cost_bps=args.cost_bps,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward regime-filtered micro-tilt shadow backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "passed_count": review["summary"]["passed_count"],
                "best_candidate": review["summary"]["best_candidate"],
                "recommended_candidate": review["summary"]["recommended_candidate"],
                "regime_filter_resolves_5bps_warning": review["decision"]["regime_filter_resolves_5bps_warning"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
