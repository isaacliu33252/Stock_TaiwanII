# ============================================================================
# SAC Agent 實現
# ============================================================================
"""
Soft Actor-Critic (SAC) Agent 實現模組

SAC 是一種適合連續動作空間的深度強化學習演算法，內建最大熵框架。
本模組基於 stable-baselines3 實現，專為股票交易環境優化。

特點：
- 自動調整探索程度
- 適合連續動作空間（如股票倉位）
- 樣本效率高

使用方法：
    from FinRL.agents import SACAgent
    
    agent = SACAgent(env)
    agent.train(total_timesteps=100000)
    agent.save("sac_stock_model")
"""

from stable_baselines3 import SAC

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SAC_CONFIG


class SACAgent:
    """
    SAC Agent 包裝類別
    
    封裝 stable-baselines3 的 SAC 模型，提供更直觀的介面用於股票交易。
    
    參數：
        env: Gymnasium 環境
        config: 字典，超參數設定，若為 None則使用 config.py 中的預設值
    """
    
    def __init__(self, env, config=None):
        """初始化 SAC Agent"""
        self.env = env
        self.config = config if config is not None else SAC_CONFIG
        self.model = SAC(
            "MlpPolicy",
            env,
            learning_rate=self.config["learning_rate"],
            buffer_size=self.config["buffer_size"],
            learning_starts=self.config["learning_starts"],
            batch_size=self.config["batch_size"],
            tau=self.config["tau"],
            gamma=self.config["gamma"],
            train_freq=self.config["train_freq"],
            gradient_steps=self.config["gradient_steps"],
            ent_coef=self.config["ent_coef"],
            target_update_interval=self.config["target_update_interval"],
            verbose=self.config["verbose"],
        )
    
    def train(self, total_timesteps, callback=None):
        """訓練 Agent"""
        return self.model.learn(
            total_timesteps=total_timesteps,
            callback=callback,
            progress_bar=True
        )
    
    def predict(self, observation, deterministic=True):
        """根據觀察執行預測"""
        return self.model.predict(observation, deterministic=deterministic)
    
    def save(self, path):
        """儲存模型"""
        self.model.save(path)
    
    @classmethod
    def load(cls, path, env):
        """載入模型"""
        instance = cls(env)
        instance.model = SAC.load(path, env=env)
        return instance
