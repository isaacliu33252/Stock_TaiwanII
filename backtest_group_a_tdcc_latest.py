#!/usr/bin/env python3
"""Backtest the latest Group A TDCC overlay without retraining the PPO model."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from stable_baselines3 import PPO

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
    attach_group_a_market_margin_shared_features_db_first,
    attach_institutional_features_db_first,
    attach_market_features_db_first,
    calculate_backtest_metrics,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_taifex_futures_features,
    payload_uses_group_a_market_margin_shared_features,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RESULT_JSON = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_tdcc_latest_backtest_202506_20260603.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2025-06-01")
    parser.add_argument("--end", default="2026-06-03")
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_prices(db_path: Path, dates: list[pd.Timestamp]) -> pd.DataFrame:
    start = str(min(dates).date())
    end = str(max(dates).date())
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (?, ?, ?) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*TICKERS, start, end],
        ).fetchdf()
    finally:
        con.close()
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.reindex(pd.to_datetime(dates)).dropna(subset=TICKERS)
    return prices


def _run_base_backtest(
    payload: dict[str, Any],
    result_json: Path,
    *,
    start: str,
    end: str,
    download_end: str,
) -> tuple[dict[str, Any], pd.DataFrame, list[dict[str, Any]], list[str]]:
    group = payload["group_a"]
    tickers = list(group["tickers"])
    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{group['model_name']}.zip"
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    history_start = str(payload.get("train_start") or group.get("train_start") or "2020-01-01")
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if payload.get("group_a_use_llm_sentiment") else None

    stock_data = load_stock_data_db_first(tickers, history_start, download_end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_a_taifex_futures_features(payload):
        stock_data = attach_group_a_taifex_futures_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, history_start, download_end)
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
        raise RuntimeError("No aligned panel rows for requested backtest")

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

    def record_rebalance(target_weights: np.ndarray, prices: np.ndarray) -> float:
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
    info = {"weights": np.zeros(len(tickers))}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(value) for value in env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    summary = {
        "source_result_json": str(result_json.resolve()),
        "model_path": str(model_path.resolve()),
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
    }
    return summary, panel, events, tickers


def _metrics(values: pd.Series, initial_cash: float, contributions: float, fees: float, rebalances: int) -> dict[str, Any]:
    returns = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    max_drawdown = float((values / values.cummax() - 1.0).min())
    invested = initial_cash + contributions
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "num_rebalances": int(rebalances),
        "fees_paid_estimate": float(fees),
        "dca_total_contributions": float(contributions),
        "total_invested_capital": float(invested),
        "net_profit": float(values.iloc[-1] - invested),
        "contribution_return": float((values.iloc[-1] - invested) / max(invested, 1.0)),
    }


def _simulate_tdcc_overlay(
    prices: pd.DataFrame,
    events: list[dict[str, Any]],
    config: dict[str, Any],
    db_path: Path,
    *,
    initial_cash: float,
    fee_rate: float,
    dca_history: list[dict[str, Any]],
) -> dict[str, Any]:
    event_by_date = {
        pd.Timestamp(event["date"]).normalize(): dict(event["target_weights"])
        for event in events
    }
    states = {dt: _raw_tdcc_state(config, db_path, dt) for dt in prices.index}
    raw_states = [str(states[dt]["state"]) for dt in prices.index]
    effective_states = _apply_hysteresis(raw_states, Variant("latest_default", risk_off_cap=float(config["risk_off"]["leverage_weight_cap"])))
    state_by_date = dict(zip(prices.index, effective_states))
    dca_by_date = {
        pd.Timestamp(item["date"]).normalize(): item
        for item in dca_history
    }
    variant = Variant(
        "latest_default",
        risk_off_cap=float(config["risk_off"]["leverage_weight_cap"]),
        caution_cap=float(config["caution"]["leverage_weight_cap"]),
        destination=str(config.get("released_leverage_budget_destination", "cash")),
        primary_fraction=float(config.get("released_to_primary_fraction", 0.5)),
        inverse_weight=(
            float(dict(config.get("inverse_hedge_on_tdcc_risk_off", {})).get("weight", 0.0))
            if dict(config.get("inverse_hedge_on_tdcc_risk_off", {})).get("enabled", False)
            else 0.0
        ),
    )
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_cash
    fees = 0.0
    contributions = 0.0
    rebalances = 0
    last_base_weights: dict[str, float] | None = None
    last_target_weights: dict[str, float] | None = None
    last_target_cash: float | None = None
    last_state: str | None = None
    curve = []
    overlay_events = []
    state_counts = {"normal": 0, "caution": 0, "risk_off": 0, "insufficient_data": 0}
    for dt, row in prices.iterrows():
        state = state_by_date[dt]
        state_counts[state] = state_counts.get(state, 0) + 1
        if dt in dca_by_date:
            item = dca_by_date[dt]
            purchase = item.get("purchases", {}).get("0050.TW")
            amount = float(item.get("total_contribution", 0.0))
            if purchase and amount > 0:
                fee = amount * fee_rate / (1.0 + fee_rate)
                buy_value = amount - fee
                shares["0050.TW"] += buy_value / float(row["0050.TW"])
                fees += fee
                contributions += amount
            elif amount > 0:
                cash += amount
                contributions += amount
        total_value = cash + sum(shares[t] * float(row[t]) for t in TICKERS)
        if dt in event_by_date:
            last_base_weights = event_by_date[dt]
        state_changed = last_state is not None and state != last_state
        should_rebalance = (dt in event_by_date) or (state_changed and last_base_weights is not None)
        if should_rebalance and last_base_weights is not None:
            base_cash = max(0.0, 1.0 - sum(last_base_weights.values()))
            target_weights, target_cash = _overlay_weights(
                last_base_weights,
                base_cash,
                state,
                variant,
                config,
                states[dt],
            )
            changed = (
                last_target_weights is None
                or any(abs(target_weights.get(t, 0.0) - last_target_weights.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_target_cash or 0.0)) > 1e-12
            )
            if changed:
                target_values = {ticker: total_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
                trade_value = sum(abs(target_values[ticker] - shares[ticker] * float(row[ticker])) for ticker in TICKERS)
                fee = trade_value * fee_rate
                total_after_fee = max(total_value - fee, 0.0)
                shares = {
                    ticker: total_after_fee * target_weights.get(ticker, 0.0) / float(row[ticker])
                    for ticker in TICKERS
                }
                cash = total_after_fee * target_cash
                fees += fee
                rebalances += 1
                last_target_weights = dict(target_weights)
                last_target_cash = float(target_cash)
                total_value = cash + sum(shares[t] * float(row[t]) for t in TICKERS)
                overlay_events.append(
                    {
                        "date": str(dt.date()),
                        "tdcc_state": state,
                        "base_weights": last_base_weights,
                        "target_weights": target_weights,
                        "target_cash_weight": target_cash,
                        "fee": float(fee),
                    }
                )
        last_state = state
        curve.append({"date": str(dt.date()), "value": float(total_value), "tdcc_state": state})
    values = pd.Series([item["value"] for item in curve], index=pd.to_datetime([item["date"] for item in curve]))
    return {
        "metrics": _metrics(values, initial_cash, contributions, fees, rebalances),
        "state_counts": state_counts,
        "events": overlay_events,
        "equity_curve": curve,
        "final_shares": shares,
        "final_cash": float(cash),
    }


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    download_end = args.download_end or args.end
    base, panel, events, tickers = _run_base_backtest(
        payload,
        result_json,
        start=args.start,
        end=args.end,
        download_end=download_end,
    )
    dates = [pd.Timestamp(value).normalize() for value in panel["date"].tolist()]
    prices = _load_prices(db_path, dates)
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    latest = _simulate_tdcc_overlay(
        prices,
        events,
        config,
        db_path,
        initial_cash=initial_cash,
        fee_rate=float(args.fee_rate),
        dca_history=base["dca_purchase_history"],
    )
    report = {
        "experiment": "group_a_latest_tdcc_backtest",
        "method_note": (
            "No retraining. Loads the Golden1_0531 PPO model and payload, records base "
            "rebalance targets, then replays the TDCC overlay with historical availability cutoffs. "
            "Requested end may be later than actual OHLCV availability."
        ),
        "requested_window": {"start": args.start, "end": args.end, "download_end": download_end},
        "actual_window": {"start": base["actual_start"], "end": base["actual_end"], "rows": base["rows"]},
        "base_strategy": "Golden1_0531",
        "latest_strategy": config["strategy_name"],
        "config": config,
        "base_exact_backtest": base,
        "latest_tdcc_overlay_replay": latest,
        "delta_latest_vs_base_exact": {
            "final_value": latest["metrics"]["final_value"] - base["final_value"],
            "sharpe_ratio": latest["metrics"]["sharpe_ratio"] - base["sharpe_ratio"],
            "max_drawdown": latest["metrics"]["max_drawdown"] - base["max_drawdown"],
            "fees_paid_estimate": latest["metrics"]["fees_paid_estimate"] - base["fees_paid_estimate"],
            "num_trades_or_rebalances": latest["metrics"]["num_rebalances"] - base["num_trades"],
        },
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        {"strategy": "Golden1_0531_base_exact", **{k: v for k, v in base.items() if isinstance(v, (int, float, str))}},
        {"strategy": "Golden1_0531_tdcc_v1_latest", **latest["metrics"]},
    ]
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Actual window: {base['actual_start']} ~ {base['actual_end']} ({base['rows']} rows)")
    print(
        "Base exact: "
        f"final={base['final_value']:.2f}, sharpe={base['sharpe_ratio']:.4f}, "
        f"mdd={base['max_drawdown']:.4%}, trades={base['num_trades']}, fees={base['fees_paid_estimate']:.2f}"
    )
    latest_metrics = latest["metrics"]
    print(
        "Latest TDCC replay: "
        f"final={latest_metrics['final_value']:.2f}, sharpe={latest_metrics['sharpe_ratio']:.4f}, "
        f"mdd={latest_metrics['max_drawdown']:.4%}, rebalances={latest_metrics['num_rebalances']}, "
        f"fees={latest_metrics['fees_paid_estimate']:.2f}"
    )


if __name__ == "__main__":
    try:
        import numpy.core.numeric as _numpy_core_numeric

        sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
    except ImportError:
        pass
    main()
