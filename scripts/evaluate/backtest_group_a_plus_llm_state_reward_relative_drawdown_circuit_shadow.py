#!/usr/bin/env python3
"""Relative drawdown circuit shadow for frozen GroupA+ GIFT reward tilt.

The circuit breaker uses only prior OOS relative performance versus equal
weight. If the reward tilt falls behind the equal-weight benchmark beyond a
threshold, it falls back to equal weight until relative performance recovers.
It is no-model, shadow-only, and never emits live target weights or actions.
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
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_relative_drawdown_circuit_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_relative_drawdown_circuit_shadow_backtest/history"


def _fold_circuit_backtest(
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
    relative_drawdown_trigger: float,
    relative_recovery_threshold: float,
    min_circuit_days: int,
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
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_weight = equal_weight.copy()
    circuit_returns: list[float] = []
    baseline_returns: list[float] = []
    turnovers: list[float] = []
    circuit_days = 0
    circuit_entries = 0
    cooldown_remaining = 0
    circuit_on = False
    circuit_equity = 1.0
    baseline_equity = 1.0
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in wide_returns.iterrows():
        relative_gap = circuit_equity / baseline_equity - 1.0 if baseline_equity > 0 else 0.0
        if circuit_on:
            cooldown_remaining = max(0, cooldown_remaining - 1)
            if cooldown_remaining == 0 and relative_gap >= -relative_recovery_threshold:
                circuit_on = False
        elif relative_gap <= -relative_drawdown_trigger:
            circuit_on = True
            cooldown_remaining = max(0, min_circuit_days - 1)
            circuit_entries += 1

        usable_returns = pd.to_numeric(return_row, errors="coerce").fillna(0.0)
        if circuit_on:
            weight = equal_weight.copy()
            circuit_days += 1
        else:
            weight = _weights_from_signal(
                wide_signal.loc[dt],
                low_threshold=low_threshold,
                high_threshold=high_threshold,
                low_score=low_score,
                mid_score=mid_score,
                high_score=high_score,
            )
        turnover = float((weight - previous_weight).abs().sum())
        circuit_return = float((weight * usable_returns).sum() - turnover * cost_rate)
        baseline_return = float((equal_weight * usable_returns).sum())
        circuit_returns.append(circuit_return)
        baseline_returns.append(baseline_return)
        turnovers.append(turnover)
        circuit_equity *= 1.0 + circuit_return
        baseline_equity *= 1.0 + baseline_return
        previous_weight = weight

    circuit_series = pd.Series(circuit_returns, index=wide_returns.index, dtype=float)
    baseline_series = pd.Series(baseline_returns, index=wide_returns.index, dtype=float)
    turnover_series = pd.Series(turnovers, index=wide_returns.index, dtype=float)
    circuit_metrics = _metrics(circuit_series, turnover=turnover_series)
    baseline_metrics = _metrics(baseline_series)
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "test_days": int(len(circuit_series)),
        "circuit_days": int(circuit_days),
        "circuit_entries": int(circuit_entries),
        "circuit_rate": _finite_float(circuit_days / len(circuit_series)) if len(circuit_series) else None,
        "thresholds": {
            "reward_low": _finite_float(low_threshold),
            "reward_high": _finite_float(high_threshold),
            "relative_drawdown_trigger": relative_drawdown_trigger,
            "relative_recovery_threshold": relative_recovery_threshold,
            "min_circuit_days": min_circuit_days,
        },
        "relative_drawdown_circuit": circuit_metrics,
        "equal_weight_baseline": baseline_metrics,
        "delta_vs_equal_weight": {
            "final_value": _finite_float((circuit_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((circuit_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((circuit_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    relative_drawdown_trigger: float = 0.005,
    relative_recovery_threshold: float = 0.001,
    min_circuit_days: int = 5,
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
        _fold_circuit_backtest(
            panel,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=float(inputs.get("low_quantile", 0.30)),
            high_quantile=float(inputs.get("high_quantile", 0.70)),
            low_score=float(inputs.get("low_score", 0.50)),
            mid_score=float(inputs.get("mid_score", 1.00)),
            high_score=float(inputs.get("high_score", 1.50)),
            cost_bps=float(inputs.get("cost_bps", 5.0)),
            relative_drawdown_trigger=relative_drawdown_trigger,
            relative_recovery_threshold=relative_recovery_threshold,
            min_circuit_days=min_circuit_days,
        )
        for fold in folds
    ] if not blockers else []
    for row in fold_rows:
        if row.get("status") != "available_for_manual_offline_review":
            blockers.append(f"fold_not_available:{row.get('fold')}:{row.get('blocking_reason')}")

    circuit_aggregate = _aggregate_folds(fold_rows)
    baseline_aggregate = baseline.get("summary", {}) if baseline else {}
    if circuit_aggregate["available_fold_count"]:
        if circuit_aggregate["positive_final_value_folds"] < min_positive_final_folds:
            warnings.append(
                f"positive_final_value_folds_below_threshold:{circuit_aggregate['positive_final_value_folds']}<{min_positive_final_folds}"
            )
        if circuit_aggregate["positive_sharpe_folds"] < min_positive_sharpe_folds:
            warnings.append(
                f"positive_sharpe_folds_below_threshold:{circuit_aggregate['positive_sharpe_folds']}<{min_positive_sharpe_folds}"
            )
        if circuit_aggregate["non_worse_drawdown_folds"] < min_non_worse_drawdown_folds:
            warnings.append(
                "non_worse_drawdown_folds_below_threshold:"
                f"{circuit_aggregate['non_worse_drawdown_folds']}<{min_non_worse_drawdown_folds}"
            )

    pass_gate = bool(
        not blockers
        and circuit_aggregate["positive_final_value_folds"] >= min_positive_final_folds
        and circuit_aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds
        and circuit_aggregate["non_worse_drawdown_folds"] >= min_non_worse_drawdown_folds
    )
    circuit_rates = [row.get("circuit_rate") for row in fold_rows if row.get("circuit_rate") is not None]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_relative_drawdown_circuit_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "relative_drawdown_circuit_shadow_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "relative_drawdown_trigger": relative_drawdown_trigger,
            "relative_recovery_threshold": relative_recovery_threshold,
            "min_circuit_days": min_circuit_days,
        },
        "summary": {
            "baseline_positive_final_value_folds": baseline_aggregate.get("positive_final_value_folds"),
            "baseline_positive_sharpe_folds": baseline_aggregate.get("positive_sharpe_folds"),
            "baseline_non_worse_drawdown_folds": baseline_aggregate.get("non_worse_drawdown_folds"),
            "relative_drawdown_circuit": circuit_aggregate,
            "delta_relative_drawdown_circuit_minus_baseline": {
                "positive_final_value_folds": (
                    circuit_aggregate["positive_final_value_folds"]
                    - int(baseline_aggregate.get("positive_final_value_folds", 0) or 0)
                ),
                "positive_sharpe_folds": (
                    circuit_aggregate["positive_sharpe_folds"]
                    - int(baseline_aggregate.get("positive_sharpe_folds", 0) or 0)
                ),
                "non_worse_drawdown_folds": (
                    circuit_aggregate["non_worse_drawdown_folds"]
                    - int(baseline_aggregate.get("non_worse_drawdown_folds", 0) or 0)
                ),
            },
            "mean_circuit_rate": _finite_float(np.mean(circuit_rates)) if circuit_rates else None,
            "pass_relative_drawdown_circuit_gate": pass_gate,
        },
        "fold_results": fold_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The circuit uses only prior OOS relative performance versus equal weight before each test-day decision.",
            "It falls back to equal weight during relative drawdown stress and reopens only after recovery.",
            "This report is a shadow diagnostic only and does not authorize live weights.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "relative_drawdown_circuit_ready_for_review": not blockers,
            "relative_drawdown_circuit_passed_shadow_gate": pass_gate,
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
    return history_dir / f"llm_state_reward_interface_relative_drawdown_circuit_shadow_backtest_{stamp}.json"


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
    parser.add_argument("--relative-drawdown-trigger", type=float, default=0.005)
    parser.add_argument("--relative-recovery-threshold", type=float, default=0.001)
    parser.add_argument("--min-circuit-days", type=int, default=5)
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
        relative_drawdown_trigger=args.relative_drawdown_trigger,
        relative_recovery_threshold=args.relative_recovery_threshold,
        min_circuit_days=args.min_circuit_days,
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        min_non_worse_drawdown_folds=args.min_non_worse_drawdown_folds,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward relative drawdown circuit shadow backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "relative_drawdown_circuit": review["summary"]["relative_drawdown_circuit"],
                "mean_circuit_rate": review["summary"]["mean_circuit_rate"],
                "relative_drawdown_circuit_passed_shadow_gate": review["decision"]["relative_drawdown_circuit_passed_shadow_gate"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
