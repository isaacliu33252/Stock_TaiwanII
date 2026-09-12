#!/usr/bin/env python3
"""EXPERIMENT (not production): arXiv:2607.00475 (Pollok & Robik) Section
V-D found that averaging outputs across independently-seeded models was the
ONLY enhancement that reliably helped in their tests -- mixture-of-experts,
larger feature sets, per-class tuning, and cross-model ensembling all did
not. This tests that specific, narrow claim on Group A+'s existing
memoryless PPO (MlpPolicy), reusing the three ALREADY-TRAINED baseline
checkpoints from the 2026-08-22 finegrained-action experiment
(experiment_finegrained_baseline_seed{42,43,44}.zip) -- no retraining.

This is a DIFFERENT mechanism from, and unaffected by, the recurrent-LSTM
collapse closed out in a2118_ppo_recurrent_lstm_multienv_experiment_2607_00475_
diagnostic_closure.json: that failure was specific to RecurrentPPO's hidden
state; plain MlpPolicy PPO has no hidden state to collapse.

METHOD: at each backtest step, query all three seeds' categorical action
distributions (model.policy.get_distribution(obs).distribution.probs) on the
SAME observation, average the three probability vectors elementwise, and
step a single shared PortfolioEnv with the ensemble's argmax action. This is
the discrete-action analogue of the paper's "average the weight outputs
across seeds" -- there is no separate weight layer to average here (Group
A+'s policy outputs a discrete action, not continuous weights directly), so
averaging the pre-argmax categorical distributions is the closest faithful
adaptation: it lets minority-seed disagreement flip the ensemble's choice
exactly the way averaging continuous weights would blend them.

Compares against: (a) the mean of the three seeds' own INDIVIDUAL backtests
(already computed in results/a2118_ppo_finegrained_00631l_action_experiment_
1787406561.json, "baseline" variant), to see whether ensembling beats simply
averaging the outcome metrics after the fact, and (b) each seed's own
individual metrics, to see whether the ensemble is more stable (lower
variance would not even apply here since ensemble produces one run, but the
question is whether it lands closer to the better seeds than the worse one).

SAFETY: read-only inference on existing checkpoints. No training, no writes
outside results/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
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

TRAIN_WINDOW = ("2020-01-01", "2023-12-31")
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
INITIAL_CASH = 1_000_000.0
CHECKPOINT_DIR = PROJECT_ROOT / "models" / "portfolio"
RESULTS_DIR = PROJECT_ROOT / "results"
DEFAULT_SEEDS = (42, 43, 44)
DEFAULT_MODEL_PREFIX = "experiment_finegrained_baseline_seed"

# Each seed's own individual backtest, from the original 2026-08-22 run
# (results/a2118_ppo_finegrained_00631l_action_experiment_1787406561.json,
# variant == "baseline"). Recorded here so this script's report is
# self-contained without re-parsing that file.
INDIVIDUAL_SEED_RESULTS = {
    42: {"final_value": 3424276.580496664, "sharpe_ratio": 1.9159739623042518, "max_drawdown": -0.2941957537598845, "num_trades": 80},
    43: {"final_value": 3552163.1371978093, "sharpe_ratio": 1.9658822051633322, "max_drawdown": -0.294745811522435, "num_trades": 71},
    44: {"final_value": 3558888.3896293286, "sharpe_ratio": 1.951799880493641, "max_drawdown": -0.3023141143620184, "num_trades": 85},
}


def _load_models(seeds, prefix):
    models = []
    for seed in seeds:
        path = CHECKPOINT_DIR / f"{prefix}{seed}.zip"
        if not path.exists():
            raise FileNotFoundError(f"missing checkpoint: {path}")
        models.append(PPO.load(str(path)))
    return models


def _ensemble_action(models, obs) -> tuple[int, np.ndarray, list[np.ndarray]]:
    obs_t = th.as_tensor(obs).float().unsqueeze(0)
    per_model_probs = []
    for model in models:
        with th.no_grad():
            dist = model.policy.get_distribution(obs_t)
        per_model_probs.append(dist.distribution.probs.numpy()[0])
    avg_probs = np.mean(per_model_probs, axis=0)
    return int(avg_probs.argmax()), avg_probs, per_model_probs


def _backtest_ensemble(models, stock_data, tickers, env_kwargs):
    panel = _align_panel(stock_data, tickers, BACKTEST_START, BACKTEST_END, shared_feature_cols=None)
    if len(panel) < 100:
        raise RuntimeError(f"回測數據不足：{len(panel)} 筆")

    env = PortfolioEnv(panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    obs, _ = env.reset()
    done = False
    action_trace = []
    disagreement_days = 0
    while not done:
        ensemble_action, avg_probs, per_model_probs = _ensemble_action(models, obs)
        individual_argmaxes = [int(p.argmax()) for p in per_model_probs]
        if len(set(individual_argmaxes)) > 1:
            disagreement_days += 1
        action_trace.append({
            "ensemble_action": ensemble_action,
            "individual_argmaxes": individual_argmaxes,
            "avg_probs": [round(float(p), 4) for p in avg_probs],
        })
        obs, _, terminated, truncated, info = env.step(ensemble_action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    total_contributions = float(env.total_contributions)
    total_invested_capital = float(INITIAL_CASH + total_contributions)
    net_profit = float(equity[-1] - total_invested_capital)
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "net_profit": net_profit,
        "contribution_return": (float(net_profit / total_invested_capital) if total_invested_capital > 0 else None),
        "total_backtest_days": len(action_trace),
        "seed_disagreement_days": disagreement_days,
        "seed_disagreement_rate": disagreement_days / len(action_trace) if action_trace else None,
        "action_trace_sample": action_trace[:10] + action_trace[-10:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--model-prefix", default=DEFAULT_MODEL_PREFIX)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    tickers = DEFAULT_GROUP_A_TICKERS
    profile = GROUP_A_PROFILE_PRESETS["default"]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = None

    print(f"Loading Group A stock data ({tickers})...")
    stock_data = load_stock_data_db_first(tickers, TRAIN_WINDOW[0], BACKTEST_END)

    print(f"Loading {len(args.seeds)} checkpoints: {args.model_prefix}{{{','.join(map(str, args.seeds))}}}.zip")
    models = _load_models(args.seeds, args.model_prefix)

    t0 = time.time()
    result = _backtest_ensemble(models, stock_data, tickers, env_kwargs)
    elapsed = time.time() - t0
    rl = result["rl_metrics"]
    ensemble_summary = {
        "final_value": result["final_value"],
        "sharpe_ratio": rl.get("sharpe"),
        "max_drawdown": rl.get("max_drawdown"),
        "annual_return": rl.get("annual_return"),
        "num_trades": result["num_trades"],
    }

    individual = {s: INDIVIDUAL_SEED_RESULTS[s] for s in args.seeds if s in INDIVIDUAL_SEED_RESULTS}
    mean_of_individuals = {
        key: float(np.mean([v[key] for v in individual.values()]))
        for key in ("final_value", "sharpe_ratio", "max_drawdown", "num_trades")
    }
    best_individual_sharpe = max(individual.items(), key=lambda kv: kv[1]["sharpe_ratio"])
    worst_individual_sharpe = min(individual.items(), key=lambda kv: kv[1]["sharpe_ratio"])

    print(f"\n=== ensemble backtest ({elapsed:.0f}s) ===")
    print(f"  final_value={ensemble_summary['final_value']:,.0f} sharpe={ensemble_summary['sharpe_ratio']:.4f} "
          f"mdd={ensemble_summary['max_drawdown']:.4f} trades={ensemble_summary['num_trades']}")
    print(f"  seed disagreement: {result['seed_disagreement_days']}/{result['total_backtest_days']} days "
          f"({result['seed_disagreement_rate']:.1%})")
    print("\n=== vs individual seeds ===")
    for seed, v in individual.items():
        print(f"  seed{seed}: sharpe={v['sharpe_ratio']:.4f} mdd={v['max_drawdown']:.4f} trades={v['num_trades']}")
    print(f"  mean-of-individuals: sharpe={mean_of_individuals['sharpe_ratio']:.4f} "
          f"mdd={mean_of_individuals['max_drawdown']:.4f}")
    print(f"  best individual (seed{best_individual_sharpe[0]}): sharpe={best_individual_sharpe[1]['sharpe_ratio']:.4f}")
    print(f"  worst individual (seed{worst_individual_sharpe[0]}): sharpe={worst_individual_sharpe[1]['sharpe_ratio']:.4f}")
    print(f"\n  ensemble vs mean-of-individuals sharpe delta: "
          f"{ensemble_summary['sharpe_ratio'] - mean_of_individuals['sharpe_ratio']:+.4f}")
    print(f"  ensemble vs best individual sharpe delta: "
          f"{ensemble_summary['sharpe_ratio'] - best_individual_sharpe[1]['sharpe_ratio']:+.4f}")
    print(f"  ensemble vs worst individual sharpe delta: "
          f"{ensemble_summary['sharpe_ratio'] - worst_individual_sharpe[1]['sharpe_ratio']:+.4f}")

    output_path = Path(args.output) if args.output else RESULTS_DIR / f"a2118_ppo_seed_averaging_ensemble_2607_00475_{int(time.time())}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "policy": "experiment_only_no_production_impact",
                "paper_ref": "arXiv:2607.00475",
                "mechanism_tested": "seed_output_averaging_section_V_D",
                "seeds": args.seeds,
                "model_prefix": args.model_prefix,
                "backtest_window": [BACKTEST_START, BACKTEST_END],
                "ensemble_result": ensemble_summary,
                "ensemble_diagnostics": {
                    "total_backtest_days": result["total_backtest_days"],
                    "seed_disagreement_days": result["seed_disagreement_days"],
                    "seed_disagreement_rate": result["seed_disagreement_rate"],
                    "action_trace_sample": result["action_trace_sample"],
                },
                "individual_seed_results": individual,
                "mean_of_individuals": mean_of_individuals,
                "best_individual": {"seed": best_individual_sharpe[0], **best_individual_sharpe[1]},
                "worst_individual": {"seed": worst_individual_sharpe[0], **worst_individual_sharpe[1]},
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
