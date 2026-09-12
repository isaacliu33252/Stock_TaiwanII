#!/usr/bin/env python3
"""Fable 00631L round-2 direction #9 (2026-08-23): does a higher PPO
timestep budget (500k vs the production-matching 100k) shrink cross-seed
variance, decoupled from any specific architecture/feature/action-space
change?

Motivation: three separate PPO modifications this session (2026-08-20 HNN
feature-extractor architecture, 2026-08-22 round-1 direction #5 volatility
features, round-1 direction #6 finegrained 00631L action space) all showed
the same signature at 100k timesteps -- roughly neutral-to-mixed mean effect,
but MDD cross-seed variance inflated 6-7.4x versus the unmodified baseline.
Round-1's own Final Recommendation named "test whether a higher timestep
budget (e.g. 500k) makes cross-seed variance converge" as the necessary
prerequisite before trying a 4th PPO modification, but never ran it.

This trains ONLY the unmodified baseline PortfolioEnv (train_dual_group_2024_
2026.py imported, never edited) at 500k timesteps x 3 seeds (42/43/44,
matching every prior experiment this session for direct comparability), with
NO architecture/feature/action-space change -- isolating the training-budget
variable alone. Compares resulting cross-seed variance directly against the
already-recorded 100k-timestep baseline stats from the 2026-08-22 finegrained-
action experiment's own baseline run (same env, same seeds, same everything
except timesteps): final_value mean=$3,511,776 std=$61,932, Sharpe mean=1.945
std=0.021, MDD mean=-0.2971 std=0.0037.

Checkpoints save to models/portfolio/experiment_500ktest_* only -- never
touches models/portfolio/last_ppo_group_a_100k.zip or group_a_production_*.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
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
CHECKPOINT_DIR = PROJECT_ROOT / "models" / "portfolio"
RESULTS_DIR = PROJECT_ROOT / "results"

# 2026-08-22 finegrained-action experiment's own baseline run, same env/seeds
# at 100k timesteps -- the reference point this script compares 500k against.
REFERENCE_100K = {
    "final_value": {"mean": 3_511_776.0, "std": 61_932.0},
    "sharpe_ratio": {"mean": 1.945, "std": 0.021},
    "max_drawdown": {"mean": -0.2971, "std": 0.0037},
}


def _train_baseline(stock_data, tickers, model_name, *, timesteps, seed, env_kwargs, ppo_kwargs):
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
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
    model.learn(total_timesteps=timesteps)
    elapsed = time.time() - t0

    assert model_name.startswith("experiment_"), "refusing to save outside the experiment_ namespace"
    model_path = CHECKPOINT_DIR / f"{model_name}.zip"
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    return model, elapsed


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
    parser.add_argument("--timesteps", type=int, default=500_000)
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
        model_name = f"experiment_500ktest_baseline_seed{seed}"
        print(f"\n=== training {model_name} (timesteps={args.timesteps}) ===")
        model, elapsed = _train_baseline(
            stock_data, tickers, model_name,
            timesteps=args.timesteps, seed=seed,
            env_kwargs=env_kwargs, ppo_kwargs=ppo_kwargs,
        )
        print(f"  trained in {elapsed:.0f}s")

        result = _backtest_group(
            model, stock_data, tickers, "GroupA_500ktest_experiment",
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
    print(f"\n=== 500k summary across {len(args.seeds)} seeds ===")
    print(f"  final_value mean={fv.mean():,.0f} std={fv.std():,.0f}")
    print(f"  sharpe mean={sh.mean():.4f} std={sh.std():.4f}")
    print(f"  mdd mean={mdd.mean():.4f} std={mdd.std():.4f}")
    print("\n=== vs 100k reference (2026-08-22 finegrained experiment baseline) ===")
    print(f"  final_value std ratio (500k/100k): {fv.std() / REFERENCE_100K['final_value']['std']:.2f}x")
    print(f"  sharpe std ratio (500k/100k): {sh.std() / REFERENCE_100K['sharpe_ratio']['std']:.2f}x")
    print(f"  mdd std ratio (500k/100k): {mdd.std() / REFERENCE_100K['max_drawdown']['std']:.2f}x")

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_500k_timestep_budget_characterization_{int(time.time())}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "policy": "experiment_only_no_production_impact",
                "tickers": tickers,
                "train_window": [TRAIN_START, TRAIN_END],
                "backtest_window": [BACKTEST_START, BACKTEST_END],
                "timesteps": args.timesteps,
                "seeds": args.seeds,
                "records": records,
                "summary_500k": {
                    "final_value": {"mean": float(fv.mean()), "std": float(fv.std())},
                    "sharpe_ratio": {"mean": float(sh.mean()), "std": float(sh.std())},
                    "max_drawdown": {"mean": float(mdd.mean()), "std": float(mdd.std())},
                },
                "reference_100k": REFERENCE_100K,
                "std_ratio_500k_over_100k": {
                    "final_value": float(fv.std() / REFERENCE_100K["final_value"]["std"]),
                    "sharpe_ratio": float(sh.std() / REFERENCE_100K["sharpe_ratio"]["std"]),
                    "max_drawdown": float(mdd.std() / REFERENCE_100K["max_drawdown"]["std"]),
                },
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
