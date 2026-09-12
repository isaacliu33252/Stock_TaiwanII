#!/usr/bin/env python3
"""EXPERIMENT (not production): does an MFCF/HNN sparse feature extractor
beat stable-baselines3's default MlpPolicy for a2118's "Last PPO" Group A
training?

Motivated by arXiv:2608.14323 (see GROUP_A_PLUS_MFCF_HNN_VOLATILITY_PILOT_
HANDOFF_20260820.md), where the same architecture idea was validated in
isolation on a supervised volatility-forecasting task. That pilot flagged --
but explicitly did not touch -- a2118's actual PPO policy as the one place
in GroupA+ with a genuinely analogous "many correlated features, hand-tuned
flat MLP" situation. This script runs that experiment.

Reuses PortfolioEnv, GROUP_A_PROFILE_PRESETS, load_stock_data_db_first,
_align_panel, and _backtest_group directly from train_dual_group_2024_2026.py
(imported, never modified) -- only the PPO construction is duplicated here
(with policy_kwargs support _train_group does not have) and its outputs are
kept fully separate from production.

SAFETY:
  - Never imports/writes anything under models/portfolio/last_ppo_* or
    group_a_production_*. All checkpoints save as
    models/portfolio/experiment_hnn_policy_<variant>_seed<N>.zip.
  - Never touches group_a_plus/runners/a2118.py, a2111.py,
    generate_dual_group_signal.py, or any results/*_latest.* pointer.
  - Uses train_dual_group_2024_2026.py's own default dates/tickers/profile
    (Group A "default": 0050/00631L/00632R/00679B, train 2020-2023,
    backtest 2024 to 2026-05-08) so both variants are trained/evaluated
    under identical conditions to each other -- NOT an attempt to reproduce
    the actual (irreproducible, see handoff doc) production Last PPO
    checkpoint.

Usage:
    python scripts/misc/train_a2118_hnn_policy_experiment_20260820.py \\
        --seeds 42 43 44 --timesteps 100000
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

from scripts.misc.a2118_hnn_policy_experiment_lib import (
    DEFAULT_MAX_CLIQUE_SIZE,
    HNNFeaturesExtractor,
    build_hnn_layers_from_samples,
)
from train_dual_group_2024_2026 import (
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
RESULTS_DIR = PROJECT_ROOT / "results"


def _sample_observations(train_panel, tickers, env_kwargs, *, n_samples: int, seed: int) -> np.ndarray:
    """Roll out the training env with random actions to collect real obs
    vectors for MFCF correlation estimation. Random-action rollouts are
    standard practice for architecture search / dependence estimation done
    before training starts; the technical-indicator features are
    date-driven and not meaningfully affected by which policy generated the
    portfolio-state features they're sampled alongside.
    """
    env = PortfolioEnv(train_panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    rng = np.random.default_rng(seed)
    obs, _ = env.reset(seed=seed)
    samples = [obs.copy()]
    for _ in range(n_samples - 1):
        action = env.action_space.sample() if hasattr(env.action_space, "sample") else rng.integers(0, 9)
        obs, _, terminated, truncated, _ = env.step(action)
        samples.append(obs.copy())
        if terminated or truncated:
            obs, _ = env.reset(seed=seed)
    return np.array(samples, dtype=float)


def _train_variant(
    stock_data, tickers, model_name, *, timesteps, seed, env_kwargs, ppo_kwargs, policy_kwargs
):
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
    env = PortfolioEnv(train_panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    t0 = time.time()
    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=ppo_kwargs.get("learning_rate", 3e-4),
        n_steps=ppo_kwargs.get("n_steps", 1024),
        gamma=ppo_kwargs.get("gamma", 0.99),
        gae_lambda=ppo_kwargs.get("gae_lambda", 0.95),
        ent_coef=ppo_kwargs.get("ent_coef", 0.08),
        seed=seed,
        policy_kwargs=policy_kwargs,
        verbose=0,
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
        "buy_and_hold_equal_final_value": result.get("buy_and_hold_equal", {}).get("final_value"),
        "buy_and_hold_50_50_blend_final_value": result.get("buy_and_hold_50_50_blend", {}).get("final_value"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--timesteps", type=int, default=DEFAULT_TIMESTEPS)
    parser.add_argument("--max-clique-size", type=int, default=DEFAULT_MAX_CLIQUE_SIZE)
    parser.add_argument("--obs-samples", type=int, default=800)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    tickers = DEFAULT_GROUP_A_TICKERS
    profile = GROUP_A_PROFILE_PRESETS["default"]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = None
    ppo_kwargs = profile["ppo"]

    print(f"Loading Group A stock data ({tickers})...")
    stock_data = load_stock_data_db_first(tickers, TRAIN_START, BACKTEST_END)
    train_panel = _align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
    print(f"Train panel: {len(train_panel)} rows, {train_panel['date'].min()} .. {train_panel['date'].max()}")

    print(f"Sampling {args.obs_samples} observations to build MFCF/HNN structure...")
    samples = _sample_observations(train_panel, tickers, env_kwargs, n_samples=args.obs_samples, seed=0)
    layers, col_perm = build_hnn_layers_from_samples(samples, max_clique_size=args.max_clique_size)
    print(f"  obs_dim={samples.shape[1]}, K*={max(layers.keys())}, layer widths={[len(layers[k]) for k in sorted(layers)]}")

    hnn_policy_kwargs = dict(
        features_extractor_class=HNNFeaturesExtractor,
        features_extractor_kwargs=dict(layers=layers, col_perm=col_perm),
        net_arch=[],
    )

    records = []
    for seed in args.seeds:
        for variant, policy_kwargs in (("baseline_mlp", None), ("hnn", hnn_policy_kwargs)):
            model_name = f"experiment_hnn_policy_{variant}_seed{seed}"
            print(f"\n=== training {model_name} (timesteps={args.timesteps}) ===")
            model, elapsed = _train_variant(
                stock_data, tickers, model_name,
                timesteps=args.timesteps, seed=seed,
                env_kwargs=env_kwargs, ppo_kwargs=ppo_kwargs, policy_kwargs=policy_kwargs,
            )
            print(f"  trained in {elapsed:.0f}s")

            backtest_env_kwargs = dict(env_kwargs)
            result = _backtest_group(
                model, stock_data, tickers, "GroupA_experiment",
                shared_feature_cols=None,
                backtest_start=BACKTEST_START, backtest_end=BACKTEST_END,
                initial_cash=INITIAL_CASH, env_kwargs=backtest_env_kwargs,
            )
            summary = _metrics_summary(result)
            summary.update({"variant": variant, "seed": seed, "train_seconds": elapsed})
            records.append(summary)
            print(
                f"  backtest: final_value={summary['final_value']:,.0f} "
                f"sharpe={summary['sharpe_ratio']:.3f} mdd={summary['max_drawdown']:.4f} "
                f"trades={summary['num_trades']}"
            )

    print("\n=== summary across seeds ===")
    for variant in ("baseline_mlp", "hnn"):
        rows = [r for r in records if r["variant"] == variant]
        fv = np.array([r["final_value"] for r in rows])
        sh = np.array([r["sharpe_ratio"] for r in rows])
        mdd = np.array([r["max_drawdown"] for r in rows])
        print(
            f"  {variant}: final_value mean={fv.mean():,.0f} std={fv.std():,.0f} "
            f"| sharpe mean={sh.mean():.3f} std={sh.std():.3f} "
            f"| mdd mean={mdd.mean():.4f} std={mdd.std():.4f}"
        )
    if records:
        bh = records[0]
        print(
            f"  buy_and_hold_equal final_value={bh['buy_and_hold_equal_final_value']:,.0f}, "
            f"buy_and_hold_50_50_blend final_value={bh['buy_and_hold_50_50_blend_final_value']:,.0f}"
        )

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_hnn_policy_experiment_{int(time.time())}.json"
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
                "max_clique_size": args.max_clique_size,
                "hnn_layer_widths": {str(k): len(v) for k, v in layers.items()},
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
