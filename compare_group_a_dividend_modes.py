#!/usr/bin/env python3
"""Compare Group A dividend cash vs reinvest modes on the same payload/model."""

from __future__ import annotations

import copy
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

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
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_margin_features,
    payload_uses_group_a_margin_shared_features,
    payload_uses_group_a_market_margin_shared_features,
)


PAYLOAD = PROJECT_ROOT / "results" / "group_a_payload_hold10_candidate_20260605.json"
OUTPUT = PROJECT_ROOT / "results" / "group_a_dividend_mode_compare_20260612.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _model_path(payload: dict[str, Any]) -> Path:
    model_name = str((payload.get("group_a", {}) or {}).get("model_name", "")).strip()
    if not model_name:
        raise ValueError("Payload missing group_a.model_name")
    path = PROJECT_ROOT / "models" / "portfolio" / model_name
    if path.suffix != ".zip":
        path = path.with_suffix(".zip")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _model_obs_dim(model_path: Path) -> int:
    with zipfile.ZipFile(str(model_path), "r") as archive:
        data = json.loads(archive.read("data"))
    return int(data["observation_space"]["_shape"][0])


def _stock_data(payload: dict[str, Any], tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    stock_data = load_stock_data_db_first(tickers, start, end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, start, end)
    return stock_data


def _run_mode(
    *,
    payload: dict[str, Any],
    model_path: Path,
    stock_data: dict[str, pd.DataFrame],
    tickers: list[str],
    shared_feature_cols: list[str],
    env_kwargs: dict[str, Any],
    start: str,
    end: str,
    dividend_mode: str,
) -> dict[str, Any]:
    mode_kwargs = copy.deepcopy(env_kwargs)
    mode_kwargs["dividend_mode"] = dividend_mode
    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols)
    if panel.empty:
        raise RuntimeError(f"No aligned panel rows for {start} ~ {end}")
    panel = panel.copy()
    active_shared_feature_cols = list(shared_feature_cols)

    load_env = PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=active_shared_feature_cols,
        initial_cash=float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH)),
        **mode_kwargs,
    )
    missing_obs = _model_obs_dim(model_path) - int(load_env.observation_space.shape[0])
    if missing_obs > 0:
        for idx in range(missing_obs):
            col = f"__model_obs_pad_{idx}"
            panel[col] = 0.0
            active_shared_feature_cols.append(col)
        load_env = PortfolioEnv(
            panel,
            tickers,
            shared_feature_cols=active_shared_feature_cols,
            initial_cash=float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH)),
            **mode_kwargs,
        )
    elif missing_obs < 0:
        raise RuntimeError(
            f"Environment observation dim {load_env.observation_space.shape[0]} exceeds model dim {_model_obs_dim(model_path)}"
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
        shared_feature_cols=active_shared_feature_cols,
        initial_cash=float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH)),
        **mode_kwargs,
    )
    obs, _ = env.reset()
    info = {"weights": [0.0] * len(tickers)}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(value) for value in env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    total_contributions = float(env.total_contributions)
    total_invested = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH) + total_contributions)
    return {
        "dividend_mode": dividend_mode,
        "actual_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_end": str(pd.Timestamp(panel["date"].max()).date()),
        "rows": int(len(panel)),
        "final_value": float(equity[-1]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics.get("sharpe_ratio", metrics.get("sharpe", 0.0))),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_rebalances": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "dca_total_contributions": total_contributions,
        "total_invested_capital": total_invested,
        "net_profit": float(equity[-1] - total_invested),
        "contribution_return": float((equity[-1] - total_invested) / max(total_invested, 1.0)),
        "total_dividend_credited": float(env.total_dividend_credited),
        "dividend_reinvestment_fees": float(env.dividend_reinvestment_fees),
        "dividend_event_count": len(env.dividend_credited_history),
        "dividend_reinvestment_count": len(env.dividend_reinvestment_history),
        "model_obs_padding_cols": int(missing_obs),
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
    }


def main() -> None:
    payload = _load_json(PAYLOAD)
    model_path = _model_path(payload)
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", []))
    start = str(payload.get("backtest_start"))
    end = str(payload.get("backtest_end"))
    stock_data = _stock_data(payload, tickers, start, end)

    rows = [
        _run_mode(
            payload=payload,
            model_path=model_path,
            stock_data=stock_data,
            tickers=tickers,
            shared_feature_cols=shared_feature_cols,
            env_kwargs=env_kwargs,
            start=start,
            end=end,
            dividend_mode=mode,
        )
        for mode in ("cash", "reinvest_weights")
    ]
    by_mode = {row["dividend_mode"]: row for row in rows}
    cash = by_mode["cash"]
    reinvest = by_mode["reinvest_weights"]
    delta_cash_vs_reinvest = {
        key: float(cash[key] - reinvest[key])
        for key in [
            "final_value",
            "annual_return",
            "sharpe_ratio",
            "max_drawdown",
            "volatility",
            "fees_paid_estimate",
            "net_profit",
            "contribution_return",
        ]
    }

    report = {
        "experiment": "group_a_dividend_mode_compare",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "payload": str(PAYLOAD.resolve()),
        "model_path": str(model_path.resolve()),
        "window": {"start": start, "end": end},
        "rows": rows,
        "delta_cash_vs_reinvest_weights": delta_cash_vs_reinvest,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    csv_path = OUTPUT.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {OUTPUT}")
    print(f"CSV:  {csv_path}")
    for row in rows:
        print(
            f"{row['dividend_mode']}: final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"dividends={row['total_dividend_credited']:.2f}, "
            f"reinvest_fees={row['dividend_reinvestment_fees']:.2f}"
        )
    print(
        "Delta cash - reinvest_weights: "
        f"final={delta_cash_vs_reinvest['final_value']:.2f}, "
        f"sharpe={delta_cash_vs_reinvest['sharpe_ratio']:.4f}, "
        f"mdd={delta_cash_vs_reinvest['max_drawdown']:.4%}"
    )


if __name__ == "__main__":
    main()
