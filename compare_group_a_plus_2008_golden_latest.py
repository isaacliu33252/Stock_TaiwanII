#!/usr/bin/env python3
"""Compare Golden1_0531 and latest GroupA+ on the TWII 2008 proxy path."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_meta_ensemble import _price_regimes
from backtest_group_a_plus_overlay import _simulate_plus
from generate_dual_group_signal import _env_kwargs_from_payload
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
from twii_proxy_utils import (
    _GROUP_B_TWII_PROXY_PARAMS,
    _build_group_b_single_proxy,
    attach_market_context,
    build_group_a_twii_proxy_data,
)


START = "2007-07-01"
END = "2010-12-31"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
GOLDEN_PAYLOAD = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
GOLDEN_MODEL = PROJECT_ROOT / "models" / "portfolio" / "group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip"
GOLDEN_2008_SOURCE = PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_20070701_20101231_20260526_193325.json"
LATEST_PAYLOAD = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260531_20260609_214023.json"
LATEST_MODEL = PROJECT_ROOT / "models" / "portfolio" / "group_a_production_2020_2025_100k.zip"
GROUP_A_PLUS_CONFIG = PROJECT_ROOT / "group_a_plus_config.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_group_a_plus_proxy_data(start: str, end: str) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    stock_data, market = build_group_a_twii_proxy_data(start, end)
    params = _GROUP_B_TWII_PROXY_PARAMS["00679B.TWO"]
    stock_data["00679B.TWO"] = attach_market_context(
        _build_group_b_single_proxy(
            market,
            "00679B.TWO",
            base_price=100.0,
            base_volume=500_000.0,
            vol_scale=params["vol_scale"],
        ),
        market,
        add_long_features=False,
    )
    return stock_data, market


def _attach_payload_features(
    stock_data: dict[str, pd.DataFrame],
    payload: dict[str, Any],
    tickers: list[str],
    start: str,
    end: str,
) -> dict[str, pd.DataFrame]:
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, start, end)
    return stock_data


def _price_frame(panel: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            ticker: pd.to_numeric(panel[f"{ticker}_close"], errors="coerce").to_numpy(dtype=float)
            for ticker in tickers
        },
        index=pd.to_datetime(panel["date"]).dt.normalize(),
    ).sort_index()


def _capture_model_events(
    *,
    name: str,
    payload_path: Path,
    model_path: Path,
    start: str,
    end: str,
) -> dict[str, Any]:
    payload = _load_json(payload_path)
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", TICKERS))
    if set(tickers) != set(TICKERS):
        raise ValueError(f"{name} expected GroupA+ tickers {TICKERS}, got {tickers}")
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))

    stock_data, _market = _build_group_a_plus_proxy_data(start, end)
    stock_data = _attach_payload_features(stock_data, payload, tickers, start, end)
    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols)
    if panel.empty:
        raise RuntimeError(f"No aligned 2008 proxy rows for {name}")

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
                    "target_cash_weight": float(max(0.0, 1.0 - sum(float(w) for w in target_weights))),
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
    prices = _price_frame(panel, tickers)
    regimes = _price_regimes(prices[["0050.TW", "00631L.TW", "00632R.TW"]], {dt: "normal" for dt in prices.index})
    equity_curve = []
    for dt, value in zip(pd.to_datetime(panel["date"]).dt.normalize(), equity):
        regime = regimes.get(dt, "risk_on")
        equity_curve.append(
            {
                "date": str(dt.date()),
                "value": float(value),
                "regime": regime,
                "tdcc_state": regime,
            }
        )

    total_contributions = float(env.total_contributions)
    total_invested_capital = float(initial_cash + total_contributions)
    return {
        "name": name,
        "payload_path": str(payload_path.resolve()),
        "model_path": str(model_path.resolve()),
        "actual_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_end": str(pd.Timestamp(panel["date"].max()).date()),
        "rows": int(len(panel)),
        "tickers": tickers,
        "shared_feature_cols": shared_feature_cols,
        "env_kwargs": env_kwargs,
        "prices": prices,
        "replay": {
            "events": events,
            "equity_curve": equity_curve,
        },
        "dca_purchase_history": env.dca_purchase_history,
        "base_metrics": {
            "final_value": float(equity[-1]),
            "annual_return": float(metrics["annual_return"]),
            "sharpe_ratio": float(metrics.get("sharpe_ratio", metrics.get("sharpe", 0.0))),
            "max_drawdown": float(metrics["max_drawdown"]),
            "volatility": float(metrics["volatility"]),
            "num_rebalances": int(env.trade_count),
            "fees_paid_estimate": float(env.fees_paid),
            "dca_total_contributions": total_contributions,
            "total_invested_capital": total_invested_capital,
            "net_profit": float(equity[-1] - total_invested_capital),
            "contribution_return": float((equity[-1] - total_invested_capital) / max(total_invested_capital, 1.0)),
        },
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
    }


def _capture_existing_golden_source(source_path: Path, start: str, end: str) -> dict[str, Any]:
    source = _load_json(source_path)
    stock_data, _market = _build_group_a_plus_proxy_data(start, end)
    prices = pd.concat(
        [
            frame.assign(date=pd.to_datetime(frame["date"]).dt.normalize()).set_index("date")["close"].rename(ticker)
            for ticker, frame in stock_data.items()
        ],
        axis=1,
    ).sort_index().loc[pd.Timestamp(source["actual_start"]) : pd.Timestamp(source["actual_end"])]
    prices = prices[TICKERS].dropna()
    regimes = _price_regimes(prices[["0050.TW", "00631L.TW", "00632R.TW"]], {dt: "normal" for dt in prices.index})

    result = source["result"]
    raw_curve = list(result.get("equity_curve", []))
    if len(raw_curve) != len(prices.index):
        usable = min(len(raw_curve), len(prices.index))
        raw_curve = raw_curve[:usable]
        prices = prices.iloc[:usable].copy()
    equity_curve = []
    for dt, value in zip(prices.index, raw_curve):
        regime = regimes.get(dt, "risk_on")
        equity_curve.append(
            {
                "date": str(dt.date()),
                "value": float(value),
                "regime": regime,
                "tdcc_state": regime,
            }
        )

    metrics = result["rl_metrics"]
    return {
        "name": "Golden1_0531",
        "payload_path": source.get("payload_path"),
        "model_path": source.get("model_path"),
        "actual_start": source["actual_start"],
        "actual_end": source["actual_end"],
        "rows": int(source["panel_rows"]),
        "tickers": TICKERS,
        "shared_feature_cols": source.get("shared_feature_cols", []),
        "env_kwargs": source.get("env_kwargs", {}),
        "prices": prices,
        "replay": {
            "events": result.get("pva_sigmoid_history", []),
            "equity_curve": equity_curve,
        },
        "dca_purchase_history": result.get("dca_purchase_history", []),
        "base_metrics": {
            "final_value": float(result["final_value"]),
            "annual_return": float(metrics["annual_return"]),
            "sharpe_ratio": float(metrics.get("sharpe", metrics.get("sharpe_ratio", 0.0))),
            "max_drawdown": float(metrics["max_drawdown"]),
            "volatility": float(metrics["volatility"]),
            "num_rebalances": int(result["num_trades"]),
            "fees_paid_estimate": float(result["fees_paid_estimate"]),
            "dca_total_contributions": float(result["dca_total_contributions"]),
            "total_invested_capital": float(result["total_invested_capital"]),
            "net_profit": float(result["net_profit"]),
            "contribution_return": float(result["contribution_return"]),
        },
        "final_weights": result.get("final_weights", {}),
    }


def _run_group_a_plus(captured: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _simulate_plus(
        captured["prices"],
        captured["replay"],
        config,
        commission_rate=0.001425,
        etf_sell_tax_rate=0.001,
        initial_cash=DEFAULT_INITIAL_CASH,
        dca_history=captured["dca_purchase_history"],
    )


def _row(name: str, kind: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy": name,
        "mode": kind,
        "final_value": float(metrics["final_value"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_rebalances": int(metrics["num_rebalances"]),
        "fees_paid_estimate": float(metrics.get("fees_paid_estimate", metrics.get("total_cost", 0.0))),
        "dca_total_contributions": float(metrics.get("dca_total_contributions", 0.0)),
        "contribution_return": float(metrics["contribution_return"]),
    }


def main() -> None:
    config = _load_json(GROUP_A_PLUS_CONFIG)
    captured = [
        _capture_existing_golden_source(GOLDEN_2008_SOURCE, START, END),
        _capture_model_events(
            name="latest_group_a_production_2020_2025_100k",
            payload_path=LATEST_PAYLOAD,
            model_path=LATEST_MODEL,
            start=START,
            end=END,
        ),
    ]
    plus_results = {item["name"]: _run_group_a_plus(item, config) for item in captured}

    rows = []
    for item in captured:
        rows.append(_row(item["name"], "base_model_2008_proxy", item["base_metrics"]))
        rows.append(_row(item["name"], "groupA_plus_current_2008_proxy", plus_results[item["name"]]["metrics"]))

    golden_plus = plus_results["Golden1_0531"]["metrics"]
    latest_plus = plus_results["latest_group_a_production_2020_2025_100k"]["metrics"]
    delta_latest_vs_golden_plus = {
        "final_value": float(latest_plus["final_value"] - golden_plus["final_value"]),
        "sharpe_ratio": float(latest_plus["sharpe_ratio"] - golden_plus["sharpe_ratio"]),
        "max_drawdown": float(latest_plus["max_drawdown"] - golden_plus["max_drawdown"]),
        "volatility": float(latest_plus["volatility"] - golden_plus["volatility"]),
        "contribution_return": float(latest_plus["contribution_return"] - golden_plus["contribution_return"]),
    }

    report = {
        "experiment": "group_a_plus_golden1_vs_latest_twii_proxy_2008",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": START, "end": END},
        "actual_window": {
            "start": captured[0]["actual_start"],
            "end": captured[0]["actual_end"],
            "rows": captured[0]["rows"],
        },
        "proxy_method": {
            "0050.TW": "1x TWII daily returns",
            "00631L.TW": "2x TWII daily returns",
            "00632R.TW": "-1x TWII daily returns",
            "00679B.TWO": "Group B style 0.45x TWII proxy with lower vol_scale; current GroupA+ target follows configured TDCC bond sleeve",
        },
        "group_a_plus_config": str(GROUP_A_PLUS_CONFIG.resolve()),
        "group_a_plus_profile": config.get("recommended_profile", {}).get("name", config.get("name")),
        "strategies": {
            item["name"]: {
                "payload_path": item["payload_path"],
                "model_path": item["model_path"],
                "base_metrics": item["base_metrics"],
                "base_final_weights": item["final_weights"],
                "group_a_plus_metrics": plus_results[item["name"]]["metrics"],
                "group_a_plus_final_weights": plus_results[item["name"]]["final_weights"],
                "group_a_plus_final_cash_weight": plus_results[item["name"]]["final_cash_weight"],
                "group_a_plus_event_count": len(plus_results[item["name"]]["events"]),
            }
            for item in captured
        },
        "delta_latest_vs_golden_on_group_a_plus": delta_latest_vs_golden_plus,
        "comparison_rows": rows,
        "limitations": [
            "This is a TWII-derived proxy path, not exact ETF trading history.",
            "00679B is synthetic because true 2008 00679B history does not exist.",
            "Institutional, margin, and LLM features are zero-filled where historical inputs are unavailable.",
        ],
    }

    output = PROJECT_ROOT / "results" / "group_a_plus_golden1_vs_latest_twii_proxy_2008_20260612.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Actual window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    for row in rows:
        print(
            f"{row['strategy']} / {row['mode']}: "
            f"final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, vol={row['volatility']:.4%}, "
            f"rebalances={row['num_rebalances']}, contribution_return={row['contribution_return']:.4%}"
        )
    print(
        "Delta latest vs Golden1 on GroupA+: "
        f"final={delta_latest_vs_golden_plus['final_value']:.2f}, "
        f"sharpe={delta_latest_vs_golden_plus['sharpe_ratio']:.4f}, "
        f"mdd={delta_latest_vs_golden_plus['max_drawdown']:.4%}, "
        f"contribution_return={delta_latest_vs_golden_plus['contribution_return']:.4%}"
    )


if __name__ == "__main__":
    main()
