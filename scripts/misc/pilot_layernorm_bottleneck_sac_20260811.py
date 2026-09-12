#!/usr/bin/env python3
"""Small pilot: does a LayerNorm bottleneck before SAC's actor/critic heads
stabilize training on Group A+'s own (noisy, single-asset) RL environment?

Research-only spike, not production. Motivated by arXiv:2606.10448
("Mitigating Bias in Low-SNR Financial Reinforcement Learning via Quantum
Representations"), which places a Parameterized Quantum Circuit bottleneck
before SAC's actor/critic heads to fight Q-value overestimation in noisy
financial states. Their own ablation table (Table 1) shows that most of the
benefit is already captured by a *classical* LayerNorm bottleneck (170% CR
vs 117% unconstrained SAC vs 195% with the full quantum version) -- the
quantum machinery is not required to get the bulk of the effect. This script
tests only that classical, zero-new-dependency piece against Group A+'s own
environment, before deciding whether the RL track (currently non-production,
see FinRL/v2/) is worth revisiting for this reason.

This is a *small* pilot: single asset (0050.TW), 3 seeds per config, ~20k SAC
timesteps -- meant to answer "does this look promising at all", not to be a
publishable/statistically rigorous result. Uses stable_baselines3.SAC with
FinRL/v2/environments/taiwan_stock_env.py in its continuous-action mode
(SAC requires a Box action space; the env's discrete engine underneath maps
continuous actions to HOLD/BUY_1000/SELL_1000 -- see
TaiwanStockTradingEnv.step()).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import torch as th
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.technical_indicators import add_technical_indicators  # noqa: E402
from FinRL.v2.environments.taiwan_stock_env import TaiwanStockTradingEnv  # noqa: E402

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
TICKER = "0050.TW"
TRAIN_START, TRAIN_END = "2015-01-01", "2022-12-31"
TEST_START, TEST_END = "2023-01-01", "2026-08-10"
TOTAL_TIMESTEPS = 20_000
SEEDS = [0, 1, 2]
OUTPUT = PROJECT_ROOT / "research" / "shadow" / "layernorm_bottleneck_sac_pilot_20260811.json"
OUTPUT_MD = PROJECT_ROOT / "research" / "shadow" / "LAYERNORM_BOTTLENECK_SAC_PILOT_20260811.md"


def load_ticker_df(start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            "SELECT dt AS date, open, high, low, close, volume FROM ohlcv "
            "WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [TICKER, start, end],
        ).fetchdf()
    finally:
        con.close()
    df["date"] = pd.to_datetime(df["date"])
    df = add_technical_indicators(df)
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df


def _build_layernorm_extractor_class(obs_dim: int):
    from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
    import gymnasium as gym

    class _LayerNormFeaturesExtractor(BaseFeaturesExtractor):
        def __init__(self, observation_space: gym.Space):
            super().__init__(observation_space, features_dim=obs_dim)
            self.norm = nn.LayerNorm(obs_dim)

        def forward(self, observations: th.Tensor) -> th.Tensor:
            return self.norm(observations)

    return _LayerNormFeaturesExtractor


def _train_one(seed: int, use_layernorm: bool, train_df: pd.DataFrame) -> dict[str, Any]:
    from stable_baselines3 import SAC
    from stable_baselines3.common.monitor import Monitor

    env = Monitor(TaiwanStockTradingEnv(df=train_df, mode="continuous"))
    obs_dim = env.observation_space.shape[0]

    policy_kwargs: dict[str, Any] = {}
    if use_layernorm:
        policy_kwargs["features_extractor_class"] = _build_layernorm_extractor_class(obs_dim)
        policy_kwargs["features_extractor_kwargs"] = {}

    model = SAC(
        "MlpPolicy",
        env,
        seed=seed,
        verbose=0,
        learning_starts=1000,
        policy_kwargs=policy_kwargs,
    )

    critic_losses: list[float] = []

    class _CriticLossCallback:
        def __init__(self, model):
            self.model = model

        def poll(self):
            val = self.model.logger.name_to_value.get("train/critic_loss")
            if val is not None:
                critic_losses.append(float(val))

    cb = _CriticLossCallback(model)

    from stable_baselines3.common.callbacks import BaseCallback

    class _PollCallback(BaseCallback):
        def _on_step(self) -> bool:
            cb.poll()
            return True

    model.learn(total_timesteps=TOTAL_TIMESTEPS, callback=_PollCallback())

    return {
        "model": model,
        "critic_loss_var": float(np.var(critic_losses)) if critic_losses else None,
        "critic_loss_mean_abs": float(np.mean(np.abs(critic_losses))) if critic_losses else None,
        "n_critic_loss_samples": len(critic_losses),
    }


def _backtest(model, test_df: pd.DataFrame) -> dict[str, Any]:
    env = TaiwanStockTradingEnv(df=test_df, mode="continuous")
    obs, _ = env.reset()
    values = [env.initial_capital]
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        values.append(env.portfolio.total_value)
        done = terminated or truncated
    values = pd.Series(values, dtype=float)
    returns = values.pct_change().dropna()
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    sharpe = (
        float(returns.mean() / returns.std() * np.sqrt(252))
        if len(returns) > 1 and returns.std() > 0
        else 0.0
    )
    max_drawdown = float((values / values.cummax() - 1.0).min())
    return {"total_return": total_return, "sharpe": sharpe, "max_drawdown": max_drawdown, "n_steps": len(values)}


def main() -> None:
    print(f"Loading {TICKER} train={TRAIN_START}..{TRAIN_END}, test={TEST_START}..{TEST_END}")
    train_df = load_ticker_df(TRAIN_START, TRAIN_END)
    test_df = load_ticker_df(TEST_START, TEST_END)
    print(f"train rows={len(train_df)}, test rows={len(test_df)}, obs cols={len(train_df.columns) - 1}")

    results: dict[str, list[dict[str, Any]]] = {"baseline": [], "layernorm": []}
    for use_ln, label in [(False, "baseline"), (True, "layernorm")]:
        for seed in SEEDS:
            print(f"--- training {label} seed={seed} ---")
            train_out = _train_one(seed, use_ln, train_df)
            bt = _backtest(train_out["model"], test_df)
            row = {
                "seed": seed,
                "critic_loss_var": train_out["critic_loss_var"],
                "critic_loss_mean_abs": train_out["critic_loss_mean_abs"],
                **bt,
            }
            print(f"    {label} seed={seed}: {row}")
            results[label].append(row)

    def _agg(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return {"mean": float(np.mean(vals)), "std": float(np.std(vals))} if vals else {"mean": None, "std": None}

    summary = {
        "ticker": TICKER,
        "train_window": [TRAIN_START, TRAIN_END],
        "test_window": [TEST_START, TEST_END],
        "total_timesteps": TOTAL_TIMESTEPS,
        "seeds": SEEDS,
        "raw": results,
        "aggregate": {
            label: {
                "critic_loss_var": _agg(rows, "critic_loss_var"),
                "total_return": _agg(rows, "total_return"),
                "sharpe": _agg(rows, "sharpe"),
                "max_drawdown": _agg(rows, "max_drawdown"),
            }
            for label, rows in results.items()
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    agg = summary["aggregate"]
    md = [
        "# LayerNorm Bottleneck SAC Pilot (small spike, 2606.10448 follow-up)",
        "",
        f"- Ticker: `{TICKER}`, train {TRAIN_START}..{TRAIN_END}, test {TEST_START}..{TEST_END}",
        f"- {TOTAL_TIMESTEPS} SAC timesteps, {len(SEEDS)} seeds per config -- small pilot, not a rigorous multi-seed study",
        "",
        "| config | critic-loss var | test total return | test Sharpe | test max drawdown |",
        "|---|---|---|---|---|",
    ]
    for label in ("baseline", "layernorm"):
        a = agg[label]
        md.append(
            f"| {label} | {a['critic_loss_var']['mean']:.4g}±{a['critic_loss_var']['std']:.4g} | "
            f"{a['total_return']['mean']:.2%}±{a['total_return']['std']:.2%} | "
            f"{a['sharpe']['mean']:.3f}±{a['sharpe']['std']:.3f} | "
            f"{a['max_drawdown']['mean']:.2%}±{a['max_drawdown']['std']:.2%} |"
        )
    md.append("")
    OUTPUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nWritten to {OUTPUT} and {OUTPUT_MD}")
    print(json.dumps(summary["aggregate"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
