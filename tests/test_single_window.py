#!/usr/bin/env python3
"""快速測試：訓練一個視窗並回測，確認 reward function 是否正確"""
import glob
import importlib.util
import json
import os
import subprocess
import sys
import time

import pyarrow.parquet as pq


def main() -> None:
    sys.path.insert(0, "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main")
    os.chdir("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")

    cache = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/data/cache/0050_2016-01-01_2026-05-05_1d.parquet"
    finrl = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL"
    out = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/FinRL/models/portfolio/test_reward"

    df = pq.read_table(cache).to_pandas(timestamp_as_object=True)
    spec = importlib.util.spec_from_file_location("ta", finrl + "/data/technical_analysis.py")
    tm = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(tm)
    df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)
    df_ta["ds"] = df_ta["date"].astype(str)

    df_train = df_ta[(df_ta["ds"] >= "2023-03-20") & (df_ta["ds"] <= "2024-10-08")].copy()
    df_test = df_ta[(df_ta["ds"] >= "2024-10-08") & (df_ta["ds"] <= "2025-01-08")].copy()
    print(f"Train: {len(df_train)} rows  {df_train['ds'].iloc[0]}~{df_train['ds'].iloc[-1]}")
    print(f"Test:  {len(df_test)} rows   {df_test['ds'].iloc[0]}~{df_test['ds'].iloc[-1]}")

    df_train.to_parquet(finrl + "/data/cache/wf_train.parquet", index=False)

    from portfolio_train_v2 import EnhancedStockTrainer

    print("\n開始訓練...")
    t0 = time.time()
    trainer = EnhancedStockTrainer(
        "0050",
        df_train,
        "ppo",
        enable_risk_manager=True,
        enable_enhanced_reward=True,
    )
    print(
        f"Reward params: dd={trainer.reward_func.drawdown_penalty}, "
        f"hold={trainer.reward_func.holding_bonus}, trade={trainer.reward_func.trade_reward}"
    )
    os.makedirs(out, exist_ok=True)
    trainer.train(timesteps=30_000, save_path=out, verbose=0)
    print(f"訓練完成 ({time.time() - t0:.0f}s)")

    parent = os.path.dirname(out.rstrip("/"))
    zips = sorted([f for f in os.listdir(parent) if f.endswith(".zip") and "test_reward" in f])
    if not zips:
        zips = sorted([f for f in os.listdir(out) if f.endswith(".zip")])
    if not zips:
        print("沒有 zip")
        sys.exit(1)
    model_path = parent + "/" + zips[-1]
    print(f"Model: {zips[-1]} ({os.path.getsize(model_path) // 1024}KB)")

    old_results = sorted(glob.glob(finrl + "/results/backtest_0050_ppo_*.json"), key=os.path.getmtime)
    for path in old_results[-5:]:
        os.remove(path)

    print("\n開始回測...")
    result = subprocess.run(
        [
            "python3",
            "run_backtest.py",
            "--agent",
            "ppo",
            "--stock",
            "0050",
            "--start",
            "2024-10-08",
            "--end",
            "2025-01-08",
            "--model",
            model_path,
            "--initial_balance",
            "1000000",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=finrl,
    )
    print("stdout:", result.stdout[-300:] if result.stdout else "")
    print("stderr:", result.stderr[-300:] if result.stderr else "")

    results = sorted(glob.glob(finrl + "/results/backtest_0050_ppo_*.json"), key=os.path.getmtime)
    if results:
        with open(results[-1]) as f:
            bt = json.load(f)
        metrics = bt["metrics"]
        print("\n=== 結果 ===")
        print(f"報酬: {metrics['total_return'] * 100:.2f}%")
        print(f"Sharpe: {metrics['sharpe_ratio']:.3f}")
        print(f"MDD: {metrics['max_drawdown'] * 100:.2f}%")
        print(f"交易: {metrics['total_trades']}")


if __name__ == "__main__":
    main()
