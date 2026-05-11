"""
Agent 超參數配置 (Hyperparameters Configuration)
================================================================================
定義 PPO 和 A2C 代理模型的超參數設定。

選擇依據:
    - 這些參數是針對金融時間序列任務調整過的
    - 參考 FinRL 官方建議和學術論文中的最佳實踐
    - 平衡訓練穩定性和樣本效率

PPO (Proximal Policy Optimization) 參數說明:
    - n_steps: 每次更新前收集的樣本數 (越大越穩定但越慢)
    - batch_size: 每次梯度更新的樣本數
    - n_epochs: 每次更新對同一批數據進行的epoch數
    - gamma: 折扣因子 (越接近1越重視長期報酬)
    - gae_lambda: GAE 參數 (影響 advantage 估計的方差/偏差權衡)
    - clip_range: PPO clipping 範圍 (控制策略更新幅度)
    - learning_rate: 學習率 (太小收斂慢，太大訓練不穩定)
    - ent_coef: 熵係數 (鼓勵探索，防止過早收斂)
"""

from typing import Dict, Any

# ================================================================================
# PPO (Proximal Policy Optimization) 超參數配置
# ================================================================================
# PPO 是本系統的首選 Agent，適合離散動作空間的金融交易任務
# 
# 優點:
#   1. 訓練穩定 - Clipping 機制防止策略更新過大
#   2. 樣本效率高 - 多次利用收集到的數據進行更新
#   3. 離散動作支援好 - 適合買入/賣出/持有的簡單動作空間
#
PPO_CONFIG: Dict[str, Any] = {
    # --- 策略網路 ---
    'policy': 'MlpPolicy',                  # 多層感知機策略網路
    'net_arch': [256, 256],                # 網路架構: 兩層 256 隱藏單元
    
    # --- 採樣設定 ---
    'n_steps': 2048,                        # 每次更新前收集 2048 個樣本
    'batch_size': 64,                      # 每批 64 樣本進行梯度更新
    
    # --- PPO 特定參數 ---
    'n_epochs': 10,                        # 每次更新對數據進行 10 個 epoch
    'gamma': 0.99,                         # 折扣因子: 0.99 (重視長期報酬)
    'gae_lambda': 0.95,                    # GAE lambda: 0.95 (平衡方差/偏差)
    'clip_range': 0.2,                     # Clipping 範圍: 0.2 (限制策略更新幅度)
    
    # --- 學習率 ---
    'learning_rate': 3e-4,                 # 學習率: 0.0003 (Adam 預設值附近)
    'lr_schedule': 'linear',              # 學習率衰減: linear (逐漸降低)
    
    # --- 探索與利用 ---
    'ent_coef': 0.01,                      # 熵係數: 0.01 (鼓勵適度探索)
    'clip_range_vf': None,                 # Value Function Clipping: None (使用 relative)
    
    # --- 正則化 ---
    'max_grad_norm': 0.5,                  # 梯度裁剪: 0.5 (防止梯度爆炸)
    'rmsprop_eps': 1e-5,                   # RMSprop epsilon: 1e-5 (數值穩定性)
    
    # --- 訓練設定 ---
    'total_timesteps': 100_000,            # 總訓練步數
    'eval_freq': 5000,                    # 每 5000 步評估一次
    'log_interval': 10,                   # 每 10 個 episode 記錄一次日誌
    
    # --- 早期停止 ---
    'patience': 20,                        # 早停耐心值: 20 次評估無改善則停止
    
    # --- 環境相關 ---
    'env_reward_scale': 1.0,               # 獎勵縮放因子
}

