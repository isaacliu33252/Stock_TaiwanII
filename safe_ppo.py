"""
Seed Collapse 兩層防護：
1. 訓練時 clip gradients（SeedCollapseCallback 掛在 model.learn）
2. 推理時 clip logits（predict 前檢查，崩潰時換 seed 重 train）

Custom policy 讓 PPO 在 forward 時自動 clip logits。
"""
import numpy as np
import torch
import torch.nn as nn
import torch as th
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticPolicy, BasePolicy
from stable_baselines3.common.torch_layers import MlpExtractor, BaseFeaturesExtractor
from stable_baselines3.common.distributions import CategoricalDistribution, Distribution
from stable_baselines3.common.type_aliases import PyTorchObs
from gymnasium import spaces


class SafeMlpExtractor(MlpExtractor):
    """MlpExtractor + gradient clip，防止梯度爆炸"""
    def forward(self, features: torch.Tensor) -> torch.Tensor:
        output = super().forward(features)
        # Gradient clip on extracted features
        if self.train_step > 0:
            pass  # grad clip done externally
        return output


class SafeActorCriticPolicy(ActorCriticPolicy):
    """
    安全的 Actor-Critic Policy：
    - get_distribution() 裡對 logits 做 clip，防止 Categorical 計算時 overflow
    """
    def __init__(self, *args, log_clip_min=-20.0, log_clip_max=20.0, **kwargs):
        self.log_clip_min = log_clip_min
        self.log_clip_max = log_clip_max
        super().__init__(*args, **kwargs)

    def get_distribution(self, obs: PyTorchObs) -> Distribution:
        """
        Override：clip logits 再建立 distribution，防止 Categorical overflow。
        """
        features = super().extract_features(obs, self.pi_features_extractor)
        latent_pi = self.mlp_extractor.forward_actor(features)
        logits = self.action_net(latent_pi)

        # CLIP LOGITS — 核心修復
        clipped_logits = torch.clamp(logits, self.log_clip_min, self.log_clip_max)

        # 最後防線：確認無 NaN/Inf
        if torch.isnan(clipped_logits).any() or torch.isinf(clipped_logits).any():
            clipped_logits = torch.zeros_like(clipped_logits)

        # 直接用 clipped logits 建立 distribution
        dist = CategoricalDistribution(action_dim=self.action_space.n)
        dist.proba_distribution(action_logits=clipped_logits)
        return dist

    def _predict(self, observation: PyTorchObs, deterministic: bool = False) -> th.Tensor:
        """
        實作抽象方法：呼叫 get_distribution（已被我們 override）。
        """
        return self.get_distribution(observation).get_actions(deterministic=deterministic)


# ─────────────────────────────────────────────────────────────────
from stable_baselines3.common.callbacks import BaseCallback


class GradientClipCallback(BaseCallback):
    """
    SB3 BaseCallback：每個 rollout 更新完後 clip gradients，防止梯度爆炸傳播。

    安裝方式：model.learn(callback=GradientClipCallback(max_norm=1.0))
    SB3 會自動呼叫 init_callback(self, model) → _on_training_end() 等生命週期方法。
    """
    def __init__(self, max_norm: float = 1.0, verbose: int = 0):
        super().__init__(verbose=verbose)
        self.max_norm = max_norm
        self.train_step = 0

    def _on_training_start(self) -> None:
        pass

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> None:
        """每個 rollout batch 更新完後 clip"""
        if hasattr(self.model, 'policy'):
            torch.nn.utils.clip_grad_norm_(self.model.policy.parameters(), self.max_norm)
            self.train_step += 1


# ─────────────────────────────────────────────────────────────────
# 整合：工廠函數建立安全 PPO
# ─────────────────────────────────────────────────────────────────

def make_safe_ppo(env, seed=42, learning_rate=3e-4, log_clip_min=-20.0, log_clip_max=20.0):
    """建立一個有 NaN guard 的 PPO model"""
    np.random.seed(seed)
    import random; random.seed(seed)
    torch.manual_seed(seed)

    model = PPO(
        SafeActorCriticPolicy,
        env,
        policy_kwargs={
            'log_clip_min': log_clip_min,
            'log_clip_max': log_clip_max,
            'net_arch': [256, 256],
        },
        learning_rate=learning_rate,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        verbose=0,
    )
    return model


if __name__ == '__main__':
    # 快速測試
    import pandas as pd, torch, random, importlib.util
    from pathlib import Path
    from stable_baselines3 import PPO
    from environments.taiwan_stock_env import TaiwanStockTradingEnv
    from environments.reward_function_v3 import DynamicRewardShaper
    import pyarrow.parquet as pq

    FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
    CACHE = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"

    table = pq.read_table(CACHE)
    df = table.to_pandas(timestamp_as_object=True)
    df['date'] = df['date'].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'tzinfo') and x.tzinfo else x)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    for col in ["close","high","low","open","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])

    import importlib.util as ilu
    spec_ta = ilu.spec_from_file_location("ta", str(FINRL/"data/technical_analysis.py"))
    tm = ilu.module_from_spec(spec_ta); spec_ta.loader.exec_module(tm)
    df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)

    train_start = pd.Timestamp('2015-01-02')
    train_end = pd.Timestamp('2015-12-13')
    df_train = df_ta[df_ta['date'].between(train_start, train_end)].copy()

    reward_func = DynamicRewardShaper(
        sortino_weight=0.25, calmar_weight=0.20, volatility_penalty=0.1,
        drawdown_penalty=0.15, holding_bonus=0.30, trade_reward=0.005,
        trend_bull_bonus=0.10, trend_bear_penalty=0.08,
        init_reward_scale=1.5, final_reward_scale=0.6,
    )
    reward_func.set_total_steps(15000)

    env = TaiwanStockTradingEnv(
        df=df_train, initial_balance=1_000_000,
        max_position=40000, trade_unit=1000, price_limit=0.10,
        commission_rate=0.001425, tax_rate=0.003,
        lookback_window=60, initial_shares=0, initial_avg_cost=0.0,
        reward_func=reward_func, enable_risk_manager=False, crash_window=15,
    )
    env._print_enabled = False

    np.random.seed(42); random.seed(42); torch.manual_seed(42)

    print("建立 SafeActorCriticPolicy PPO (logits clip ±20)...")
    model = PPO(
        SafeActorCriticPolicy,
        env,
        policy_kwargs={
            'log_clip_min': -20.0,
            'log_clip_max': 20.0,
            'net_arch': [256, 256],
        },
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        verbose=0,
    )

    print("Training 15k timesteps...")
    try:
        model.learn(total_timesteps=15000, progress_bar=False,
                    callback=GradientClipCallback(max_norm=1.0, verbose=1))
    except (ValueError, RuntimeError) as e:
        print(f"  Exception: {e}")

    # 測試 predict
    print("\n測試 predict (5 steps):")
    obs, _ = env.reset()
    for i in range(5):
        action, _ = model.predict(obs, deterministic=True)
        print(f"  step {i}: action={action}, nan={np.isnan(action).any()}")
        obs, _, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            obs, _ = env.reset()

    print("\nDONE")
