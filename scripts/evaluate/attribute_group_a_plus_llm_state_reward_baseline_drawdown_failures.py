#!/usr/bin/env python3
"""Attribute drawdown failures in the frozen GIFT baseline shadow backtest.

This diagnostic rebuilds the no-model baseline path and explains folds where
max drawdown worsened versus equal weight. It never trains models, outputs live
target weights, or changes rebalance decisions.
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
    _finite_float,
    _load_panel,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_baseline_drawdown_attribution.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_baseline_drawdown_attribution/history"


def _worst_drawdown_date(returns: pd.Series) -> tuple[pd.Timestamp | None, float | None]:
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None, None
    equity = (1.0 + clean).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    idx = drawdown.idxmin()
    return pd.Timestamp(idx), _finite_float(drawdown.loc[idx])


def _rebuild_fold_path(
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
    returns = test.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers)
    signals = (
        panel[panel["ticker"].isin(eligible_tickers)]
        .pivot(index="date", columns="ticker", values="reward_proxy")
        .sort_index()
        .shift(1)
        .reindex(returns.index)
        .reindex(columns=eligible_tickers)
    )
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_weight = equal_weight.copy()
    cost_rate = cost_bps / 10_000.0
    rows: list[dict[str, Any]] = []
    for dt, return_row in returns.iterrows():
        usable_returns = pd.to_numeric(return_row, errors="coerce").fillna(0.0)
        weight = _weights_from_signal(
            signals.loc[dt],
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        turnover = float((weight - previous_weight).abs().sum())
        contribution = weight * usable_returns
        baseline_contribution = equal_weight * usable_returns
        rows.append(
            {
                "date": pd.Timestamp(dt),
                "candidate_return": float(contribution.sum() - turnover * cost_rate),
                "baseline_return": float(baseline_contribution.sum()),
                "turnover": turnover,
                "weights": weight.to_dict(),
                "returns": usable_returns.to_dict(),
                "contribution": contribution.to_dict(),
                "baseline_contribution": baseline_contribution.to_dict(),
                "active_contribution": (contribution - baseline_contribution).to_dict(),
            }
        )
        previous_weight = weight
    path = pd.DataFrame(rows)
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "path": path,
        "thresholds": {
            "low_reward_threshold": _finite_float(low_threshold),
            "high_reward_threshold": _finite_float(high_threshold),
        },
    }


def _attribute_fold(path: pd.DataFrame, *, top_n: int) -> dict[str, Any]:
    candidate_returns = path.set_index("date")["candidate_return"]
    baseline_returns = path.set_index("date")["baseline_return"]
    candidate_trough_date, candidate_mdd = _worst_drawdown_date(candidate_returns)
    baseline_trough_date, baseline_mdd = _worst_drawdown_date(baseline_returns)
    active_returns = candidate_returns - baseline_returns
    active_cumulative = (1.0 + active_returns).cumprod() - 1.0
    worst_active_dates = path.assign(active_return=active_returns.values).nsmallest(top_n, "active_return")

    active_by_ticker: dict[str, float] = {}
    for row in path.itertuples(index=False):
        for ticker, value in row.active_contribution.items():
            active_by_ticker[ticker] = active_by_ticker.get(ticker, 0.0) + float(value)
    worst_tickers = sorted(active_by_ticker.items(), key=lambda item: item[1])[:top_n]

    trough_detail: dict[str, Any] = {}
    if candidate_trough_date is not None:
        row = path[path["date"] == candidate_trough_date].iloc[0]
        trough_detail = {
            "date": candidate_trough_date.date().isoformat(),
            "candidate_return": _finite_float(row["candidate_return"]),
            "baseline_return": _finite_float(row["baseline_return"]),
            "active_return": _finite_float(row["candidate_return"] - row["baseline_return"]),
            "turnover": _finite_float(row["turnover"]),
            "largest_negative_active_tickers": [
                {"ticker": ticker, "active_contribution": _finite_float(value)}
                for ticker, value in sorted(row["active_contribution"].items(), key=lambda item: item[1])[:top_n]
            ],
            "weights": {ticker: _finite_float(value) for ticker, value in row["weights"].items()},
        }

    return {
        "candidate_max_drawdown": candidate_mdd,
        "baseline_max_drawdown": baseline_mdd,
        "delta_max_drawdown": _finite_float((candidate_mdd or 0.0) - (baseline_mdd or 0.0)),
        "candidate_trough_date": candidate_trough_date.date().isoformat() if candidate_trough_date is not None else None,
        "baseline_trough_date": baseline_trough_date.date().isoformat() if baseline_trough_date is not None else None,
        "active_cumulative_return_end": _finite_float(active_cumulative.iloc[-1]) if len(active_cumulative) else None,
        "trough_detail": trough_detail,
        "worst_active_return_dates": [
            {
                "date": row["date"].date().isoformat(),
                "active_return": _finite_float(row["active_return"]),
                "candidate_return": _finite_float(row["candidate_return"]),
                "baseline_return": _finite_float(row["baseline_return"]),
                "turnover": _finite_float(row["turnover"]),
            }
            for _, row in worst_active_dates.iterrows()
        ],
        "worst_active_contribution_tickers": [
            {"ticker": ticker, "active_contribution_sum": _finite_float(value)}
            for ticker, value in worst_tickers
        ],
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    top_n: int = 5,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    baseline = _load_json(baseline_path)
    blockers: list[str] = []
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
    if not eligible_tickers:
        blockers.append("missing_eligible_tickers")
    if {"00631L.TW", "00632R.TW"} & set(eligible_tickers):
        blockers.append("leveraged_or_inverse_ticker_not_excluded")

    fold_results = baseline.get("fold_results") if isinstance(baseline.get("fold_results"), list) else []
    failing_folds = [
        fold
        for fold in fold_results
        if (fold.get("delta_vs_equal_weight") or {}).get("max_drawdown") is not None
        and float((fold.get("delta_vs_equal_weight") or {}).get("max_drawdown")) < 0
    ]
    rows: list[dict[str, Any]] = []
    if not blockers:
        for fold in failing_folds:
            rebuilt = _rebuild_fold_path(
                panel,
                fold,
                eligible_tickers=eligible_tickers,
                low_quantile=float(inputs.get("low_quantile", 0.30)),
                high_quantile=float(inputs.get("high_quantile", 0.70)),
                low_score=float(inputs.get("low_score", 0.50)),
                mid_score=float(inputs.get("mid_score", 1.00)),
                high_score=float(inputs.get("high_score", 1.50)),
                cost_bps=float(inputs.get("cost_bps", 5.0)),
            )
            if rebuilt.get("status") != "available_for_manual_offline_review":
                blockers.append(f"fold_rebuild_failed:{fold.get('fold')}:{rebuilt.get('blocking_reason')}")
                continue
            rows.append(
                {
                    "fold": fold["fold"],
                    "test_start": fold["test_start"],
                    "test_end": fold["test_end"],
                    "baseline_report_delta_max_drawdown": (fold.get("delta_vs_equal_weight") or {}).get("max_drawdown"),
                    "thresholds": rebuilt["thresholds"],
                    "attribution": _attribute_fold(rebuilt["path"], top_n=top_n),
                }
            )

    worst = sorted(
        rows,
        key=lambda row: row["attribution"].get("delta_max_drawdown") or 0.0,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_baseline_drawdown_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "drawdown_failure_attribution_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "top_n": top_n,
        },
        "summary": {
            "baseline_fold_count": len(fold_results),
            "failing_drawdown_fold_count": len(failing_folds),
            "attributed_fold_count": len(rows),
            "worst_fold": worst[0]["fold"] if worst else None,
            "worst_delta_max_drawdown": worst[0]["attribution"].get("delta_max_drawdown") if worst else None,
            "worst_trough_date": worst[0]["attribution"].get("candidate_trough_date") if worst else None,
        },
        "failing_fold_attribution": worst,
        "blocking_reasons": sorted(set(blockers)),
        "interpretation": [
            "Attribution explains why the no-model reward tilt worsened drawdown in specific OOS folds.",
            "Negative active contribution means the reward tilt underweighted winners or overweighted losers versus equal weight.",
            "This report is diagnostic only and does not authorize model training or live allocation changes.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "drawdown_failure_attribution_ready": not blockers,
            "drawdown_issue_requires_additional_risk_control": len(rows) > 0 and not blockers,
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
    return history_dir / f"llm_state_reward_interface_baseline_drawdown_attribution_{stamp}.json"


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
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        top_n=args.top_n,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward baseline drawdown attribution: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "failing_drawdown_fold_count": review["summary"]["failing_drawdown_fold_count"],
                "worst_fold": review["summary"]["worst_fold"],
                "worst_delta_max_drawdown": review["summary"]["worst_delta_max_drawdown"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
