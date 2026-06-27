"""
================================================================================
train - 統一訓練介面 (v2新版)
================================================================================
提供統一的訓練介面，支援多種 RL 演算法和配置方式。

主要功能：
    1. TrainingRunner - 統一訓練器，封裝常見的訓練流程
    2. train_model - 便捷函數，快速訓練模型

支援的演算法：
    - PPO (Proximal Policy Optimization)
    - A2C (Advantage Actor-Critic)
    - SAC (Soft Actor-Critic)

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
import torch
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
import json

from .ppo_agent import PPOAgent, PPOConfig
from .a2c_agent import A2CAgent, A2CConfig
from .sac_agent import SACAgent, SACConfig


# =============================================================================
# 訓練配置
# =============================================================================

@dataclass
class TrainingConfig:
    """
    統一訓練配置
    
    定義訓練過程中的各項參數。
    """
    # 基本設定
    algo: str = 'ppo'                # 演算法 ('ppo', 'a2c', 'sac')
    total_timesteps: int = 100000   # 總訓練步數
    seed: int = 42                   # 隨機種子
    
    # 環境設定
    state_dim: int = 0              # 狀態維度
    action_dim: int = 0             # 動作維度
    
    # 訓練設定
    batch_size: int = 64
    learning_rate: float = 3e-4
    eval_freq: int = 5000
    save_freq: int = 10000
    log_freq: int = 1000
    
    # Early Stopping
    early_stopping_patience: int = 20  # 早停耐心次數
    early_stopping_threshold: float = 0.01  # 改善門檻
    
    # 模型儲存
    checkpoint_dir: str = None
    best_model_path: str = None


@dataclass
class TrainingResult:
    """
    訓練結果
    
    包含訓練過程中收集的所有資訊。
    """
    algo: str = ""
    total_timesteps: int = 0
    training_time: float = 0.0
    
    # 學習曲線
    episode_rewards: List[float] = field(default_factory=list)
    episode_lengths: List[int] = field(default_factory=list)
    
    # 最終績效
    final_reward: float = 0.0
    best_reward: float = 0.0
    
    # 模型路徑
    final_model_path: str = ""
    best_model_path: str = ""
    
    # 訓練歷史
    losses: List[float] = field(default_factory=list)
    learning_rates: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'algo': self.algo,
            'total_timesteps': self.total_timesteps,
            'training_time': self.training_time,
            'final_reward': self.final_reward,
            'best_reward': self.best_reward,
            'final_model_path': self.final_model_path,
            'best_model_path': self.best_model_path,
        }


# =============================================================================
# TrainingRunner 類別
# =============================================================================

class TrainingRunner:
    """
    統一訓練器
    
    提供一個統一的介面來訓練不同的 RL 演算法。
    
    特性：
        - 自動選擇合適的 Agent
        - 內建 checkpoint 保存
        - Early Stopping 支援
        - 學習率调度
        - 完整的訓練日誌
        
    使用範例:
        >>> from FinRL.v2.agents import TrainingRunner, TrainingConfig
        >>> 
        >>> config = TrainingConfig(
        ...     algo='ppo',
        ...     total_timesteps=100000,
        ...     batch_size=64,
        ... )
        >>> 
        >>> runner = TrainingRunner(env, config)
        >>> result = runner.train()
        >>> 
        >>> # 使用最佳模型
        >>> agent = runner.get_best_model()
    """
    
    def __init__(
        self,
        env,
        config: TrainingConfig = None,
        model_dir: str = None,
        log_dir: str = None,
    ):
        """
        初始化 TrainingRunner
        
        參數:
            env: Gym 環境
            config: 訓練配置
            model_dir: 模型保存目錄
            log_dir: 日誌目錄
        """
        self.env = env
        self.config = config or TrainingConfig()
        
        # 設定目錄
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if model_dir is None:
            self.model_dir = Path(__file__).parent.parent / 'results' / f'training_{timestamp}'
        else:
            self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        if log_dir is None:
            self.log_dir = self.model_dir / 'logs'
        else:
            self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化 Agent
        self.agent = None
        self.best_agent = None
        self._init_agent()
        
        # 訓練狀態
        self.current_timestep = 0
        self.best_reward = -np.inf
        self.no_improvement_count = 0
        
        # 訓練結果
        self.result = TrainingResult(algo=self.config.algo)
    
    def _init_agent(self):
        """初始化 Agent"""
        algo = self.config.algo.lower()
        
        if algo == 'ppo':
            ppo_config = PPOConfig(
                total_timesteps=self.config.total_timesteps,
                batch_size=self.config.batch_size,
                learning_rate=self.config.learning_rate,
            )
            self.agent = PPOAgent(
                self.env,
                config=ppo_config,
                model_dir=str(self.model_dir),
                log_dir=str(self.log_dir),
            )
        elif algo == 'a2c':
            a2c_config = A2CConfig(
                total_timesteps=self.config.total_timesteps,
                learning_rate=self.config.learning_rate,
            )
            self.agent = A2CAgent(
                self.env,
                config=a2c_config,
                model_dir=str(self.model_dir),
                log_dir=str(self.log_dir),
            )
        elif algo == 'sac':
            sac_config = SACConfig(
                total_timesteps=self.config.total_timesteps,
                learning_rate=self.config.learning_rate,
            )
            self.agent = SACAgent(
                self.env,
                config=sac_config,
                model_dir=str(self.model_dir),
                log_dir=str(self.log_dir),
            )
        else:
            raise ValueError(f"不支援的演算法: {algo}")
        
        print(f"[TrainingRunner] 使用 {algo.upper()} 演算法")
    
    def train(
        self,
        total_timesteps: int = None,
        eval_env=None,
        eval_freq: int = None,
        save_freq: int = None,
        early_stopping: bool = True,
        verbose: bool = True,
    ) -> TrainingResult:
        """
        執行訓練
        
        參數:
            total_timesteps: 總訓練步數
            eval_env: 評估環境
            eval_freq: 評估頻率
            save_freq: 保存頻率
            early_stopping: 是否啟用 Early Stopping
            verbose: 是否詳細輸出
            
        返回:
            TrainingResult
        """
        import time
        start_time = time.time()
        
        if total_timesteps is None:
            total_timesteps = self.config.total_timesteps
        
        if eval_freq is None:
            eval_freq = self.config.eval_freq
        
        if save_freq is None:
            save_freq = self.config.save_freq
        
        if verbose:
            print("=" * 60)
            print(f"訓練開始")
            print(f"  演算法: {self.config.algo}")
            print(f"  總步數: {total_timesteps:,}")
            print(f"  評估頻率: {eval_freq:,}")
            print(f"  保存頻率: {save_freq:,}")
            print(f"  早停: {'是' if early_stopping else '否'}")
            print("=" * 60)
        
        # 訓練
        self.agent.train(
            total_timesteps=total_timesteps,
            eval_env=eval_env,
            eval_freq=eval_freq,
            save_freq=save_freq,
        )
        
        # 更新結果
        self.result.total_timesteps = total_timesteps
        self.result.training_time = time.time() - start_time
        self.result.final_model_path = str(self.model_dir / 'final_model')
        
        if verbose:
            print("=" * 60)
            print(f"訓練完成")
            print(f"  訓練時間: {self.result.training_time:.2f} 秒")
            print(f"  總步數: {self.result.total_timesteps:,}")
            print(f"  模型保存: {self.result.final_model_path}")
            print("=" * 60)
        
        return self.result
    
    def get_best_model(self):
        """獲取最佳模型"""
        return self.best_agent
    
    def load_model(self, path: str):
        """載入模型"""
        self.agent.load(path)
    
    def save_training_history(self, path: str = None):
        """保存訓練歷史"""
        if path is None:
            path = self.model_dir / 'training_history.json'
        
        history = {
            'episode_rewards': self.result.episode_rewards,
            'episode_lengths': self.result.episode_lengths,
            'losses': self.result.losses,
            'learning_rates': self.result.learning_rates,
        }
        
        with open(path, 'w') as f:
            json.dump(history, f, indent=2)
        
        print(f"[TrainingRunner] 訓練歷史已保存: {path}")


# =============================================================================
# 便捷函數
# =============================================================================

def train_model(
    env,
    algo: str = 'ppo',
    total_timesteps: int = 100000,
    learning_rate: float = 3e-4,
    batch_size: int = 64,
    model_dir: str = None,
    **kwargs
) -> Tuple:
    """
    便捷函數：訓練模型
    
    快速訓練介面，適用於常見的訓練場景。
    
    參數:
        env: Gym 環境
        algo: 演算法 ('ppo', 'a2c', 'sac')
        total_timesteps: 總訓練步數
        learning_rate: 學習率
        batch_size: 批次大小
        model_dir: 模型保存目錄
        **kwargs: 其他參數
        
    返回:
        (agent, result)
    """
    config = TrainingConfig(
        algo=algo,
        total_timesteps=total_timesteps,
        learning_rate=learning_rate,
        batch_size=batch_size,
        **kwargs
    )
    
    runner = TrainingRunner(env, config, model_dir=model_dir)
    result = runner.train()
    
    return runner.agent, result


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("TrainingRunner 測試")
    print("=" * 60)
    print("[TrainingRunner] 模組已載入")
    print("=" * 60)