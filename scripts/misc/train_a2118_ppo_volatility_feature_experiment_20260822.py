#!/usr/bin/env python3
"""EXPERIMENT (not production): does adding realized-volatility features to
a2118 Last PPO's observation space improve Group A training, per Fable
00631L direction #5?

Evidence motivating this (2026-08-21 Fable review): train_dual_group_2024_
2026.py's FEATURE_COLUMNS (close_ma120_ratio, close_ma240_ratio, ma60_
ma240_ratio, momentum_21/63/126/252, rolling_mdd_63) applied identically to
every ticker contains ZERO volatility-derived feature. 00631L's entire
character (2x daily-reset leverage, vol drag, path-dependent compounding) is
a volatility phenomenon, yet the RL policy choosing allocations is blind to
volatility in its own state -- it can only infer regime shifts indirectly
through momentum/MA-ratio lag. The only vol-aware component in the whole
pipeline (PVA's realized_vol_20) is a post-hoc weight-blending input, not
something the policy network itself observes.

Different lever from the 2026-08-20 mfcf_hnn_a2118_ppo_policy_architecture_
experiment (closed_negative): that one changed the FEATURE EXTRACTOR
architecture (dense MLP vs sparse HNN) on the SAME 37-dim observation. This
changes the INPUT SPACE itself (adds 3 new per-ticker features), same
default MlpPolicy architecture both variants.

METHOD: reuses PortfolioEnv/GROUP_A_PROFILE_PRESETS/load_stock_data_db_first/
_align_panel/_backtest_group directly from train_dual_group_2024_2026.py
(imported, never modified). Volatility columns are injected directly into
each ticker's raw stock_data dataframe BEFORE _align_panel runs (mirroring
how attach_institutional_features_db_first etc. already inject unprefixed
DB columns that _compute_features preserves and _align_panel ticker-
prefixes) -- train_dual_group_2024_2026.py's own FEATURE_COLUMNS global is
monkey-patched in-process only, exactly like the two same-week defensive-
basket pilots' TICKERS monkey-patch, never written to disk.

SAFETY: same as the 2026-08-20 experiment -- never touches
models/portfolio/last_ppo_group_a_100k.zip or group_a_production_*; all
checkpoints save as models/portfolio/experiment_volfeat_*.
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

import train_dual_group_2024_2026 as train_mod
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
VOL_FEATURE_NAMES = ("realized_volatility_20d", "realized_volatility_60d", "volatility_persistence_ratio")


def _inject_volatility_columns(stock_data: dict) -> dict:
    """Return a copy of stock_data with 3 new per-ticker volatility columns
    added to each ticker's own OHLCV dataframe, using the same formulas as
    group_a_plus/integrations/leveraged_compounding_regime.py's
    build_compounding_features (realized_volatility_20d/60d, ratio) -- just
    applied per-ticker generically instead of only to the 00631L/0050 pair,
    since FEATURE_COLUMNS applies uniformly across all portfolio tickers.
    """
    import pandas as pd

    out = {}
    for ticker, df in stock_data.items():
        df = df.copy()
        returns = pd.to_numeric(df["close"], errors="coerce").pct_change()
        vol20 = returns.rolling(20, min_periods=20).std()
        vol60 = returns.rolling(60, min_periods=60).std()
        df["realized_volatility_20d"] = vol20
        df["realized_volatility_60d"] = vol60
        df["volatility_persistence_ratio"] = vol20 / vol60.replace(0.0, np.nan)
        out[ticker] = df
    return out


def _train_variant(stock_data, tickers, model_name, *, timesteps, seed, env_kwargs, ppo_kwargs):
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
    return model, elapsed, train_panel.shape[1]


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
    stock_data_base = load_stock_data_db_first(tickers, TRAIN_START, BACKTEST_END)
    stock_data_volfeat = _inject_volatility_columns(stock_data_base)

    original_feature_columns = list(train_mod.FEATURE_COLUMNS)
    volfeat_feature_columns = original_feature_columns + list(VOL_FEATURE_NAMES)

    records = []
    for seed in args.seeds:
        for variant in ("baseline", "volfeat"):
            model_name = f"experiment_volfeat_{variant}_seed{seed}"
            if variant == "baseline":
                train_mod.FEATURE_COLUMNS = original_feature_columns
                stock_data = stock_data_base
            else:
                train_mod.FEATURE_COLUMNS = volfeat_feature_columns
                stock_data = stock_data_volfeat

            print(f"\n=== training {model_name} (timesteps={args.timesteps}, FEATURE_COLUMNS={len(train_mod.FEATURE_COLUMNS)}) ===")
            model, elapsed, obs_dim = _train_variant(
                stock_data, tickers, model_name,
                timesteps=args.timesteps, seed=seed,
                env_kwargs=env_kwargs, ppo_kwargs=ppo_kwargs,
            )
            print(f"  trained in {elapsed:.0f}s, panel cols (proxy for feature richness)={obs_dim}")

            result = _backtest_group(
                model, stock_data, tickers, "GroupA_volfeat_experiment",
                shared_feature_cols=None,
                backtest_start=BACKTEST_START, backtest_end=BACKTEST_END,
                initial_cash=INITIAL_CASH, env_kwargs=dict(env_kwargs),
            )
            summary = _metrics_summary(result)
            summary.update({"variant": variant, "seed": seed, "train_seconds": elapsed})
            records.append(summary)
            print(
                f"  backtest: final_value={summary['final_value']:,.0f} "
                f"sharpe={summary['sharpe_ratio']:.3f} mdd={summary['max_drawdown']:.4f} "
                f"trades={summary['num_trades']}"
            )

    train_mod.FEATURE_COLUMNS = original_feature_columns  # restore

    print("\n=== summary across seeds ===")
    for variant in ("baseline", "volfeat"):
        rows = [r for r in records if r["variant"] == variant]
        fv = np.array([r["final_value"] for r in rows])
        sh = np.array([r["sharpe_ratio"] for r in rows])
        mdd = np.array([r["max_drawdown"] for r in rows])
        print(
            f"  {variant}: final_value mean={fv.mean():,.0f} std={fv.std():,.0f} "
            f"| sharpe mean={sh.mean():.3f} std={sh.std():.3f} "
            f"| mdd mean={mdd.mean():.4f} std={mdd.std():.4f}"
        )

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_volatility_feature_experiment_{int(time.time())}.json"
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
                "vol_feature_names": list(VOL_FEATURE_NAMES),
                "baseline_feature_columns": original_feature_columns,
                "volfeat_feature_columns": volfeat_feature_columns,
                "records": records,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
