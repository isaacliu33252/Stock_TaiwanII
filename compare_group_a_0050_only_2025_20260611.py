#!/usr/bin/env python3
"""Compare Golden1_0531 and latest Group A as 0050-only overlays."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

from generate_dual_group_signal import (
    _align_panel,
    _env_kwargs_from_payload,
    attach_group_a_market_margin_shared_features_db_first,
    attach_group_a_margin_shared_features_db_first,
    attach_group_a_taifex_futures_features_db_first,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    attach_market_features_db_first,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_margin_features,
    payload_uses_group_a_margin_shared_features,
    payload_uses_group_a_market_margin_shared_features,
    payload_uses_group_a_taifex_futures_features,
    _llm_sentiment_path_from_payload,
)
from train_dual_group_2024_2026 import PortfolioEnv


PROJECT_ROOT = Path(__file__).resolve().parent
START = "2025-01-01"
END = "2026-06-11"
INITIAL_CASH = 1_000_000.0
COMMISSION_RATE = 0.001425
ETF_SELL_TAX_RATE = 0.001

GOLDEN_PAYLOAD = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
LATEST_PAYLOAD = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260531_20260609_214023.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _price_frame(panel: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if "tic" in panel.columns or "ticker" in panel.columns:
        ticker_col = "tic" if "tic" in panel.columns else "ticker"
        wide = panel.pivot(index="date", columns=ticker_col, values="close")
        wide.index = pd.to_datetime(wide.index).normalize()
        return wide[tickers].sort_index()
    dates = pd.to_datetime(panel["date"]).dt.normalize()
    wide = pd.DataFrame(
        {ticker: pd.to_numeric(panel[f"{ticker}_close"], errors="coerce").to_numpy() for ticker in tickers},
        index=dates,
    )
    return wide.sort_index()


def _load_panel(payload: dict[str, Any], start: str, end: str) -> tuple[pd.DataFrame, list[str], list[str], dict[str, Any]]:
    tickers = list(payload["group_a"]["tickers"])
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    stock_data = load_stock_data_db_first(tickers, start, end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_taifex_futures_features(payload):
        stock_data = attach_group_a_taifex_futures_features_db_first(stock_data, tickers, start, end)
    if shared_feature_cols:
        llm_enabled = bool(payload.get("group_a_use_llm_sentiment", False))
        llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if llm_enabled else None
        stock_data = attach_market_features_db_first(
            stock_data,
            tickers,
            start,
            end,
            include_llm_sentiment=llm_enabled,
            llm_sentiment_path=llm_path,
        )
    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols or None)
    if panel.empty:
        raise RuntimeError("No aligned panel rows")
    return panel, tickers, shared_feature_cols, env_kwargs


def _capture_events(name: str, payload_path: Path, start: str, end: str) -> dict[str, Any]:
    payload = _load_json(payload_path)
    panel, tickers, shared_feature_cols, env_kwargs = _load_panel(payload, start, end)
    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{payload['group_a']['model_name']}.zip"
    initial_cash = float(payload.get("initial_cash_per_group", INITIAL_CASH))

    load_env = PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols or None,
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
        shared_feature_cols=shared_feature_cols or None,
        initial_cash=initial_cash,
        **env_kwargs,
    )
    original_rebalance = env._rebalance
    events: list[dict[str, Any]] = []

    def record_rebalance(target_weights: np.ndarray, prices: np.ndarray) -> float:
        fee = original_rebalance(target_weights, prices)
        if fee > 0:
            trade_idx = min(env.step_idx + 1, len(env.date_strings) - 1)
            events.append(
                {
                    "date": env.date_strings[trade_idx],
                    "step_idx": int(trade_idx),
                    "target_0050_weight": float(dict(zip(tickers, target_weights)).get("0050.TW", 0.0)),
                    "target_weights": {ticker: float(weight) for ticker, weight in zip(tickers, target_weights)},
                    "target_cash_weight": float(max(0.0, 1.0 - float(np.sum(target_weights)))),
                    "fee": float(fee),
                }
            )
        return fee

    env._rebalance = record_rebalance  # type: ignore[method-assign]
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(action)
        done = bool(terminated or truncated)

    return {
        "name": name,
        "payload": str(payload_path),
        "model": str(model_path),
        "actual_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_end": str(pd.Timestamp(panel["date"].max()).date()),
        "tickers": tickers,
        "shared_feature_cols": shared_feature_cols,
        "prices": _price_frame(panel, tickers),
        "events": events,
        "dca_purchase_history": env.dca_purchase_history,
    }


def _metrics(series: pd.Series, *, rebalances: int, total_cost: float, contributions: float) -> dict[str, float]:
    returns = series.pct_change().dropna()
    years = max(len(returns) / 252.0, 1 / 252.0)
    total_return = float(series.iloc[-1] / INITIAL_CASH - 1.0)
    annual_return = float((series.iloc[-1] / INITIAL_CASH) ** (1.0 / years) - 1.0)
    vol = float(returns.std(ddof=0) * np.sqrt(252)) if len(returns) else 0.0
    sharpe = float((returns.mean() / returns.std(ddof=0)) * np.sqrt(252)) if len(returns) and returns.std(ddof=0) > 0 else 0.0
    peak = series.cummax()
    mdd = float((series / peak - 1.0).min())
    invested = INITIAL_CASH + contributions
    return {
        "final_value": float(series.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
        "num_rebalances": int(rebalances),
        "total_cost": float(total_cost),
        "dca_total_contributions": float(contributions),
        "total_invested_capital": float(invested),
        "net_profit": float(series.iloc[-1] - invested),
        "contribution_return": float((series.iloc[-1] - invested) / invested),
    }


def _apply_0050_weight_overlay(
    events: list[dict[str, Any]],
    *,
    price_series: pd.Series | None = None,
    max_weight_step: float | None = None,
    max_weight: float | None = None,
    min_weight: float = 0.0,
    min_rebalance_delta: float = 0.0,
    ma_brake_window: int | None = None,
    ma_brake_ratio: float = 1.0,
    ma_brake_max_weight: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    adjusted_events: list[dict[str, Any]] = []
    last_weight: float | None = None
    changed_count = 0
    skipped_count = 0
    brake_count = 0
    ma_series = None
    if price_series is not None and ma_brake_window is not None and ma_brake_max_weight is not None:
        ma_series = price_series.rolling(int(ma_brake_window), min_periods=max(5, int(ma_brake_window) // 3)).mean()
    for event in events:
        event_date = pd.Timestamp(event["date"]).normalize()
        raw_weight = float(event["target_0050_weight"])
        target_weight = max(float(min_weight), raw_weight)
        if max_weight is not None:
            target_weight = min(float(max_weight), target_weight)
        if last_weight is not None:
            if max_weight_step is not None:
                step = float(max_weight_step)
                target_weight = last_weight + max(min(target_weight - last_weight, step), -step)
            if abs(target_weight - last_weight) < float(min_rebalance_delta):
                target_weight = last_weight
                skipped_count += 1
        if ma_series is not None and price_series is not None:
            price = price_series.get(event_date)
            ma_value = ma_series.get(event_date)
            if pd.notna(price) and pd.notna(ma_value) and float(price) <= float(ma_value) * float(ma_brake_ratio):
                target_weight = min(target_weight, float(ma_brake_max_weight))
                brake_count += 1
        if abs(target_weight - raw_weight) > 1e-12:
            changed_count += 1
        adjusted = dict(event)
        adjusted["raw_target_0050_weight"] = raw_weight
        adjusted["target_0050_weight"] = float(target_weight)
        adjusted_events.append(adjusted)
        last_weight = float(target_weight)
    return adjusted_events, {
        "enabled": bool(
            max_weight_step is not None
            or max_weight is not None
            or float(min_weight) > 0.0
            or float(min_rebalance_delta) > 0.0
            or ma_series is not None
        ),
        "max_weight_step": max_weight_step,
        "max_weight": max_weight,
        "min_weight": float(min_weight),
        "min_rebalance_delta": float(min_rebalance_delta),
        "ma_brake_window": ma_brake_window,
        "ma_brake_ratio": float(ma_brake_ratio),
        "ma_brake_max_weight": ma_brake_max_weight,
        "changed_events": int(changed_count),
        "skipped_small_delta_events": int(skipped_count),
        "ma_brake_events": int(brake_count),
    }


def _replay_0050_only(
    captured: dict[str, Any],
    *,
    weight_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prices = captured["prices"]
    close_0050 = prices["0050.TW"]
    if weight_overlay:
        overlay_events, overlay_report = _apply_0050_weight_overlay(
            captured["events"],
            price_series=close_0050,
            **weight_overlay,
        )
    else:
        overlay_events, overlay_report = _apply_0050_weight_overlay(captured["events"])
    event_map = {pd.Timestamp(e["date"]).normalize(): e for e in overlay_events}
    dca_map: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for item in captured["dca_purchase_history"]:
        dca_map.setdefault(pd.Timestamp(item["date"]).normalize(), []).append(item)

    cash = INITIAL_CASH
    shares = 0.0
    target_weight = 0.0
    total_cost = 0.0
    contributions = 0.0
    events: list[dict[str, Any]] = []
    values: list[tuple[pd.Timestamp, float]] = []

    for dt, price in close_0050.items():
        price = float(price)
        if dt in dca_map:
            for dca in dca_map[dt]:
                amount = float(dca.get("total_contribution", 0.0))
                fee = amount * COMMISSION_RATE / (1.0 + COMMISSION_RATE)
                buy_value = amount - fee
                shares += buy_value / price
                total_cost += fee
                contributions += amount

        total = cash + shares * price
        if dt in event_map:
            target_weight = max(min(float(event_map[dt]["target_0050_weight"]), 1.0), 0.0)
            target_value = total * target_weight
            current_value = shares * price
            delta = target_value - current_value
            fee = 0.0
            if delta > 0:
                buy_value = min(delta, cash / (1.0 + COMMISSION_RATE))
                fee = buy_value * COMMISSION_RATE
                cash -= buy_value + fee
                shares += buy_value / price
            elif delta < 0:
                sell_value = min(-delta, current_value)
                fee_rate = COMMISSION_RATE + ETF_SELL_TAX_RATE
                fee = sell_value * fee_rate
                cash += sell_value - fee
                shares -= sell_value / price
            total_cost += fee
            total = cash + shares * price
            events.append(
                {
                    "date": str(dt.date()),
                    "price": price,
                    "target_0050_weight": target_weight,
                    "target_0050_shares": float(shares),
                    "cash": float(cash),
                    "fee": float(fee),
                    "value": float(total),
                }
            )
        values.append((dt, cash + shares * price))

    series = pd.Series([v for _, v in values], index=[dt for dt, _ in values], dtype=float)
    final_price = float(close_0050.iloc[-1])
    final_value = float(series.iloc[-1])
    return {
        "metrics": _metrics(series, rebalances=len(events), total_cost=total_cost, contributions=contributions),
        "final_0050_shares": float(shares),
        "final_0050_weight": float(shares * final_price / final_value),
        "final_cash_weight": float(cash / final_value),
        "weight_overlay": overlay_report,
        "events": events,
        "equity_curve": [{"date": str(dt.date()), "value": float(v)} for dt, v in values],
    }


def main() -> None:
    captured = [
        _capture_events("Golden1_0531", GOLDEN_PAYLOAD, START, END),
        _capture_events("latest_group_a", LATEST_PAYLOAD, START, END),
    ]
    improved_overlay = {
        "max_weight_step": 0.03,
    }
    improved_trend_overlay = {
        "max_weight_step": 0.03,
        "ma_brake_window": 60,
        "ma_brake_ratio": 1.0,
        "ma_brake_max_weight": 0.47,
    }
    results = {
        "Golden1_0531": _replay_0050_only(captured[0]),
        "latest_group_a": _replay_0050_only(captured[1]),
        "latest_group_a_improved_0050_step3pp": _replay_0050_only(
            captured[1],
            weight_overlay=improved_overlay,
        ),
        "latest_group_a_improved_0050_step3pp_ma60_brake": _replay_0050_only(
            captured[1],
            weight_overlay=improved_trend_overlay,
        ),
    }
    rows = []
    for name in [
        "Golden1_0531",
        "latest_group_a",
        "latest_group_a_improved_0050_step3pp",
        "latest_group_a_improved_0050_step3pp_ma60_brake",
    ]:
        metrics = results[name]["metrics"]
        rows.append({"strategy": name, **metrics})

    out_json = PROJECT_ROOT / "results" / "group_a_0050_only_golden1_vs_latest_20250102_20260611.json"
    out_csv = out_json.with_suffix(".csv")
    payload = {
        "experiment": "group_a_0050_only_golden1_vs_latest",
        "method": "Replay each Group A model's target 0050 weight only; all non-0050 exposure is held as cash. Includes 0050 DCA contributions and ETF transaction costs.",
        "requested_window": {"start": START, "end": END},
        "actual_window": {"start": captured[0]["actual_start"], "end": captured[0]["actual_end"]},
        "improvement": {
            "name": "latest_group_a_improved_0050_step3pp",
            "rule": "Use latest Group A raw 0050 target, but limit each rebalance event's 0050 target-weight change to +/-3 percentage points; excess stays in cash.",
            "overlay": improved_overlay,
        },
        "second_improvement": {
            "name": "latest_group_a_improved_0050_step3pp_ma60_brake",
            "rule": "Apply the +/-3pp 0050 target-weight step limit, and when 0050 closes below its 60-day moving average, cap 0050 at 47%; excess stays in cash.",
            "overlay": improved_trend_overlay,
        },
        "strategies": {
            "Golden1_0531": {
                "payload": captured[0]["payload"],
                "model": captured[0]["model"],
                "shared_feature_cols": captured[0]["shared_feature_cols"],
                **results["Golden1_0531"],
            },
            "latest_group_a": {
                "payload": captured[1]["payload"],
                "model": captured[1]["model"],
                "shared_feature_cols": captured[1]["shared_feature_cols"],
                **results["latest_group_a"],
            },
            "latest_group_a_improved_0050_step3pp": {
                "payload": captured[1]["payload"],
                "model": captured[1]["model"],
                "shared_feature_cols": captured[1]["shared_feature_cols"],
                **results["latest_group_a_improved_0050_step3pp"],
            },
            "latest_group_a_improved_0050_step3pp_ma60_brake": {
                "payload": captured[1]["payload"],
                "model": captured[1]["model"],
                "shared_feature_cols": captured[1]["shared_feature_cols"],
                **results["latest_group_a_improved_0050_step3pp_ma60_brake"],
            },
        },
        "comparison_rows": rows,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"JSON: {out_json}")
    print(f"CSV:  {out_csv}")
    for row in rows:
        print(
            f"{row['strategy']}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, vol={row['volatility']:.4%}, "
            f"contribution_return={row['contribution_return']:.4%}, rebalances={row['num_rebalances']}"
        )


if __name__ == "__main__":
    main()
