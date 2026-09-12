#!/usr/bin/env python3
"""EXPERIMENT (not production): does a finer-grained discrete 00631L
action space improve a2118 Last PPO training, per Fable 00631L direction #6?

Evidence motivating this (2026-08-21 Fable review): under the default
("triplet_v2"-style, GROUP_A_DEFAULT_ACTION_LABELS) action schema that Last
PPO's own training actually falls back to for an unrecognized model name
(confirmed empirically today -- see project_2608_14323_a2118_hnn_ppo_
experiment_20260822 and project_fable_00631l_direction_5_20260822, whose
baseline runs both used this schema), PPO can only choose 00631L weight from
exactly {0%, 15%, 30%} (plus hold/full-0050/inverse) -- see
train_dual_group_2024_2026.py PortfolioEnv._target_weights(), the
unconditioned fallback block. group_a_plus/integrations/letf_quadratic_
bound.py (arXiv:2301.03186) shows a daily-reset leveraged ETF's cumulative
log-return depends only on the aggregate (m1, m2) statistics of the realized
daily-return multiset, not path order -- with only 3 discrete weight levels,
the policy cannot express "slightly less exposure to trim variance while a
noisy-but-favorable mean forecast persists", it can only jump in 15pp steps.

METHOD: subclasses PortfolioEnv (train_dual_group_2024_2026.py imported,
NEVER modified) to override _target_weights() and action_space with 7 evenly
spaced 00631L levels {0,5,10,15,20,25,30}% instead of {0,15,30}% -- same
MAXIMUM exposure (30%, matching the "default" profile's own leverage_cap so
this isolates granularity, not additional risk budget), same 0050 fallback
behavior, same hold/inverse actions preserved. Everything else (env kwargs,
PPO hyperparameters, reward, panel/features) is identical to the baseline.

SAFETY: same discipline as the two prior PPO experiments this session --
never touches models/portfolio/last_ppo_group_a_100k.zip or
train_dual_group_2024_2026.py; checkpoints save as
models/portfolio/experiment_finegrained_*.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from gymnasium import spaces
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (
    DEFAULT_GROUP_A_TICKERS,
    GROUP_A_PROFILE_PRESETS,
    PortfolioEnv,
    _align_panel,
    _backtest_group,
    _weights_for,
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
# Same max exposure (0.30, matching the default profile's leverage_cap) as
# the baseline's {0, 0.15, 0.30} -- only the step size changes.
FINEGRAINED_00631L_LEVELS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30)


class FineGrained00631LEnv(PortfolioEnv):
    """Same env, more 00631L weight levels: 7 discrete steps of 5pp each
    instead of the baseline's 3 steps of 15pp each, same max exposure.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # hold (0) + one action per level (0.0 duplicates "full 0050", kept
        # for a clean, evenly-spaced action->weight mapping) + inverse (last).
        self.action_space = spaces.Discrete(len(FINEGRAINED_00631L_LEVELS) + 2)

    def _target_weights(self, action: int) -> np.ndarray:
        t = self.tickers
        if action == 0:
            return self.weights.copy()
        n_levels = len(FINEGRAINED_00631L_LEVELS)
        if 1 <= action <= n_levels:
            target_00631l = min(self.leverage_cap, FINEGRAINED_00631L_LEVELS[action - 1])
            return _weights_for(t, {"0050.TW": 1.0 - target_00631l, "00631L.TW": target_00631l})
        # last action: inverse hedge, mirrors the baseline schema's inverse action.
        return _weights_for(t, {"0050.TW": 0.70, "00632R.TW": min(self.inverse_cap, 0.30)})


def _train_variant(env_cls, stock_data, tickers, model_name, *, timesteps, seed, env_kwargs, ppo_kwargs):
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
    env = env_cls(train_panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
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


def _backtest_variant(env_cls, model, stock_data, tickers, env_kwargs):
    """Mirrors _backtest_group but constructs env_cls instead of the fixed
    PortfolioEnv, so the finegrained variant is evaluated with its own
    action space (imported _backtest_group hardcodes PortfolioEnv)."""
    from train_dual_group_2024_2026 import _align_panel as align, calculate_backtest_metrics

    panel = align(stock_data, tickers, BACKTEST_START, BACKTEST_END, shared_feature_cols=None)
    env = env_cls(panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    obs, _ = env.reset()
    done = False
    info = {"weights": np.zeros(len(tickers))}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    equity = [float(v) for v in env.equity_curve]
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
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
        for variant, env_cls in (("baseline", PortfolioEnv), ("finegrained", FineGrained00631LEnv)):
            model_name = f"experiment_finegrained_{variant}_seed{seed}"
            print(f"\n=== training {model_name} (timesteps={args.timesteps}, action_space={'default' if env_cls is PortfolioEnv else len(FINEGRAINED_00631L_LEVELS) + 2}) ===")
            model, elapsed = _train_variant(
                env_cls, stock_data, tickers, model_name,
                timesteps=args.timesteps, seed=seed,
                env_kwargs=env_kwargs, ppo_kwargs=ppo_kwargs,
            )
            print(f"  trained in {elapsed:.0f}s")

            result = _backtest_group(model, stock_data, tickers, "GroupA_finegrained_experiment", shared_feature_cols=None, backtest_start=BACKTEST_START, backtest_end=BACKTEST_END, initial_cash=INITIAL_CASH, env_kwargs=dict(env_kwargs)) if env_cls is PortfolioEnv else _backtest_variant(env_cls, model, stock_data, tickers, dict(env_kwargs))
            summary = _metrics_summary(result)
            summary.update({"variant": variant, "seed": seed, "train_seconds": elapsed})
            records.append(summary)
            print(
                f"  backtest: final_value={summary['final_value']:,.0f} "
                f"sharpe={summary['sharpe_ratio']:.3f} mdd={summary['max_drawdown']:.4f} "
                f"trades={summary['num_trades']}"
            )

    print("\n=== summary across seeds ===")
    for variant in ("baseline", "finegrained"):
        rows = [r for r in records if r["variant"] == variant]
        fv = np.array([r["final_value"] for r in rows])
        sh = np.array([r["sharpe_ratio"] for r in rows])
        mdd = np.array([r["max_drawdown"] for r in rows])
        print(
            f"  {variant}: final_value mean={fv.mean():,.0f} std={fv.std():,.0f} "
            f"| sharpe mean={sh.mean():.3f} std={sh.std():.3f} "
            f"| mdd mean={mdd.mean():.4f} std={mdd.std():.4f}"
        )

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_finegrained_00631l_action_experiment_{int(time.time())}.json"
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
                "finegrained_00631l_levels": list(FINEGRAINED_00631L_LEVELS),
                "records": records,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
