#!/usr/bin/env python3
"""Regenerate a clean Group A payload by replaying an existing model/payload."""

from __future__ import annotations

import copy
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from compare_group_a_dividend_modes import _model_path, _stock_data
from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import (
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    _buy_and_hold,
    _weights_for,
    calculate_backtest_metrics,
)


SOURCE_PAYLOAD = PROJECT_ROOT / "results" / "group_a_payload_hold10_candidate_20260605.json"
OUTPUT = PROJECT_ROOT / "results" / "group_a_payload_clean_cashdiv_dca8000_20260612.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _model_obs_dim(model_path: Path) -> int:
    with zipfile.ZipFile(str(model_path), "r") as archive:
        data = json.loads(archive.read("data"))
    return int(data["observation_space"]["_shape"][0])


def _build_env(
    *,
    panel: pd.DataFrame,
    tickers: list[str],
    shared_feature_cols: list[str],
    env_kwargs: dict[str, Any],
    initial_cash: float,
) -> PortfolioEnv:
    return PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **env_kwargs,
    )


def _panel_with_model_padding(
    *,
    stock_data: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
    shared_feature_cols: list[str],
    env_kwargs: dict[str, Any],
    initial_cash: float,
    model_path: Path,
) -> tuple[pd.DataFrame, list[str], int]:
    panel = _align_panel(stock_data, tickers, start, end, shared_feature_cols=shared_feature_cols).copy()
    active_shared = list(shared_feature_cols)
    env = _build_env(
        panel=panel,
        tickers=tickers,
        shared_feature_cols=active_shared,
        env_kwargs=env_kwargs,
        initial_cash=initial_cash,
    )
    missing_obs = _model_obs_dim(model_path) - int(env.observation_space.shape[0])
    if missing_obs < 0:
        raise RuntimeError(
            f"Environment observation dim {env.observation_space.shape[0]} exceeds model dim {_model_obs_dim(model_path)}"
        )
    for idx in range(missing_obs):
        col = f"__model_obs_pad_{idx}"
        panel[col] = 0.0
        active_shared.append(col)
    return panel, active_shared, missing_obs


def _replay(payload: dict[str, Any]) -> dict[str, Any]:
    model_path = _model_path(payload)
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    env_kwargs["dividend_mode"] = "cash"
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", []))
    start = str(payload["backtest_start"])
    end = str(payload["backtest_end"])
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    stock_data = _stock_data(payload, tickers, start, end)
    panel, active_shared, padding_cols = _panel_with_model_padding(
        stock_data=stock_data,
        tickers=tickers,
        start=start,
        end=end,
        shared_feature_cols=shared_feature_cols,
        env_kwargs=env_kwargs,
        initial_cash=initial_cash,
        model_path=model_path,
    )

    load_env = _build_env(
        panel=panel,
        tickers=tickers,
        shared_feature_cols=active_shared,
        env_kwargs=env_kwargs,
        initial_cash=initial_cash,
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
    env = _build_env(
        panel=panel,
        tickers=tickers,
        shared_feature_cols=active_shared,
        env_kwargs=env_kwargs,
        initial_cash=initial_cash,
    )
    obs, _ = env.reset()
    info = {"weights": [0.0] * len(tickers)}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    total_contributions = float(env.total_contributions)
    total_invested_capital = float(initial_cash + total_contributions)
    net_profit = float(equity[-1] - total_invested_capital)
    metrics = calculate_backtest_metrics(equity)

    result = {
        "group": "GroupA",
        "tickers": tickers,
        "backtest_start": str(panel["date"].min().date()),
        "backtest_end": str(panel["date"].max().date()),
        "backtest_rows": int(len(panel)),
        "final_value": float(equity[-1]),
        "rl_metrics": metrics,
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "pva_sigmoid_count": int(env.pva_sigmoid_count),
        "dca_purchase_count": int(env.dca_purchase_count),
        "dca_total_contributions": total_contributions,
        "total_invested_capital": total_invested_capital,
        "net_profit": net_profit,
        "contribution_return": float(net_profit / total_invested_capital) if total_invested_capital > 0 else None,
        "dca_config": {
            "dca_day": int(env.dca_day),
            "monthly_amounts": {
                ticker: float(amount)
                for ticker, amount in zip(tickers, env.dca_amount_array)
                if float(amount) > 0.0
            },
        },
        "dividend_credited_history": env.dividend_credited_history,
        "total_dividend_credited": float(env.total_dividend_credited),
        "dividend_config": {"mode": str(env.dividend_mode)},
        "dividend_reinvestment_fees": float(env.dividend_reinvestment_fees),
        "dividend_reinvestment_history": env.dividend_reinvestment_history,
        "dca_purchase_history": env.dca_purchase_history,
        "pva_sigmoid_history": env.pva_sigmoid_history,
        "inverse_forced_exit_history": env.inverse_forced_exit_history,
        "sjm_state_history": env.sjm_state_history,
        "sjm_state_counts": {
            state: int(sum(1 for item in env.sjm_state_history if item.get("state") == state))
            for state in ("S", "J", "M")
        },
        "final_weights": {ticker: float(w) for ticker, w in zip(tickers, info["weights"])},
        "equity_curve": equity,
        "buy_and_hold_equal": _buy_and_hold(
            panel,
            tickers,
            np.ones(len(tickers), dtype=float) / len(tickers),
            initial_cash,
        ),
        "buy_and_hold_50_50_blend": _buy_and_hold(
            panel,
            tickers,
            _weights_for(tickers, {"0050.TW": 0.5, "00631L.TW": 0.5}),
            initial_cash,
        ),
        "model_obs_padding_cols": int(padding_cols),
    }
    return result


def main() -> None:
    payload = _load_json(SOURCE_PAYLOAD)
    clean = copy.deepcopy(payload)
    result = _replay(clean)

    clean["generated_at"] = datetime.now().isoformat(timespec="seconds")
    clean["source_payload"] = str(SOURCE_PAYLOAD.resolve())
    clean["group_a_dca_enabled"] = True
    clean["group_a_dca_config"] = {
        "dca_day": 20,
        "monthly_amounts": {"0050.TW": 8000.0},
        "note": "Group A DCA is applied only during evaluation/backtest, not PPO training reward.",
    }
    clean["group_a_dividend_config"] = {
        "mode": "cash",
        "note": "Group A dividends are credited on ex-dividend day and retained as cash; DCA remains fixed separately.",
    }
    clean.setdefault("group_a", {})["result"] = result
    clean["strategy_note"] = (
        "Clean payload regenerated 2026-06-12 with fixed DCA 8000 and cash dividend mode "
        "after dividend panel support was restored."
    )

    OUTPUT.write_text(json.dumps(clean, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"JSON: {OUTPUT}")
    print(
        "GroupA clean replay: "
        f"final={result['final_value']:.2f}, sharpe={result['rl_metrics']['sharpe']:.4f}, "
        f"mdd={result['rl_metrics']['max_drawdown']:.4%}, "
        f"dca={result['dca_total_contributions']:.2f}, dividends={result['total_dividend_credited']:.2f}"
    )


if __name__ == "__main__":
    main()
