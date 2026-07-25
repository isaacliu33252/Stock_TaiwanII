#!/usr/bin/env python3
"""Baseline shadow backtest for the frozen GroupA+ GIFT state/reward panel.

This is a no-model OOS check. It uses each fold's training window only to set
reward quantile thresholds, then applies prior-day frozen rewards in the test
window. It never outputs live target weights or rebalance decisions.
"""

from __future__ import annotations

import argparse
import hashlib
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
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_frozen_panel_baseline_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_frozen_panel_baseline_shadow_backtest/history"
DEFAULT_EXCLUDED_TICKERS = ["00631L.TW", "00632R.TW"]


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _load_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    panel = pd.read_parquet(path)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values(["date", "ticker"]).reset_index(drop=True)


def _metrics(returns: pd.Series, *, turnover: pd.Series | None = None) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return {
            "final_value": None,
            "total_return": None,
            "annual_return": None,
            "annual_volatility": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "worst_daily_return": None,
            "mean_daily_turnover": None,
            "total_turnover": None,
        }
    equity = (1.0 + clean).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    years = len(clean) / 252.0
    ann_return = equity.iloc[-1] ** (1.0 / years) - 1.0 if years > 0 else np.nan
    ann_vol = clean.std(ddof=0) * np.sqrt(252)
    sharpe = ann_return / ann_vol if ann_vol > 0 else np.nan
    turnover_clean = (
        pd.to_numeric(turnover, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if turnover is not None
        else pd.Series(dtype=float)
    )
    return {
        "final_value": _finite_float(equity.iloc[-1]),
        "total_return": _finite_float(equity.iloc[-1] - 1.0),
        "annual_return": _finite_float(ann_return),
        "annual_volatility": _finite_float(ann_vol),
        "sharpe_ratio": _finite_float(sharpe),
        "max_drawdown": _finite_float(drawdown.min()),
        "worst_daily_return": _finite_float(clean.min()),
        "mean_daily_turnover": _finite_float(turnover_clean.mean()) if len(turnover_clean) else 0.0,
        "total_turnover": _finite_float(turnover_clean.sum()) if len(turnover_clean) else 0.0,
    }


def _weights_from_signal(
    reward_signal: pd.Series,
    *,
    low_threshold: float,
    high_threshold: float,
    low_score: float,
    mid_score: float,
    high_score: float,
) -> pd.Series:
    signal = pd.to_numeric(reward_signal, errors="coerce")
    scores = pd.Series(mid_score, index=signal.index, dtype=float)
    scores[signal <= low_threshold] = low_score
    scores[signal >= high_threshold] = high_score
    scores = scores.where(signal.notna(), mid_score).clip(lower=0.0)
    if scores.sum() <= 0:
        return pd.Series(1.0 / len(scores), index=scores.index, dtype=float)
    return scores / scores.sum()


def _fold_backtest(
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
        return {
            "fold": fold["fold"],
            "status": "blocked",
            "blocking_reason": "empty_train_reward_or_test_frame",
        }
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
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_candidate = equal_weight.copy()
    candidate_returns: list[float] = []
    baseline_returns: list[float] = []
    turnovers: list[float] = []
    dates: list[pd.Timestamp] = []
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in wide_returns.iterrows():
        usable_returns = pd.to_numeric(return_row.reindex(eligible_tickers), errors="coerce").fillna(0.0)
        signal_row = wide_signal.loc[dt].reindex(eligible_tickers)
        candidate_weight = _weights_from_signal(
            signal_row,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        turnover = float((candidate_weight - previous_candidate).abs().sum())
        candidate_return = float((candidate_weight * usable_returns).sum() - turnover * cost_rate)
        baseline_return = float((equal_weight * usable_returns).sum())
        candidate_returns.append(candidate_return)
        baseline_returns.append(baseline_return)
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
        "thresholds": {
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_reward_threshold": _finite_float(low_threshold),
            "high_reward_threshold": _finite_float(high_threshold),
        },
        "candidate": candidate_metrics,
        "equal_weight_baseline": baseline_metrics,
        "delta_vs_equal_weight": {
            "final_value": _finite_float((candidate_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((candidate_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((candidate_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
    }


def _aggregate_folds(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in rows if row.get("status") == "available_for_manual_offline_review"]
    deltas = [row["delta_vs_equal_weight"] for row in available]
    return {
        "fold_count": len(rows),
        "available_fold_count": len(available),
        "positive_final_value_folds": int(sum((delta.get("final_value") or 0.0) > 0 for delta in deltas)),
        "positive_sharpe_folds": int(sum((delta.get("sharpe_ratio") or 0.0) > 0 for delta in deltas)),
        "non_worse_drawdown_folds": int(sum((delta.get("max_drawdown") or 0.0) >= 0 for delta in deltas)),
        "mean_delta_final_value": _finite_float(np.mean([delta.get("final_value") for delta in deltas])) if deltas else None,
        "mean_delta_sharpe_ratio": _finite_float(np.mean([delta.get("sharpe_ratio") for delta in deltas])) if deltas else None,
        "mean_delta_max_drawdown": _finite_float(np.mean([delta.get("max_drawdown") for delta in deltas])) if deltas else None,
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    excluded_tickers: list[str] | None = None,
    low_quantile: float = 0.30,
    high_quantile: float = 0.70,
    low_score: float = 0.50,
    mid_score: float = 1.00,
    high_score: float = 1.50,
    cost_bps: float = 5.0,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
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

    fold_rows = [
        _fold_backtest(
            panel,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=low_quantile,
            high_quantile=high_quantile,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
            cost_bps=cost_bps,
        )
        for fold in folds
    ] if not blockers else []
    for row in fold_rows:
        if row.get("status") != "available_for_manual_offline_review":
            blockers.append(f"fold_not_available:{row.get('fold')}:{row.get('blocking_reason')}")

    aggregate = _aggregate_folds(fold_rows)
    if aggregate["available_fold_count"]:
        if aggregate["positive_final_value_folds"] < min_positive_final_folds:
            warnings.append(
                f"positive_final_value_folds_below_threshold:{aggregate['positive_final_value_folds']}<{min_positive_final_folds}"
            )
        if aggregate["positive_sharpe_folds"] < min_positive_sharpe_folds:
            warnings.append(
                f"positive_sharpe_folds_below_threshold:{aggregate['positive_sharpe_folds']}<{min_positive_sharpe_folds}"
            )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_baseline_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "baseline_shadow_backtest_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "walk_forward_audit": str(walk_forward_audit_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": sorted(excluded),
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_score": low_score,
            "mid_score": mid_score,
            "high_score": high_score,
            "cost_bps": cost_bps,
        },
        "summary": aggregate
        | {
            "candidate_rule": "train_quantile_reward_tilt_prior_day_signal",
            "baseline_rule": "equal_weight_eligible_tickers",
            "pass_min_positive_final_folds": aggregate["positive_final_value_folds"] >= min_positive_final_folds
            if aggregate["available_fold_count"]
            else False,
            "pass_min_positive_sharpe_folds": aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds
            if aggregate["available_fold_count"]
            else False,
        },
        "fold_results": fold_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "This rule is a no-model sanity baseline for the frozen state/reward interface.",
            "Signals are lagged one trading date before being applied to test returns.",
            "The result can justify further shadow research only; it is not a live allocation rule.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "baseline_shadow_backtest_ready_for_review": not blockers,
            "next_shadow_model_design_allowed": not blockers
            and aggregate["positive_final_value_folds"] >= min_positive_final_folds
            and aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds,
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
    return history_dir / f"llm_state_reward_interface_frozen_panel_baseline_shadow_backtest_{stamp}.json"


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
    parser.add_argument("--low-quantile", type=float, default=0.30)
    parser.add_argument("--high-quantile", type=float, default=0.70)
    parser.add_argument("--low-score", type=float, default=0.50)
    parser.add_argument("--mid-score", type=float, default=1.00)
    parser.add_argument("--high-score", type=float, default=1.50)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--min-positive-final-folds", type=int, default=4)
    parser.add_argument("--min-positive-sharpe-folds", type=int, default=4)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        excluded_tickers=args.exclude_ticker or None,
        low_quantile=args.low_quantile,
        high_quantile=args.high_quantile,
        low_score=args.low_score,
        mid_score=args.mid_score,
        high_score=args.high_score,
        cost_bps=args.cost_bps,
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward frozen panel baseline shadow backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "available_fold_count": review["summary"]["available_fold_count"],
                "positive_final_value_folds": review["summary"]["positive_final_value_folds"],
                "positive_sharpe_folds": review["summary"]["positive_sharpe_folds"],
                "next_shadow_model_design_allowed": review["decision"]["next_shadow_model_design_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