# ================================================================================
# A2C (Advantage Actor-Critic) 超參數配置
# ================================================================================
# A2C 是 PPO 的簡單版本，用作 Baseline 和驗證對比
#
# 優點:
#   1. 簡單快速 - 同步更新，不需要複雜的緩衝區管理
#   2. 記憶體效率 - 不需要保存完整的 rollout 緩衝區
#   3. 容易調試 - 架構簡單，問題容易定位
#
# 缺點:
#   1. 訓練可能不穩定 - 同步更新可能导致策略震盪
#   2. 樣本效率可能較低 - 每次更新只使用一次數據
#
A2C_CONFIG: Dict[str, Any] = {
    # --- 策略網路 ---
    'policy': 'MlpPolicy',                  # 多層感知機策略網路
    'net_arch': [256, 256],                # 網路架構: 兩層 256 隱藏單元
    
    # --- 採樣設定 ---
    'n_steps': 5,                          # 每個 worker 每次更新前收集 5 步 (A2C 同步)
    
    # --- A2C 特定參數 ---
    'gamma': 0.99,                         # 折扣因子: 0.99
    'gae_lambda': 1.0,                     # GAE lambda: 1.0 (等於 TD(1)，無偏差但高方差)
    
    # --- 學習率 ---
    'learning_rate': 3e-4,                 # 學習率: 0.0003
    
    # --- 探索與利用 ---
    'ent_coef': 0.1,                       # 熵係數: 0.1 (比 PPO 更高，鼓勵更多探索)
    
    # --- 優勢估計 ---
    'use_rmsprop': True,                   # 使用 RMSprop 優化器
    'rmsprop_eps': 1e-5,                   # RMSprop epsilon
    
    # --- 正則化 ---
    'max_grad_norm': 0.5,                  # 梯度裁剪: 0.5
    
    # --- 訓練設定 ---
    'total_timesteps': 100_000,            # 總訓練步數
    'eval_freq': 5000,                     # 每 5000 步評估一次
    'log_interval': 10,                   # 每 10 個 episode 記錄一次日誌
    
    # --- 早期停止 ---
    'patience': 20,                        # 早停耐心值: 20 次
    
    # --- 環境相關 ---
    'env_reward_scale': 1.0,               # 獎勵縮放因子
}

# ================================================================================
# 共享的超參數 (兩個 Agent 都使用)
# ================================================================================
SHARED_CONFIG: Dict[str, Any] = {
    # --- 環境設定 ---
    'lookback_window': 60,                 # 回看窗口: 60 天 (用於計算技術指標)
    'initial_balance': 1_000_000,         # 初始資金: 100 萬 TWD
    
    # --- 風險管理 ---
    'stop_loss': 0.10,                     # 停損門檻: 10%
    'take_profit': 0.20,                   # 停利門檻: 20%
    
    # --- 評估設定 ---
    'n_eval_episodes': 10,                 # 評估時執行的 episode 數
    'deterministic': True,                 # 評估時使用確定性策略 (不吃灰)
}

# ================================================================================
# 訓練流程配置
# ================================================================================
TRAINING_CONFIG = {
    # --- 訓練模式 ---
    'mode': 'train',                       # train / eval / continue
    
    # --- 模型儲存 ---
    'save_freq': 10000,                    # 每 10000 步儲存一次模型
    'checkpoint_dir': './results/models',  # 模型儲存目錄
    
    # --- 日誌設定 ---
    'log_dir': './results/logs',           # 日誌目錄
    'tensorboard_log_dir': './results/logs/tensorboard',
    
    # --- 驗證設定 ---
    'validate_during_training': True,      # 訓練時同時驗證
    'eval_during_training': True,          # 訓練時同時評估
    
    # --- 設備設定 ---
    'device': 'auto',                      # auto / cpu / cuda (自動選擇 GPU 若可用)
}

# ================================================================================
# 模型評估配置
# ================================================================================
EVALUATION_CONFIG = {
    # --- 評估設定 ---
    'deterministic': True,                 # 使用確定性策略 (不添加隨機性)
    'render': False,                       # 是否渲染環境 (False 以加快速度)
    'n_eval_episodes': 10,                 # 評估 episode 數
    
    # --- 回測設定 ---
    'backtest_start_date': '2000-01-01',   # 回測開始日期
    'backtest_end_date': '2010-12-31',    # 回測結束日期
    
    # --- Benchmark ---
    'benchmark': '0050.TW',                # Benchmark ETF
}
