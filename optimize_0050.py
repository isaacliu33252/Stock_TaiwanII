"""
0050.TW 超參數網格搜索 - 即時回報版
每組實驗做完立即通知結果
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_data_loader import download_all_stocks
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from environments.reward_function_v2 import RewardFunction
from stable_baselines3 import PPO

TICKER = "0050.TW"
INITIAL_BALANCE = 1_000_000
TRAIN_STEPS = 100_000
TELEGRAM_TOKEN = "8713079660:***"  # masked
CHAT_ID = "8605791933"

def _notify(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass

# ── 超參數組合 ──────────────────────────────────────────
PPO_CONFIGS = [
    {"lr": 1e-4,  "n_steps": 2048, "batch": 64,  "epochs": 10, "gamma": 0.99, "clip": 0.2},
    {"lr": 3e-4,  "n_steps": 2048, "batch": 64,  "epochs": 10, "gamma": 0.99, "clip": 0.2},
    {"lr": 5e-4,  "n_steps": 2048, "batch": 64,  "epochs": 10, "gamma": 0.99, "clip": 0.2},
    {"lr": 3e-4,  "n_steps": 4096, "batch": 128, "epochs": 5,  "gamma": 0.99, "clip": 0.2},
    {"lr": 1e-4,  "n_steps": 1024, "batch": 32,  "epochs": 20, "gamma": 0.95, "clip": 0.1},
]

REWARD_CONFIGS = [
    {"trade": 0.0,   "hold": 0.1, "dd": 0.5, "sortino": 0.2,  "calmar": 0.15, "vol": 0.1},
    {"trade": 0.001, "hold": 0.2, "dd": 0.8, "sortino": 0.3,  "calmar": 0.2,  "vol": 0.2},
    {"trade": 0.005, "hold": 0.05,"dd": 1.0, "sortino": 0.5,  "calmar": 0.3,  "vol": 0.3},
    {"trade": 0.0,   "hold": 0.3, "dd": 0.3, "sortino": 0.1,  "calmar": 0.05, "vol": 0.0},
]

TOTAL_RUNS = len(PPO_CONFIGS) * len(REWARD_CONFIGS)

def make_env(df, reward_func):
    return TaiwanStockTradingEnv(
        df=df, initial_balance=INITIAL_BALANCE,
        max_position=4000, trade_unit=1000, price_limit=0.10,
        commission_rate=0.001425, tax_rate=0.003,
        lookback_window=60, reward_func=reward_func,
    )

def evaluate_sharpe(env, model):
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs)
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    pv = np.array(env.portfolio_value_history)
    returns = np.diff(pv) / pv[:-1]
    returns = returns[~np.isnan(returns) & ~np.isinf(returns)]
    if len(returns) < 2 or np.std(returns, ddof=1) == 0:
        return -999.0
    return round(float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252)), 3)  # Sample std

def run_experiment(ppo_cfg, reward_cfg, df_train, df_test, run_id):
    reward_func = RewardFunction(
        trade_penalty=reward_cfg["trade"],
        holding_bonus=reward_cfg["hold"],
        drawdown_penalty=reward_cfg["dd"],
        sortino_weight=reward_cfg["sortino"],
        calmar_weight=reward_cfg["calmar"],
        volatility_penalty=reward_cfg["vol"],
    )
    env = make_env(df_train, reward_func)
    model = PPO(
        "MlpPolicy", env,
        learning_rate=ppo_cfg["lr"], n_steps=ppo_cfg["n_steps"],
        batch_size=ppo_cfg["batch"], n_epochs=ppo_cfg["epochs"],
        gamma=ppo_cfg["gamma"], clip_range=ppo_cfg["clip"],
        verbose=0,
    )
    model.learn(total_timesteps=TRAIN_STEPS, progress_bar=False)
    eval_env = make_env(df_test, reward_func)
    sharpe = evaluate_sharpe(eval_env, model)
    pv = np.array(env.portfolio_value_history)
    final_value = round(float(pv[-1]), 2) if len(pv) > 0 else 0.0
    trades = len(env.trade_history)
    result = {
        "run_id": run_id, "ppo": ppo_cfg, "reward": reward_cfg,
        "sharpe": sharpe, "train_final_value": final_value,
        "num_trades": trades,
    }
    model_dir = PROJECT_ROOT / "FinRL" / "models" / "portfolio" / "optimize"
    os.makedirs(model_dir, exist_ok=True)
    model.save(str(model_dir / f"run_{run_id:03d}"))
    return result

def main():
    print(f"\n{'='*60}")
    print(f"0050.TW 超參數網格搜索 ({TOTAL_RUNS} 組)")
    print(f"{'='*60}\n")

    _notify(f"🔍 0050 網格搜索啟動\n{TOTAL_RUNS} 組實驗，預計 {(TOTAL_RUNS*4)//60} 小時左右")

    from datetime import timedelta
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    stock_data = download_all_stocks([TICKER], start_date, end_date)
    df = stock_data[TICKER]
    split = int(len(df) * 0.8)
    df_train = df.iloc[:split].copy()
    df_test  = df.iloc[split:].copy()
    print(f"訓練: {len(df_train)} 筆 | 測試: {len(df_test)} 筆\n")

    all_results = []
    run_id = 0
    best_sharpe = -999.0
    best_result = None

    for pi, ppo_cfg in enumerate(PPO_CONFIGS):
        for ri, reward_cfg in enumerate(REWARD_CONFIGS):
            run_id += 1
            print(f"[{run_id}/{TOTAL_RUNS}] PPO[{pi}] Reward[{ri}]...", end=" ", flush=True)
            try:
                result = run_experiment(ppo_cfg, reward_cfg, df_train, df_test, run_id)
                all_results.append(result)
                ppo_desc = f"lr={ppo_cfg['lr']} n={ppo_cfg['n_steps']} b={ppo_cfg['batch']} e={ppo_cfg['epochs']}"
                rew_desc = f"trade={reward_cfg['trade']} hold={reward_cfg['hold']} dd={reward_cfg['dd']}"
                msg = (f"✅ [{run_id}/{TOTAL_RUNS}] Sharpe={result['sharpe']:.3f} | "
                       f"Value=${result['train_final_value']:,.0f} | Trades={result['num_trades']}\n"
                       f"PPO: {ppo_desc}\n"
                       f"Reward: {rew_desc}")
                print(f"Sharpe={result['sharpe']:.3f} Value=${result['train_final_value']:,.0f} Trades={result['num_trades']}")
            except Exception as e:
                print(f"❌ {e}")
                msg = f"❌ [{run_id}/{TOTAL_RUNS}] 失敗: {e}"
                all_results.append({"run_id": run_id, "error": str(e)})

            _notify(msg)

            if result.get("sharpe", -999) > best_sharpe:
                best_sharpe = result.get("sharpe", -999)
                best_result = result

    all_results.sort(key=lambda x: x.get("sharpe", -999), reverse=True)

    print(f"\n{'='*60}")
    print("TOP 5 結果")
    print(f"{'='*60}")
    for i, r in enumerate(all_results[:5], 1):
        print(f"\n#{i} Sharpe={r.get('sharpe','?')} | Value=${r.get('train_final_value',0):,.0f}")
        print(f"   PPO: lr={r['ppo']['lr']}, n_steps={r['ppo']['n_steps']}, batch={r['ppo']['batch']}")
        print(f"   Reward: trade={r['reward']['trade']}, hold={r['reward']['hold']}, dd={r['reward']['dd']}")

    out_file = PROJECT_ROOT / "results" / f"optimize_0050_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.parent.mkdir(exist_ok=True)
    with open(out_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n結果已儲存: {out_file}")

    best = all_results[0]
    _notify(f"🏆 0050 網格搜索完成！\n最佳 Sharpe={best.get('sharpe','?')}\nModel: run_{best['run_id']:03d}")

if __name__ == "__main__":
    main()
