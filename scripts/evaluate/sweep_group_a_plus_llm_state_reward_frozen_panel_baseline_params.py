#!/usr/bin/env python3
"""Sweep no-model baseline parameters for the frozen GroupA+ GIFT panel.

This searches only transparent rule parameters for offline review. It does not
train models, output actions, target weights, or live rebalance decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

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
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_frozen_panel_baseline_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_frozen_panel_baseline_param_sweep/history"


def _score_candidate(aggregate: dict[str, Any]) -> float:
    return float(
        10.0 * aggregate.get("positive_final_value_folds", 0)
        + 8.0 * aggregate.get("positive_sharpe_folds", 0)
        + 6.0 * aggregate.get("non_worse_drawdown_folds", 0)
        + 50.0 * (aggregate.get("mean_delta_final_value") or 0.0)
        + 5.0 * (aggregate.get("mean_delta_sharpe_ratio") or 0.0)
        + 20.0 * (aggregate.get("mean_delta_max_drawdown") or 0.0)
    )


def _prepare_wide(panel, *, eligible_tickers: list[str]) -> dict[str, Any]:
    eligible_panel = panel[panel["ticker"].isin(eligible_tickers)].copy()
    wide_returns = eligible_panel.pivot(index="date", columns="ticker", values="return").sort_index()
    wide_signal = eligible_panel.pivot(index="date", columns="ticker", values="reward_proxy").sort_index().shift(1)
    equal_weight = {ticker: 1.0 / len(eligible_tickers) for ticker in eligible_tickers}
    return {
        "eligible_panel": eligible_panel,
        "wide_returns": wide_returns,
        "wide_signal": wide_signal,
        "equal_weight": equal_weight,
    }


def _fold_backtest_fast(
    prepared: dict[str, Any],
    fold: dict[str, Any],
    *,
    eligible_tickers: list[str],
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    high_score: float,
    cost_bps: float,
) -> dict[str, Any]:
    panel = prepared["eligible_panel"]
    train = panel[
        (panel["date"] >= fold["train_start"])
        & (panel["date"] <= fold["train_end"])
    ]
    train_reward = train["reward_proxy"].replace([float("inf"), float("-inf")], pd.NA).dropna()
    if train_reward.empty:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_reward"}
    low_threshold = float(train_reward.quantile(low_quantile))
    high_threshold = float(train_reward.quantile(high_quantile))
    returns = prepared["wide_returns"].loc[fold["test_start"] : fold["test_end"], eligible_tickers]
    signals = prepared["wide_signal"].reindex(returns.index).loc[:, eligible_tickers]
    if returns.empty:
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_test_frame"}

    equal_weight = prepared["equal_weight"]
    equal_weight_series = pd.Series(equal_weight, dtype=float).reindex(eligible_tickers)
    previous_candidate = equal_weight_series.copy()
    candidate_returns: list[float] = []
    baseline_returns: list[float] = []
    turnovers: list[float] = []
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in returns.iterrows():
        usable_returns = return_row.reindex(eligible_tickers).fillna(0.0)
        candidate_weight = _weights_from_signal(
            signals.loc[dt].reindex(eligible_tickers),
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=1.0,
            high_score=high_score,
        )
        turnover = float((candidate_weight - previous_candidate).abs().sum())
        candidate_returns.append(float((candidate_weight * usable_returns).sum() - turnover * cost_rate))
        baseline_returns.append(float((equal_weight_series * usable_returns).sum()))
        turnovers.append(turnover)
        previous_candidate = candidate_weight

    candidate_series = pd.Series(candidate_returns, index=returns.index, dtype=float)
    baseline_series = pd.Series(baseline_returns, index=returns.index, dtype=float)
    turnover_series = pd.Series(turnovers, index=returns.index, dtype=float)
    candidate_metrics = _metrics(candidate_series, turnover=turnover_series)
    baseline_metrics = _metrics(baseline_series)
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "delta_vs_equal_weight": {
            "final_value": _finite_float((candidate_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((candidate_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((candidate_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
    }


def _evaluate_params(
    prepared: dict[str, Any],
    folds: list[dict[str, Any]],
    *,
    eligible_tickers: list[str],
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    high_score: float,
    cost_bps: float,
) -> dict[str, Any]:
    rows = [
        _fold_backtest_fast(
            prepared,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=low_quantile,
            high_quantile=high_quantile,
            low_score=low_score,
            high_score=high_score,
            cost_bps=cost_bps,
        )
        for fold in folds
    ]
    aggregate = _aggregate_folds(rows)
    return {
        "params": {
            "low_quantile": low_quantile,
            "high_quantile": high_quantile,
            "low_score": low_score,
            "mid_score": 1.0,
            "high_score": high_score,
            "cost_bps": cost_bps,
        },
        "aggregate": aggregate,
        "rank_score": _finite_float(_score_candidate(aggregate)),
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    walk_forward_audit_path: Path = DEFAULT_WF_AUDIT,
    excluded_tickers: list[str] | None = None,
    low_quantiles: list[float] | None = None,
    high_quantiles: list[float] | None = None,
    low_scores: list[float] | None = None,
    high_scores: list[float] | None = None,
    cost_bps_values: list[float] | None = None,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 2,
    top_n: int = 15,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    audit = _load_json(walk_forward_audit_path)
    blockers: list[str] = []
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

    low_quantiles = low_quantiles or [0.30]
    high_quantiles = high_quantiles or [0.70]
    low_scores = low_scores or [0.50, 0.75, 0.90]
    high_scores = high_scores or [1.10, 1.25, 1.50]
    cost_bps_values = cost_bps_values or [5.0]
    grid = [
        row
        for row in product(low_quantiles, high_quantiles, low_scores, high_scores, cost_bps_values)
        if row[0] < row[1] and row[2] <= 1.0 <= row[3]
    ]

    prepared = _prepare_wide(panel, eligible_tickers=eligible_tickers) if not blockers else {}
    rows = [
        _evaluate_params(
            prepared,
            folds,
            eligible_tickers=eligible_tickers,
            low_quantile=low_q,
            high_quantile=high_q,
            low_score=low_s,
            high_score=high_s,
            cost_bps=cost_bps,
        )
        for low_q, high_q, low_s, high_s, cost_bps in grid
    ] if not blockers else []
    ranked = sorted(rows, key=lambda row: row["rank_score"] if row["rank_score"] is not None else -1e9, reverse=True)
    recommended = [
        row
        for row in ranked
        if row["aggregate"]["positive_final_value_folds"] >= min_positive_final_folds
        and row["aggregate"]["positive_sharpe_folds"] >= min_positive_sharpe_folds
        and row["aggregate"]["non_worse_drawdown_folds"] >= min_non_worse_drawdown_folds
    ]
    best = ranked[0] if ranked else None
    best_recommended = recommended[0] if recommended else None

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_baseline_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "baseline_param_sweep_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "walk_forward_audit": str(walk_forward_audit_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": sorted(excluded),
            "grid_size": len(grid),
            "thresholds": {
                "min_positive_final_folds": min_positive_final_folds,
                "min_positive_sharpe_folds": min_positive_sharpe_folds,
                "min_non_worse_drawdown_folds": min_non_worse_drawdown_folds,
            },
        },
        "summary": {
            "evaluated_count": len(rows),
            "recommended_count": len(recommended),
            "best_params": best["params"] if best else None,
            "best_aggregate": best["aggregate"] if best else None,
            "best_recommended_params": best_recommended["params"] if best_recommended else None,
            "best_recommended_aggregate": best_recommended["aggregate"] if best_recommended else None,
        },
        "top_candidates": ranked[:top_n],
        "recommended_candidates": recommended[:top_n],
        "blocking_reasons": sorted(set(blockers)),
        "interpretation": [
            "This sweep searches transparent no-model reward-tilt parameters only.",
            "Recommended candidates must preserve return and Sharpe fold counts while improving drawdown fold count.",
            "Any selected parameters require a separate frozen baseline review before model design.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "baseline_param_sweep_ready_for_review": not blockers,
            "recommended_baseline_variant_available": bool(best_recommended) and not blockers,
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
    return history_dir / f"llm_state_reward_interface_frozen_panel_baseline_param_sweep_{stamp}.json"


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


def _float_list(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--walk-forward-audit", default=str(DEFAULT_WF_AUDIT))
    parser.add_argument("--exclude-ticker", action="append", default=[])
    parser.add_argument("--low-quantiles", default=None)
    parser.add_argument("--high-quantiles", default=None)
    parser.add_argument("--low-scores", default=None)
    parser.add_argument("--high-scores", default=None)
    parser.add_argument("--cost-bps-values", default=None)
    parser.add_argument("--min-positive-final-folds", type=int, default=4)
    parser.add_argument("--min-positive-sharpe-folds", type=int, default=4)
    parser.add_argument("--min-non-worse-drawdown-folds", type=int, default=2)
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        walk_forward_audit_path=_resolve(args.walk_forward_audit),
        excluded_tickers=args.exclude_ticker or None,
        low_quantiles=_float_list(args.low_quantiles),
        high_quantiles=_float_list(args.high_quantiles),
        low_scores=_float_list(args.low_scores),
        high_scores=_float_list(args.high_scores),
        cost_bps_values=_float_list(args.cost_bps_values),
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        min_non_worse_drawdown_folds=args.min_non_worse_drawdown_folds,
        top_n=args.top_n,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward frozen panel baseline param sweep: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "evaluated_count": review["summary"]["evaluated_count"],
                "recommended_count": review["summary"]["recommended_count"],
                "best_recommended_params": review["summary"]["best_recommended_params"],
                "recommended_baseline_variant_available": review["decision"]["recommended_baseline_variant_available"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
