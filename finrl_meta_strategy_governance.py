#!/usr/bin/env python3
"""FinRL-Meta-inspired governance utilities for local Group A/B strategies."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class TradeCostParams:
    commission_rate: float = 0.001425
    sell_tax_rate: float = 0.001
    slippage_rate: float = 0.0005


@dataclass(frozen=True)
class StressGateParams:
    enabled: bool = True
    use_quantile_thresholds: bool = False
    quantile_window: int = 252
    quantile_min_periods: int = 126
    caution_quantile: float = 0.25
    risk_off_quantile: float = 0.10
    caution_drawdown: float = -0.06
    risk_off_drawdown: float = -0.12
    caution_momentum21: float = -0.03
    risk_off_momentum21: float = -0.08
    caution_a_weight_cap: float = 0.625
    risk_off_a_weight_cap: float = 0.55


@dataclass(frozen=True)
class ABGovernanceParams:
    strategy_name: str = "ab_dynamic_lb126_band008_hold10_no2884_governed"
    initial_capital: float = 2_000_000.0
    base_a_weight: float = 0.625
    dynamic_lookback: int = 126
    dynamic_band: float = 0.08
    upper_a_weight: float = 0.70
    upper_mid_a_weight: float = 0.65
    lower_mid_a_weight: float = 0.60
    lower_a_weight: float = 0.55
    calendar_rebalance: str = "quarterly"
    drift_threshold: float = 0.05
    min_transfer_notional: float = 50_000.0
    cooldown_days: int = 20
    cost: TradeCostParams = field(default_factory=TradeCostParams)
    stress_gate: StressGateParams = field(default_factory=StressGateParams)

    @property
    def deterministic_id(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def resolve_project_path(project_root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    return path


def rolling_sharpe(returns: pd.Series, *, window: int = 126, min_periods: int = 63) -> pd.Series:
    returns = pd.Series(returns, dtype=float)
    mean = returns.rolling(window=window, min_periods=min_periods).mean()
    std = returns.rolling(window=window, min_periods=min_periods).std()
    return ((mean / std) * math.sqrt(252)).replace([float("inf"), -float("inf")], 0.0).fillna(0.0)


def metrics(
    values: pd.Series,
    *,
    events: int = 0,
    total_cost: float = 0.0,
    turnovers: pd.Series | None = None,
) -> dict[str, Any]:
    values = values.dropna().astype(float)
    daily = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    downside = daily[daily < 0.0]
    drawdown = values / values.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(daily.std() * math.sqrt(252)) if len(daily) > 1 else 0.0
    sortino = (
        float((daily.mean() / downside.std()) * math.sqrt(252))
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )
    avg_daily_turnover = float(pd.Series(turnovers, dtype=float).mean()) if turnovers is not None and len(turnovers) else 0.0
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "annual_return": annual_return,
        "sharpe_ratio": (
            float((daily.mean() / daily.std()) * math.sqrt(252))
            if len(daily) > 1 and daily.std() > 0
            else 0.0
        ),
        "sortino_ratio": sortino,
        "calmar_ratio": float(annual_return / abs(max_drawdown)) if max_drawdown < 0 else 0.0,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
        "num_events": int(events),
        "total_cost": float(total_cost),
        "avg_daily_cost": float(total_cost / max(len(values), 1)),
        "avg_daily_turnover": avg_daily_turnover,
        "latest_rolling_sharpe_126": float(rolling_sharpe(daily, window=126, min_periods=63).iloc[-1]) if len(daily) else 0.0,
    }


def calendar_due(date: pd.Timestamp, previous: pd.Timestamp | None, mode: str) -> bool:
    if previous is None:
        return True
    if mode == "none":
        return False
    if mode == "monthly":
        return date.year != previous.year or date.month != previous.month
    if mode == "quarterly":
        return date.year != previous.year or (date.month - 1) // 3 != (previous.month - 1) // 3
    raise ValueError(f"Unsupported calendar mode: {mode}")


def trade_cost(
    transfer_notional: float,
    *,
    sell_notional: float,
    params: TradeCostParams,
) -> dict[str, float]:
    commission = abs(transfer_notional) * params.commission_rate
    sell_tax = max(sell_notional, 0.0) * params.sell_tax_rate
    slippage = abs(transfer_notional) * params.slippage_rate
    return {
        "commission": float(commission),
        "sell_tax": float(sell_tax),
        "slippage": float(slippage),
        "total_cost": float(commission + sell_tax + slippage),
    }


def rolling_dynamic_targets(
    a_returns: pd.Series,
    b_returns: pd.Series,
    params: ABGovernanceParams,
) -> pd.DataFrame:
    lookback = int(params.dynamic_lookback)
    a_rel = (1.0 + a_returns).rolling(lookback).apply(lambda x: float(x.prod() - 1.0), raw=False)
    b_rel = (1.0 + b_returns).rolling(lookback).apply(lambda x: float(x.prod() - 1.0), raw=False)
    a_sharpe = a_returns.rolling(lookback).mean() / a_returns.rolling(lookback).std()
    b_sharpe = b_returns.rolling(lookback).mean() / b_returns.rolling(lookback).std()
    score = (a_rel - b_rel).fillna(0.0) + 0.03 * ((a_sharpe - b_sharpe) * math.sqrt(252)).fillna(0.0)
    lagged = score.shift(1).fillna(0.0)

    target = pd.Series(float(params.base_a_weight), index=a_returns.index, dtype=float)
    target[lagged > params.dynamic_band] = float(params.upper_a_weight)
    target[(lagged > params.dynamic_band / 2.0) & (lagged <= params.dynamic_band)] = float(params.upper_mid_a_weight)
    target[(lagged < -params.dynamic_band / 2.0) & (lagged >= -params.dynamic_band)] = float(params.lower_mid_a_weight)
    target[lagged < -params.dynamic_band] = float(params.lower_a_weight)
    return pd.DataFrame({"raw_target_a_weight": target, "dynamic_score_lag1": lagged}, index=a_returns.index)


def stress_state(
    group_a_value: pd.Series,
    params: StressGateParams,
) -> pd.DataFrame:
    peak = group_a_value.cummax()
    drawdown = (group_a_value / peak - 1.0).shift(1).fillna(0.0)
    momentum21 = group_a_value.pct_change(21).shift(1).fillna(0.0)
    if params.use_quantile_thresholds:
        caution_drawdown = (
            drawdown.rolling(params.quantile_window, min_periods=params.quantile_min_periods)
            .quantile(params.caution_quantile)
            .fillna(params.caution_drawdown)
        )
        risk_off_drawdown = (
            drawdown.rolling(params.quantile_window, min_periods=params.quantile_min_periods)
            .quantile(params.risk_off_quantile)
            .fillna(params.risk_off_drawdown)
        )
        caution_momentum = (
            momentum21.rolling(params.quantile_window, min_periods=params.quantile_min_periods)
            .quantile(params.caution_quantile)
            .fillna(params.caution_momentum21)
        )
        risk_off_momentum = (
            momentum21.rolling(params.quantile_window, min_periods=params.quantile_min_periods)
            .quantile(params.risk_off_quantile)
            .fillna(params.risk_off_momentum21)
        )
    else:
        caution_drawdown = pd.Series(float(params.caution_drawdown), index=group_a_value.index)
        risk_off_drawdown = pd.Series(float(params.risk_off_drawdown), index=group_a_value.index)
        caution_momentum = pd.Series(float(params.caution_momentum21), index=group_a_value.index)
        risk_off_momentum = pd.Series(float(params.risk_off_momentum21), index=group_a_value.index)
    state = pd.Series("normal", index=group_a_value.index, dtype=object)
    state[(drawdown <= caution_drawdown) | (momentum21 <= caution_momentum)] = "caution"
    state[(drawdown <= risk_off_drawdown) | (momentum21 <= risk_off_momentum)] = "risk_off"
    return pd.DataFrame(
        {
            "stress_state": state,
            "group_a_drawdown_lag1": drawdown,
            "group_a_momentum21_lag1": momentum21,
            "caution_drawdown_threshold": caution_drawdown,
            "risk_off_drawdown_threshold": risk_off_drawdown,
            "caution_momentum21_threshold": caution_momentum,
            "risk_off_momentum21_threshold": risk_off_momentum,
        }
    )


def apply_stress_gate(targets: pd.Series, stress: pd.DataFrame, params: StressGateParams) -> pd.Series:
    if not params.enabled:
        return targets.astype(float)
    gated = targets.astype(float).copy()
    caution = stress["stress_state"].eq("caution")
    risk_off = stress["stress_state"].eq("risk_off")
    gated[caution] = gated[caution].clip(upper=float(params.caution_a_weight_cap))
    gated[risk_off] = gated[risk_off].clip(upper=float(params.risk_off_a_weight_cap))
    return gated


def hold_targets_until_calendar(index: pd.Index, raw_targets: pd.Series, mode: str) -> pd.Series:
    held: list[float] = []
    previous: pd.Timestamp | None = None
    current = float(raw_targets.iloc[0])
    for raw_date in index:
        date = pd.Timestamp(raw_date)
        if calendar_due(date, previous, mode):
            current = float(raw_targets.loc[date])
        held.append(current)
        previous = date
    return pd.Series(held, index=index, dtype=float)


def simulate_ab_governed(ab: pd.DataFrame, params: ABGovernanceParams) -> tuple[pd.Series, list[dict[str, Any]], pd.DataFrame]:
    a_returns = ab["group_a_value"].pct_change().fillna(0.0)
    b_returns = ab["group_b_value"].pct_change().fillna(0.0)
    dynamic = rolling_dynamic_targets(a_returns, b_returns, params)
    stress = stress_state(ab["group_a_value"].astype(float), params.stress_gate)
    gated = apply_stress_gate(dynamic["raw_target_a_weight"], stress, params.stress_gate)
    targets = hold_targets_until_calendar(ab.index, gated, params.calendar_rebalance)

    first_target = float(targets.iloc[0])
    a_value = float(params.initial_capital) * first_target
    b_value = float(params.initial_capital) * (1.0 - first_target)
    last_target = first_target
    previous_date: pd.Timestamp | None = None
    last_rebalance_date: pd.Timestamp | None = None
    values: list[tuple[pd.Timestamp, float]] = []
    events: list[dict[str, Any]] = []
    diagnostic = pd.concat([dynamic, stress], axis=1)
    diagnostic["gated_target_a_weight"] = gated
    diagnostic["target_a_weight"] = targets

    for date in a_returns.index:
        a_value *= 1.0 + float(a_returns.loc[date])
        b_value *= 1.0 + float(b_returns.loc[date])
        total = a_value + b_value
        current_a = a_value / total if total > 0 else 0.0
        target_a = float(targets.loc[date])
        target_changed = abs(target_a - last_target) > 1e-12
        calendar = calendar_due(pd.Timestamp(date), previous_date, params.calendar_rebalance)
        drift = abs(current_a - target_a) >= float(params.drift_threshold)
        transfer = abs(total * target_a - a_value)
        cooldown_elapsed = (
            True
            if last_rebalance_date is None
            else (pd.Timestamp(date) - last_rebalance_date).days >= int(params.cooldown_days)
        )
        forced = target_changed and str(diagnostic.loc[date, "stress_state"]) == "risk_off"
        should_rebalance = (target_changed or calendar or drift) and transfer >= float(params.min_transfer_notional)
        if should_rebalance and (cooldown_elapsed or forced):
            target_a_value = total * target_a
            sell_notional = max(a_value - target_a_value, 0.0)
            costs = trade_cost(transfer, sell_notional=sell_notional, params=params.cost)
            total_after_cost = total - costs["total_cost"]
            pre_a_value = a_value
            pre_b_value = b_value
            a_value = total_after_cost * target_a
            b_value = total_after_cost * (1.0 - target_a)
            total = total_after_cost
            reason = "target_change" if target_changed else ("calendar" if calendar else "drift")
            event = {
                "date": str(pd.Timestamp(date).date()),
                "reason": reason,
                "stress_state": str(diagnostic.loc[date, "stress_state"]),
                "pre_group_a_weight": float(current_a),
                "target_group_a_weight": float(target_a),
                "last_group_a_weight": float(last_target),
                "transfer_notional": float(transfer),
                "sell_notional": float(sell_notional),
                "pre_group_a_value": float(pre_a_value),
                "pre_group_b_value": float(pre_b_value),
                "post_group_a_value": float(a_value),
                "post_group_b_value": float(b_value),
                "cash": 0.0,
                **costs,
            }
            events.append(event)
            last_target = target_a
            last_rebalance_date = pd.Timestamp(date)
        values.append((pd.Timestamp(date), total))
        previous_date = pd.Timestamp(date)

    curve = pd.Series([value for _, value in values], index=[date for date, _ in values], dtype=float)
    return curve, events, diagnostic


def simulate_ab_validation_selector(
    ab: pd.DataFrame,
    candidate_params: list[ABGovernanceParams],
    execution_params: ABGovernanceParams,
    *,
    validation_days: int = 126,
    metric: str = "sharpe_ratio",
) -> tuple[pd.Series, list[dict[str, Any]], pd.DataFrame, list[dict[str, Any]]]:
    """Select an A/B allocator at calendar rebalance dates using trailing validation.

    Each candidate is simulated once to create lagged target diagnostics and a
    comparable validation curve. At every calendar rebalance, the selector picks
    the candidate with the best trailing validation metric and holds its target
    until the next rebalance/target event.
    """
    if not candidate_params:
        raise ValueError("candidate_params must not be empty")

    candidate_curves: dict[str, pd.Series] = {}
    candidate_diagnostics: dict[str, pd.DataFrame] = {}
    for params in candidate_params:
        curve, _, diagnostic = simulate_ab_governed(ab, params)
        candidate_curves[params.strategy_name] = curve
        candidate_diagnostics[params.strategy_name] = diagnostic

    choices: list[dict[str, Any]] = []
    chosen_variant = candidate_params[0].strategy_name
    chosen_targets: list[float] = []
    previous_date: pd.Timestamp | None = None
    for i, raw_date in enumerate(ab.index):
        date = pd.Timestamp(raw_date)
        if calendar_due(date, previous_date, execution_params.calendar_rebalance):
            start_i = max(0, i - int(validation_days))
            scores = []
            for params in candidate_params:
                name = params.strategy_name
                part = candidate_curves[name].iloc[start_i : i + 1]
                if len(part) > 5:
                    row = metrics(part)
                    score = float(row.get(metric, row["sharpe_ratio"]))
                else:
                    row = metrics(candidate_curves[name].iloc[: i + 1])
                    score = float(row.get(metric, row["sharpe_ratio"]))
                scores.append((score, float(row["final_value"]), name, row))
            scores.sort(reverse=True)
            chosen_variant = scores[0][2]
            choices.append(
                {
                    "date": str(date.date()),
                    "chosen_variant": chosen_variant,
                    "validation_days": int(validation_days),
                    "metric": metric,
                    "scores": [
                        {
                            "variant": name,
                            "score": score,
                            "final_value": final_value,
                            "sharpe_ratio": row["sharpe_ratio"],
                            "max_drawdown": row["max_drawdown"],
                        }
                        for score, final_value, name, row in scores
                    ],
                }
            )
        chosen_targets.append(float(candidate_diagnostics[chosen_variant].loc[date, "target_a_weight"]))
        previous_date = date

    target_series = pd.Series(chosen_targets, index=ab.index, dtype=float)
    a_returns = ab["group_a_value"].pct_change().fillna(0.0)
    b_returns = ab["group_b_value"].pct_change().fillna(0.0)
    a_value = float(execution_params.initial_capital) * float(target_series.iloc[0])
    b_value = float(execution_params.initial_capital) * (1.0 - float(target_series.iloc[0]))
    last_target = float(target_series.iloc[0])
    previous_date = None
    last_rebalance_date: pd.Timestamp | None = None
    values: list[tuple[pd.Timestamp, float]] = []
    events: list[dict[str, Any]] = []

    choice_by_date = {pd.Timestamp(item["date"]): item["chosen_variant"] for item in choices}
    active_variant = choices[0]["chosen_variant"] if choices else candidate_params[0].strategy_name
    diagnostic = pd.DataFrame(index=ab.index)
    diagnostic["target_a_weight"] = target_series
    diagnostic["chosen_variant"] = ""

    for date in a_returns.index:
        if pd.Timestamp(date) in choice_by_date:
            active_variant = choice_by_date[pd.Timestamp(date)]
        diagnostic.loc[date, "chosen_variant"] = active_variant
        stress_label = str(candidate_diagnostics[active_variant].loc[date, "stress_state"])
        a_value *= 1.0 + float(a_returns.loc[date])
        b_value *= 1.0 + float(b_returns.loc[date])
        total = a_value + b_value
        current_a = a_value / total if total > 0 else 0.0
        target_a = float(target_series.loc[date])
        target_changed = abs(target_a - last_target) > 1e-12
        calendar = calendar_due(pd.Timestamp(date), previous_date, execution_params.calendar_rebalance)
        drift = abs(current_a - target_a) >= float(execution_params.drift_threshold)
        transfer = abs(total * target_a - a_value)
        cooldown_elapsed = (
            True
            if last_rebalance_date is None
            else (pd.Timestamp(date) - last_rebalance_date).days >= int(execution_params.cooldown_days)
        )
        forced = target_changed and stress_label == "risk_off"
        should_rebalance = (target_changed or calendar or drift) and transfer >= float(execution_params.min_transfer_notional)
        if should_rebalance and (cooldown_elapsed or forced):
            target_a_value = total * target_a
            sell_notional = max(a_value - target_a_value, 0.0)
            costs = trade_cost(transfer, sell_notional=sell_notional, params=execution_params.cost)
            total_after_cost = total - costs["total_cost"]
            pre_a_value = a_value
            pre_b_value = b_value
            a_value = total_after_cost * target_a
            b_value = total_after_cost * (1.0 - target_a)
            total = total_after_cost
            reason = "target_change" if target_changed else ("calendar" if calendar else "drift")
            events.append(
                {
                    "date": str(pd.Timestamp(date).date()),
                    "reason": reason,
                    "chosen_variant": active_variant,
                    "stress_state": stress_label,
                    "pre_group_a_weight": float(current_a),
                    "target_group_a_weight": float(target_a),
                    "last_group_a_weight": float(last_target),
                    "transfer_notional": float(transfer),
                    "sell_notional": float(sell_notional),
                    "pre_group_a_value": float(pre_a_value),
                    "pre_group_b_value": float(pre_b_value),
                    "post_group_a_value": float(a_value),
                    "post_group_b_value": float(b_value),
                    "cash": 0.0,
                    **costs,
                }
            )
            last_target = target_a
            last_rebalance_date = pd.Timestamp(date)
        values.append((pd.Timestamp(date), total))
        previous_date = pd.Timestamp(date)

    curve = pd.Series([value for _, value in values], index=[date for date, _ in values], dtype=float)
    return curve, events, diagnostic, choices


def write_epoch_oos_scaffold(
    output: Path,
    *,
    strategy_name: str,
    train_windows: list[tuple[str, str]],
    test_windows: list[tuple[str, str]],
    params: dict[str, Any],
) -> None:
    """Write a reproducible epoch-by-epoch OOS evaluation plan.

    This does not train a model by itself. It records the split protocol and the
    config hash so future RL runs can evaluate every epoch in a consistent way.
    """
    payload = {
        "strategy_name": strategy_name,
        "purpose": "epoch_by_epoch_oos_evaluation_scaffold",
        "note": "Freeze fitted scalers/normalizers after each train epoch, then evaluate deterministic policy on train and OOS windows.",
        "train_windows": [{"start": s, "end": e} for s, e in train_windows],
        "test_windows": [{"start": s, "end": e} for s, e in test_windows],
        "params": params,
        "config_id": hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:10],
        "required_outputs_per_epoch": [
            "train_metrics",
            "oos_metrics",
            "portfolio_curve",
            "trade_log",
            "normalizer_state_hash",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
