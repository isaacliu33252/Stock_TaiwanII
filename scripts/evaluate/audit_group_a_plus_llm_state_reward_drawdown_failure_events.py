#!/usr/bin/env python3
"""Audit event windows around GIFT reward-tilt drawdown failures.

The audit rebuilds failing OOS folds from the frozen panel and records the
pre/post-trough event path: active weights, active return contribution, bucket
exposures, and reward-signal concentration. It is research-only and does not
train models, output live weights, or change strategy targets.
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
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import (  # noqa: E402
    BOND_BUCKET,
    HIGH_DIVIDEND_BUCKET,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_drawdown_failure_event_audit.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_drawdown_failure_event_audit/history"
BUCKETS = {
    "market_core": ["0050.TW"],
    "high_dividend": HIGH_DIVIDEND_BUCKET,
    "bond": BOND_BUCKET,
}


def _bucket_sum(values: pd.Series, tickers: list[str]) -> float:
    present = [ticker for ticker in tickers if ticker in values.index]
    return float(values.reindex(present).fillna(0.0).sum()) if present else 0.0


def _max_drawdown_date(returns: pd.Series) -> pd.Timestamp | None:
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    equity = (1.0 + clean).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return pd.Timestamp(drawdown.idxmin())


def _signal_concentration(weight: pd.Series, equal_weight: pd.Series) -> float | None:
    active = (weight - equal_weight).clip(lower=0.0)
    total = float(active.sum())
    if total <= 0:
        return 0.0
    share = active / total
    return _finite_float(float((share**2).sum()))


def _rebuild_event_path(
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
) -> tuple[pd.DataFrame, dict[str, Any]]:
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
        return pd.DataFrame(), {"blocking_reason": "empty_train_reward_or_test_frame"}

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
    drawdowns = (
        panel[panel["ticker"].isin(eligible_tickers)]
        .pivot(index="date", columns="ticker", values="drawdown_depth")
        .sort_index()
        .shift(1)
        .reindex(returns.index)
        .reindex(columns=eligible_tickers)
    )
    vols = (
        panel[panel["ticker"].isin(eligible_tickers)]
        .pivot(index="date", columns="ticker", values="realized_volatility")
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
        signal_row = signals.loc[dt].reindex(eligible_tickers)
        weight = _weights_from_signal(
            signal_row,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        turnover = float((weight - previous_weight).abs().sum())
        baseline_contrib = equal_weight * usable_returns
        candidate_contrib = weight * usable_returns
        active_contrib = candidate_contrib - baseline_contrib
        active_weight = weight - equal_weight
        rows.append(
            {
                "date": pd.Timestamp(dt),
                "candidate_return": float(candidate_contrib.sum() - turnover * cost_rate),
                "baseline_return": float(baseline_contrib.sum()),
                "active_return_before_cost": float(active_contrib.sum()),
                "turnover": turnover,
                "turnover_cost": turnover * cost_rate,
                "reward_signal": signal_row.to_dict(),
                "weights": weight.to_dict(),
                "active_weight": active_weight.to_dict(),
                "returns": usable_returns.to_dict(),
                "active_contribution": active_contrib.to_dict(),
                "lagged_drawdown_depth": pd.to_numeric(drawdowns.loc[dt], errors="coerce").to_dict(),
                "lagged_realized_volatility": pd.to_numeric(vols.loc[dt], errors="coerce").to_dict(),
                "positive_active_weight_hhi": _signal_concentration(weight, equal_weight),
                "bucket_active_weight": {
                    name: _bucket_sum(active_weight, tickers) for name, tickers in BUCKETS.items()
                },
                "bucket_active_contribution": {
                    name: _bucket_sum(active_contrib, tickers) for name, tickers in BUCKETS.items()
                },
            }
        )
        previous_weight = weight
    return pd.DataFrame(rows), {
        "low_reward_threshold": _finite_float(low_threshold),
        "high_reward_threshold": _finite_float(high_threshold),
    }


def _event_window(path: pd.DataFrame, *, trough_date: pd.Timestamp, window: int, top_n: int) -> dict[str, Any]:
    dates = list(path["date"])
    trough_idx = dates.index(trough_date)
    start = max(0, trough_idx - window)
    end = min(len(path), trough_idx + window + 1)
    event = path.iloc[start:end].copy()
    rows: list[dict[str, Any]] = []
    for _, row in event.iterrows():
        active_contrib = row["active_contribution"]
        active_weight = row["active_weight"]
        reward_signal = row["reward_signal"]
        rows.append(
            {
                "date": row["date"].date().isoformat(),
                "days_from_trough": int((row["date"] - trough_date).days),
                "candidate_return": _finite_float(row["candidate_return"]),
                "baseline_return": _finite_float(row["baseline_return"]),
                "active_return_after_cost": _finite_float(row["candidate_return"] - row["baseline_return"]),
                "active_return_before_cost": _finite_float(row["active_return_before_cost"]),
                "turnover": _finite_float(row["turnover"]),
                "turnover_cost": _finite_float(row["turnover_cost"]),
                "positive_active_weight_hhi": row["positive_active_weight_hhi"],
                "bucket_active_weight": {
                    name: _finite_float(value) for name, value in row["bucket_active_weight"].items()
                },
                "bucket_active_contribution": {
                    name: _finite_float(value) for name, value in row["bucket_active_contribution"].items()
                },
                "worst_active_contribution_tickers": [
                    {
                        "ticker": ticker,
                        "active_contribution": _finite_float(value),
                        "active_weight": _finite_float(active_weight.get(ticker)),
                        "reward_signal": _finite_float(reward_signal.get(ticker)),
                    }
                    for ticker, value in sorted(active_contrib.items(), key=lambda item: item[1])[:top_n]
                ],
                "largest_active_overweight_tickers": [
                    {
                        "ticker": ticker,
                        "active_weight": _finite_float(value),
                        "active_contribution": _finite_float(active_contrib.get(ticker)),
                        "reward_signal": _finite_float(reward_signal.get(ticker)),
                    }
                    for ticker, value in sorted(active_weight.items(), key=lambda item: item[1], reverse=True)[:top_n]
                    if value > 0
                ],
            }
        )
    active_by_bucket = {
        name: float(sum(row["bucket_active_contribution"][name] for _, row in event.iterrows()))
        for name in BUCKETS
    }
    active_weight_by_bucket = {
        name: float(np.mean([row["bucket_active_weight"][name] for _, row in event.iterrows()]))
        for name in BUCKETS
    }
    worst_days = sorted(rows, key=lambda row: row["active_return_after_cost"] or 0.0)[:top_n]
    return {
        "event_start": event.iloc[0]["date"].date().isoformat(),
        "event_end": event.iloc[-1]["date"].date().isoformat(),
        "event_days": int(len(event)),
        "window_pre_post_observations": window,
        "sum_active_contribution_by_bucket": {
            name: _finite_float(value) for name, value in active_by_bucket.items()
        },
        "mean_active_weight_by_bucket": {
            name: _finite_float(value) for name, value in active_weight_by_bucket.items()
        },
        "worst_active_return_days": worst_days,
        "daily_events": rows,
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    window: int = 10,
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
            path, thresholds = _rebuild_event_path(
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
            if path.empty:
                blockers.append(f"fold_event_path_failed:{fold.get('fold')}:{thresholds.get('blocking_reason')}")
                continue
            trough_date = _max_drawdown_date(path.set_index("date")["candidate_return"])
            if trough_date is None:
                blockers.append(f"fold_trough_missing:{fold.get('fold')}")
                continue
            event = _event_window(path, trough_date=trough_date, window=window, top_n=top_n)
            rows.append(
                {
                    "fold": fold["fold"],
                    "test_start": fold["test_start"],
                    "test_end": fold["test_end"],
                    "baseline_report_delta_max_drawdown": (fold.get("delta_vs_equal_weight") or {}).get("max_drawdown"),
                    "candidate_trough_date": trough_date.date().isoformat(),
                    "thresholds": thresholds,
                    "event_window": event,
                }
            )

    bucket_totals: dict[str, float] = {name: 0.0 for name in BUCKETS}
    bucket_weight_means: dict[str, list[float]] = {name: [] for name in BUCKETS}
    worst_fold = None
    if rows:
        worst_fold = min(rows, key=lambda row: row["baseline_report_delta_max_drawdown"] or 0.0)
        for row in rows:
            event = row["event_window"]
            for name, value in event["sum_active_contribution_by_bucket"].items():
                bucket_totals[name] += float(value or 0.0)
            for name, value in event["mean_active_weight_by_bucket"].items():
                bucket_weight_means[name].append(float(value or 0.0))

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_drawdown_failure_event_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "drawdown_failure_event_audit_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "window": window,
            "top_n": top_n,
        },
        "summary": {
            "baseline_fold_count": len(fold_results),
            "failing_drawdown_fold_count": len(failing_folds),
            "audited_failing_fold_count": len(rows),
            "worst_fold": worst_fold["fold"] if worst_fold else None,
            "worst_fold_trough_date": worst_fold["candidate_trough_date"] if worst_fold else None,
            "worst_fold_delta_max_drawdown": worst_fold["baseline_report_delta_max_drawdown"] if worst_fold else None,
            "event_sum_active_contribution_by_bucket": {
                name: _finite_float(value) for name, value in bucket_totals.items()
            },
            "event_mean_active_weight_by_bucket": {
                name: _finite_float(np.mean(values)) if values else None
                for name, values in bucket_weight_means.items()
            },
            "dominant_negative_event_bucket": (
                min(bucket_totals.items(), key=lambda item: item[1])[0] if rows else None
            ),
        },
        "failing_fold_events": sorted(rows, key=lambda row: row["baseline_report_delta_max_drawdown"] or 0.0),
        "blocking_reasons": sorted(set(blockers)),
        "interpretation": [
            "Event windows use prior-day reward signals and lagged panel features only.",
            "Positive active weight means reward tilt overweight versus equal weight.",
            "Negative active contribution identifies where active allocation hurt drawdown versus equal weight.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "state_redesign_diagnostic_ready": not blockers,
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
    return history_dir / f"llm_state_reward_interface_drawdown_failure_event_audit_{stamp}.json"


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
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        window=args.window,
        top_n=args.top_n,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward drawdown failure event audit: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "summary": review["summary"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
