#!/usr/bin/env python3
"""Backtest the latest saved Group B model without retraining."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

from generate_dual_group_signal import _env_kwargs_from_payload, _llm_sentiment_path_from_payload
from train_dual_group_2024_2026 import (
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    attach_market_features_db_first,
    calculate_backtest_metrics,
    load_stock_data_db_first,
    payload_uses_group_b_institutional_features,
    payload_uses_group_b_margin_features,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RESULT_JSON = PROJECT_ROOT / "results" / "group_b_backtest_20240101_20260508_20260530_110011.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_b_latest_no2884_backtest_20240101_20260605.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-05")
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _run_backtest(
    payload: dict[str, Any],
    result_json: Path,
    *,
    start: str,
    end: str,
    download_end: str,
) -> dict[str, Any]:
    group = payload["group_b"]
    tickers = list(group["tickers"])
    removed_tickers = [ticker for ticker in tickers if ticker == "2884.TW"]
    tickers = [ticker for ticker in tickers if ticker != "2884.TW"]
    if not tickers:
        raise RuntimeError("No Group B tickers remain after excluding 2884.TW")

    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{group['model_name']}.zip"
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    history_start = str(payload.get("train_start") or group.get("train_start") or "2017-01-01")
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_b")
    dca_cfg = payload.get("group_b_dca_config", {}) or {}
    if dca_cfg.get("monthly_amounts"):
        env_kwargs["dca_monthly_amounts"] = {
            ticker: float(amount)
            for ticker, amount in dict(dca_cfg["monthly_amounts"]).items()
            if ticker in tickers
        }
        env_kwargs["dca_day"] = int(dca_cfg.get("dca_day", 20))
    llm_path = _llm_sentiment_path_from_payload(payload, "group_b") if payload.get("group_b_use_llm_sentiment") else None

    stock_data = load_stock_data_db_first(tickers, history_start, download_end)
    if payload_uses_group_b_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_b_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, history_start, download_end)
    if shared_feature_cols:
        stock_data = attach_market_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
            include_llm_sentiment=bool(payload.get("group_b_use_llm_sentiment", False)),
            llm_sentiment_path=llm_path,
        )

    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols)
    if panel.empty:
        raise RuntimeError("No aligned panel rows for requested Group B backtest")

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
    obs, _ = env.reset()
    info = {"weights": np.zeros(len(tickers))}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(value) for value in env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    return {
        "source_result_json": str(result_json.resolve()),
        "model_path": str(model_path.resolve()),
        "removed_tickers": removed_tickers,
        "tickers": tickers,
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
        "pva_sigmoid_count": int(env.pva_sigmoid_count),
        "dca_purchase_count": int(env.dca_purchase_count),
        "dca_total_contributions": float(env.total_contributions),
        "total_invested_capital": float(initial_cash + env.total_contributions),
        "net_profit": float(equity[-1] - initial_cash - env.total_contributions),
        "contribution_return": float((equity[-1] - initial_cash - env.total_contributions) / max(initial_cash + env.total_contributions, 1.0)),
        "total_dividend_credited": float(env.total_dividend_credited),
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
        "equity_curve": equity,
        "dca_purchase_history": env.dca_purchase_history,
        "pva_sigmoid_history": env.pva_sigmoid_history,
        "sjm_state_counts": {
            state: int(sum(1 for item in env.sjm_state_history if item.get("state") == state))
            for state in ("S", "J", "M")
        },
    }


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    download_end = args.download_end or args.end
    result = _run_backtest(
        payload,
        result_json,
        start=str(args.start),
        end=str(args.end),
        download_end=str(download_end),
    )
    report = {
        "experiment": "group_b_latest_no2884_backtest",
        "method_note": "No retraining. Loads the latest saved Group B model/payload and excludes 2884.TW if present.",
        "requested_window": {"start": args.start, "end": args.end, "download_end": download_end},
        "actual_window": {"start": result["actual_start"], "end": result["actual_end"], "rows": result["rows"]},
        "group_b_latest": result,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    row = {k: v for k, v in result.items() if isinstance(v, (int, float, str))}
    pd.DataFrame([{"strategy": "group_b_latest_no2884", **row}]).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Actual window: {result['actual_start']} ~ {result['actual_end']} ({result['rows']} rows)")
    print(f"Tickers: {result['tickers']}")
    print(f"Removed tickers: {result['removed_tickers']}")
    print(
        "Group B latest no-2884: "
        f"final={result['final_value']:.2f}, sharpe={result['sharpe_ratio']:.4f}, "
        f"mdd={result['max_drawdown']:.4%}, trades={result['num_trades']}, "
        f"fees={result['fees_paid_estimate']:.2f}"
    )


if __name__ == "__main__":
    try:
        import numpy.core.numeric as _numpy_core_numeric

        sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
    except ImportError:
        pass
    main()
