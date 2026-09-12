#!/usr/bin/env python3
"""Fable 00631L round-2 direction #7 (2026-08-22/23): does golden1's PPO
policy's own action-distribution entropy carry information beyond NCF's H20
confidence?

Motivation (Fable): golden1's PPO policy and NCF's H20 classifier are two
independent subsystems that currently never see each other's uncertainty --
NCF's `confidence` (prob_magnitude, see ncf_00631l.py) measures how far the
classifier's H20 probability is from 0.5; PPO's policy network separately
produces a categorical action distribution every day whose entropy is a
completely different kind of uncertainty signal (how spread out the RL
policy's preference is across its discrete weight-allocation choices), never
computed or logged anywhere in this codebase before.

METHOD: loads the REAL production PPO checkpoint (models/portfolio/last_ppo_
group_a_100k.zip) read-only (inference only, no training, no checkpoint
write) and replays it day-by-day over the same date range NCF's h20/
confidence panel covers (2025-01-02 onward), reusing PortfolioEnv/
_align_panel/load_stock_data_db_first/GROUP_A_PROFILE_PRESETS from
train_dual_group_2024_2026.py unmodified (same harness already used for this
session's other PPO experiments). At each step, before taking the
deterministic action (matching production inference behavior exactly),
extracts the categorical action distribution's Shannon entropy via
model.policy.get_distribution(obs).distribution.entropy() -- SB3's standard
policy-distribution API, read-only, never used in this codebase before.

Then joins the resulting entropy series (by date) against results/ncf_00631l_
panel_latest_20260716.csv's confidence/prob_up_h20 columns and reports:
  1. correlation between PPO entropy and NCF confidence (low correlation
     would support these being independent uncertainty signals);
  2. whether PPO entropy predicts NCF's own forward forecast error
     (|h20_prob_up - realized_direction|) better, worse, or independently of
     what NCF confidence already predicts (confidence should already be
     inversely correlated with error by construction/calibration -- the
     question is whether entropy adds anything on top).

Research-only diagnostic. No production code touched, no weights changed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import torch
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (  # noqa: E402
    DEFAULT_GROUP_A_TICKERS,
    GROUP_A_PROFILE_PRESETS,
    PortfolioEnv,
    _align_panel,
    load_stock_data_db_first,
)
from generate_dual_group_signal import _adapt_obs_for_model  # noqa: E402

PRODUCTION_MODEL_PATH = PROJECT_ROOT / "models" / "portfolio" / "last_ppo_group_a_100k.zip"
DATA_START = "2020-01-01"
BACKTEST_START = "2025-01-02"
BACKTEST_END = "2026-07-16"  # matches the pinned NCF panel's coverage end
INITIAL_CASH = 1_000_000.0
NCF_PANEL_PATH = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260716.csv"
OUTPUT_CSV = PROJECT_ROOT / "results" / "ppo_entropy_vs_ncf_confidence_20260823.csv"
OUTPUT_JSON = PROJECT_ROOT / "results" / "ppo_entropy_vs_ncf_confidence_20260823.json"


def replay_and_extract_entropy() -> pd.DataFrame:
    tickers = DEFAULT_GROUP_A_TICKERS
    profile = GROUP_A_PROFILE_PRESETS["default"]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = None

    print(f"Loading Group A stock data ({tickers})...")
    stock_data = load_stock_data_db_first(tickers, DATA_START, BACKTEST_END)
    panel = _align_panel(stock_data, tickers, BACKTEST_START, BACKTEST_END, shared_feature_cols=None)
    print(f"Backtest panel: {panel['date'].min().date()} ~ {panel['date'].max().date()} ({len(panel)} rows)")

    print(f"Loading production PPO checkpoint (read-only, inference only): {PRODUCTION_MODEL_PATH}")
    model = PPO.load(str(PRODUCTION_MODEL_PATH))

    env = PortfolioEnv(panel, tickers, shared_feature_cols=None, initial_cash=INITIAL_CASH, **env_kwargs)
    obs, _ = env.reset()
    done = False
    records = []
    while not done:
        date_str = env.date_strings[env.step_idx]
        adapted_obs = _adapt_obs_for_model(obs, model)
        obs_tensor, _ = model.policy.obs_to_tensor(adapted_obs)
        with torch.no_grad():
            distribution = model.policy.get_distribution(obs_tensor)
            entropy = float(distribution.distribution.entropy().item())
            probs = distribution.distribution.probs.squeeze(0).cpu().numpy().tolist()
        action, _ = model.predict(adapted_obs, deterministic=True)
        records.append({"date": date_str, "ppo_entropy": entropy, "ppo_action": int(action), "ppo_action_probs": probs})
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated

    return pd.DataFrame(records)


def main() -> None:
    entropy_df = replay_and_extract_entropy()
    entropy_df["date"] = pd.to_datetime(entropy_df["date"]).dt.strftime("%Y-%m-%d")
    entropy_df = entropy_df.set_index("date")

    ncf = pd.read_csv(NCF_PANEL_PATH, encoding="utf-8-sig")
    ncf["date"] = pd.to_datetime(ncf["date"]).dt.strftime("%Y-%m-%d")
    ncf = ncf.set_index("date")

    # ncf_00631l.py's panel has no "actual_up_h20" column directly -- derive
    # the realized forward-20-trading-day direction from DB close prices,
    # same convention used elsewhere this session (round-2 direction #3).
    con = duckdb.connect(str(PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"), read_only=True)
    px = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = '00631L.TW' ORDER BY dt").fetchdf()
    con.close()
    px["dt"] = pd.to_datetime(px["dt"])
    close = px.set_index("dt")["close"].astype(float)
    fwd20_return = close.shift(-20) / close - 1.0
    actual_up_h20 = (fwd20_return > 0).astype(float)
    actual_up_h20.index = actual_up_h20.index.strftime("%Y-%m-%d")

    combined = entropy_df.join(ncf[["prob_up_h20", "confidence"]], how="inner")
    combined = combined.dropna(subset=["ppo_entropy", "confidence"])
    combined["actual_up_h20"] = actual_up_h20.reindex(combined.index)
    print(f"\nJoined rows: {len(combined)}")

    corr_pearson = combined["ppo_entropy"].corr(combined["confidence"])
    corr_spearman = combined["ppo_entropy"].corr(combined["confidence"], method="spearman")
    print(f"Pearson corr(ppo_entropy, ncf_confidence): {corr_pearson:.4f}")
    print(f"Spearman corr(ppo_entropy, ncf_confidence): {corr_spearman:.4f}")

    resolved = combined.dropna(subset=["actual_up_h20"]).copy()
    if len(resolved) >= 20:
        resolved["ncf_error"] = (resolved["prob_up_h20"] - resolved["actual_up_h20"]).abs()
        corr_entropy_error = resolved["ppo_entropy"].corr(resolved["ncf_error"])
        corr_confidence_error = resolved["confidence"].corr(resolved["ncf_error"])
        print(f"\nResolved rows: {len(resolved)}")
        print(f"corr(ppo_entropy, ncf_h20_error): {corr_entropy_error:.4f}")
        print(f"corr(ncf_confidence, ncf_h20_error): {corr_confidence_error:.4f}  (expect negative if confidence is well-calibrated)")

        # partial correlation: does entropy explain error variance beyond confidence?
        import numpy as _np

        x = resolved[["confidence"]].to_numpy()
        x = _np.column_stack([_np.ones(len(x)), x])
        y = resolved["ncf_error"].to_numpy()
        beta, *_ = _np.linalg.lstsq(x, y, rcond=None)
        residual_error = y - x @ beta
        corr_entropy_residual_error = float(_np.corrcoef(resolved["ppo_entropy"].to_numpy(), residual_error)[0, 1])
        print(f"corr(ppo_entropy, ncf_h20_error residual after removing confidence's linear effect): {corr_entropy_residual_error:.4f}")
    else:
        corr_entropy_error = None
        corr_confidence_error = None
        corr_entropy_residual_error = None
        print("\nInsufficient resolved rows for forecast-error analysis")

    combined.drop(columns=["ppo_action_probs"]).to_csv(OUTPUT_CSV, encoding="utf-8-sig")
    import json

    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "n_joined": int(len(combined)),
                "n_resolved": int(len(resolved)) if len(resolved) >= 20 else None,
                "corr_pearson_entropy_confidence": float(corr_pearson),
                "corr_spearman_entropy_confidence": float(corr_spearman),
                "corr_entropy_ncf_error": corr_entropy_error,
                "corr_confidence_ncf_error": corr_confidence_error,
                "corr_entropy_residual_error_after_confidence": corr_entropy_residual_error,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {OUTPUT_CSV}\nSaved: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
