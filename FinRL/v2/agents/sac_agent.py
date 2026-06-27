"""
================================================================================
SACAgent - SAC (Soft Actor-Critic) 訓練器 (v2新版)
================================================================================
Soft Actor-Critic (SAC) 是一種最大熵強化學習演算法，適合連續動作空間。

SAC 的核心思想：
    1. 最大化期望報酬 + 熵（鼓勵探索）
    2. 使用兩個 Q 網路避免 overestimate
    3. 自動調整溫度參數

優點：
    - 訓練穩定，收斂性好
    - 適合連續動作空間
    - 有理論保障

適用場景：
    - 投資組合優化（連續持倉比重）
    - 資產配置

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import gymnasium as gym

try:
    from stable_baselines3 import SAC as SB3_SAC
    from stable_baselines3.common.vec_env import DummyVecEnv
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False

from gymnasium import spaces


@dataclass
class SACConfig:
    learning_rate: float = 3e-4
    batch_size: int = 256
    gamma: float = 0.99
    tau: float = 0.005
    ent_coef: str = 'auto'
    total_timesteps: int = 100000
    device: str = "auto"


class SACAgent:
    """
    SAC Agent 訓練器
    
    適用於連續動作空間的策略優化。
    """
    
    def __init__(
        self,
        env: gym.Env,
        config: SACConfig = None,
        model_dir: str = None,
    ):
        self.env = env
        self.config = config or SACConfig()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if model_dir is None:
            self.model_dir = Path(__file__).parent.parent / 'results' / f'sac_{timestamp}'
        else:
            self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_dim = env.observation_space.shape[0]
        self.action_dim = env.action_space.shape[0]
        
        self.model = None
        self._init_model()
    
    def _init_model(self):
        if SB3_AVAILABLE:
            print("[SACAgent] 使用 Stable-Baselines3 SAC")
            vec_env = DummyVecEnv([lambda: self.env])
            
            self.model = SB3_SAC(
                'MlpPolicy',
                vec_env,
                learning_rate=self.config.learning_rate,
                batch_size=self.config.batch_size,
                gamma=self.config.gamma,
                tau=self.config.tau,
                ent_coef=self.config.ent_coef,
                verbose=1,
                device=self.config.device,
            )
        else:
            print("[SACAgent] Stable-Baselines3 未安裝")
    
    def train(self, total_timesteps: int = None, callback=None):
        if total_timesteps is None:
            total_timesteps = self.config.total_timesteps
        
        print("=" * 60)
        print(f"SAC Agent 訓練開始")
        print(f"  - 總訓練步數: {total_timesteps:,}")
        print(f"  - 學習率: {self.config.learning_rate}")
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
        print("=" * 60)
    
    def predict(self, observation: np.ndarray, deterministic: bool = True) -> Tuple[np.ndarray, None]:
        if SB3_AVAILABLE:
            action, _ = self.model.predict(observation, deterministic=deterministic)
            return action, None
        else:
            return np.zeros(self.action_dim), None
    
    def save(self, path: str):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if SB3_AVAILABLE:
            self.model.save(str(path))
            print(f"[SACAgent] 模型已保存: {path}")
    
    def load(self, path: str):
        path = Path(path)
        
        if SB3_AVAILABLE:
            if path.suffix == '':
                path = path.with_suffix('.zip')
            
            self.model = SB3_SAC.load(str(path), env=self.env)
            print(f"[SACAgent] 模型已載入: {path}")


def train_sac(
    env: gym.Env,
    total_timesteps: int = 100000,
    learning_rate: float = 3e-4,
    model_dir: str = None,
    **kwargs
) -> SACAgent:
    config = SACConfig(total_timesteps=total_timesteps, learning_rate=learning_rate, **kwargs)
    agent = SACAgent(env, config=config, model_dir=model_dir)
    agent.train()
    return agent


if __name__ == '__main__':
    print("=" * 60)
    print("SAC Agent 測試")
    print("=" * 60)
    print("[SAC Agent] 模組已載入")
    print("=" * 60)