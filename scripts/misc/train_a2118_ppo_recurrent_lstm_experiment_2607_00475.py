#!/usr/bin/env python3
"""EXPERIMENT (not production): arXiv:2607.00475 (Pollok & Robik,
"End-to-End Parametric Portfolio Policies for Cross-Asset Futures Timing")
found that on 16 liquid CME futures, an attention/recurrent policy that
carries state across time (their Transformer, and to a lesser extent an
LSTM) trades far less than a memoryless policy, and that this lower
turnover is what lets gross Sharpe survive realistic transaction costs.
Group A+'s a2118 Last PPO policy uses SB3's default MlpPolicy -- a
memoryless mapping from a single day's flat 52-ish-dim engineered feature
vector to an action, with NO temporal state carried across steps at all.

This tests the paper's core mechanism (does giving the policy real
temporal memory reduce turnover / change trading behavior) with the
CHEAPEST faithful test available: swap SB3's PPO+MlpPolicy for
sb3-contrib's RecurrentPPO+MlpLstmPolicy. This requires NO change to
PortfolioEnv's observation space (still the same flat per-step vector);
the LSTM inside the policy network carries hidden state across the
rollout itself, exactly matching the paper's LSTM baseline architecture,
without the much larger engineering lift of redesigning the observation
space into an explicit lookback window (which would be needed to also
test a Transformer/attention extractor -- deliberately deferred until
this cheaper test says the temporal-memory direction is worth pursuing
at all).

Applicability caveats going in (recorded before results, not after):
1. Group A+'s PortfolioEnv already penalizes turnover directly via
   `turnover_penalty` in the reward AND structurally via
   `min_rebalance_days=5` -- unlike the paper's setup, where turnover
   reduction is a side effect the architecture has to discover on its
   own. Any turnover benefit from adding an LSTM may be small on top of
   these existing mechanisms.
2. The paper trains via a differentiable Sharpe loss (supervised-style
   backprop through continuous portfolio weights); Group A+ trains via
   PPO policy-gradient RL on a small discrete action space. The
   mechanism by which architecture shapes turnover need not transfer
   across these different training paradigms.
3. Three prior PPO architecture/feature/action-space modifications this
   session (2026-08-20 HNN extractor, 2026-08-22 volatility features,
   2026-08-22 finegrained action space) all showed the same signature at
   100k timesteps: roughly neutral-to-mixed mean effect, but 6-7.4x
   inflated cross-seed MDD variance. A 500k-timestep control run (round-2
   direction #9) showed variance does NOT reliably converge with more
   budget either. This experiment inherits that risk.

METHOD: subclasses nothing -- imports PortfolioEnv unmodified from
train_dual_group_2024_2026.py, same tickers/profile/windows/seeds as
every prior PPO experiment this session, only the model class changes
(sb3_contrib.RecurrentPPO with MlpLstmPolicy instead of
stable_baselines3.PPO with MlpPolicy). Same n_steps=1024 as the
production PPO hyperparameters; batch_size set equal to n_steps because
RecurrentPPO with a single environment requires the whole rollout to be
one contiguous sequence per minibatch.

Backtest requires custom handling (NOT the shared `_backtest_group`
helper, which calls `model.predict(obs, deterministic=True)` with no
state -- correct for memoryless PPO but WRONG for RecurrentPPO, where
omitting state/episode_start resets the LSTM hidden state every single
step and silently defeats the entire point of this experiment). This
script threads `lstm_states` and `episode_start` through the backtest
loop by hand.

SAFETY: never touches models/portfolio/last_ppo_group_a_100k.zip or
train_dual_group_2024_2026.py; checkpoints save as
models/portfolio/experiment_recurrentlstm_*.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from sb3_contrib import RecurrentPPO

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
CHECKPOINT_DIR = PROJECT_ROOT / "models" / "portfolio"
RESULTS_DIR = PROJECT_ROOT / "results"

# 2026-08-22 finegrained-action experiment's own baseline run, same env/
# seeds/windows at 100k timesteps with plain MlpPolicy PPO -- the reference
# point this script compares the recurrent LSTM policy against.
REFERENCE_100K_MLP = {
    "final_value": {"mean": 3_511_776.0, "std": 61_932.0},
    "sharpe_ratio": {"mean": 1.945, "std": 0.021},
    "max_drawdown": {"mean": -0.2971, "std": 0.0037},
}


def _train_recurrent(stock_data, tickers, model_name, *, timesteps, seed, env_kwargs, ppo_kwargs):
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
    env = PortfolioEnv(train_panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    n_steps = ppo_kwargs.get("n_steps", 1024)
    t0 = time.time()
    model = RecurrentPPO(
        "MlpLstmPolicy", env,
        learning_rate=ppo_kwargs.get("learning_rate", 3e-4),
        n_steps=n_steps,
        batch_size=n_steps,  # single env -> whole rollout is one sequence
        gamma=ppo_kwargs.get("gamma", 0.99),
        gae_lambda=ppo_kwargs.get("gae_lambda", 0.95),
        ent_coef=ppo_kwargs.get("ent_coef", 0.08),
        seed=seed, verbose=0,
    )
    model.learn(total_timesteps=timesteps)
    elapsed = time.time() - t0

    assert model_name.startswith("experiment_recurrentlstm_"), "refusing to save outside the experiment namespace"
    model_path = CHECKPOINT_DIR / f"{model_name}.zip"
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    return model, elapsed


def _backtest_recurrent(model, stock_data, tickers, group_label, *, shared_feature_cols,
                         backtest_start, backtest_end, initial_cash, env_kwargs):
    """Recurrent-policy backtest loop. Cannot reuse `_backtest_group`: that
    helper calls model.predict(obs, deterministic=True) with no state/
    episode_start, which for RecurrentPPO re-zeros the LSTM hidden state
    every step -- silently equivalent to a memoryless policy and defeating
    this experiment's entire point. This loop threads lstm_states and
    episode_start correctly instead.
    """
    panel = _align_panel(stock_data, tickers, backtest_start, backtest_end, shared_feature_cols=shared_feature_cols)
    if len(panel) < 100:
        raise RuntimeError(f"Group {group_label} 回測數據不足：{len(panel)} 筆")

    env = PortfolioEnv(panel, tickers, shared_feature_cols=shared_feature_cols,
                        initial_cash=initial_cash, **dict(env_kwargs or {}))
    obs, _ = env.reset()
    lstm_states = None
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
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "net_profit": net_profit,
        "contribution_return": (float(net_profit / total_invested_capital) if total_invested_capital > 0 else None),
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
        model_name = f"experiment_recurrentlstm_baseline_seed{seed}"
        print(f"\n=== training {model_name} (timesteps={args.timesteps}) ===")
        model, elapsed = _train_recurrent(
            stock_data, tickers, model_name,
            timesteps=args.timesteps, seed=seed,
            env_kwargs=env_kwargs, ppo_kwargs=ppo_kwargs,
        )
        print(f"  trained in {elapsed:.0f}s")

        result = _backtest_recurrent(
            model, stock_data, tickers, "GroupA_recurrentlstm_experiment",
            shared_feature_cols=None,
            backtest_start=BACKTEST_START, backtest_end=BACKTEST_END,
            initial_cash=INITIAL_CASH, env_kwargs=dict(env_kwargs),
        )
        summary = _metrics_summary(result)
        summary.update({"seed": seed, "train_seconds": elapsed})
        records.append(summary)
        print(
            f"  backtest: final_value={summary['final_value']:,.0f} "
            f"sharpe={summary['sharpe_ratio']:.3f} mdd={summary['max_drawdown']:.4f} "
            f"trades={summary['num_trades']}"
        )

    fv = np.array([r["final_value"] for r in records])
    sh = np.array([r["sharpe_ratio"] for r in records])
    mdd = np.array([r["max_drawdown"] for r in records])
    trades = np.array([r["num_trades"] for r in records])
    print(f"\n=== recurrent LSTM summary across {len(args.seeds)} seeds ===")
    print(f"  final_value mean={fv.mean():,.0f} std={fv.std():,.0f}")
    print(f"  sharpe mean={sh.mean():.4f} std={sh.std():.4f}")
    print(f"  mdd mean={mdd.mean():.4f} std={mdd.std():.4f}")
    print(f"  num_trades mean={trades.mean():.1f} std={trades.std():.1f}")
    print("\n=== vs 100k MlpPolicy (memoryless) reference ===")
    print(f"  sharpe delta (mean): {sh.mean() - REFERENCE_100K_MLP['sharpe_ratio']['mean']:+.4f}")
    print(f"  mdd delta (mean): {mdd.mean() - REFERENCE_100K_MLP['max_drawdown']['mean']:+.4f}")
    print(f"  mdd std ratio (recurrent/mlp): {mdd.std() / REFERENCE_100K_MLP['max_drawdown']['std']:.2f}x")

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_recurrent_lstm_experiment_2607_00475_{int(time.time())}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "policy": "experiment_only_no_production_impact",
                "paper_ref": "arXiv:2607.00475",
                "tickers": tickers,
                "train_window": [TRAIN_START, TRAIN_END],
                "backtest_window": [BACKTEST_START, BACKTEST_END],
                "timesteps": args.timesteps,
                "seeds": args.seeds,
                "records": records,
                "summary_recurrent_lstm": {
                    "final_value": {"mean": float(fv.mean()), "std": float(fv.std())},
                    "sharpe_ratio": {"mean": float(sh.mean()), "std": float(sh.std())},
                    "max_drawdown": {"mean": float(mdd.mean()), "std": float(mdd.std())},
                    "num_trades": {"mean": float(trades.mean()), "std": float(trades.std())},
                },
                "reference_100k_mlp_memoryless": REFERENCE_100K_MLP,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
