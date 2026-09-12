#!/usr/bin/env python3
"""EXPERIMENT (not production): robustness follow-up to
eval_a2118_ppo_seed_averaging_ensemble_2607_00475.py. Two checks the first
pass didn't cover:

1. Sub-period consistency: the first pass reported one Sharpe/MDD number
   over the whole 2024-01-01..2026-05-08 backtest window (the same window
   every prior PPO experiment this session used). This splits that window
   into 2024 and 2025-2026-05-08 sub-periods and reports ensemble vs
   individual-seed metrics in each separately, so a result driven by one
   lucky sub-period isn't mistaken for a general property.
2. Seed-count sensitivity: arXiv:2607.00475 Section V-D reports that adding
   more than three seeds did not materially change their results. Given two
   freshly trained extra seeds (45, 46; see
   train_a2118_ppo_baseline_extra_seeds_2607_00475.py), this reports
   ensembles over {42,43,44}, {42,43,44,45}, and {42,43,44,45,46} so the
   same claim can be checked here.

METHOD: single shared PortfolioEnv per ensemble/individual run (matching
the original script's protocol exactly), but this version also records the
per-step date so the equity curve can be sliced by calendar sub-period
without re-running the backtest per sub-period.

SAFETY: read-only inference on existing checkpoints. No training, no writes
outside results/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import torch as th
from stable_baselines3 import PPO

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

BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
SUB_PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2025_2026": ("2025-01-01", "2026-05-08"),
}
INITIAL_CASH = 1_000_000.0
CHECKPOINT_DIR = PROJECT_ROOT / "models" / "portfolio"
RESULTS_DIR = PROJECT_ROOT / "results"
MODEL_PREFIX = "experiment_finegrained_baseline_seed"
ALL_SEEDS = (42, 43, 44, 45, 46)
ENSEMBLE_SUBSETS = [(42, 43, 44), (42, 43, 44, 45), (42, 43, 44, 45, 46)]


def _load_models(seeds):
    models = {}
    for seed in seeds:
        path = CHECKPOINT_DIR / f"{MODEL_PREFIX}{seed}.zip"
        if not path.exists():
            raise FileNotFoundError(f"missing checkpoint: {path}")
        models[seed] = PPO.load(str(path))
    return models


def _ensemble_action(models, obs):
    obs_t = th.as_tensor(obs).float().unsqueeze(0)
    per_model_probs = []
    for model in models:
        with th.no_grad():
            dist = model.policy.get_distribution(obs_t)
        per_model_probs.append(dist.distribution.probs.numpy()[0])
    avg_probs = np.mean(per_model_probs, axis=0)
    return int(avg_probs.argmax())


def _run_backtest(action_fn, stock_data, tickers, env_kwargs, dates):
    """action_fn(obs) -> int action. Returns dated equity series (post-step
    values, aligned 1:1 with `dates`) plus final env-level counters."""
    panel = _align_panel(stock_data, tickers, BACKTEST_START, BACKTEST_END, shared_feature_cols=None)
    env = PortfolioEnv(panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    obs, _ = env.reset()
    done = False
    while not done:
        action = action_fn(obs)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    equity = [float(v) for v in env.equity_curve]
    # env takes len(panel)-1 steps (needs next-day price for each step's return,
    # so the final panel row has no corresponding step); equity has one entry
    # per step plus the initial pre-step baseline, i.e. len(equity) == len(dates).
    # equity[0] is the baseline entering dates[0]; equity[i] (i>=1) is the
    # post-step value after trading on dates[i-1].
    assert len(equity) == len(dates), f"equity/date length mismatch: {len(equity)} vs {len(dates)}"
    return equity, int(env.trade_count)


def _sub_period_metrics(equity, dates, start, end):
    dates = np.asarray(dates)
    mask = (dates >= np.datetime64(start)) & (dates <= np.datetime64(end))
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return None
    # equity[i] is the value AFTER trading on dates[i-1]; equity[lo] (== the
    # baseline entering dates[lo]) through equity[hi+1] (the value after the
    # last in-range trading day) is this sub-period's own equity trajectory.
    lo, hi = idx[0], idx[-1]
    segment = equity[lo:hi + 2]
    return calculate_backtest_metrics(segment, initial_value=segment[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(ALL_SEEDS))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    tickers = DEFAULT_GROUP_A_TICKERS
    profile = GROUP_A_PROFILE_PRESETS["default"]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = None

    print(f"Loading Group A stock data ({tickers})...")
    stock_data = load_stock_data_db_first(tickers, "2020-01-01", BACKTEST_END)
    panel = _align_panel(stock_data, tickers, BACKTEST_START, BACKTEST_END, shared_feature_cols=None)
    dates = panel["date"].dt.strftime("%Y-%m-%d").to_numpy(dtype="datetime64[D]")

    available_seeds = [s for s in args.seeds if (CHECKPOINT_DIR / f"{MODEL_PREFIX}{s}.zip").exists()]
    missing = sorted(set(args.seeds) - set(available_seeds))
    if missing:
        print(f"WARNING: skipping unavailable seeds (checkpoint not found yet): {missing}")
    print(f"Loading checkpoints for seeds: {available_seeds}")
    models = _load_models(available_seeds)

    report = {"individual": {}, "ensembles": {}}

    print("\n=== individual seeds ===")
    for seed, model in models.items():
        t0 = time.time()
        equity, trades = _run_backtest(
            lambda obs, m=model: int(m.predict(obs, deterministic=True)[0]),
            stock_data, tickers, env_kwargs, dates,
        )
        full = calculate_backtest_metrics(equity, initial_value=equity[0])
        sub = {name: _sub_period_metrics(equity, dates, *rng) for name, rng in SUB_PERIODS.items()}
        report["individual"][seed] = {"full": full, "sub_periods": sub, "num_trades": trades, "elapsed_s": time.time() - t0}
        print(f"  seed{seed}: full sharpe={full['sharpe']:.4f} mdd={full['max_drawdown']:.4f} | "
              f"2024 sharpe={sub['2024']['sharpe']:.4f} mdd={sub['2024']['max_drawdown']:.4f} | "
              f"2025-26 sharpe={sub['2025_2026']['sharpe']:.4f} mdd={sub['2025_2026']['max_drawdown']:.4f}")

    print("\n=== ensembles ===")
    for subset in ENSEMBLE_SUBSETS:
        subset = tuple(s for s in subset if s in models)
        if len(subset) < 2:
            print(f"  subset {subset}: skipped (need >=2 available models)")
            continue
        subset_models = [models[s] for s in subset]
        equity, trades = _run_backtest(
            lambda obs, ms=subset_models: _ensemble_action(ms, obs),
            stock_data, tickers, env_kwargs, dates,
        )
        full = calculate_backtest_metrics(equity, initial_value=equity[0])
        sub = {name: _sub_period_metrics(equity, dates, *rng) for name, rng in SUB_PERIODS.items()}
        key = "+".join(map(str, subset))
        report["ensembles"][key] = {"seeds": list(subset), "full": full, "sub_periods": sub, "num_trades": trades}
        print(f"  {{{key}}}: full sharpe={full['sharpe']:.4f} mdd={full['max_drawdown']:.4f} trades={trades} | "
              f"2024 sharpe={sub['2024']['sharpe']:.4f} mdd={sub['2024']['max_drawdown']:.4f} | "
              f"2025-26 sharpe={sub['2025_2026']['sharpe']:.4f} mdd={sub['2025_2026']['max_drawdown']:.4f}")

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_seed_averaging_robustness_2607_00475_{int(time.time())}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
