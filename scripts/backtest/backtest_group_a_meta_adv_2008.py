#!/usr/bin/env python3
"""Backtest the selected Group A meta overlay on the 2008 TWII proxy path.

This replays the canonical Golden1_0531 2008 PVA events and DCA purchases, then
applies the currently selected adv_conditional_inverse overlay.  TDCC history is
not available for 2008, so the stress test uses price-regime risk-off as the
overlay trigger.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from stable_baselines3 import PPO

from generate_dual_group_signal import _env_kwargs_from_payload
from backtest_group_a_meta_ensemble import _normalize, _price_regimes, _rule_strategy
from backtest_group_a_tdcc_latest import _metrics
from train_dual_group_2024_2026 import (
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    attach_group_a_margin_shared_features_db_first,
    attach_group_a_market_margin_shared_features_db_first,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    calculate_backtest_metrics,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_margin_features,
    payload_uses_group_a_margin_shared_features,
    payload_uses_group_a_market_margin_shared_features,
)
from twii_proxy_utils import DEFAULT_TWII_MARKET_CACHE, build_group_a_twii_proxy_data


PROJECT_ROOT = Path(__file__).resolve().parent
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_20070701_20101231_20260526_193325.json"
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_meta_ensemble_real_config.json"
DEFAULT_PAYLOAD = PROJECT_ROOT / "results" / "group_a_runtime_payload_primary_20260524.json"
DEFAULT_START = "2007-07-01"
DEFAULT_END = "2010-12-31"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results"


@dataclass(frozen=True)
class Variant:
    name: str
    risk_off_cap: float = 0.08
    conditional_inverse_weight: float = 0.01
    severe_inverse_weight: float = 0.0
    severe_ret5_threshold: float = -0.05
    severe_ret20_threshold: float = -0.10
    recovery_cash_cap: float | None = None
    recovery_leverage_cap: float | None = None
    recovery_requires_risk_on: bool = False
    momentum_cash_floor: bool = False
    momentum_cash_ma60_floor: float = 0.15
    momentum_cash_ma20_floor: float = 0.10
    momentum_cash_base_floor: float = 0.025
    adaptive_momentum_cash: bool = False
    severe_price_only: bool = False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--model", default=None)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _variants() -> list[Variant]:
    return [
        Variant("adv_conditional_inverse"),
        Variant("recovery_cash10", recovery_cash_cap=0.10),
        Variant("recovery_cash05", recovery_cash_cap=0.05),
        Variant("severe_inverse_03", severe_inverse_weight=0.03),
        Variant("severe_inverse_05", severe_inverse_weight=0.05),
        Variant("severe_inverse_08", severe_inverse_weight=0.08),
        Variant("severe_inverse_05_relaxed", severe_inverse_weight=0.05, severe_ret5_threshold=-0.03, severe_ret20_threshold=-0.06),
        Variant("severe_inverse_08_relaxed", severe_inverse_weight=0.08, severe_ret5_threshold=-0.03, severe_ret20_threshold=-0.06),
        Variant("severe_inverse_05_fast", severe_inverse_weight=0.05, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("severe_inverse_08_fast", severe_inverse_weight=0.08, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("severe_inverse_10_fast", severe_inverse_weight=0.10, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("severe_inverse_05_crash_strict", severe_inverse_weight=0.05, severe_ret5_threshold=-0.04, severe_ret20_threshold=-0.08),
        Variant("momentum_cash", momentum_cash_floor=True),
        Variant("momcash_light_12_08", momentum_cash_floor=True, momentum_cash_ma60_floor=0.12, momentum_cash_ma20_floor=0.08),
        Variant("momcash_mid_18_12", momentum_cash_floor=True, momentum_cash_ma60_floor=0.18, momentum_cash_ma20_floor=0.12),
        Variant("momcash_high_22_15", momentum_cash_floor=True, momentum_cash_ma60_floor=0.22, momentum_cash_ma20_floor=0.15),
        Variant("momcash_base05_15_10", momentum_cash_floor=True, momentum_cash_base_floor=0.05),
        Variant("combo_momcash_severe03_fast", momentum_cash_floor=True, severe_inverse_weight=0.03, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("combo_momcash_severe05_fast", momentum_cash_floor=True, severe_inverse_weight=0.05, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("combo_momcash_severe08_fast", momentum_cash_floor=True, severe_inverse_weight=0.08, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("combo_momcash_severe10_fast", momentum_cash_floor=True, severe_inverse_weight=0.10, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant(
            "adaptive_momcash_price_severe10",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.18,
            momentum_cash_ma20_floor=0.12,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.10,
            severe_ret5_threshold=-0.02,
            severe_ret20_threshold=-0.05,
            severe_price_only=True,
        ),
        Variant(
            "adaptive_momcash_price_severe08",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.18,
            momentum_cash_ma20_floor=0.12,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.08,
            severe_ret5_threshold=-0.02,
            severe_ret20_threshold=-0.05,
            severe_price_only=True,
        ),
        Variant(
            "adaptive_momcash_price_severe12",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.18,
            momentum_cash_ma20_floor=0.12,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.12,
            severe_ret5_threshold=-0.02,
            severe_ret20_threshold=-0.05,
            severe_price_only=True,
        ),
        Variant(
            "adaptive_momcash_price_severe10_soft",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.18,
            momentum_cash_ma20_floor=0.12,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.10,
            severe_ret5_threshold=-0.015,
            severe_ret20_threshold=-0.04,
            severe_price_only=True,
        ),
        Variant(
            "adaptive_momcash_price_severe10_strict",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.18,
            momentum_cash_ma20_floor=0.12,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.10,
            severe_ret5_threshold=-0.03,
            severe_ret20_threshold=-0.06,
            severe_price_only=True,
        ),
        Variant(
            "adaptive_balanced20_13_price_severe10",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.20,
            momentum_cash_ma20_floor=0.13,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.10,
            severe_ret5_threshold=-0.02,
            severe_ret20_threshold=-0.05,
            severe_price_only=True,
        ),
        Variant(
            "adaptive_high_price_severe10",
            momentum_cash_floor=True,
            momentum_cash_ma60_floor=0.22,
            momentum_cash_ma20_floor=0.15,
            adaptive_momentum_cash=True,
            severe_inverse_weight=0.10,
            severe_ret5_threshold=-0.02,
            severe_ret20_threshold=-0.05,
            severe_price_only=True,
        ),
        Variant("combo_momcash_severe08_relaxed", momentum_cash_floor=True, severe_inverse_weight=0.08, severe_ret5_threshold=-0.03, severe_ret20_threshold=-0.06),
        Variant("combo_mid_momcash_severe05_fast", momentum_cash_floor=True, momentum_cash_ma60_floor=0.18, momentum_cash_ma20_floor=0.12, severe_inverse_weight=0.05, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("combo_high_momcash_severe05_fast", momentum_cash_floor=True, momentum_cash_ma60_floor=0.22, momentum_cash_ma20_floor=0.15, severe_inverse_weight=0.05, severe_ret5_threshold=-0.02, severe_ret20_threshold=-0.05),
        Variant("recovery_leverage_step12", recovery_cash_cap=0.10, recovery_leverage_cap=0.12),
        Variant("recovery_leverage_step18", recovery_cash_cap=0.10, recovery_leverage_cap=0.18),
        Variant("riskon_recovery_step18", recovery_cash_cap=0.10, recovery_leverage_cap=0.18, recovery_requires_risk_on=True),
        Variant("combo_cash10_severe05_step12", recovery_cash_cap=0.10, recovery_leverage_cap=0.12, severe_inverse_weight=0.05),
        Variant("combo_cash10_severe05_step18", recovery_cash_cap=0.10, recovery_leverage_cap=0.18, severe_inverse_weight=0.05),
        Variant("combo_cash05_severe05_relaxed", recovery_cash_cap=0.05, severe_inverse_weight=0.05, severe_ret5_threshold=-0.03, severe_ret20_threshold=-0.06),
    ]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_proxy_prices(start: str, end: str) -> pd.DataFrame:
    stock_data, _market = build_group_a_twii_proxy_data(start, end)
    rows = []
    for ticker in TICKERS:
        frame = stock_data[ticker][["date", "close"]].copy()
        frame["ticker"] = ticker
        rows.append(frame)
    prices = pd.concat(rows, ignore_index=True).pivot(index="date", columns="ticker", values="close")
    prices.index = pd.to_datetime(prices.index).normalize()
    return prices.sort_index().dropna(subset=TICKERS)


def _resolve_group_a_model_path(payload: dict[str, Any], override: str | None) -> Path:
    if override:
        candidate = _resolve(override)
        if candidate.exists():
            return candidate
        if candidate.suffix != ".zip" and candidate.with_suffix(".zip").exists():
            return candidate.with_suffix(".zip")
        raise FileNotFoundError(candidate)
    group_a = dict(payload.get("group_a", {}) or {})
    model_name = group_a.get("model_name")
    if model_name:
        candidate = PROJECT_ROOT / "models" / "portfolio" / str(model_name)
        if candidate.exists():
            return candidate
        if candidate.suffix != ".zip" and candidate.with_suffix(".zip").exists():
            return candidate.with_suffix(".zip")
    resume_model = payload.get("group_a_resume_model") or group_a.get("resume_model")
    if resume_model:
        candidate = Path(str(resume_model))
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Unable to resolve Group A model path from payload")


def _load_proxy_stock_data(payload: dict[str, Any], start: str, end: str) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    stock_data, market = build_group_a_twii_proxy_data(start, end)
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", TICKERS))
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, start, end)
    return stock_data, market


def _run_base_exact_events(
    payload: dict[str, Any],
    *,
    model_path: Path,
    start: str,
    end: str,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", TICKERS))
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    stock_data, market = _load_proxy_stock_data(payload, start, end)
    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols)
    if panel.empty:
        raise RuntimeError("No aligned 2008 proxy panel rows")
    load_env = PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **env_kwargs,
    )
    model = PPO.load(
        str(model_path),
        env=load_env,
        custom_objects={
            "action_space": load_env.action_space,
            "observation_space": load_env.observation_space,
            "_last_obs": None,
            "_last_original_obs": None,
            "_last_episode_starts": None,
        },
    )
    env = PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **env_kwargs,
    )
    events: list[dict[str, Any]] = []
    original_rebalance = env._rebalance

    def record_rebalance(target_weights, prices):
        fee = original_rebalance(target_weights, prices)
        if fee > 0:
            trade_idx = min(env.step_idx + 1, len(env.date_strings) - 1)
            events.append(
                {
                    "date": env.date_strings[trade_idx],
                    "step_idx": int(trade_idx),
                    "target_weights": {
                        ticker: float(weight)
                        for ticker, weight in zip(tickers, target_weights)
                    },
                    "fee": float(fee),
                }
            )
        return fee

    env._rebalance = record_rebalance  # type: ignore[method-assign]
    obs, _ = env.reset()
    info = {"weights": [0.0] * len(tickers)}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(value) for value in env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    base = {
        "actual_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_end": str(pd.Timestamp(panel["date"].max()).date()),
        "rows": int(len(panel)),
        "final_value": float(equity[-1]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics.get("sharpe_ratio", metrics.get("sharpe", 0.0))),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "dca_purchase_count": int(env.dca_purchase_count),
        "dca_total_contributions": float(env.total_contributions),
        "total_invested_capital": float(initial_cash + env.total_contributions),
        "net_profit": float(equity[-1] - initial_cash - env.total_contributions),
        "contribution_return": float((equity[-1] - initial_cash - env.total_contributions) / max(initial_cash + env.total_contributions, 1.0)),
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
        "equity_curve": equity,
        "dca_purchase_history": env.dca_purchase_history,
        "rebalance_events": events,
        "pva_sigmoid_history": env.pva_sigmoid_history,
        "pva_sigmoid_count": int(env.pva_sigmoid_count),
    }
    if "tic" in panel.columns:
        prices = panel.pivot(index="date", columns="tic", values="close").sort_index()
    else:
        prices = pd.DataFrame(
            {
                ticker: pd.to_numeric(panel[f"{ticker}_close"], errors="coerce").to_numpy()
                for ticker in TICKERS
            },
            index=pd.to_datetime(panel["date"]).dt.normalize(),
        ).sort_index()
    prices.index = pd.to_datetime(prices.index).normalize()
    return base, prices.dropna(subset=TICKERS), market, events


def _event_map(events: list[dict[str, Any]]) -> dict[pd.Timestamp, dict[str, float]]:
    return {
        pd.Timestamp(event["date"]).normalize(): {
            ticker: float(weight)
            for ticker, weight in dict(event.get("target_weights", {})).items()
            if ticker in TICKERS
        }
        for event in events
    }


def _blend_targets(ppo: dict[str, float], regime: str) -> tuple[dict[str, float], float, dict[str, Any]]:
    ppo, ppo_cash = _normalize(ppo, max(0.0, 1.0 - sum(float(v) for v in ppo.values())))
    rule, rule_cash = _rule_strategy(regime)
    if regime == "risk_on":
        alloc = {"ppo": 0.85, "rule_based": 0.05, "sac_proxy_fallback_to_ppo": 0.10}
    elif regime == "risk_off":
        alloc = {"ppo": 0.95, "rule_based": 0.05}
    else:
        alloc = {"ppo": 0.90, "rule_based": 0.10}

    total_alloc = sum(alloc.values())
    alloc = {name: weight / total_alloc for name, weight in alloc.items()}
    weights = {ticker: 0.0 for ticker in TICKERS}
    cash = 0.0
    for name, sleeve_weight in alloc.items():
        if name == "rule_based":
            sleeve_weights, sleeve_cash = rule, rule_cash
        else:
            sleeve_weights, sleeve_cash = ppo, ppo_cash
        for ticker in TICKERS:
            weights[ticker] += sleeve_weight * sleeve_weights.get(ticker, 0.0)
        cash += sleeve_weight * sleeve_cash
    weights, cash = _normalize(weights, cash)
    return weights, cash, {"regime": regime, "allocator_weights": alloc}


def _apply_adv_conditional_inverse(
    weights: dict[str, float],
    cash: float,
    *,
    variant: Variant,
    risk_off: bool,
    conditional_inverse_allowed: bool,
    severe_inverse_allowed: bool,
    recovery_allowed: bool,
    cash_floor_override: float | None,
) -> tuple[dict[str, float], float, dict[str, Any]]:
    target = dict(weights)
    target_cash = float(cash)
    released = 0.0
    inverse_added = 0.0
    inverse_zeroed = 0.0
    cap = None

    if risk_off:
        cap = variant.risk_off_cap
        prior = target.get("00631L.TW", 0.0)
        target["00631L.TW"] = min(prior, cap)
        released = max(0.0, prior - target["00631L.TW"])
        target["0050.TW"] = target.get("0050.TW", 0.0) + released

        if conditional_inverse_allowed:
            add = min(variant.conditional_inverse_weight, max(target_cash, 0.0))
            if add < variant.conditional_inverse_weight:
                from_primary = min(variant.conditional_inverse_weight - add, max(target.get("0050.TW", 0.0), 0.0))
                target["0050.TW"] = max(target.get("0050.TW", 0.0) - from_primary, 0.0)
                add += from_primary
            target["00632R.TW"] = target.get("00632R.TW", 0.0) + add
            target_cash = max(0.0, target_cash - min(variant.conditional_inverse_weight, target_cash))
            inverse_added = add

        if severe_inverse_allowed and variant.severe_inverse_weight > inverse_added:
            extra_need = variant.severe_inverse_weight - inverse_added
            add = min(extra_need, max(target_cash, 0.0))
            if add < extra_need:
                from_primary = min(extra_need - add, max(target.get("0050.TW", 0.0), 0.0))
                target["0050.TW"] = max(target.get("0050.TW", 0.0) - from_primary, 0.0)
                add += from_primary
            target["00632R.TW"] = target.get("00632R.TW", 0.0) + add
            target_cash = max(0.0, target_cash - min(extra_need, target_cash))
            inverse_added += add

    if (
        not risk_off
        and variant.severe_price_only
        and severe_inverse_allowed
        and variant.severe_inverse_weight > inverse_added
    ):
        extra_need = variant.severe_inverse_weight - inverse_added
        add = min(extra_need, max(target_cash, 0.0))
        if add < extra_need:
            from_primary = min(extra_need - add, max(target.get("0050.TW", 0.0), 0.0))
            target["0050.TW"] = max(target.get("0050.TW", 0.0) - from_primary, 0.0)
            add += from_primary
        target["00632R.TW"] = target.get("00632R.TW", 0.0) + add
        target_cash = max(0.0, target_cash - min(extra_need, target_cash))
        inverse_added += add

    if not conditional_inverse_allowed and target.get("00632R.TW", 0.0) < 0.01:
        inverse_zeroed = target.get("00632R.TW", 0.0)
        target["00632R.TW"] = 0.0
        target_cash += inverse_zeroed

    recovery_cash_redeployed = 0.0
    recovery_leverage_added = 0.0
    if recovery_allowed and variant.recovery_cash_cap is not None and target_cash > variant.recovery_cash_cap:
        recovery_cash_redeployed = target_cash - variant.recovery_cash_cap
        target_cash = variant.recovery_cash_cap
        if variant.recovery_leverage_cap is not None:
            leverage_room = max(0.0, variant.recovery_leverage_cap - target.get("00631L.TW", 0.0))
            recovery_leverage_added = min(recovery_cash_redeployed, leverage_room)
            target["00631L.TW"] = target.get("00631L.TW", 0.0) + recovery_leverage_added
        target["0050.TW"] = target.get("0050.TW", 0.0) + recovery_cash_redeployed - recovery_leverage_added

    cash_floor_release = 0.0
    if cash_floor_override is not None and target_cash < cash_floor_override:
        need_cash = cash_floor_override - target_cash
        primary_available = max(target.get("0050.TW", 0.0), 0.0)
        cash_floor_release = min(need_cash, primary_available)
        target["0050.TW"] = primary_available - cash_floor_release
        target_cash += cash_floor_release

    target, target_cash = _normalize(target, target_cash)
    return target, target_cash, {
        "variant": variant.name,
        "risk_off_cap": cap,
        "released_leverage_budget": released,
        "released_destination": "0050.TW",
        "conditional_inverse_allowed": conditional_inverse_allowed,
        "severe_inverse_allowed": severe_inverse_allowed,
        "inverse_added": inverse_added,
        "inverse_zeroed": inverse_zeroed,
        "recovery_allowed": recovery_allowed,
        "recovery_cash_redeployed": recovery_cash_redeployed,
        "recovery_leverage_added": recovery_leverage_added,
        "cash_floor_override": cash_floor_override,
        "cash_floor_release": cash_floor_release,
    }


def _simulate(
    prices: pd.DataFrame,
    source: dict[str, Any],
    *,
    variant: Variant,
    fee_rate: float,
    base_exact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = source["result"]
    replay_source = base_exact or canonical
    event_key = "rebalance_events" if base_exact is not None else "pva_sigmoid_history"
    pva_by_date = _event_map(replay_source.get(event_key, []))
    dca_by_date = {
        pd.Timestamp(item["date"]).normalize(): item
        for item in replay_source.get("dca_purchase_history", [])
    }
    tdcc_unavailable = {dt: "normal" for dt in prices.index}
    regime_by_date = _price_regimes(prices, tdcc_unavailable)
    overlay_state_by_date = {
        dt: ("risk_off" if regime == "risk_off" else "normal")
        for dt, regime in regime_by_date.items()
    }

    initial_cash = float(replay_source["total_invested_capital"] - replay_source["dca_total_contributions"])
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_cash
    fees = 0.0
    contributions = 0.0
    rebalances = 0
    last_ppo: dict[str, float] | None = None
    last_target: dict[str, float] | None = None
    last_cash_weight: float | None = None
    last_regime: str | None = None
    curve: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    regime_counts = {"risk_on": 0, "neutral": 0, "risk_off": 0}
    close = prices["0050.TW"]
    ma20 = close.rolling(20, min_periods=10).mean()
    ma60 = close.rolling(60, min_periods=20).mean()
    ma20_rising = ma20.diff(5) > 0
    ret5 = close.pct_change(5)
    ret20 = close.pct_change(20)
    ret21 = close.pct_change(21)
    conditional_inverse_count = 0
    severe_inverse_count = 0
    recovery_count = 0
    momentum_cash_count = 0
    risk_off_rebalance_count = 0

    for dt, row in prices.iterrows():
        regime = regime_by_date[dt]
        overlay_state = overlay_state_by_date[dt]
        regime_counts[regime] = regime_counts.get(regime, 0) + 1

        if dt in dca_by_date:
            item = dca_by_date[dt]
            amount = float(item.get("total_contribution", 0.0))
            purchase = item.get("purchases", {}).get("0050.TW")
            if purchase and amount > 0:
                fee = amount * fee_rate / (1.0 + fee_rate)
                shares["0050.TW"] += (amount - fee) / float(row["0050.TW"])
                fees += fee
                contributions += amount
            elif amount > 0:
                cash += amount
                contributions += amount

        total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
        updated = False
        if dt in pva_by_date:
            last_ppo = pva_by_date[dt]
            updated = True
        regime_changed = last_regime is not None and regime != last_regime

        if (updated or regime_changed) and last_ppo is not None:
            conditional_inverse_allowed = (
                overlay_state == "risk_off"
                and pd.notna(ma60.loc[dt])
                and pd.notna(ret5.loc[dt])
                and float(close.loc[dt]) < float(ma60.loc[dt])
                and float(ret5.loc[dt]) < -0.03
            )
            severe_inverse_allowed = (
                (overlay_state == "risk_off" or variant.severe_price_only)
                and pd.notna(ma60.loc[dt])
                and pd.notna(ret5.loc[dt])
                and pd.notna(ret20.loc[dt])
                and float(close.loc[dt]) < float(ma60.loc[dt])
                and float(ret5.loc[dt]) < variant.severe_ret5_threshold
                and float(ret20.loc[dt]) < variant.severe_ret20_threshold
            )
            recovery_allowed = (
                overlay_state != "risk_off"
                and pd.notna(ma60.loc[dt])
                and pd.notna(ret21.loc[dt])
                and float(close.loc[dt]) > float(ma60.loc[dt])
                and float(ret21.loc[dt]) > 0.0
                and (regime == "risk_on" or not variant.recovery_requires_risk_on)
            )
            if conditional_inverse_allowed:
                conditional_inverse_count += 1
            if severe_inverse_allowed:
                severe_inverse_count += 1
            if recovery_allowed:
                recovery_count += 1
            cash_floor_override = None
            if variant.momentum_cash_floor:
                current_close = float(close.loc[dt])
                use_high_floor = (
                    variant.adaptive_momentum_cash
                    and pd.notna(ret20.loc[dt])
                    and pd.notna(ma60.loc[dt])
                    and current_close < float(ma60.loc[dt])
                    and float(ret20.loc[dt]) < -0.03
                )
                if use_high_floor:
                    cash_floor_override = max(0.22, variant.momentum_cash_ma60_floor)
                elif pd.notna(ma60.loc[dt]) and current_close < float(ma60.loc[dt]):
                    cash_floor_override = variant.momentum_cash_ma60_floor
                elif (
                    pd.notna(ma20.loc[dt])
                    and (current_close < float(ma20.loc[dt]) or not bool(ma20_rising.loc[dt]))
                ):
                    cash_floor_override = variant.momentum_cash_ma20_floor
                else:
                    cash_floor_override = variant.momentum_cash_base_floor
                if cash_floor_override > variant.momentum_cash_base_floor:
                    momentum_cash_count += 1
            blended, blended_cash, blend_diag = _blend_targets(last_ppo, regime)
            target, target_cash, overlay_diag = _apply_adv_conditional_inverse(
                blended,
                blended_cash,
                variant=variant,
                risk_off=(overlay_state == "risk_off"),
                conditional_inverse_allowed=conditional_inverse_allowed,
                severe_inverse_allowed=severe_inverse_allowed,
                recovery_allowed=recovery_allowed,
                cash_floor_override=cash_floor_override,
            )
            changed = (
                last_target is None
                or any(abs(target.get(t, 0.0) - last_target.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_cash_weight or 0.0)) > 1e-12
            )
            if changed:
                target_values = {ticker: total_value * target.get(ticker, 0.0) for ticker in TICKERS}
                trade_value = sum(abs(target_values[ticker] - shares[ticker] * float(row[ticker])) for ticker in TICKERS)
                fee = trade_value * fee_rate
                after_fee = max(total_value - fee, 0.0)
                shares = {
                    ticker: after_fee * target.get(ticker, 0.0) / float(row[ticker])
                    for ticker in TICKERS
                }
                cash = after_fee * target_cash
                fees += fee
                rebalances += 1
                if overlay_state == "risk_off":
                    risk_off_rebalance_count += 1
                last_target = dict(target)
                last_cash_weight = float(target_cash)
                total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
                events.append(
                    {
                        "date": str(dt.date()),
                        "regime": regime,
                        "overlay_state": overlay_state,
                        "base_ppo_weights": last_ppo,
                        "target_weights": target,
                        "target_cash_weight": target_cash,
                        "fee": fee,
                        "blend": blend_diag,
                        "overlay": overlay_diag,
                    }
                )

        last_regime = regime
        curve.append({"date": str(dt.date()), "value": float(total_value), "regime": regime, "overlay_state": overlay_state})

    values = pd.Series([item["value"] for item in curve], index=pd.to_datetime([item["date"] for item in curve]))
    final_value = float(values.iloc[-1])
    final_weights = {
        ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / max(final_value, 1.0))
        for ticker in TICKERS
    }
    final_cash_weight = float(cash / max(final_value, 1.0))
    return {
        "metrics": _metrics(values, initial_cash, contributions, fees, rebalances),
        "events": events,
        "equity_curve": curve,
        "regime_counts": regime_counts,
        "control_counts": {
            "risk_off_rebalances": risk_off_rebalance_count,
            "conditional_inverse": conditional_inverse_count,
            "severe_inverse": severe_inverse_count,
            "recovery": recovery_count,
            "momentum_cash": momentum_cash_count,
        },
        "final_shares": shares,
        "final_cash": float(cash),
        "final_weights": final_weights,
        "final_cash_weight": final_cash_weight,
    }


def _comparison_rows(source: dict[str, Any], variant_replays: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    canonical = source["result"]
    canonical_metrics = canonical["rl_metrics"]
    rows = [
        {
            "strategy": "Golden1_0531_canonical_2008_proxy",
            "final_value": canonical["final_value"],
            "total_return": canonical_metrics["total_return"],
            "annual_return": canonical_metrics["annual_return"],
            "sharpe_ratio": canonical_metrics.get("sharpe", canonical_metrics.get("sharpe_ratio", 0.0)),
            "max_drawdown": canonical_metrics["max_drawdown"],
            "num_rebalances": canonical["num_trades"],
            "fees_paid_estimate": canonical["fees_paid_estimate"],
            "dca_total_contributions": canonical["dca_total_contributions"],
            "contribution_return": canonical["contribution_return"],
        },
    ]
    for name, replay in variant_replays.items():
        rows.append({"strategy": f"GroupA_meta_{name}_2008_proxy", **replay["metrics"]})
    for benchmark_name in ["hold_0050", "blend50", "hold_00631L", "hold_00632R"]:
        benchmark = source["benchmarks"][benchmark_name]
        metrics = benchmark["metrics"]
        rows.append(
            {
                "strategy": benchmark_name,
                "final_value": benchmark["final_value"],
                "total_return": metrics["total_return"],
                "annual_return": metrics["annual_return"],
                "sharpe_ratio": metrics["sharpe"],
                "max_drawdown": metrics["max_drawdown"],
                "num_rebalances": 0,
                "fees_paid_estimate": 0.0,
                "dca_total_contributions": 0.0,
                "contribution_return": None,
            }
        )
    return rows


def main() -> None:
    args = _parse_args()
    source_path = _resolve(args.source)
    config_path = _resolve(args.config)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    payload_path = _resolve(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    model_path = _resolve_group_a_model_path(payload, args.model)
    base_exact, prices, _market, base_events = _run_base_exact_events(
        payload,
        model_path=model_path,
        start=args.start,
        end=args.end,
    )
    variant_replays = {
        variant.name: _simulate(prices, source, variant=variant, fee_rate=float(args.fee_rate), base_exact=base_exact)
        for variant in _variants()
    }
    replay = variant_replays["adv_conditional_inverse"]
    canonical = source["result"]
    rows = _comparison_rows(source, variant_replays)
    ranked = sorted(
        (
            {
                "variant": name,
                **replay_item["metrics"],
                "final_cash_weight": replay_item["final_cash_weight"],
                "final_00631L_weight": replay_item["final_weights"]["00631L.TW"],
                "control_counts": replay_item["control_counts"],
                "delta_final_vs_canonical": replay_item["metrics"]["final_value"] - canonical["final_value"],
                "delta_mdd_vs_canonical": replay_item["metrics"]["max_drawdown"] - canonical["rl_metrics"]["max_drawdown"],
                "delta_final_vs_base_exact": replay_item["metrics"]["final_value"] - base_exact["final_value"],
                "delta_sharpe_vs_base_exact": replay_item["metrics"]["sharpe_ratio"] - base_exact["sharpe_ratio"],
                "delta_mdd_vs_base_exact": replay_item["metrics"]["max_drawdown"] - base_exact["max_drawdown"],
            }
            for name, replay_item in variant_replays.items()
        ),
        key=lambda row: (row["final_value"], row["sharpe_ratio"]),
        reverse=True,
    )

    if args.output:
        output = _resolve(args.output)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = DEFAULT_OUTPUT_DIR / f"group_a_meta_adv_conditional_inverse_twii_proxy_2008_{args.start.replace('-', '')}_{args.end.replace('-', '')}_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "experiment": "group_a_meta_adv_conditional_inverse_twii_proxy_2008_sweep",
        "source": str(source_path.resolve()),
        "config": str(config_path.resolve()),
        "payload": str(payload_path.resolve()),
        "model_path": str(model_path.resolve()),
        "selected_allocator_profile": config.get("selected_allocator_profile"),
        "selected_signal_profile": "adv_conditional_inverse",
        "proxy_asset": "^TWII",
        "twii_market_cache": str(DEFAULT_TWII_MARKET_CACHE.resolve()),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": base_exact["actual_start"], "end": base_exact["actual_end"], "rows": base_exact["rows"]},
        "method_note": (
            "Runs Golden1_0531 on the 2008 proxy path, records every PPO/PVA rebalance event, then applies the selected meta "
            "adv_conditional_inverse overlay. 2008 TDCC history is unavailable, so risk-off "
            "overlay state is driven by the price-regime proxy."
        ),
        "limitations": [
            "Synthetic 0050/00631L/00632R prices are generated from TWII daily returns.",
            "TDCC, A2C, and SAC 2008 histories are unavailable; A2C/SAC allocation sleeves fall back to PPO where needed.",
            "This is a stress test for strategy behavior on a 2008-like path, not an exact historical execution record.",
        ],
        "strategy_controls": {
            "risk_off_00631L_cap": 0.08,
            "released_leverage_budget_destination": "0050.TW",
            "zero_small_inverse_threshold": 0.01,
            "conditional_inverse_weight": 0.01,
            "conditional_inverse_condition": "0050 close < MA60 and 5-day return < -3%",
        },
        "canonical_2008_proxy": {
            "final_value": canonical["final_value"],
            "rl_metrics": canonical["rl_metrics"],
            "num_trades": canonical["num_trades"],
            "fees_paid_estimate": canonical["fees_paid_estimate"],
            "dca_total_contributions": canonical["dca_total_contributions"],
            "contribution_return": canonical["contribution_return"],
        },
        "base_exact_event_capture": base_exact,
        "base_event_count": len(base_events),
        "variant_ranking": ranked,
        "variant_replays": variant_replays,
        "meta_adv_conditional_inverse_replay": replay,
        "delta_meta_vs_canonical": {
            "final_value": replay["metrics"]["final_value"] - canonical["final_value"],
            "sharpe_ratio": replay["metrics"]["sharpe_ratio"] - canonical["rl_metrics"].get("sharpe", 0.0),
            "max_drawdown": replay["metrics"]["max_drawdown"] - canonical["rl_metrics"]["max_drawdown"],
            "fees_paid_estimate": replay["metrics"]["fees_paid_estimate"] - canonical["fees_paid_estimate"],
            "rebalances": replay["metrics"]["num_rebalances"] - canonical["num_trades"],
            "contribution_return": replay["metrics"]["contribution_return"] - canonical["contribution_return"],
        },
        "delta_meta_vs_base_exact_capture": {
            "final_value": replay["metrics"]["final_value"] - base_exact["final_value"],
            "sharpe_ratio": replay["metrics"]["sharpe_ratio"] - base_exact["sharpe_ratio"],
            "max_drawdown": replay["metrics"]["max_drawdown"] - base_exact["max_drawdown"],
            "fees_paid_estimate": replay["metrics"]["fees_paid_estimate"] - base_exact["fees_paid_estimate"],
            "rebalances": replay["metrics"]["num_rebalances"] - base_exact["num_trades"],
            "contribution_return": replay["metrics"]["contribution_return"] - base_exact["contribution_return"],
        },
        "comparison_rows": rows,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    ranking_csv_path = output.with_name(output.stem + "_ranking.csv")
    pd.DataFrame(ranked).to_csv(ranking_csv_path, index=False, encoding="utf-8-sig")

    metrics = replay["metrics"]
    delta = report["delta_meta_vs_canonical"]
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Ranking CSV: {ranking_csv_path}")
    print(f"Actual window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    print(
        "Canonical Golden1_0531: "
        f"final={canonical['final_value']:.2f}, sharpe={canonical['rl_metrics'].get('sharpe', 0.0):.4f}, "
        f"mdd={canonical['rl_metrics']['max_drawdown']:.4%}, trades={canonical['num_trades']}"
    )
    print(
        "Base exact capture: "
        f"final={base_exact['final_value']:.2f}, sharpe={base_exact['sharpe_ratio']:.4f}, "
        f"mdd={base_exact['max_drawdown']:.4%}, trades={base_exact['num_trades']}, events={len(base_events)}"
    )
    print(
        "Meta adv_conditional_inverse: "
        f"final={metrics['final_value']:.2f}, sharpe={metrics['sharpe_ratio']:.4f}, "
        f"mdd={metrics['max_drawdown']:.4%}, rebalances={metrics['num_rebalances']}, "
        f"cash={replay['final_cash_weight']:.2%}"
    )
    print(
        "Delta vs canonical: "
        f"final={delta['final_value']:.2f}, sharpe={delta['sharpe_ratio']:.4f}, "
        f"mdd={delta['max_drawdown']:.4%}, rebalances={delta['rebalances']}"
    )
    delta_exact = report["delta_meta_vs_base_exact_capture"]
    print(
        "Delta vs base exact capture: "
        f"final={delta_exact['final_value']:.2f}, sharpe={delta_exact['sharpe_ratio']:.4f}, "
        f"mdd={delta_exact['max_drawdown']:.4%}, rebalances={delta_exact['rebalances']}"
    )
    print("Top variants:")
    for row in ranked[:8]:
        print(
            f"  {row['variant']}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, rebalances={row['num_rebalances']}, "
            f"cash={row['final_cash_weight']:.2%}, 631L={row['final_00631L_weight']:.2%}"
        )


if __name__ == "__main__":
    main()
