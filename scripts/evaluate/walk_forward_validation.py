#!/usr/bin/env python3
"""Walk-Forward 驗證：3個 training 期 × 同一 test 期（2025-06-01~2026-05-20）
公平比較不同訓練期長度的真實 out-of-sample 表現。

WF-A: 2020-01-02~2024-12-31 (5年)  → test 2025-06~2026-05
WF-B: 2021-01-01~2024-12-31 (4年)  → test 2025-06~2026-05
WF-C: 2022-01-01~2025-05-31 (3.3年) → test 2025-06~2026-05

用法：python3 walk_forward_validation.py
"""
import sys, json, subprocess
from pathlib import Path

PROJECT = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main")
WF_CONFIGS = [
    {
        "name": "WF-A_5yr_2020-2024",
        "train_start": "2020-01-02",
        "train_end": "2024-12-31",
        "test_start": "2025-06-01",
        "test_end": "2026-05-20",
        "model_name": "group_a_wf_a",
    },
    {
        "name": "WF-B_4yr_2021-2024",
        "train_start": "2021-01-01",
        "train_end": "2024-12-31",
        "test_start": "2025-06-01",
        "test_end": "2026-05-20",
        "model_name": "group_a_wf_b",
    },
    {
        "name": "WF-C_3.3yr_2022-2025",
        "train_start": "2022-01-01",
        "train_end": "2025-05-31",
        "test_start": "2025-06-01",
        "test_end": "2026-05-20",
        "model_name": "group_a_wf_c",
    },
]

def run_wf(cfg):
    """訓練並回測單一 WF window。"""
    import pandas as pd, numpy as np
    sys.path.insert(0, str(PROJECT))
    from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE, TRANSACTION_TAX_RATE
    from train_segments import (
        PortfolioEnv, FEATURE_COLUMNS, load_stock_data, _align_panel,
        calculate_backtest_metrics, INITIAL_CASH
    )
    from stable_baselines3 import PPO

    print(f"\n{'='*60}")
    print(f"  {cfg['name']}")
    print(f"{'='*60}")

    # ── 1. 訓練 ──────────────────────────────────────────────
    tickers = ["0050.TW", "00631L.TW", "00632R.TW"]
    train_data = load_stock_data(tickers, cfg["train_start"], cfg["train_end"])
    panel = _align_panel(train_data, tickers, cfg["train_start"], cfg["train_end"],
                         feature_columns=FEATURE_COLUMNS)
    print(f"Training panel: {len(panel)} rows, "
          f"{panel['date'].min().date()} ~ {panel['date'].max().date()}")

    env = PortfolioEnv(panel, tickers, feature_columns=FEATURE_COLUMNS,
                       initial_cash=INITIAL_CASH, commission_rate=COMMISSION_RATE)
    model = PPO("MlpPolicy", env, verbose=0, n_steps=2048, batch_size=64,
                learning_rate=3e-4, gamma=0.99, clip_range=0.2,
                ent_coef=0.01, max_grad_norm=0.5, seed=42)
    model.learn(total_timesteps=20_000, progress_bar=False)
    model_path = PROJECT / "models" / "portfolio" / f"{cfg['model_name']}.zip"
    model.save(str(model_path))
    print(f"Model saved: {model_path.name}")

    # ── 2. 回測 ───────────────────────────────────────────────
    test_data = load_stock_data(tickers, cfg["test_start"], cfg["test_end"])
    test_panel = _align_panel(test_data, tickers, cfg["test_start"], cfg["test_end"],
                              feature_columns=FEATURE_COLUMNS)
    print(f"Test panel: {len(test_panel)} rows, "
          f"{test_panel['date'].min().date()} ~ {test_panel['date'].max().date()}")

    test_env = PortfolioEnv(test_panel, tickers, feature_columns=FEATURE_COLUMNS,
                            initial_cash=INITIAL_CASH, commission_rate=COMMISSION_RATE)
    test_env.reset()
    done = False
    equity = [INITIAL_CASH]
    while not done:
        action, _ = model.predict(test_env._get_obs(), deterministic=True)
        _, reward, terminated, truncated, _ = test_env.step(int(action))
        done = terminated or truncated
        equity.append(test_env._portfolio_value(test_env.price_array[test_env.step_idx]))
    equity = equity[:-1]

    metrics = calculate_backtest_metrics(equity)
    print(f"\n  Final Value: {equity[-1]:,.0f}")
    print(f"  Sharpe:      {metrics['sharpe']:.4f}")
    print(f"  Max DD:      {metrics['max_drawdown']*100:.2f}%")
    print(f"  Vol:         {metrics['volatility']*100:.2f}%")
    print(f"  Train rows:  {len(panel)}, Test rows: {len(test_panel)}")

    return {
        "name": cfg["name"],
        "train_start": cfg["train_start"],
        "train_end": cfg["train_end"],
        "train_rows": len(panel),
        "test_rows": len(test_panel),
        "final_value": equity[-1],
        "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"],
        "volatility": metrics["volatility"],
        "total_return": metrics["total_return"],
    }

if __name__ == "__main__":
    results = []
    for cfg in WF_CONFIGS:
        r = run_wf(cfg)
        results.append(r)

    print(f"\n{'='*60}")
    print("  Walk-Forward Summary（同一 test 期: 2025-06-01~2026-05-20）")
    print(f"{'='*60}")
    print(f"{'Name':<25} {'Train':>8} {'Final':>12} {'Sharpe':>8} {'MDD':>8} {'Vol':>8}")
    print("-"*75)
    for r in results:
        print(f"{r['name']:<25} {r['train_rows']:>8,} "
              f"{r['final_value']:>12,.0f} {r['sharpe']:>8.4f} "
              f"{r['max_drawdown']*100:>7.2f}% {r['volatility']*100:>7.2f}%")

    # 寫入結果
    out_path = PROJECT / "results" / "walk_forward_comparison.json"
    with open(out_path, "w") as f:
        json.dump({"windows": WF_CONFIGS, "results": results}, f, indent=2, default=str)
    print(f"\n結果寫入: {out_path}")
