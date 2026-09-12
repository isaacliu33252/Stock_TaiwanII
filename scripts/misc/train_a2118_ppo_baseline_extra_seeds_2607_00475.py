#!/usr/bin/env python3
"""EXPERIMENT (not production): follow-up to eval_a2118_ppo_seed_averaging_
ensemble_2607_00475.py. Trains additional baseline (default action schema)
PPO checkpoints beyond the existing seeds {42,43,44}
(experiment_finegrained_baseline_seed*.zip), using the IDENTICAL recipe
(same PortfolioEnv, same GROUP_A_PROFILE_PRESETS["default"] env/ppo
kwargs, same 2020-2023 train window, 100k timesteps) so they can be added
to the seed-averaging ensemble test. This is arXiv:2607.00475 Section V-D's
own robustness check ("we also tested larger seed ensembles, but adding
more than three seeds did not materially change the results") replicated
on Group A+'s task.

SAFETY: never touches models/portfolio/last_ppo_group_a_100k.zip or
train_dual_group_2024_2026.py; checkpoints save as
models/portfolio/experiment_finegrained_baseline_seed{45,46}.zip, same
namespace as the existing seed42/43/44 baseline checkpoints (same variant,
new seed values only).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (  # noqa: E402
    DEFAULT_GROUP_A_TICKERS,
    GROUP_A_PROFILE_PRESETS,
    PortfolioEnv,
    _align_panel,
    _backtest_group,
    load_stock_data_db_first,
)

TRAIN_START = "2020-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
INITIAL_CASH = 1_000_000.0
DEFAULT_TIMESTEPS = 100_000
CHECKPOINT_DIR = PROJECT_ROOT / "models" / "portfolio"
EXTRA_SEEDS = (45, 46)


def main() -> None:
    tickers = DEFAULT_GROUP_A_TICKERS
    profile = GROUP_A_PROFILE_PRESETS["default"]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = None
    ppo_kwargs = profile["ppo"]

    print(f"Loading Group A stock data ({tickers})...")
    stock_data = load_stock_data_db_first(tickers, TRAIN_START, BACKTEST_END)
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)

    for seed in EXTRA_SEEDS:
        model_name = f"experiment_finegrained_baseline_seed{seed}"
        print(f"\n=== training {model_name} (timesteps={DEFAULT_TIMESTEPS}) ===")
        env = PortfolioEnv(train_panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
        t0 = time.time()
        model = PPO(
            "MlpPolicy", env,
            learning_rate=ppo_kwargs.get("learning_rate", 3e-4),
            n_steps=ppo_kwargs.get("n_steps", 1024),
            gamma=ppo_kwargs.get("gamma", 0.99),
            gae_lambda=ppo_kwargs.get("gae_lambda", 0.95),
            ent_coef=ppo_kwargs.get("ent_coef", 0.08),
            seed=seed, verbose=0,
        )
        model.learn(total_timesteps=DEFAULT_TIMESTEPS)
        elapsed = time.time() - t0
        model_path = CHECKPOINT_DIR / f"{model_name}.zip"
        model.save(str(model_path))
        print(f"  trained in {elapsed:.0f}s, saved {model_path}")

        result = _backtest_group(
            model, stock_data, tickers, f"GroupA_extra_seed{seed}",
            shared_feature_cols=None, backtest_start=BACKTEST_START, backtest_end=BACKTEST_END,
            initial_cash=INITIAL_CASH, env_kwargs=dict(env_kwargs),
        )
        rl = result["rl_metrics"]
        print(
            f"  backtest: final_value={result['final_value']:,.0f} sharpe={rl.get('sharpe'):.4f} "
            f"mdd={rl.get('max_drawdown'):.4f} trades={result['num_trades']}"
        )


if __name__ == "__main__":
    main()
