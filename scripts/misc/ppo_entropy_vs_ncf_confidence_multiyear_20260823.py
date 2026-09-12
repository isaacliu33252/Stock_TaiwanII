#!/usr/bin/env python3
"""Fable 00631L round-2 direction #7 follow-up (2026-08-23): multi-year OOS
check of the PPO-entropy-vs-NCF-confidence partial correlation.

The single-window version (ppo_entropy_vs_ncf_confidence_20260823.py, 2025-01
~2026-07, n=370) found a small residual correlation (-0.09) between PPO
entropy and NCF's H20 forecast error after controlling for NCF confidence --
real but too weak/single-window to trust. User asked how to strengthen this.

This reuses the already-existing NCF backfill panels (2020/2021/2022 rate-
hike/2023/2024, from round-1/round-2 direction #3's investigation -- no new
ML training) to extend the same PPO-entropy replay across 2020-2026 (~2100+
trading days spanning 6 independent-ish calendar years, vs the single 1.5-
year window), reusing the real production PPO checkpoint for read-only
inference exactly as the single-window version does. Reports the partial
correlation (PPO entropy vs NCF H20 error, controlling for NCF confidence)
computed PER YEAR SEPARATELY as well as pooled, to check whether the small
residual effect is a consistent, same-signed signal across independent years
or noise that varies with window (the same OOS discipline used elsewhere
this session, e.g. GROUP_A_PLUS_20260810_2301_03186... pseudo-replication
lesson).

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
DATA_START = "2019-06-01"
BACKTEST_START = "2020-01-02"
BACKTEST_END = "2026-07-16"
INITIAL_CASH = 1_000_000.0
OUTPUT_CSV = PROJECT_ROOT / "results" / "ppo_entropy_vs_ncf_confidence_multiyear_20260823.csv"
OUTPUT_JSON = PROJECT_ROOT / "results" / "ppo_entropy_vs_ncf_confidence_multiyear_20260823.json"

NCF_PANELS = {
    "2020": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2020_20260716.csv",
    "2021": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2021_20260726.csv",
    "2022": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
    "2023": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2023_20260726.csv",
    "2024": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2024_20260726.csv",
    "2025_2026": PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260716.csv",
}


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
        action, _ = model.predict(adapted_obs, deterministic=True)
        records.append({"date": date_str, "ppo_entropy": entropy})
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
        if len(records) % 250 == 0:
            print(f"  ...replayed {len(records)} days ({date_str})")

    return pd.DataFrame(records)


def load_ncf_panels() -> pd.DataFrame:
    frames = []
    for label, path in NCF_PANELS.items():
        ncf = pd.read_csv(path, encoding="utf-8-sig")
        ncf["date"] = pd.to_datetime(ncf["date"]).dt.strftime("%Y-%m-%d")
        ncf = ncf.set_index("date")[["prob_up_h20", "confidence"]].dropna()
        ncf["source_panel"] = label
        frames.append(ncf)
    combined = pd.concat(frames).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def partial_corr(entropy: np.ndarray, confidence: np.ndarray, error: np.ndarray) -> float:
    x = np.column_stack([np.ones(len(confidence)), confidence])
    beta, *_ = np.linalg.lstsq(x, error, rcond=None)
    residual_error = error - x @ beta
    if np.std(entropy) < 1e-9 or np.std(residual_error) < 1e-9:
        return float("nan")
    return float(np.corrcoef(entropy, residual_error)[0, 1])


def main() -> None:
    entropy_df = replay_and_extract_entropy()
    entropy_df["date"] = pd.to_datetime(entropy_df["date"]).dt.strftime("%Y-%m-%d")
    entropy_df = entropy_df.set_index("date")

    ncf = load_ncf_panels()

    con = duckdb.connect(str(PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"), read_only=True)
    px = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = '00631L.TW' ORDER BY dt").fetchdf()
    con.close()
    px["dt"] = pd.to_datetime(px["dt"])
    close = px.set_index("dt")["close"].astype(float)
    fwd20_return = close.shift(-20) / close - 1.0
    actual_up_h20 = (fwd20_return > 0).astype(float)
    actual_up_h20.index = actual_up_h20.index.strftime("%Y-%m-%d")

    combined = entropy_df.join(ncf, how="inner")
    combined["actual_up_h20"] = actual_up_h20.reindex(combined.index)
    combined = combined.dropna(subset=["ppo_entropy", "confidence", "prob_up_h20", "actual_up_h20"])
    combined["ncf_error"] = (combined["prob_up_h20"] - combined["actual_up_h20"]).abs()
    combined["year"] = pd.to_datetime(combined.index).year
    print(f"\nTotal joined+resolved rows: {len(combined)}")
    print(combined.groupby("source_panel").size())

    results = {}
    print("\n=== Per-year partial correlation (ppo_entropy vs ncf_error, controlling for confidence) ===")
    for year, group in combined.groupby("year"):
        if len(group) < 20:
            print(f"  {year}: n={len(group)} (too small, skipped)")
            continue
        pc = partial_corr(group["ppo_entropy"].to_numpy(), group["confidence"].to_numpy(), group["ncf_error"].to_numpy())
        raw_corr = group["ppo_entropy"].corr(group["ncf_error"])
        conf_ppo_corr = group["ppo_entropy"].corr(group["confidence"])
        print(f"  {year}: n={len(group)}  raw_corr(entropy,error)={raw_corr:+.4f}  "
              f"corr(entropy,confidence)={conf_ppo_corr:+.4f}  partial_corr={pc:+.4f}")
        results[str(year)] = {
            "n": int(len(group)),
            "raw_corr_entropy_error": float(raw_corr),
            "corr_entropy_confidence": float(conf_ppo_corr),
            "partial_corr_entropy_error_given_confidence": pc,
        }

    pooled_pc = partial_corr(
        combined["ppo_entropy"].to_numpy(), combined["confidence"].to_numpy(), combined["ncf_error"].to_numpy()
    )
    pooled_raw = combined["ppo_entropy"].corr(combined["ncf_error"])
    pooled_conf_corr = combined["ppo_entropy"].corr(combined["confidence"])
    print(f"\nPooled (all years, n={len(combined)}): raw_corr={pooled_raw:+.4f}  "
          f"corr(entropy,confidence)={pooled_conf_corr:+.4f}  partial_corr={pooled_pc:+.4f}")

    n_years_same_sign_as_pooled = sum(
        1 for r in results.values()
        if not np.isnan(r["partial_corr_entropy_error_given_confidence"])
        and np.sign(r["partial_corr_entropy_error_given_confidence"]) == np.sign(pooled_pc)
    )
    print(f"\nYears with partial_corr same sign as pooled: {n_years_same_sign_as_pooled}/{len([r for r in results.values() if not np.isnan(r['partial_corr_entropy_error_given_confidence'])])}")

    combined.drop(columns=[]).to_csv(OUTPUT_CSV, encoding="utf-8-sig")
    import json

    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "n_total": int(len(combined)),
                "per_year": results,
                "pooled": {
                    "n": int(len(combined)),
                    "raw_corr_entropy_error": float(pooled_raw),
                    "corr_entropy_confidence": float(pooled_conf_corr),
                    "partial_corr_entropy_error_given_confidence": pooled_pc,
                },
                "n_years_same_sign_as_pooled": n_years_same_sign_as_pooled,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {OUTPUT_CSV}\nSaved: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
