#!/usr/bin/env python3
"""Shadow-evaluate 00631L-vs-0050 relative re-entry opportunities.

Research-only. This does not update live signals or execution plans.

The baseline is holding 0050. Candidate actions move a small fixed slice from
0050 into 00631L, then label whether that relative risk-up action helped over
the forward horizon after drawdown and turnover penalties.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    _fit_predict_linear,
    _load_panel,
    _predict_action_error_percentiles,
    _predict_action_regrets,
    _resolve,
    _utility,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date


DEFAULT_PANEL = "results/ncf_00631l_panel_latest_20260804.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_0050_relative_reentry_opportunity_latest.json"
DEFAULT_ACTIONS = ("KEEP", "SHIFT_00631L_2", "SHIFT_00631L_5", "SHIFT_00631L_10")
FEATURE_COLUMNS = (
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "confidence",
    "ret_0050_1d",
    "ret_0050_5d",
    "ret_0050_20d",
    "ret_00631l_1d",
    "ret_00631l_5d",
    "ret_00631l_20d",
    "spread_00631l_0050_1d",
    "spread_00631l_0050_5d",
    "spread_00631l_0050_20d",
    "vol_0050_20d",
    "vol_00631l_20d",
    "drawdown_0050_60d",
    "drawdown_00631l_60d",
)


def _parse_shift_step(action: str) -> float | None:
    prefix = "SHIFT_00631L_"
    if action == "KEEP":
        return None
    if not action.startswith(prefix):
        raise ValueError(f"Unsupported action: {action}")
    try:
        step = float(action.removeprefix(prefix)) / 100.0
    except ValueError as exc:
        raise ValueError(f"Unsupported action: {action}") from exc
    if step <= 0.0 or step > 1.0:
        raise ValueError(f"Unsupported action: {action}")
    return step


def _relative_weights(step: float) -> dict[str, float]:
    return {
        "0050.TW": max(1.0 - float(step), 0.0),
        "00631L.TW": min(max(float(step), 0.0), 1.0),
        "00632R.TW": 0.0,
        "00679B.TWO": 0.0,
        "cash": 0.0,
    }


def _load_trading_index(db_path: Path, start: str, end: str) -> pd.DatetimeIndex:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt, count(DISTINCT ticker) AS ticker_count
            FROM ohlcv
            WHERE ticker IN ('0050.TW', '00631L.TW', '00632R.TW', '00679B.TWO')
              AND dt BETWEEN ? AND ?
            GROUP BY dt
            HAVING ticker_count = 4
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No complete GroupA price dates between {start} and {end}")
    return pd.DatetimeIndex(pd.to_datetime(frame["dt"]))


def build_relative_features(
    prices: pd.DataFrame,
    panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for pos, dt in enumerate(prices.index):
        panel_row = panel.loc[dt] if panel is not None and dt in panel.index else pd.Series(dtype=float)

        def ret(ticker: str, lookback: int) -> float:
            if pos < lookback:
                return 0.0
            return float(prices.iloc[pos][ticker] / prices.iloc[pos - lookback][ticker] - 1.0)

        def vol(ticker: str, lookback: int) -> float:
            if pos < lookback:
                return 0.0
            returns = prices[ticker].pct_change().iloc[max(0, pos - lookback + 1) : pos + 1]
            return float(returns.std(ddof=0) * np.sqrt(252.0)) if len(returns.dropna()) else 0.0

        def drawdown(ticker: str, lookback: int) -> float:
            start = max(0, pos - lookback + 1)
            window = prices[ticker].iloc[start : pos + 1]
            peak = float(window.max()) if len(window) else float(prices.iloc[pos][ticker])
            return float(prices.iloc[pos][ticker] / max(peak, 1e-12) - 1.0)

        ret_0050_1d = ret("0050.TW", 1)
        ret_0050_5d = ret("0050.TW", 5)
        ret_0050_20d = ret("0050.TW", 20)
        ret_00631l_1d = ret("00631L.TW", 1)
        ret_00631l_5d = ret("00631L.TW", 5)
        ret_00631l_20d = ret("00631L.TW", 20)
        rows.append(
            {
                "prob_up_h1": float(panel_row.get("prob_up_h1", 0.5) or 0.5),
                "prob_up_h5": float(panel_row.get("prob_up_h5", 0.5) or 0.5),
                "prob_up_h20": float(panel_row.get("prob_up_h20", 0.5) or 0.5),
                "prob_fwd_mdd_gt5_h20": float(panel_row.get("prob_fwd_mdd_gt5_h20", 0.0) or 0.0),
                "prob_fwd_gain_gt5_h20": float(panel_row.get("prob_fwd_gain_gt5_h20", 0.5) or 0.5),
                "confidence": float(panel_row.get("confidence", 0.5) or 0.5),
                "ret_0050_1d": ret_0050_1d,
                "ret_0050_5d": ret_0050_5d,
                "ret_0050_20d": ret_0050_20d,
                "ret_00631l_1d": ret_00631l_1d,
                "ret_00631l_5d": ret_00631l_5d,
                "ret_00631l_20d": ret_00631l_20d,
                "spread_00631l_0050_1d": ret_00631l_1d - ret_0050_1d,
                "spread_00631l_0050_5d": ret_00631l_5d - ret_0050_5d,
                "spread_00631l_0050_20d": ret_00631l_20d - ret_0050_20d,
                "vol_0050_20d": vol("0050.TW", 20),
                "vol_00631l_20d": vol("00631L.TW", 20),
                "drawdown_0050_60d": drawdown("0050.TW", 60),
                "drawdown_00631l_60d": drawdown("00631L.TW", 60),
            }
        )
    return pd.DataFrame(rows, index=prices.index).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_relative_labels(
    prices: pd.DataFrame,
    *,
    horizon: int,
    lambda_mdd: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    actions: tuple[str, ...],
) -> pd.DataFrame:
    keep_weights = _relative_weights(0.0)
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for dt in prices.index:
        pos = int(prices.index.get_loc(dt))
        if pos + int(horizon) >= len(prices):
            continue
        row: dict[str, float] = {}
        for action in actions:
            step = _parse_shift_step(action)
            action_weights = keep_weights if step is None else _relative_weights(step)
            result = _utility(
                prices,
                pos,
                action_weights=action_weights,
                keep_weights=keep_weights,
                horizon=int(horizon),
                lambda_mdd=float(lambda_mdd),
                gamma_turnover=float(gamma_turnover),
                eta_missed_rebound=float(eta_missed_rebound),
            )
            row[action] = 0.0 if action == "KEEP" else float(result["action_regret"])
        rows.append(row)
        index.append(dt)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index))


def select_relative_actions(
    predicted_regrets: pd.DataFrame,
    *,
    edge_threshold: float,
    regret_clip: float,
    actions: tuple[str, ...],
    reliability_percentiles: pd.DataFrame | None = None,
    max_error_percentile: float = 1.0,
    action_allowed: pd.Series | None = None,
    block_reasons: pd.Series | None = None,
    permission_probability: pd.Series | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dt in predicted_regrets.index:
        preds = {
            action: float(np.clip(predicted_regrets.loc[dt].get(action, 0.0), -float(regret_clip), float(regret_clip)))
            for action in actions
        }
        preds["KEEP"] = 0.0
        best = max(actions, key=lambda action: (preds[action], action == "KEEP"))
        reliability_percentile = None
        reliability_gate_pass = True
        allowed = True if action_allowed is None else bool(action_allowed.loc[dt])
        block_reason = None if block_reasons is None else block_reasons.loc[dt]
        permission_prob = None if permission_probability is None else float(permission_probability.loc[dt])
        candidate = best
        if not allowed and best != "KEEP":
            best = "KEEP"
        if best != "KEEP" and preds[best] <= float(edge_threshold):
            best = "KEEP"
        if best != "KEEP" and reliability_percentiles is not None:
            reliability_percentile = float(reliability_percentiles.loc[dt].get(best, 1.0))
            reliability_gate_pass = reliability_percentile <= float(max_error_percentile)
            if not reliability_gate_pass:
                best = "KEEP"
        rows.append(
            {
                "date": str(dt.date()),
                "action": best,
                "shift_00631l_weight": 0.0 if best == "KEEP" else float(_parse_shift_step(best) or 0.0),
                "predicted_regret": float(preds[best]),
                "predicted_regrets": preds,
                "candidate_action_before_reliability": candidate,
                "candidate_predicted_regret_before_reliability": float(preds[candidate]),
                "reliability_error_percentile": reliability_percentile,
                "reliability_gate_pass": bool(reliability_gate_pass),
                "action_allowed": bool(allowed),
                "block_reason": None if pd.isna(block_reason) else block_reason,
                "risk_up_permission_probability": permission_prob,
            }
        )
    return pd.DataFrame(rows)


def slow_bear_reentry_allowed(
    features: pd.DataFrame,
    *,
    enabled: bool,
    drawdown_0050_60d_max: float,
    ret_0050_20d_max: float,
    spread_00631l_0050_20d_max: float,
    momentum_ret_0050_20d_max: float,
) -> tuple[pd.Series, pd.Series]:
    if not enabled:
        return pd.Series(True, index=features.index, dtype=bool), pd.Series(None, index=features.index, dtype=object)
    deep_drawdown = (
        (features["drawdown_0050_60d"] <= float(drawdown_0050_60d_max))
        & (features["ret_0050_20d"] < float(ret_0050_20d_max))
    )
    momentum_breakdown = (
        (features["ret_0050_20d"] <= float(momentum_ret_0050_20d_max))
        & (features["spread_00631l_0050_20d"] < float(spread_00631l_0050_20d_max))
    )
    blocked = deep_drawdown | momentum_breakdown
    reasons = pd.Series(None, index=features.index, dtype=object)
    reasons.loc[deep_drawdown] = (
        "slow_bear_block:deep_drawdown:"
        f"drawdown_0050_60d<={float(drawdown_0050_60d_max):.4f},"
        f"ret_0050_20d<{float(ret_0050_20d_max):.4f}"
    )
    reasons.loc[momentum_breakdown] = (
        "slow_bear_block:momentum_breakdown:"
        f"ret_0050_20d<={float(momentum_ret_0050_20d_max):.4f},"
        f"spread_00631l_0050_20d<{float(spread_00631l_0050_20d_max):.4f}"
    )
    return ~blocked, reasons


def build_permission_labels(
    labels: pd.DataFrame,
    *,
    action: str,
    min_realized_edge: float,
) -> pd.Series:
    if action not in labels.columns:
        raise ValueError(f"Permission action {action} missing from labels")
    return (labels[action].astype(float) > float(min_realized_edge)).astype(float)


def predict_permission_probability(
    features: pd.DataFrame,
    permission_labels: pd.Series,
    *,
    min_train_days: int,
    train_window_days: int,
    ridge_alpha: float,
    feature_columns: tuple[str, ...] = FEATURE_COLUMNS,
) -> pd.Series:
    values: list[float] = []
    for dt in features.index:
        past_idx = permission_labels.index[permission_labels.index < dt]
        if train_window_days > 0:
            past_idx = past_idx[-int(train_window_days):]
        if len(past_idx) < int(min_train_days):
            values.append(0.5)
            continue
        pred = _fit_predict_linear(
            features.loc[past_idx, list(feature_columns)],
            permission_labels.loc[past_idx],
            features.loc[dt, list(feature_columns)],
            ridge_alpha=ridge_alpha,
        )
        values.append(float(np.clip(pred, 0.0, 1.0)))
    return pd.Series(values, index=features.index, dtype=float)


def risk_up_permission_allowed(
    probability: pd.Series,
    *,
    enabled: bool,
    min_probability: float,
) -> tuple[pd.Series, pd.Series]:
    if not enabled:
        return pd.Series(True, index=probability.index, dtype=bool), pd.Series(None, index=probability.index, dtype=object)
    allowed = probability >= float(min_probability)
    reasons = pd.Series(None, index=probability.index, dtype=object)
    reasons.loc[~allowed] = (
        "risk_up_permission_block:"
        f"probability<{float(min_probability):.4f}"
    )
    return allowed, reasons


def _action_counts(decisions: pd.DataFrame) -> dict[str, int]:
    if decisions.empty:
        return {}
    return {str(k): int(v) for k, v in decisions["action"].value_counts().sort_index().items()}


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    panel_path: str | None,
    horizon: int,
    min_train_days: int,
    train_window_days: int,
    ridge_alpha: float,
    edge_threshold: float,
    regret_clip: float,
    lambda_mdd: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    actions: tuple[str, ...],
    selective_reliability: bool,
    reliability_max_error_percentile: float,
    reliability_min_train_days: int,
    slow_bear_gate: bool,
    slow_bear_drawdown_0050_60d_max: float,
    slow_bear_ret_0050_20d_max: float,
    slow_bear_spread_00631l_0050_20d_max: float,
    slow_bear_momentum_ret_0050_20d_max: float,
    risk_up_permission_gate: bool,
    risk_up_permission_action: str,
    risk_up_permission_min_probability: float,
    risk_up_permission_min_realized_edge: float,
    risk_up_permission_min_train_days: int,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    index = _load_trading_index(db_path, start, resolved_end)
    actual_end = str(index.max().date())
    prices, dividend_coverage = _load_total_return_prices(db_path, index)
    panel = _load_panel(panel_path) if panel_path else None
    features = build_relative_features(prices, panel)
    labels = build_relative_labels(
        prices,
        horizon=horizon,
        lambda_mdd=lambda_mdd,
        gamma_turnover=gamma_turnover,
        eta_missed_rebound=eta_missed_rebound,
        actions=actions,
    )
    features_for_prediction = features.reindex(features.index).fillna(0.0)
    predicted = _predict_action_regrets(
        features_for_prediction,
        labels,
        min_train_days=min_train_days,
        train_window_days=train_window_days,
        ridge_alpha=ridge_alpha,
        regret_clip=regret_clip,
        actions=actions,
        feature_columns=FEATURE_COLUMNS,
    )
    reliability = (
        _predict_action_error_percentiles(
            features_for_prediction,
            labels,
            predicted,
            min_train_days=reliability_min_train_days,
            train_window_days=train_window_days,
            ridge_alpha=ridge_alpha,
            actions=actions,
            feature_columns=FEATURE_COLUMNS,
        )
        if selective_reliability
        else None
    )
    action_allowed, block_reasons = slow_bear_reentry_allowed(
        features_for_prediction,
        enabled=slow_bear_gate,
        drawdown_0050_60d_max=slow_bear_drawdown_0050_60d_max,
        ret_0050_20d_max=slow_bear_ret_0050_20d_max,
        spread_00631l_0050_20d_max=slow_bear_spread_00631l_0050_20d_max,
        momentum_ret_0050_20d_max=slow_bear_momentum_ret_0050_20d_max,
    )
    permission_labels = build_permission_labels(
        labels,
        action=risk_up_permission_action,
        min_realized_edge=risk_up_permission_min_realized_edge,
    )
    permission_probability = predict_permission_probability(
        features_for_prediction,
        permission_labels,
        min_train_days=risk_up_permission_min_train_days,
        train_window_days=train_window_days,
        ridge_alpha=ridge_alpha,
    )
    permission_allowed, permission_reasons = risk_up_permission_allowed(
        permission_probability,
        enabled=risk_up_permission_gate,
        min_probability=risk_up_permission_min_probability,
    )
    combined_allowed = action_allowed & permission_allowed
    combined_reasons = block_reasons.copy()
    permission_blocked = (~permission_allowed) & combined_reasons.isna()
    combined_reasons.loc[permission_blocked] = permission_reasons.loc[permission_blocked]
    decisions = select_relative_actions(
        predicted,
        edge_threshold=edge_threshold,
        regret_clip=regret_clip,
        actions=actions,
        reliability_percentiles=reliability,
        max_error_percentile=reliability_max_error_percentile,
        action_allowed=combined_allowed,
        block_reasons=combined_reasons,
        permission_probability=permission_probability,
    )
    realized_edges = []
    for row in decisions.to_dict(orient="records"):
        dt = pd.Timestamp(row["date"])
        action = str(row["action"])
        if action != "KEEP" and dt in labels.index and action in labels.columns:
            realized_edges.append(float(labels.loc[dt, action]))
    label_summary: dict[str, Any] = {}
    for action in actions:
        if action == "KEEP" or action not in labels.columns:
            continue
        series = labels[action].astype(float)
        label_summary[action] = {
            "n": int(series.count()),
            "mean_realized_regret": float(series.mean()) if len(series) else 0.0,
            "positive_rate": float((series > 0.0).mean()) if len(series) else 0.0,
            "p90_realized_regret": float(series.quantile(0.90)) if len(series) else 0.0,
        }
    labeled_decisions = decisions[decisions["date"].isin({str(dt.date()) for dt in labels.index})]
    feature_only_decisions = decisions[~decisions["date"].isin(set(labeled_decisions["date"].astype(str)))]
    recent = decisions.tail(20).to_dict(orient="records")
    non_keep = labeled_decisions[labeled_decisions["action"] != "KEEP"]
    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": actual_end, "requested_end": end, "resolved_end": resolved_end},
        "ncf_panel": panel_path,
        "feature_rows": int(len(features)),
        "label_rows": int(len(labels)),
        "decision_rows": int(len(decisions)),
        "latest_inference": {
            "enabled": True,
            "feature_only_decision_rows": int(len(feature_only_decisions)),
            "last_labeled_decision_date": str(labels.index.max().date()) if len(labels.index) else None,
            "last_feature_decision_date": str(features.index.max().date()) if len(features.index) else None,
            "note": "Trailing feature-only decisions are predicted from past realized labels and are not included in realized edge metrics.",
        },
        "actions": list(actions),
        "method": {
            "baseline": "100pct_0050",
            "candidate_actions": "fixed_weight_shift_from_0050_to_00631l",
            "horizon": int(horizon),
            "edge_threshold": float(edge_threshold),
            "regret_clip": float(regret_clip),
            "min_train_days": int(min_train_days),
            "train_window_days": int(train_window_days),
            "ridge_alpha": float(ridge_alpha),
            "selective_reliability": bool(selective_reliability),
            "reliability_max_error_percentile": float(reliability_max_error_percentile),
            "slow_bear_gate": {
                "enabled": bool(slow_bear_gate),
                "drawdown_0050_60d_max": float(slow_bear_drawdown_0050_60d_max),
                "ret_0050_20d_max": float(slow_bear_ret_0050_20d_max),
                "spread_00631l_0050_20d_max": float(slow_bear_spread_00631l_0050_20d_max),
                "momentum_ret_0050_20d_max": float(slow_bear_momentum_ret_0050_20d_max),
                "blocked_days": int((~action_allowed).sum()),
            },
            "risk_up_permission_gate": {
                "enabled": bool(risk_up_permission_gate),
                "action": str(risk_up_permission_action),
                "min_probability": float(risk_up_permission_min_probability),
                "min_realized_edge": float(risk_up_permission_min_realized_edge),
                "min_train_days": int(risk_up_permission_min_train_days),
                "blocked_days": int((~permission_allowed).sum()),
                "mean_probability": float(permission_probability.mean()) if len(permission_probability) else None,
            },
        },
        "dividend_coverage": dividend_coverage,
        "label_summary": label_summary,
        "action_counts": _action_counts(labeled_decisions),
        "all_decision_action_counts": _action_counts(decisions),
        "non_keep_days": int(len(non_keep)),
        "non_keep_decisions": non_keep.to_dict(orient="records"),
        "recent_decisions": recent,
        "realized_selected_edge": {
            "count": int(len(realized_edges)),
            "mean": float(np.mean(realized_edges)) if realized_edges else None,
            "positive_rate": float(np.mean([v > 0.0 for v in realized_edges])) if realized_edges else None,
            "worst": float(np.min(realized_edges)) if realized_edges else None,
            "p10": float(np.quantile(realized_edges, 0.10)) if realized_edges else None,
            "median": float(np.median(realized_edges)) if realized_edges else None,
            "p90": float(np.quantile(realized_edges, 0.90)) if realized_edges else None,
        },
    }


def _parse_windows(raw: str) -> list[tuple[str, str, str, str | None, str]]:
    out: list[tuple[str, str, str, str | None, str]] = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) not in (3, 4, 5):
            raise ValueError("--windows items must be label:start:end[:panel[:bucket]]")
        label, start, end = parts[:3]
        panel = parts[3] if len(parts) >= 4 and parts[3] else DEFAULT_PANEL
        bucket = parts[4] if len(parts) >= 5 and parts[4] else "custom"
        out.append((label, start, end, panel, bucket))
    return out


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts: dict[str, int] = {}
    for result in results:
        for action, count in (result.get("action_counts") or {}).items():
            action_counts[action] = action_counts.get(action, 0) + int(count)
    selected_edges = [
        result.get("realized_selected_edge", {}).get("mean")
        for result in results
        if result.get("realized_selected_edge", {}).get("mean") is not None
    ]
    return {
        "windows": int(len(results)),
        "action_counts": action_counts,
        "non_keep_days": int(sum(int(result.get("non_keep_days", 0) or 0) for result in results)),
        "mean_selected_edge_across_active_windows": float(np.mean(selected_edges)) if selected_edges else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default=f"active_2025_2026:2025-01-02:latest:{DEFAULT_PANEL}:tuning_window")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--min-train-days", type=int, default=120)
    parser.add_argument("--train-window-days", type=int, default=420)
    parser.add_argument("--ridge-alpha", type=float, default=10.0)
    parser.add_argument("--edge-threshold", type=float, default=0.0005)
    parser.add_argument("--regret-clip", type=float, default=0.02)
    parser.add_argument("--lambda-mdd", type=float, default=0.35)
    parser.add_argument("--gamma-turnover", type=float, default=0.015)
    parser.add_argument("--eta-missed-rebound", type=float, default=0.30)
    parser.add_argument("--actions", default=",".join(DEFAULT_ACTIONS))
    parser.add_argument("--selective-reliability", action="store_true")
    parser.add_argument("--reliability-max-error-percentile", type=float, default=0.70)
    parser.add_argument("--reliability-min-train-days", type=int, default=60)
    parser.add_argument("--slow-bear-gate", action="store_true")
    parser.add_argument("--slow-bear-drawdown-0050-60d-max", type=float, default=-0.08)
    parser.add_argument("--slow-bear-ret-0050-20d-max", type=float, default=0.0)
    parser.add_argument("--slow-bear-spread-00631l-0050-20d-max", type=float, default=0.0)
    parser.add_argument("--slow-bear-momentum-ret-0050-20d-max", type=float, default=-0.03)
    parser.add_argument("--risk-up-permission-gate", action="store_true")
    parser.add_argument("--risk-up-permission-action", default="SHIFT_00631L_5")
    parser.add_argument("--risk-up-permission-min-probability", type=float, default=0.55)
    parser.add_argument("--risk-up-permission-min-realized-edge", type=float, default=0.0)
    parser.add_argument("--risk-up-permission-min-train-days", type=int, default=60)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--latest-output",
        default=None,
        help="Optional second path for the same shadow payload, typically report/group_a_plus/latest/.",
    )
    args = parser.parse_args()

    db_path = _resolve(args.db)
    actions = tuple(part.strip().upper() for part in str(args.actions).split(",") if part.strip())
    results = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            panel_path=panel,
            horizon=int(args.horizon),
            min_train_days=int(args.min_train_days),
            train_window_days=int(args.train_window_days),
            ridge_alpha=float(args.ridge_alpha),
            edge_threshold=float(args.edge_threshold),
            regret_clip=float(args.regret_clip),
            lambda_mdd=float(args.lambda_mdd),
            gamma_turnover=float(args.gamma_turnover),
            eta_missed_rebound=float(args.eta_missed_rebound),
            actions=actions,
            selective_reliability=bool(args.selective_reliability),
            reliability_max_error_percentile=float(args.reliability_max_error_percentile),
            reliability_min_train_days=int(args.reliability_min_train_days),
            slow_bear_gate=bool(args.slow_bear_gate),
            slow_bear_drawdown_0050_60d_max=float(args.slow_bear_drawdown_0050_60d_max),
            slow_bear_ret_0050_20d_max=float(args.slow_bear_ret_0050_20d_max),
            slow_bear_spread_00631l_0050_20d_max=float(args.slow_bear_spread_00631l_0050_20d_max),
            slow_bear_momentum_ret_0050_20d_max=float(args.slow_bear_momentum_ret_0050_20d_max),
            risk_up_permission_gate=bool(args.risk_up_permission_gate),
            risk_up_permission_action=str(args.risk_up_permission_action).upper(),
            risk_up_permission_min_probability=float(args.risk_up_permission_min_probability),
            risk_up_permission_min_realized_edge=float(args.risk_up_permission_min_realized_edge),
            risk_up_permission_min_train_days=int(args.risk_up_permission_min_train_days),
        )
        for label, start, end, panel, bucket in _parse_windows(str(args.windows))
    ]
    payload = {
        "report_type": "00631l_0050_relative_reentry_opportunity",
        "status": "shadow_only_no_live_action",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": {
            "actions": list(actions),
            "feature_columns": list(FEATURE_COLUMNS),
            "baseline": "100pct_0050",
            "candidate_actions": "fixed_weight_shift_from_0050_to_00631l",
        },
        "results": results,
        "summary": _summary(results),
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    output.write_text(text, encoding="utf-8")
    latest_output = _resolve(args.latest_output) if args.latest_output else None
    if latest_output is not None and latest_output != output:
        latest_output.parent.mkdir(parents=True, exist_ok=True)
        latest_output.write_text(text, encoding="utf-8")
    print(f"JSON: {output}")
    if latest_output is not None and latest_output != output:
        print(f"Latest JSON: {latest_output}")
    print(f"Windows: {len(results)}, action_counts={payload['summary']['action_counts']}")


if __name__ == "__main__":
    main()
