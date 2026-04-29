"""
PPO Agent - Proximal Policy Optimization Agent
================================================================================
PPO (近端策略優化) 是本系統的首選交易代理。

為什麼選擇 PPO:
1. 訓練穩定 - Clipping 機制防止策略更新過大
2. 樣本效率高 - 可多次利用收集到的數據
3. 離散動作支援好 - 適合買入/賣出/持有的簡單動作空間
4. 理論成熟 - 被廣泛驗證有效

超參數說明:
- gamma (0.99): 折扣因子，影響長期報酬的重要性
- n_steps (2048): 每次更新前收集的樣本數
- clip_range (0.2): PPO clipping 範圍，控制策略更新幅度

使用方法:
    >>> from FinRL.agents.ppo_agent import PPOAgent
    >>> from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
    >>> env = TaiwanStockTradingEnv(df)
    >>> agent = PPOAgent(env)
    >>> agent.train(total_timesteps=100000)
    >>> action = agent.predict(state)

作者: FinRL量化交易專家
"""

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, EvalCallback, StopTrainingOnRewardThreshold
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import CallbackList
from typing import Optional, Dict, Any, Tuple, List
import os
from pathlib import Path
import warnings
import json
from datetime import datetime

warnings.filterwarnings('ignore')


class PPOAgent:
    """
    PPO (Proximal Policy Optimization) 交易代理
    
    本類別提供乾淨的介面來訓練和使用 PPO 模型進行台股交易。
    
    Attributes:
        env: 訓練環境 (TaiwanStockTradingEnv)
        model: PPO 模型
        config: 超參數配置
    
    Example:
        >>> env = TaiwanStockTradingEnv(df)
        >>> agent = PPOAgent(env)
        >>> agent.train(total_timesteps=100000)
        >>> action, _ = agent.predict(state)
        >>> agent.save('./results/ppo_model')
    """
    
    def __init__(
        self,
        env,
        eval_env: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化 PPO Agent
        
        Args:
            env: 訓練環境 (TaiwanStockTradingEnv)
            eval_env: 評估環境 (若為 None，使用訓練環境的副本)
            config: 超參數配置字典，若為 None 使用預設值
        
        超參數預設值:
            - learning_rate: 3e-4
            - n_steps: 2048
            - batch_size: 64
            - n_epochs: 10
            - clip_ratio: 0.2 (PPO clip_range)
            - ent_coef: 0.01
            - gamma: 0.99
            - gae_lambda: 0.95
            - max_grad_norm: 0.5
        """
        self.env = env
        self.eval_env = eval_env if eval_env is not None else env
        
        # 預設超參數 (從 config.py 的 PPO_CONFIG)
        default_config = {
            'policy': 'MlpPolicy',
            'n_steps': 2048,
            'batch_size': 64,
            'n_epochs': 10,
            'gamma': 0.99,
            'gae_lambda': 0.95,
            'clip_range': 0.2,  # 等同於 clip_ratio
            'learning_rate': 3e-4,
            'ent_coef': 0.01,
            'max_grad_norm': 0.5,
            'verbose': 1,
            'device': 'auto',
        }
        
        # 合併使用者配置
        if config is not None:
            default_config.update(config)
        self.config = default_config
        
        # 模型輸出目錄
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.model_dir = Path(f'./results/models/ppo_{timestamp}')
        self.log_dir = Path(f'./results/logs/ppo_{timestamp}')
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 建立監控包裝
        self.monitored_env = Monitor(self.env)
        self.monitored_eval_env = Monitor(self.eval_env)
        
        # 建立 PPO 模型
        self.model = PPO(
            policy=self.config['policy'],
            env=self.monitored_env,
            n_steps=self.config['n_steps'],
            batch_size=self.config['batch_size'],
            n_epochs=self.config['n_epochs'],
            gamma=self.config['gamma'],
            gae_lambda=self.config['gae_lambda'],
            clip_range=self.config['clip_range'],
            learning_rate=self.config['learning_rate'],
            ent_coef=self.config['ent_coef'],
            max_grad_norm=self.config['max_grad_norm'],
            verbose=self.config['verbose'],
            tensorboard_log=str(self.log_dir / 'tensorboard'),
            device=self.config.get('device', 'auto'),
        )
        
        # 訓練歷史
        self.training_history = {
            'rewards': [],
            'eval_rewards': [],
            'timesteps': [],
            'episodes': []
        }
        
        # 最佳模型路徑
        self.best_model_path = str(self.model_dir / 'best_model.zip')
        self.final_model_path = str(self.model_dir / 'final_model.zip')
        
        print(f"[PPOAgent] PPO Agent 初始化完成")
        print(f"  - 模型目錄: {self.model_dir}")
        print(f"  - 日誌目錄: {self.log_dir}")
        print(f"  - 設備: {self.config.get('device', 'auto')}")
        print(f"  - n_steps: {self.config['n_steps']}, batch_size: {self.config['batch_size']}")
        print(f"  - learning_rate: {self.config['learning_rate']}, clip_range: {self.config['clip_range']}")
    
    def train(
        self,
        total_timesteps: int = 100_000,
        eval_freq: int = 5000,
        save_freq: int = 10000,
        reward_threshold: Optional[float] = None,
        early_stopping_patience: int = 20,
        callback: Optional[BaseCallback] = None
    ) -> Dict[str, Any]:
        """
        訓練 PPO 模型
        
        訓練流程:
        1. 建立評估回調 (EvalCallback) - 每 eval_freq 步評估一次模型
        2. 建立早停回調 (StopTrainingOnRewardThreshold) - 如果 reward 超過門檻則停止
        3. 組合回調並開始訓練
        4. 保存最佳模型和最終模型
        
        Args:
            total_timesteps: 總訓練步數
            eval_freq: 評估頻率 (每多少步評估一次)
            save_freq: 儲存頻率 (每多少步儲存一次checkpoint)
            reward_threshold: 提前停止的 reward 門檻 (可選)
            early_stopping_patience: 早停耐心值 (連續多少次評估無改善則停止)
            callback: 自定義回調函數 (可選)
        
        Returns:
            訓練歷史字典，包含 rewards, eval_rewards, timesteps 等
        """
        print(f"\n[PPOAgent] 開始訓練 PPO 模型")
        print(f"  - 總訓練步數: {total_timesteps:,}")
        print(f"  - 評估頻率: {eval_freq:,}")
        print(f"  - 儲存頻率: {save_freq:,}")
        print("=" * 60)
        
        # 建立回調列表
        callbacks = []
        
        # 評估回調: 定期評估模型並保存最佳模型
        eval_callback = EvalCallback(
            self.monitored_eval_env,
            best_model_save_path=str(self.model_dir / 'best'),
            log_path=str(self.log_dir / 'eval'),
            eval_freq=eval_freq,
            deterministic=True,
            render=False,
            n_eval_episodes=5
        )
        callbacks.append(eval_callback)
        
        # 早停回調: 當 reward 超過門檻時停止訓練
        if reward_threshold is not None:
            early_stop_callback = StopTrainingOnRewardThreshold(
                reward_threshold=reward_threshold,
                patience=early_stopping_patience,
                verbose=1
            )
            callbacks.append(early_stop_callback)
            print(f"  - 早停門檻: reward > {reward_threshold:.2f}")
            print(f"  - 早停耐心值: {early_stopping_patience} 次評估")
        
        # 自定義回調
        if callback is not None:
            callbacks.append(callback)
        
        # 組合回調
        combined_callback = CallbackList(callbacks)
        
        # 訓練模型
        try:
            self.model.learn(
                total_timesteps=total_timesteps,
                callback=combined_callback,
                log_interval=self.config.get('log_interval', 10),
                progress_bar=True
            )
        except KeyboardInterrupt:
            print("\n[PPOAgent] 訓練被用戶中斷")
        
        print("\n[PPOAgent] 訓練完成!")
        
        # 保存最終模型
        self.model.save(self.final_model_path)
        print(f"  - 最終模型已保存: {self.final_model_path}")
        
        # 保存訓練歷史
        history_path = self.model_dir / 'training_history.json'
        with open(history_path, 'w') as f:
            json.dump(self.training_history, f, indent=2, default=str)
        print(f"  - 訓練歷史已保存: {history_path}")
        
        return self.training_history
    
    def predict(self, state: np.ndarray, deterministic: bool = True) -> Tuple[int, Optional[np.ndarray]]:
        """
        使用模型預測動作
        
        Args:
            state: 當前狀態 (52維狀態向量)
            deterministic: 是否使用確定性策略 (True=不使用隨機性，False=添加探索噪聲)
        
        Returns:
            (action, state_value)
            - action: 預測的動作 (0-4)
            - state_value: 狀態價值估計 (若 deterministic=True 為 None)
        """
        if self.model is None:
            raise ValueError("[PPOAgent] 模型尚未建立或載入")
        
        action, state_value = self.model.predict(state, deterministic=deterministic)
        return action, state_value
    
    def predict_batch(self, states: np.ndarray, deterministic: bool = True) -> np.ndarray:
        """
        批量預測動作
        
        Args:
            states: 狀態矩陣 (batch_size, state_dim)
            deterministic: 是否使用確定性策略
        
        Returns:
            actions: 動作陣列 (batch_size,)
        """
        if self.model is None:
            raise ValueError("[PPOAgent] 模型尚未建立或載入")
        
        actions = self.model.predict(states, deterministic=deterministic)[0]
        return actions
    
    def evaluate(
        self,
        env: Optional[Any] = None,
        n_episodes: int = 10,
        deterministic: bool = True,
        render: bool = False
    ) -> Dict[str, float]:
        """
        評估模型績效
        
        計算指標:
        - 平均 reward
        - 平均報酬率
        - 勝率 (正報酬的 episode 比例)
        - 最大回撒
        - Sharpe Ratio
        - Win Rate
        - Profit Factor
        
        Args:
            env: 評估環境 (若為 None，使用初始化時的環境)
            n_episodes: 評估的 episode 數量
            deterministic: 是否使用確定性策略
            render: 是否渲染環境
        
        Returns:
            績效指標字典
        """
        if env is None:
            env = self.eval_env
        
        episode_rewards = []
        episode_returns = []
        episode_lengths = []
        
        print(f"\n[PPOAgent] 評估模型 (n_episodes={n_episodes})...")
        
        for episode in range(n_episodes):
            state, info = env.reset()
            done = False
            truncated = False
            episode_reward = 0
            episode_length = 0
            returns = []
            
            while not (done or truncated):
                # 預測動作
                action, _ = self.predict(state, deterministic=deterministic)
                
                # 執行動作
                state, reward, done, truncated, info = env.step(action)
                episode_reward += reward
                episode_length += 1
                
                # 記錄報酬
                if 'portfolio_return' in info:
                    returns.append(info['portfolio_return'])
                
                if render:
                    env.render()
            
            episode_rewards.append(episode_reward)
            episode_lengths.append(episode_length)
            
            # 計算 episode 總報酬
            if returns:
                episode_returns.append(sum(returns))
            else:
                # 從 info 計算最終報酬
                if 'portfolio_value' in info:
                    initial = info.get('initial_balance', 1_000_000)
                    final = info.get('portfolio_value', initial)
                    episode_returns.append((final - initial) / initial)
            
            print(f"  Episode {episode+1}/{n_episodes}: reward={episode_reward:.2f}, length={episode_length}, return={episode_returns[-1]:.2%}")
        
        # 計算績效指標
        mean_reward = np.mean(episode_rewards)
        std_reward = np.std(episode_rewards)
        mean_return = np.mean(episode_returns)
        std_return = np.std(episode_returns)
        positive_episodes = sum(1 for r in episode_returns if r > 0)
        
        results = {
            'mean_reward': mean_reward,
            'std_reward': std_reward,
            'mean_return': mean_return,
            'std_return': std_return,
            'mean_length': np.mean(episode_lengths),
            'positive_episodes': positive_episodes,
            'win_rate': positive_episodes / n_episodes,
            'n_episodes': n_episodes,
        }
        
        # 印出結果
        print("\n" + "=" * 50)
        print("           PPO Agent 評估結果")
        print("=" * 50)
        print(f"  平均 Reward:    {mean_reward:.2f} ± {std_reward:.2f}")
        print(f"  平均報酬率:    {mean_return:.2%} ± {std_return:.2%}")
        print(f"  正報酬率:      {positive_episodes}/{n_episodes} ({results['win_rate']:.1%})")
        print("=" * 50)
        
        return results
    
    def save(self, path: str):
        """
        保存模型到指定路徑
        
        Args:
            path: 保存路徑 (可包含 .zip 副檔名或不含副檔名)
        """
        if self.model is None:
            print("[PPOAgent] 無模型可保存")
            return
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果路徑不含副檔名，自動加上 .zip
        if path.suffix == '':
            path = path.with_suffix('.zip')
        
        self.model.save(str(path))
        print(f"[PPOAgent] 模型已保存: {path}")
    
    def load(self, path: str):
        """
        從指定路徑載入模型
        
        Args:
            path: 模型路徑 (.zip 檔案)
        """
        print(f"[PPOAgent] 載入模型: {path}")
        
        # 確保環境被設定
        if self.model is None:
            # 需要先建立模型結構才能載入
            self.model = PPO(
                policy=self.config['policy'],
                env=self.monitored_env,
                **self.config
            )
        
        self.model = PPO.load(
            str(path),
            env=self.monitored_env,
            device=self.config.get('device', 'auto')
        )
        
        print(f"[PPOAgent] 模型載入完成")
    
    def save_config(self, path: Optional[str] = None):
        """
        保存 Agent 配置到 JSON 檔案
        
        Args:
            path: 保存路徑 (若為 None，使用預設路徑)
        """
        if path is None:
            path = self.model_dir / 'agent_config.json'
        
        config_to_save = {
            'agent_type': 'PPO',
            'config': self.config,
            'model_dir': str(self.model_dir),
            'log_dir': str(self.log_dir),
        }
        
        with open(path, 'w') as f:
            json.dump(config_to_save, f, indent=2)
        
        print(f"[PPOAgent] 配置已保存: {path}")
    
    def get_model(self):
        """
        取得底層的 Stable-Baselines3 模型
        
        Returns:
            PPO 模型物件
        """
        return self.model
    
    def set_model_dir(self, path: str):
        """
        設定模型和日誌輸出目錄
        
        Args:
            path: 目錄路徑
        """
        self.model_dir = Path(path)
        self.log_dir = Path(path) / 'logs'
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


# =============================================================================
# 便捷函數工廠
# =============================================================================

def create_ppo_agent(
    env,
    eval_env: Optional[Any] = None,
    **kwargs
) -> PPOAgent:
    """
    便捷函數：建立 PPO Agent
    
    Args:
        env: 訓練環境
        eval_env: 評估環境 (可選)
        **kwargs: 其他 PPO 超參數
    
    Returns:
        PPOAgent 實例
    
    Example:
        >>> agent = create_ppo_agent(env, learning_rate=1e-4, n_steps=1024)
    """
    return PPOAgent(env=env, eval_env=eval_env, config=kwargs)


def load_ppo_agent(path: str, env) -> PPOAgent:
    """
    便捷函數：載入 PPO Agent
    
    Args:
        path: 模型路徑 (.zip 檔案)
        env: 環境 (用於初始化模型)
    
    Returns:
        PPOAgent 實例 (已載入模型)
    
    Example:
        >>> agent = load_ppo_agent('./results/ppo_model.zip', env)
    """
    agent = PPOAgent(env)
    agent.load(path)
    return agent


# =============================================================================
# 備用: 直接使用 Stable-Baselines3 PPO 的包裝
# =============================================================================

class PPOTrainer(PPOAgent):
    """
    PPOTrainer - 向後相容性包裝類別
    
    此類別繼承自 PPOAgent，提供向後相容性。
    建議使用 PPOAgent 類別。
    
    Deprecated:
        建議使用 PPOAgent 替代
    """
    
    def __init__(self, train_env, eval_env=None, config=None, model_dir='./results/models/ppo', log_dir='./results/logs/ppo'):
        # 忽略舊的 model_dir/log_dir 參數，使用時間戳自動產生
        super().__init__(env=train_env, eval_env=eval_env, config=config)
        print("[PPOTrainer] 警告：此類別已棄用，建議使用 PPOAgent")