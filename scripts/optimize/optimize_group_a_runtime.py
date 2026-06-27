#!/usr/bin/env python3
"""Runtime-only optimization sweep for the promoted Group A checkpoint."""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from stable_baselines3 import PPO

from generate_dual_group_signal import _env_kwargs_from_payload, _llm_sentiment_path_from_payload
from train_dual_group_2024_2026 import (
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    attach_institutional_features_db_first,
    attach_market_features_db_first,
    calculate_backtest_metrics,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = PROJECT_ROOT / "results" / "group_a_release_runtime_j15_20260522.json"

try:
    import numpy.core.numeric as _numpy_core_numeric

    sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
except ImportError:
    pass


def _float_grid(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _int_grid(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _load_group_a_context(result_json: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    if "group_a" not in payload:
        raise KeyError(f"{result_json} does not contain group_a payload")
    group_payload = payload["group_a"]
    tickers = list(group_payload["tickers"])
    return payload, group_payload, tickers


def _run_backtest(
    model: PPO,
    panel,
    tickers: list[str],
    env_kwargs: dict[str, Any],
    initial_cash: float,
    shared_feature_cols: list[str] | None,
) -> dict[str, Any]:
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
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
    }


def _score(result: dict[str, Any], baseline: dict[str, Any], max_extra_trades: int) -> tuple[float, bool, str]:
    drawdown_ok = float(result["max_drawdown"]) >= float(baseline["max_drawdown"]) - 1e-9
    trades_ok = int(result["num_trades"]) <= int(baseline["num_trades"]) + max_extra_trades
    if not drawdown_ok:
        return -1e12, False, "worse_drawdown"
    if not trades_ok:
        return -1e12, False, "too_many_trades"
    value_delta = float(result["final_value"]) - float(baseline["final_value"])
    sharpe_delta = float(result["sharpe_ratio"]) - float(baseline["sharpe_ratio"])
    return value_delta + sharpe_delta * 250_000.0, True, "candidate"


def main() -> None:
    parser = argparse.ArgumentParser(description="Runtime-only Group A optimization sweep")
    parser.add_argument("--result-json", default=str(DEFAULT_BASELINE))
    parser.add_argument("--output", default=None)
    parser.add_argument("--pva-weight-grid", default="0.28,0.30,0.32")
    parser.add_argument("--pva-j-grid", default="0.13,0.15,0.17")
    parser.add_argument("--pva-drift-grid", default="0.04,0.05,0.06")
    parser.add_argument("--pva-min-leverage-grid", default="0.30,0.35,0.40")
    parser.add_argument("--pva-buy-dip-grid", default="0.50,0.60,0.70")
    parser.add_argument("--dca-day-grid", default="15,20,25")
    parser.add_argument("--max-extra-trades", type=int, default=0)
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    result_json = Path(args.result_json)
    if not result_json.is_absolute():
        result_json = (PROJECT_ROOT / result_json).resolve()
    payload, group_payload, tickers = _load_group_a_context(result_json)

    model_name = str(group_payload["model_name"])
    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{model_name}.zip"
    if not model_path.exists():
        raise FileNotFoundError(f"Model path not found: {model_path}")

    train_start = str(payload.get("train_start") or group_payload.get("train_start") or "2024-01-01")
    download_end = str(payload.get("download_end") or payload.get("backtest_end") or "2026-05-22")
    backtest_start = str(payload.get("backtest_start") or group_payload.get("backtest_start") or "2024-01-02")
    backtest_end = str(payload.get("backtest_end") or group_payload.get("backtest_end") or "2026-05-21")
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))

    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if payload.get("group_a_use_llm_sentiment") else None

    stock_data = load_stock_data_db_first(tickers, train_start, download_end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, train_start, download_end)
    if shared_feature_cols:
        stock_data = attach_market_features_db_first(
            stock_data,
            tickers,
            train_start,
            download_end,
            include_llm_sentiment=bool(payload.get("group_a_use_llm_sentiment", False)),
            llm_sentiment_path=llm_path,
        )
    panel = _align_panel(stock_data, tickers, backtest_start, backtest_end, shared_feature_cols=shared_feature_cols)

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
    baseline = _run_backtest(model, panel, tickers, env_kwargs, initial_cash, shared_feature_cols)

    grids = {
        "pva_weight": _float_grid(args.pva_weight_grid),
        "pva_j_state_weight": _float_grid(args.pva_j_grid),
        "pva_drift_threshold": _float_grid(args.pva_drift_grid),
        "pva_min_leverage_scale": _float_grid(args.pva_min_leverage_grid),
        "pva_buy_dip_strength": _float_grid(args.pva_buy_dip_grid),
        "dca_day": _int_grid(args.dca_day_grid),
    }

    runs: list[dict[str, Any]] = []
    keys = list(grids)
    for values in itertools.product(*(grids[key] for key in keys)):
        overrides = dict(zip(keys, values))
        trial_kwargs = copy.deepcopy(env_kwargs)
        trial_kwargs.update({key: value for key, value in overrides.items() if key != "dca_day"})
        trial_kwargs["dca_day"] = int(overrides["dca_day"])
        result = _run_backtest(model, panel, tickers, trial_kwargs, initial_cash, shared_feature_cols)
        score, eligible, reason = _score(result, baseline, args.max_extra_trades)
        result.update(
            {
                "overrides": overrides,
                "delta_final_value": float(result["final_value"] - baseline["final_value"]),
                "delta_sharpe": float(result["sharpe_ratio"] - baseline["sharpe_ratio"]),
                "delta_max_drawdown": float(result["max_drawdown"] - baseline["max_drawdown"]),
                "delta_trades": int(result["num_trades"] - baseline["num_trades"]),
                "eligible": bool(eligible),
                "eligibility_reason": reason,
                "score": float(score),
            }
        )
        runs.append(result)

    runs.sort(key=lambda item: item["score"], reverse=True)
    best = runs[0] if runs else None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"group_a_runtime_opt_sweep_{timestamp}.json"
    if not output.is_absolute():
        output = (PROJECT_ROOT / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "experiment": "group_a_runtime_opt_sweep",
                "source_result_json": str(result_json),
                "model_path": str(model_path),
                "window": {"train_start": train_start, "download_end": download_end, "backtest_start": backtest_start, "backtest_end": backtest_end},
                "baseline": baseline,
                "grids": grids,
                "best": best,
                "top": runs[: max(int(args.top_n), 1)],
                "runs": runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {output}")
    print(f"Baseline final={baseline['final_value']:.2f} sharpe={baseline['sharpe_ratio']:.6f} mdd={baseline['max_drawdown']:.6f} trades={baseline['num_trades']}")
    if best:
        print(
            "Best "
            f"final={best['final_value']:.2f} "
            f"delta={best['delta_final_value']:.2f} "
            f"sharpe={best['sharpe_ratio']:.6f} "
            f"delta_sharpe={best['delta_sharpe']:.6f} "
            f"mdd={best['max_drawdown']:.6f} "
            f"trades={best['num_trades']} "
            f"eligible={best['eligible']} "
            f"overrides={best['overrides']}"
        )


if __name__ == "__main__":
    main()
