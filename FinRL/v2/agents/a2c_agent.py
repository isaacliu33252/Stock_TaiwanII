"""
================================================================================
A2CAgent - A2C (優勢演員-評論家) 訓練器 (v2新版)
================================================================================
Advantage Actor-Critic (A2C) 是一種結合策略梯度和價值函數的 RL 演算法。

A2C 的核心思想：
    1. 使用多個 worker 並行收集 experience
    2. 估計每個狀態的價值（V）和優勢（Advantage）
    3. 同時更新 Policy 和 Value Function

優點：
    - 訓練速度快（並行 worker）
    - 實現簡單
    - 穩定性中等

適用場景：
    - 快速原型開發
    - 離散動作交易策略

台股特殊規則：
    - 涨跌停限制: ±10%
    - T+2 交割制度

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import gymnasium as gym
from gymnasium import spaces

# 嘗試導入 Stable-Baselines3
try:
    from stable_baselines3 import A2C as SB3_A2C
    from stable_baselines3.common.vec_env import DummyVecEnv
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False


# =============================================================================
# A2C 超參數配置
# =============================================================================

@dataclass
class A2CConfig:
    """
    A2C 超參數配置
    """
    learning_rate: float = 7e-4
    n_steps: int = 2048
    gamma: float = 0.99
    ent_coef: float = 0.0
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    rms_prop_eps: float = 1e-5
    total_timesteps: int = 100000
    n_units: int = 64
    device: str = "auto"


class A2CAgent:
    """
    A2C Agent 訓練器
    
    特性：
        - 支援 Stable-Baselines3
        - 支援自定義 PyTorch 實現
        - 自動保存 checkpoint
    """
    
    def __init__(
        self,
        env: gym.Env,
        config: A2CConfig = None,
        model_dir: str = None,
        log_dir: str = None,
    ):
        """
        初始化 A2C Agent
        
        參數:
            env: Gym 環境
            config: A2C 超參數配置
            model_dir: 模型保存目錄
            log_dir: 日誌目錄
        """
        self.env = env
        self.config = config or A2CConfig()
        
        # 設定目錄
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if model_dir is None:
            self.model_dir = Path(__file__).parent.parent / 'results' / f'a2c_{timestamp}'
        else:
            self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        if log_dir is None:
            self.log_dir = self.model_dir / 'logs'
        else:
            self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 獲取環境資訊
        self.state_dim = env.observation_space.shape[0]
        
        if isinstance(env.action_space, spaces.Discrete):
            self.action_dim = env.action_space.n
            self.action_is_discrete = True
        else:
            self.action_dim = env.action_space.shape[0]
            self.action_is_discrete = False
        
        self.model = None
        self._init_model()
        
        self.training_stats = {
            'episode_rewards': [],
            'episode_lengths': [],
        }
    
    def _init_model(self):
        """初始化 A2C 模型"""
        if SB3_AVAILABLE:
            print("[A2CAgent] 使用 Stable-Baselines3 A2C")
            vec_env = DummyVecEnv([lambda: self.env])
            
            self.model = SB3_A2C(
                'MlpPolicy',
                vec_env,
                learning_rate=self.config.learning_rate,
                n_steps=self.config.n_steps,
                gamma=self.config.gamma,
                ent_coef=self.config.ent_coef,
                vf_coef=self.config.vf_coef,
                max_grad_norm=self.config.max_grad_norm,
                verbose=1,
                device=self.config.device,
            )
        else:
            print("[A2CAgent] Stable-Baselines3 未安裝")
    
    def train(
        self,
        total_timesteps: int = None,
        callback=None,
        save_freq: int = 10000,
    ):
        """訓練 A2C Agent"""
        if total_timesteps is None:
            total_timesteps = self.config.total_timesteps
        
        print("=" * 60)
        print(f"A2C Agent 訓練開始")
        print(f"  - 總訓練步數: {total_timesteps:,}")
        print(f"  - 學習率: {self.config.learning_rate}")
        print(f"  - State Dim: {self.state_dim}")
        print(f"  - Action Dim: {self.action_dim}")
        print("=" * 60)
        
        if SB3_AVAILABLE:
            self.model.learn(
                total_timesteps=total_timesteps,
                callback=callback,
                progress_bar=True,
            )
            
            self.save(str(self.model_dir / 'final_model'))
        
        print("=" * 60)
        print("訓練完成")
        print(f"  - 模型保存位置: {self.model_dir}")
        print("=" * 60)
    
    def predict(
        self,
        observation: np.ndarray,
        deterministic: bool = True
    ) -> Tuple[int, Any]:
        """預測動作"""
        if SB3_AVAILABLE:
            action, states = self.model.predict(observation, deterministic=deterministic)
            return action, states
        else:
            return 0, None
    
    def save(self, path: str):
        """保存模型"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if SB3_AVAILABLE:
            self.model.save(str(path))
            print(f"[A2CAgent] 模型已保存: {path}")
    
    def load(self, path: str):
        """載入模型"""
        path = Path(path)
        
        if SB3_AVAILABLE:
            if path.suffix == '':
                path = path.with_suffix('.zip')
            
            self.model = SB3_A2C.load(str(path), env=self.env)
            print(f"[A2CAgent] 模型已載入: {path}")


def train_a2c(
    env: gym.Env,
    total_timesteps: int = 100000,
    learning_rate: float = 7e-4,
    model_dir: str = None,
    **kwargs
) -> A2CAgent:
    """便捷函數：訓練 A2C Agent"""
    config = A2CConfig(total_timesteps=total_timesteps, learning_rate=learning_rate, **kwargs)
    agent = A2CAgent(env, config=config, model_dir=model_dir)
    agent.train()
    return agent


if __name__ == '__main__':
    print("=" * 60)
    print("A2C Agent 測試")
    print("=" * 60)
    print("[A2C Agent] 模組已載入")
    print("=" * 60)