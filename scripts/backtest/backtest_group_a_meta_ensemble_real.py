#!/usr/bin/env python3
"""Backtest Group A meta ensemble using real A2C/SAC shadow checkpoints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from stable_baselines3 import A2C, SAC

from backtest_group_a_meta_ensemble import (
    _allocator_weights,
    _normalize,
    _price_regimes,
    _rule_strategy,
)
from backtest_group_a_tdcc_latest import (
    DEFAULT_CONFIG,
    DEFAULT_DB,
    DEFAULT_RESULT_JSON,
    PROJECT_ROOT,
    TICKERS,
    _load_prices,
    _metrics,
    _resolve,
    _run_base_backtest,
    _simulate_tdcc_overlay,
)
from evaluate_group_a_tdcc_overlay_variants import (
    Variant,
    _apply_hysteresis,
    _overlay_weights,
    _raw_tdcc_state,
)
from generate_dual_group_signal import _env_kwargs_from_payload, _llm_sentiment_path_from_payload
from train_dual_group_2024_2026 import (
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    attach_group_a_taifex_futures_features_db_first,
    attach_institutional_features_db_first,
    attach_market_features_db_first,
    calculate_backtest_metrics,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_taifex_futures_features,
)
from train_group_a_a2c_sac_shadow import ContinuousWeightPortfolioEnv, DiscreteToContinuousActionEnv


DEFAULT_TRAINING_REPORT = PROJECT_ROOT / "results" / "group_a_a2c_sac_shadow_training_100k_20260603.json"
DEFAULT_A2C_MODEL = PROJECT_ROOT / "models" / "portfolio" / "group_a_a2c_shadow_20260603_110247.zip"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_meta_ensemble_real_backtest_202506_20260603.json"
DEFAULT_META_CONFIG = PROJECT_ROOT / "group_a_meta_ensemble_real_config.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--training-report", default=str(DEFAULT_TRAINING_REPORT))
    parser.add_argument("--a2c-model-path", default=None)
    parser.add_argument("--sac-model-path", default=None)
    parser.add_argument("--sac-mode", choices=["discrete_scalar", "continuous_weights"], default=None)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="TDCC overlay config")
    parser.add_argument("--meta-config", default=str(DEFAULT_META_CONFIG), help="Meta ensemble allocator config")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2025-06-01")
    parser.add_argument("--end", default="2026-06-03")
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _load_panel(
    payload: dict[str, Any],
    *,
    start: str,
    end: str,
    download_end: str,
) -> tuple[pd.DataFrame, list[str], dict[str, Any], list[str], float]:
    group = payload["group_a"]
    tickers = list(group["tickers"])
    history_start = str(payload.get("train_start") or group.get("train_start") or "2020-01-01")
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if payload.get("group_a_use_llm_sentiment") else None
    stock_data = load_stock_data_db_first(tickers, history_start, download_end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_a_taifex_futures_features(payload):
        stock_data = attach_group_a_taifex_futures_features_db_first(stock_data, tickers, history_start, download_end)
    if shared_feature_cols:
        stock_data = attach_market_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
            include_llm_sentiment=bool(payload.get("group_a_use_llm_sentiment", False)),
            llm_sentiment_path=llm_path,
        )
    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols)
    if panel.empty:
        raise RuntimeError("No aligned panel rows")
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    return panel, tickers, env_kwargs, shared_feature_cols, initial_cash


def _run_shadow_agent(
    model_path: Path,
    model_cls: type[A2C] | type[SAC],
    panel: pd.DataFrame,
    tickers: list[str],
    env_kwargs: dict[str, Any],
    shared_feature_cols: list[str],
    initial_cash: float,
    *,
    continuous: bool,
    continuous_weights: bool = False,
) -> dict[str, Any]:
    env_cls = ContinuousWeightPortfolioEnv if continuous_weights else PortfolioEnv
    base_env = env_cls(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **dict(env_kwargs),
    )
    env = DiscreteToContinuousActionEnv(base_env) if continuous and not continuous_weights else base_env
    model = model_cls.load(str(model_path), env=env)
    events: list[dict[str, Any]] = []
    original_rebalance = base_env._rebalance

    def record_rebalance(target_weights: np.ndarray, prices: np.ndarray) -> float:
        fee = original_rebalance(target_weights, prices)
        if fee > 0:
            trade_idx = min(base_env.step_idx + 1, len(base_env.date_strings) - 1)
            events.append(
                {
                    "date": base_env.date_strings[trade_idx],
                    "step_idx": int(trade_idx),
                    "target_weights": {
                        ticker: float(weight)
                        for ticker, weight in zip(tickers, target_weights)
                    },
                    "fee": float(fee),
                }
            )
        return fee

    base_env._rebalance = record_rebalance  # type: ignore[method-assign]
    obs, _ = env.reset()
    info = {"weights": np.zeros(len(tickers))}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(value) for value in base_env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    return {
        "model_path": str(model_path.resolve()),
        "actual_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_end": str(pd.Timestamp(panel["date"].max()).date()),
        "rows": int(len(panel)),
        "final_value": float(equity[-1]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics.get("sharpe_ratio", metrics.get("sharpe", 0.0))),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_trades": int(base_env.trade_count),
        "fees_paid_estimate": float(base_env.fees_paid),
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
        "equity_curve": equity,
        "rebalance_events": events,
    }


def _event_map(events: list[dict[str, Any]]) -> dict[pd.Timestamp, dict[str, float]]:
    return {
        pd.Timestamp(event["date"]).normalize(): dict(event["target_weights"])
        for event in events
    }


def _allocator_profile_from_config(config: dict[str, Any]) -> dict[str, dict[str, float]]:
    profile_name = str(config.get("selected_allocator_profile") or "")
    profiles = dict(config.get("allocator_profiles", {}) or {})
    if profile_name and profile_name in profiles:
        return {
            regime: {name: float(weight) for name, weight in dict(weights).items()}
            for regime, weights in dict(profiles[profile_name]).items()
        }
    return {
        "risk_on": {
            "ppo": _allocator_weights("risk_on").get("ppo", 0.0),
            "a2c": _allocator_weights("risk_on").get("a2c_proxy", 0.0),
            "sac": _allocator_weights("risk_on").get("sac_proxy", 0.0),
            "rule_based": _allocator_weights("risk_on").get("rule_based", 0.0),
        },
        "neutral": {
            "ppo": _allocator_weights("neutral").get("ppo", 0.0),
            "a2c": _allocator_weights("neutral").get("a2c_proxy", 0.0),
            "sac": _allocator_weights("neutral").get("sac_proxy", 0.0),
            "rule_based": _allocator_weights("neutral").get("rule_based", 0.0),
        },
        "risk_off": {
            "ppo": _allocator_weights("risk_off").get("ppo", 0.0),
            "a2c": _allocator_weights("risk_off").get("a2c_proxy", 0.0),
            "sac": _allocator_weights("risk_off").get("sac_proxy", 0.0),
            "rule_based": _allocator_weights("risk_off").get("rule_based", 0.0),
        },
    }


def _blend_real(
    ppo: dict[str, float],
    a2c: dict[str, float],
    sac: dict[str, float],
    regime: str,
    allocator_profile: dict[str, dict[str, float]],
) -> tuple[dict[str, float], float, dict[str, Any]]:
    rule, rule_cash = _rule_strategy(regime)
    ppo, ppo_cash = _normalize(ppo, max(0.0, 1.0 - sum(ppo.values())))
    a2c, a2c_cash = _normalize(a2c, max(0.0, 1.0 - sum(a2c.values())))
    sac, sac_cash = _normalize(sac, max(0.0, 1.0 - sum(sac.values())))
    sleeves = {
        "ppo": (ppo, ppo_cash),
        "a2c": (a2c, a2c_cash),
        "sac": (sac, sac_cash),
        "rule_based": (rule, rule_cash),
    }
    alloc = dict(allocator_profile.get(regime, allocator_profile.get("neutral", {})))
    total_alloc = sum(max(float(weight), 0.0) for weight in alloc.values())
    if total_alloc <= 0:
        alloc = {"ppo": 1.0, "a2c": 0.0, "sac": 0.0, "rule_based": 0.0}
        total_alloc = 1.0
    alloc = {name: max(float(weight), 0.0) / total_alloc for name, weight in alloc.items()}
    weights = {ticker: 0.0 for ticker in TICKERS}
    cash = 0.0
    for name, sleeve_weight in alloc.items():
        sleeve_weights, sleeve_cash = sleeves[name]
        for ticker in TICKERS:
            weights[ticker] += sleeve_weight * sleeve_weights.get(ticker, 0.0)
        cash += sleeve_weight * sleeve_cash
    weights, cash = _normalize(weights, cash)
    return weights, cash, {
        "regime": regime,
        "allocator_weights": alloc,
        "sleeves": {
            name: {"weights": sleeve_weights, "cash": sleeve_cash}
            for name, (sleeve_weights, sleeve_cash) in sleeves.items()
        },
    }


def _simulate_real_meta(
    prices: pd.DataFrame,
    *,
    ppo_events: list[dict[str, Any]],
    a2c_events: list[dict[str, Any]],
    sac_events: list[dict[str, Any]],
    config: dict[str, Any],
    allocator_profile: dict[str, dict[str, float]],
    db_path: Path,
    initial_cash: float,
    fee_rate: float,
    dca_history: list[dict[str, Any]],
) -> dict[str, Any]:
    ppo_by_date = _event_map(ppo_events)
    a2c_by_date = _event_map(a2c_events)
    sac_by_date = _event_map(sac_events)
    raw = {dt: _raw_tdcc_state(config, db_path, dt) for dt in prices.index}
    raw_states = [str(raw[dt]["state"]) for dt in prices.index]
    effective_states = _apply_hysteresis(raw_states, Variant("latest_default", risk_off_cap=float(config["risk_off"]["leverage_weight_cap"])))
    tdcc_by_date = dict(zip(prices.index, effective_states))
    regime_by_date = _price_regimes(prices, tdcc_by_date)
    variant = Variant(
        "latest_default",
        risk_off_cap=float(config["risk_off"]["leverage_weight_cap"]),
        caution_cap=float(config["caution"]["leverage_weight_cap"]),
        destination=str(config.get("released_leverage_budget_destination", "cash")),
        primary_fraction=float(config.get("released_to_primary_fraction", 0.5)),
    )
    dca_by_date = {pd.Timestamp(item["date"]).normalize(): item for item in dca_history}

    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_cash
    fees = 0.0
    contributions = 0.0
    rebalances = 0
    last_ppo: dict[str, float] | None = None
    last_a2c: dict[str, float] | None = None
    last_sac: dict[str, float] | None = None
    last_target: dict[str, float] | None = None
    last_cash: float | None = None
    last_state: str | None = None
    last_regime: str | None = None
    curve: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    regime_counts = {"risk_on": 0, "neutral": 0, "risk_off": 0}
    state_counts = {"normal": 0, "caution": 0, "risk_off": 0, "insufficient_data": 0}

    for dt, row in prices.iterrows():
        tdcc_state = tdcc_by_date[dt]
        regime = regime_by_date[dt]
        state_counts[tdcc_state] = state_counts.get(tdcc_state, 0) + 1
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
        if dt in dca_by_date:
            item = dca_by_date[dt]
            purchase = item.get("purchases", {}).get("0050.TW")
            amount = float(item.get("total_contribution", 0.0))
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
        if dt in ppo_by_date:
            last_ppo = ppo_by_date[dt]
            updated = True
        if dt in a2c_by_date:
            last_a2c = a2c_by_date[dt]
            updated = True
        if dt in sac_by_date:
            last_sac = sac_by_date[dt]
            updated = True
        state_changed = last_state is not None and tdcc_state != last_state
        regime_changed = last_regime is not None and regime != last_regime
        should_rebalance = updated or state_changed or regime_changed
        if should_rebalance and last_ppo is not None:
            a2c_weights = last_a2c if last_a2c is not None else last_ppo
            sac_weights = last_sac if last_sac is not None else last_ppo
            blended, blended_cash, diagnostics = _blend_real(last_ppo, a2c_weights, sac_weights, regime, allocator_profile)
            target, target_cash = _overlay_weights(blended, blended_cash, tdcc_state, variant, config, raw[dt])
            target, target_cash = _normalize(target, target_cash)
            changed = (
                last_target is None
                or any(abs(target.get(t, 0.0) - last_target.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_cash or 0.0)) > 1e-12
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
                last_target = dict(target)
                last_cash = target_cash
                total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
                events.append(
                    {
                        "date": str(dt.date()),
                        "tdcc_state": tdcc_state,
                        "regime": regime,
                        "target_weights": target,
                        "target_cash_weight": target_cash,
                        "pre_tdcc_meta_weights": blended,
                        "pre_tdcc_meta_cash_weight": blended_cash,
                        "fee": float(fee),
                        "diagnostics": diagnostics,
                    }
                )
        last_state = tdcc_state
        last_regime = regime
        curve.append({"date": str(dt.date()), "value": float(total_value), "tdcc_state": tdcc_state, "regime": regime})

    values = pd.Series([item["value"] for item in curve], index=pd.to_datetime([item["date"] for item in curve]))
    final_value = float(values.iloc[-1])
    final_weights = {ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / final_value) for ticker in TICKERS}
    return {
        "metrics": _metrics(values, initial_cash, contributions, fees, rebalances),
        "tdcc_state_counts": state_counts,
        "regime_counts": regime_counts,
        "events": events,
        "equity_curve": curve,
        "final_shares": shares,
        "final_cash": float(cash),
        "final_weights": final_weights,
        "final_cash_weight": float(cash / max(final_value, 1.0)),
    }


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    training_report = _resolve(args.training_report)
    config_path = _resolve(args.config)
    meta_config_path = _resolve(args.meta_config)
    db_path = _resolve(args.db)
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    trained = json.loads(training_report.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    meta_config = json.loads(meta_config_path.read_text(encoding="utf-8"))
    allocator_profile = _allocator_profile_from_config(meta_config)
    download_end = args.download_end or args.end
    base, base_panel, ppo_events, tickers = _run_base_backtest(
        payload,
        result_json,
        start=args.start,
        end=args.end,
        download_end=download_end,
    )
    panel, _tickers, env_kwargs, shared_feature_cols, initial_cash = _load_panel(
        payload,
        start=args.start,
        end=args.end,
        download_end=download_end,
    )
    dates = [pd.Timestamp(value).normalize() for value in base_panel["date"].tolist()]
    prices = _load_prices(db_path, dates)
    a2c_path = (
        _resolve(args.a2c_model_path)
        if args.a2c_model_path
        else Path(trained.get("models", {}).get("a2c", {}).get("model_path", str(DEFAULT_A2C_MODEL)))
    )
    sac_path = (
        _resolve(args.sac_model_path)
        if args.sac_model_path
        else Path(trained["models"]["sac"]["model_path"])
    )
    sac_mode = str(args.sac_mode or trained["models"]["sac"].get("sac_mode", trained.get("sac_mode", "discrete_scalar")))
    sac_continuous_weights = sac_mode == "continuous_weights"
    a2c = _run_shadow_agent(a2c_path, A2C, panel, tickers, env_kwargs, shared_feature_cols, initial_cash, continuous=False)
    sac = _run_shadow_agent(
        sac_path,
        SAC,
        panel,
        tickers,
        env_kwargs,
        shared_feature_cols,
        initial_cash,
        continuous=True,
        continuous_weights=sac_continuous_weights,
    )
    latest_tdcc = _simulate_tdcc_overlay(
        prices,
        ppo_events,
        config,
        db_path,
        initial_cash=initial_cash,
        fee_rate=float(args.fee_rate),
        dca_history=base["dca_purchase_history"],
    )
    meta = _simulate_real_meta(
        prices,
        ppo_events=ppo_events,
        a2c_events=a2c["rebalance_events"],
        sac_events=sac["rebalance_events"],
        config=config,
        allocator_profile=allocator_profile,
        db_path=db_path,
        initial_cash=initial_cash,
        fee_rate=float(args.fee_rate),
        dca_history=base["dca_purchase_history"],
    )
    report = {
        "experiment": "GroupA_meta_ensemble_real_shadow",
        "method_note": (
            "No production promotion. Uses Golden1 PPO plus retrained A2C/SAC shadow checkpoints. "
            "SAC checkpoint was trained through a continuous-to-discrete action wrapper."
        ),
        "source_result_json": str(result_json.resolve()),
        "training_report": str(training_report.resolve()),
        "tdcc_config": str(config_path.resolve()),
        "meta_config": str(meta_config_path.resolve()),
        "sac_mode": sac_mode,
        "requested_window": {"start": args.start, "end": args.end, "download_end": download_end},
        "actual_window": {"start": base["actual_start"], "end": base["actual_end"], "rows": base["rows"]},
        "selected_allocator_profile": str(meta_config.get("selected_allocator_profile") or "legacy_default"),
        "regime_allocator": allocator_profile,
        "base_exact_backtest": base,
        "a2c_shadow_backtest": a2c,
        "sac_shadow_backtest": sac,
        "latest_tdcc_overlay_replay": latest_tdcc,
        "meta_ensemble_real_replay": meta,
        "delta_meta_vs_base_exact": {
            "final_value": meta["metrics"]["final_value"] - base["final_value"],
            "sharpe_ratio": meta["metrics"]["sharpe_ratio"] - base["sharpe_ratio"],
            "max_drawdown": meta["metrics"]["max_drawdown"] - base["max_drawdown"],
            "fees_paid_estimate": meta["metrics"]["fees_paid_estimate"] - base["fees_paid_estimate"],
            "num_trades_or_rebalances": meta["metrics"]["num_rebalances"] - base["num_trades"],
        },
        "delta_meta_vs_latest_tdcc": {
            "final_value": meta["metrics"]["final_value"] - latest_tdcc["metrics"]["final_value"],
            "sharpe_ratio": meta["metrics"]["sharpe_ratio"] - latest_tdcc["metrics"]["sharpe_ratio"],
            "max_drawdown": meta["metrics"]["max_drawdown"] - latest_tdcc["metrics"]["max_drawdown"],
            "fees_paid_estimate": meta["metrics"]["fees_paid_estimate"] - latest_tdcc["metrics"]["fees_paid_estimate"],
            "num_rebalances": meta["metrics"]["num_rebalances"] - latest_tdcc["metrics"]["num_rebalances"],
        },
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    rows = [
        {"strategy": "Golden1_0531_base_exact", **{k: v for k, v in base.items() if isinstance(v, (int, float, str))}},
        {"strategy": "A2C_shadow_100k", **{k: v for k, v in a2c.items() if isinstance(v, (int, float, str))}},
        {"strategy": "SAC_shadow_100k", **{k: v for k, v in sac.items() if isinstance(v, (int, float, str))}},
        {"strategy": "Golden1_0531_tdcc_v1_latest", **latest_tdcc["metrics"]},
        {"strategy": "GroupA_meta_ensemble_real_shadow", **meta["metrics"]},
    ]
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Actual window: {base['actual_start']} ~ {base['actual_end']} ({base['rows']} rows)")
    print(f"Base: final={base['final_value']:.2f}, sharpe={base['sharpe_ratio']:.4f}, mdd={base['max_drawdown']:.4%}")
    print(f"A2C:  final={a2c['final_value']:.2f}, sharpe={a2c['sharpe_ratio']:.4f}, mdd={a2c['max_drawdown']:.4%}")
    print(f"SAC:  final={sac['final_value']:.2f}, sharpe={sac['sharpe_ratio']:.4f}, mdd={sac['max_drawdown']:.4%}")
    print(
        "Meta real: "
        f"final={meta['metrics']['final_value']:.2f}, sharpe={meta['metrics']['sharpe_ratio']:.4f}, "
        f"mdd={meta['metrics']['max_drawdown']:.4%}, rebalances={meta['metrics']['num_rebalances']}"
    )


if __name__ == "__main__":
    try:
        import numpy.core.numeric as _numpy_core_numeric

        sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
    except ImportError:
        pass
    main()
