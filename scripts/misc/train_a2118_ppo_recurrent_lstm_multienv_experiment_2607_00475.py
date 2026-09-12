#!/usr/bin/env python3
"""EXPERIMENT (not production): follow-up to
train_a2118_ppo_recurrent_lstm_experiment_2607_00475.py.

That first attempt swapped a2118's PPO+MlpPolicy for sb3-contrib's
RecurrentPPO+MlpLstmPolicy under the EXACT single-environment protocol
used by every prior a2118 PPO experiment this session, and found (verified
by direct policy-distribution inspection, not just the backtest, so this
was confirmed to be a real training outcome and not a harness bug): the
trained policy's action-probability distribution saturates to a near-fixed
point within the first few steps of a rollout and barely responds to the
market-state input afterward, independent of seed (42 vs 44 converge to
visually the same fixed distribution) and independent of training budget
(300 steps and 100k steps give the same fixed point). The LSTM hidden
state effectively becomes a self-sustaining attractor that ignores
observations rather than encoding useful market history -- "recurrent
state collapse."

This is a well-documented failure mode for RecurrentPPO trained on a
SINGLE long, highly autocorrelated environment sequence: the sb3-contrib
docs/examples themselves recommend multiple parallel environments so that
each PPO rollout buffer contains several decorrelated partial sequences
rather than one very long one, giving less biased advantage estimates and
less opportunity for the hidden state to lock onto a fixed point early in
training. Group A+'s existing PPO convention (all prior experiments this
session) trains on a single environment instance, since the underlying
memoryless MlpPolicy has no hidden state that can collapse this way -- so
this instability is specific to adding recurrence, not inherited from
prior experiments.

METHOD: identical training/backtest windows, tickers, profile, and
per-update PPO hyperparameters (learning_rate, gamma, gae_lambda,
ent_coef) as the single-env attempt. The only change: training uses
`stable_baselines3.common.vec_env.DummyVecEnv` with N_ENVS=8 independent
PortfolioEnv instances (same training panel, independent stochastic
action sampling per env during rollout collection -- environment
transitions themselves are deterministic given actions, so
decorrelation comes entirely from independently sampled actions across
the 8 parallel copies). n_steps is reduced from 1024 to 128 so the total
rollout buffer size (n_steps * n_envs = 1024) matches the single-env
attempt's buffer size exactly -- this isolates "many short decorrelated
sequences vs one long sequence" as the only structural change, not
"more total experience per update." batch_size=256 (a multiple of
n_envs=8, required by RecurrentPPO's sequence-aware minibatching).
Backtest (a single deterministic environment, not vectorized) reuses the
state-threading logic from the single-env attempt unchanged.

SAFETY: never touches models/portfolio/last_ppo_group_a_100k.zip or
train_dual_group_2024_2026.py; checkpoints save as
models/portfolio/experiment_recurrentlstm_multienv_*.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.vec_env import DummyVecEnv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (  # noqa: E402
    DEFAULT_GROUP_A_TICKERS,
    GROUP_A_PROFILE_PRESETS,
    PortfolioEnv,
    _align_panel,
    calculate_backtest_metrics,
    load_stock_data_db_first,
)

TRAIN_START = "2020-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
INITIAL_CASH = 1_000_000.0
DEFAULT_TIMESTEPS = 100_000
N_ENVS = 8
N_STEPS_PER_ENV = 128  # n_steps * N_ENVS == 1024, same total buffer as the single-env attempt
BATCH_SIZE = 256  # multiple of N_ENVS, required by RecurrentPPO sequence-aware minibatching
CHECKPOINT_DIR = PROJECT_ROOT / "models" / "portfolio"
RESULTS_DIR = PROJECT_ROOT / "results"

REFERENCE_100K_MLP = {
    "final_value": {"mean": 3_511_776.0, "std": 61_932.0},
    "sharpe_ratio": {"mean": 1.945, "std": 0.021},
    "max_drawdown": {"mean": -0.2971, "std": 0.0037},
}
REFERENCE_SINGLE_ENV_RECURRENT = {
    "final_value": {"mean": 3_534_494.0, "std": 0.0},
    "sharpe_ratio": {"mean": 1.840, "std": 0.0},
    "max_drawdown": {"mean": -0.3615, "std": 0.0},
    "num_trades": {"mean": 94.0, "std": 0.0},
    "note": "collapsed to a near-fixed action distribution independent of seed/budget -- see 2026-08-24 handoff",
}


def _make_env(train_panel, tickers, env_kwargs):
    def _init():
        return PortfolioEnv(train_panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    return _init


def _train_recurrent_multienv(stock_data, tickers, model_name, *, timesteps, seed, env_kwargs, ppo_kwargs):
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
    vec_env = DummyVecEnv([_make_env(train_panel, tickers, env_kwargs) for _ in range(N_ENVS)])
    t0 = time.time()
    model = RecurrentPPO(
        "MlpLstmPolicy", vec_env,
        learning_rate=ppo_kwargs.get("learning_rate", 3e-4),
        n_steps=N_STEPS_PER_ENV,
        batch_size=BATCH_SIZE,
        gamma=ppo_kwargs.get("gamma", 0.99),
        gae_lambda=ppo_kwargs.get("gae_lambda", 0.95),
        ent_coef=ppo_kwargs.get("ent_coef", 0.08),
        seed=seed, verbose=0,
    )
    model.learn(total_timesteps=timesteps)
    elapsed = time.time() - t0

    assert model_name.startswith("experiment_recurrentlstm_multienv_"), "refusing to save outside the experiment namespace"
    model_path = CHECKPOINT_DIR / f"{model_name}.zip"
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    vec_env.close()
    return model, elapsed


def _probe_action_distribution(model, env, n=20):
    """Diagnostic: does the trained policy's action distribution still
    depend on the observation, or has it collapsed to a near-fixed point
    (the failure mode found in the single-env attempt)? Returns the
    per-step argmax action and the max probability at each step so
    collapse is visible directly, not inferred from trade counts.
    """
    import torch as th

    shape = model.policy.lstm_hidden_state_shape
    lstm_states = (th.zeros(shape), th.zeros(shape))
    obs, _ = env.reset()
    episode_start = np.ones((1,), dtype=bool)
    trace = []
    for _ in range(n):
        obs_t = th.as_tensor(obs).float().unsqueeze(0)
        es_t = th.as_tensor(episode_start).float()
        with th.no_grad():
            dist, lstm_states = model.policy.get_distribution(obs_t, lstm_states, es_t)
        probs = dist.distribution.probs.numpy()[0]
        trace.append({"argmax": int(probs.argmax()), "max_prob": float(probs.max()), "probs": [round(float(p), 4) for p in probs]})
        obs, _, term, trunc, info = env.step(int(probs.argmax()))
        episode_start = np.array([term or trunc], dtype=bool)
        if term or trunc:
            break
    return trace


def _backtest_recurrent(model, stock_data, tickers, group_label, *, shared_feature_cols,
                         backtest_start, backtest_end, initial_cash, env_kwargs):
    panel = _align_panel(stock_data, tickers, backtest_start, backtest_end, shared_feature_cols=shared_feature_cols)
    if len(panel) < 100:
        raise RuntimeError(f"Group {group_label} 回測數據不足：{len(panel)} 筆")

    env = PortfolioEnv(panel, tickers, shared_feature_cols=shared_feature_cols,
                        initial_cash=initial_cash, **dict(env_kwargs or {}))

    import torch as th
    shape = model.policy.lstm_hidden_state_shape
    lstm_states = (th.zeros(shape), th.zeros(shape))
    obs, _ = env.reset()
    episode_start = np.ones((1,), dtype=bool)
    done = False
    while not done:
        action, lstm_states = model.predict(
            obs, state=lstm_states, episode_start=episode_start, deterministic=True,
        )
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        episode_start = np.array([done], dtype=bool)

    equity = [float(v) for v in env.equity_curve]
    total_contributions = float(env.total_contributions)
    total_invested_capital = float(initial_cash + total_contributions)
    net_profit = float(equity[-1] - total_invested_capital)
    probe_env = PortfolioEnv(panel, tickers, shared_feature_cols=shared_feature_cols,
                              initial_cash=initial_cash, **dict(env_kwargs or {}))
    action_probe = _probe_action_distribution(model, probe_env)
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "net_profit": net_profit,
        "contribution_return": (float(net_profit / total_invested_capital) if total_invested_capital > 0 else None),
        "action_distribution_probe": action_probe,
    }


def _metrics_summary(result: dict) -> dict:
    rl = result["rl_metrics"]
    return {
        "final_value": result["final_value"],
        "sharpe_ratio": rl.get("sharpe"),
        "max_drawdown": rl.get("max_drawdown"),
        "annual_return": rl.get("annual_return"),
        "num_trades": result["num_trades"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--timesteps", type=int, default=DEFAULT_TIMESTEPS)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    tickers = DEFAULT_GROUP_A_TICKERS
    profile = GROUP_A_PROFILE_PRESETS["default"]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = None
    ppo_kwargs = profile["ppo"]

    print(f"Loading Group A stock data ({tickers})...")
    stock_data = load_stock_data_db_first(tickers, TRAIN_START, BACKTEST_END)

    records = []
    for seed in args.seeds:
        model_name = f"experiment_recurrentlstm_multienv_baseline_seed{seed}"
        print(f"\n=== training {model_name} (timesteps={args.timesteps}, n_envs={N_ENVS}) ===")
        model, elapsed = _train_recurrent_multienv(
            stock_data, tickers, model_name,
            timesteps=args.timesteps, seed=seed,
            env_kwargs=env_kwargs, ppo_kwargs=ppo_kwargs,
        )
        print(f"  trained in {elapsed:.0f}s")

        result = _backtest_recurrent(
            model, stock_data, tickers, "GroupA_recurrentlstm_multienv_experiment",
            shared_feature_cols=None,
            backtest_start=BACKTEST_START, backtest_end=BACKTEST_END,
            initial_cash=INITIAL_CASH, env_kwargs=dict(env_kwargs),
        )
        summary = _metrics_summary(result)
        summary.update({"seed": seed, "train_seconds": elapsed, "action_distribution_probe": result["action_distribution_probe"]})
        records.append(summary)
        max_probs = [s["max_prob"] for s in result["action_distribution_probe"]]
        print(
            f"  backtest: final_value={summary['final_value']:,.0f} "
            f"sharpe={summary['sharpe_ratio']:.3f} mdd={summary['max_drawdown']:.4f} "
            f"trades={summary['num_trades']}"
        )
        print(f"  action-prob probe (first {len(max_probs)} steps) max_prob range: [{min(max_probs):.3f}, {max(max_probs):.3f}]")

    fv = np.array([r["final_value"] for r in records])
    sh = np.array([r["sharpe_ratio"] for r in records])
    mdd = np.array([r["max_drawdown"] for r in records])
    trades = np.array([r["num_trades"] for r in records])
    print(f"\n=== recurrent LSTM (multi-env) summary across {len(args.seeds)} seeds ===")
    print(f"  final_value mean={fv.mean():,.0f} std={fv.std():,.0f}")
    print(f"  sharpe mean={sh.mean():.4f} std={sh.std():.4f}")
    print(f"  mdd mean={mdd.mean():.4f} std={mdd.std():.4f}")
    print(f"  num_trades mean={trades.mean():.1f} std={trades.std():.1f}")
    print("\n=== vs single-env recurrent attempt (collapsed) ===")
    print(f"  final_value identical to single-env collapse point? {bool(np.all(np.abs(fv - REFERENCE_SINGLE_ENV_RECURRENT['final_value']['mean']) < 1.0))}")
    print("\n=== vs 100k MlpPolicy (memoryless) reference ===")
    print(f"  sharpe delta (mean): {sh.mean() - REFERENCE_100K_MLP['sharpe_ratio']['mean']:+.4f}")
    print(f"  mdd delta (mean): {mdd.mean() - REFERENCE_100K_MLP['max_drawdown']['mean']:+.4f}")

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_recurrent_lstm_multienv_experiment_2607_00475_{int(time.time())}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "policy": "experiment_only_no_production_impact",
                "paper_ref": "arXiv:2607.00475",
                "n_envs": N_ENVS,
                "n_steps_per_env": N_STEPS_PER_ENV,
                "batch_size": BATCH_SIZE,
                "tickers": tickers,
                "train_window": [TRAIN_START, TRAIN_END],
                "backtest_window": [BACKTEST_START, BACKTEST_END],
                "timesteps": args.timesteps,
                "seeds": args.seeds,
                "records": records,
                "summary_recurrent_lstm_multienv": {
                    "final_value": {"mean": float(fv.mean()), "std": float(fv.std())},
                    "sharpe_ratio": {"mean": float(sh.mean()), "std": float(sh.std())},
                    "max_drawdown": {"mean": float(mdd.mean()), "std": float(mdd.std())},
                    "num_trades": {"mean": float(trades.mean()), "std": float(trades.std())},
                },
                "reference_100k_mlp_memoryless": REFERENCE_100K_MLP,
                "reference_single_env_recurrent_collapsed": REFERENCE_SINGLE_ENV_RECURRENT,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
