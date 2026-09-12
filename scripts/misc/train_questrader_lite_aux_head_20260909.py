#!/usr/bin/env python3
"""QUESTrader-lite: cheap partial version of 2608.15841's auxiliary-task idea,
without the full meta-gradient machinery.

Adds ONE fixed (hand-picked, not discovered) auxiliary prediction head to the
existing cap20 PPO recipe (2017-2019 training window, triplet_v2, 00631L cap
20%, seed=42 -- the recipe established as this project's best independent-
model candidate today): predict standardized 5-day forward realized
volatility of 0050.TW from the shared value-latent features, added as an
extra MSE loss term alongside the normal PPO loss (policy_loss + vf_coef *
value_loss + ent_coef * entropy_loss + aux_coef * aux_loss).

This is the "cheap version" flagged in the 2608.15841 desk review
(GROUP_A_PLUS_20260908_2608_15841_QUESTRADER_DESK_REVIEW_HANDOFF.md) as the
lower-cost way to test whether an auxiliary risk-related prediction task
helps the model develop the within-golden1-regime risk modulation that
today's day-by-day diagnostic
(project_a2118_independent_ppo_model_experiment_20260908.md) found the plain
cap20 model lacks -- without needing institutional/LLM-sentiment data that
doesn't exist for the 2017-2019 training window.

The auxiliary target is NOT part of the observation (that would leak the
label into the actor's input) -- it is carried alongside each rollout step
via a custom RolloutBuffer field, exactly the way GVF answer heads are
trained in the source paper (just with one fixed cumulant instead of
automatically discovered ones, and no meta-gradient on top).

Read-only research. Does not touch any production/live file. Saves a new
model checkpoint (`a2118_independent_ppo_v1_80k_cap20_auxvol`) and result
JSON files; does not modify golden1_0531 / a2118 production wiring.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import torch as th
import torch.nn as nn
import torch.nn.functional as F
import gymnasium as gym
from gymnasium import spaces

from stable_baselines3 import PPO
from stable_baselines3.common.buffers import RolloutBuffer
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.utils import explained_variance, obs_as_tensor

import train_dual_group_2024_2026 as tdg

SEED = 42
TIMESTEPS = 80_000
TRAIN_START = "2016-01-01"
TRAIN_END = "2019-12-31"
DOWNLOAD_END = "2026-09-05"
AUX_HORIZON = 5
AUX_COEF = 0.1
MODEL_NAME = "a2118_independent_ppo_v1_80k_cap20_auxvol"

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-01", "2026-09-04"),
]


# ---------------------------------------------------------------------------
# Auxiliary target: standardized 5-day forward realized volatility of 0050
# ---------------------------------------------------------------------------
def compute_aux_targets(panel: pd.DataFrame, ticker: str = "0050.TW", horizon: int = AUX_HORIZON) -> np.ndarray:
    close = panel[f"{ticker}_close"].to_numpy(dtype=float)
    n = len(close)
    log_ret = np.zeros(n, dtype=float)
    log_ret[1:] = np.diff(np.log(np.clip(close, 1e-6, None)))
    targets = np.zeros(n, dtype=np.float64)
    for i in range(n):
        window = log_ret[i + 1 : i + 1 + horizon]
        targets[i] = float(np.std(window)) if len(window) > 0 else (targets[i - 1] if i > 0 else 0.0)
    mean, std = targets.mean(), targets.std()
    if std < 1e-12:
        std = 1.0
    return ((targets - mean) / std).astype(np.float32)


class AuxTargetWrapper(gym.Wrapper):
    """Injects info['aux_target'] per step, aligned to the step_idx AT THE TIME
    step() is called (i.e. same time index as the observation used to pick
    the action), not the resulting new state.
    """

    def __init__(self, env, aux_targets: np.ndarray):
        super().__init__(env)
        self._aux_targets = aux_targets

    def step(self, action):
        idx_before = min(self.env.step_idx, len(self._aux_targets) - 1)
        obs, reward, terminated, truncated, info = self.env.step(action)
        info = dict(info)
        info["aux_target"] = float(self._aux_targets[idx_before])
        return obs, reward, terminated, truncated, info


# ---------------------------------------------------------------------------
# Custom RolloutBuffer carrying the auxiliary target alongside each step
# ---------------------------------------------------------------------------
class AuxRolloutBuffer(RolloutBuffer):
    def reset(self) -> None:
        super().reset()
        self.aux_targets = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)

    def add(self, obs, action, reward, episode_start, value, log_prob, aux_target=None) -> None:  # type: ignore[override]
        pos = self.pos
        super().add(obs, action, reward, episode_start, value, log_prob)
        if aux_target is not None:
            self.aux_targets[pos] = np.asarray(aux_target, dtype=np.float32)

    def get(self, batch_size: int | None = None):  # type: ignore[override]
        assert self.full
        indices = np.random.permutation(self.buffer_size * self.n_envs)
        if not self.generator_ready:
            _tensor_names = ["observations", "actions", "values", "log_probs", "advantages", "returns", "aux_targets"]
            for tensor in _tensor_names:
                self.__dict__[tensor] = self.swap_and_flatten(self.__dict__[tensor])
            self.generator_ready = True
        if batch_size is None:
            batch_size = self.buffer_size * self.n_envs
        start_idx = 0
        while start_idx < self.buffer_size * self.n_envs:
            batch_inds = indices[start_idx : start_idx + batch_size]
            samples = self._get_samples(batch_inds)
            aux = self.to_torch(self.aux_targets[batch_inds].flatten())
            yield samples, aux
            start_idx += batch_size


# ---------------------------------------------------------------------------
# Policy with one extra auxiliary regression head off the value latent
# ---------------------------------------------------------------------------
class AuxActorCriticPolicy(ActorCriticPolicy):
    def _build(self, lr_schedule) -> None:
        super()._build(lr_schedule)
        self.aux_net = nn.Linear(self.mlp_extractor.latent_dim_vf, 1)
        self.optimizer = self.optimizer_class(self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs)

    def evaluate_actions_with_aux(self, obs, actions):
        features = self.extract_features(obs)
        if self.share_features_extractor:
            latent_pi, latent_vf = self.mlp_extractor(features)
        else:
            pi_features, vf_features = features
            latent_pi = self.mlp_extractor.forward_actor(pi_features)
            latent_vf = self.mlp_extractor.forward_critic(vf_features)
        distribution = self._get_action_dist_from_latent(latent_pi)
        log_prob = distribution.log_prob(actions)
        values = self.value_net(latent_vf)
        entropy = distribution.entropy()
        aux_pred = self.aux_net(latent_vf).flatten()
        return values, log_prob, entropy, aux_pred


# ---------------------------------------------------------------------------
# PPO subclass: collect_rollouts stores aux_target; train() adds aux MSE loss
# ---------------------------------------------------------------------------
class AuxPPO(PPO):
    def __init__(self, *args, aux_coef: float = AUX_COEF, **kwargs):
        self.aux_coef = aux_coef
        super().__init__(*args, **kwargs)

    def collect_rollouts(self, env, callback, rollout_buffer, n_rollout_steps: int) -> bool:
        assert self._last_obs is not None
        self.policy.set_training_mode(False)
        n_steps = 0
        rollout_buffer.reset()
        if self.use_sde:
            self.policy.reset_noise(env.num_envs)
        callback.on_rollout_start()

        while n_steps < n_rollout_steps:
            if self.use_sde and self.sde_sample_freq > 0 and n_steps % self.sde_sample_freq == 0:
                self.policy.reset_noise(env.num_envs)
            with th.no_grad():
                obs_tensor = obs_as_tensor(self._last_obs, self.device)
                actions, values, log_probs = self.policy(obs_tensor)
            actions = actions.cpu().numpy()
            clipped_actions = actions
            if isinstance(self.action_space, spaces.Box):
                clipped_actions = np.clip(actions, self.action_space.low, self.action_space.high)

            new_obs, rewards, dones, infos = env.step(clipped_actions)
            self.num_timesteps += env.num_envs
            callback.update_locals(locals())
            if not callback.on_step():
                return False
            self._update_info_buffer(infos, dones)
            n_steps += 1

            if isinstance(self.action_space, spaces.Discrete):
                actions = actions.reshape(-1, 1)

            for idx, done in enumerate(dones):
                if done and infos[idx].get("terminal_observation") is not None and infos[idx].get("TimeLimit.truncated", False):
                    terminal_obs = self.policy.obs_to_tensor(infos[idx]["terminal_observation"])[0]
                    with th.no_grad():
                        terminal_value = self.policy.predict_values(terminal_obs)[0]
                    rewards[idx] += self.gamma * terminal_value

            aux_target = np.array([float(infos[i].get("aux_target", 0.0)) for i in range(env.num_envs)], dtype=np.float32)
            rollout_buffer.add(
                self._last_obs, actions, rewards, self._last_episode_starts, values, log_probs, aux_target=aux_target
            )
            self._last_obs = new_obs
            self._last_episode_starts = dones

        with th.no_grad():
            values = self.policy.predict_values(obs_as_tensor(new_obs, self.device))
        rollout_buffer.compute_returns_and_advantage(last_values=values, dones=dones)
        callback.on_rollout_end()
        return True

    def train(self) -> None:
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)
        clip_range = self.clip_range(self._current_progress_remaining)
        clip_range_vf = self.clip_range_vf(self._current_progress_remaining) if self.clip_range_vf is not None else None

        entropy_losses, pg_losses, value_losses, aux_losses, clip_fractions = [], [], [], [], []
        continue_training = True

        for epoch in range(self.n_epochs):
            approx_kl_divs = []
            for rollout_data, aux_targets in self.rollout_buffer.get(self.batch_size):
                actions = rollout_data.actions
                if isinstance(self.action_space, spaces.Discrete):
                    actions = rollout_data.actions.long().flatten()

                values, log_prob, entropy, aux_pred = self.policy.evaluate_actions_with_aux(rollout_data.observations, actions)
                values = values.flatten()
                advantages = rollout_data.advantages
                if self.normalize_advantage and len(advantages) > 1:
                    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                ratio = th.exp(log_prob - rollout_data.old_log_prob)
                policy_loss_1 = advantages * ratio
                policy_loss_2 = advantages * th.clamp(ratio, 1 - clip_range, 1 + clip_range)
                policy_loss = -th.min(policy_loss_1, policy_loss_2).mean()
                pg_losses.append(policy_loss.item())
                clip_fractions.append(th.mean((th.abs(ratio - 1) > clip_range).float()).item())

                if clip_range_vf is None:
                    values_pred = values
                else:
                    values_pred = rollout_data.old_values + th.clamp(values - rollout_data.old_values, -clip_range_vf, clip_range_vf)
                value_loss = F.mse_loss(rollout_data.returns, values_pred)
                value_losses.append(value_loss.item())

                entropy_loss = -th.mean(-log_prob) if entropy is None else -th.mean(entropy)
                entropy_losses.append(entropy_loss.item())

                aux_loss = F.mse_loss(aux_pred, aux_targets)
                aux_losses.append(aux_loss.item())

                loss = policy_loss + self.ent_coef * entropy_loss + self.vf_coef * value_loss + self.aux_coef * aux_loss

                with th.no_grad():
                    log_ratio = log_prob - rollout_data.old_log_prob
                    approx_kl_div = th.mean((th.exp(log_ratio) - 1) - log_ratio).cpu().numpy()
                    approx_kl_divs.append(approx_kl_div)

                if self.target_kl is not None and approx_kl_div > 1.5 * self.target_kl:
                    continue_training = False
                    if self.verbose >= 1:
                        print(f"Early stopping at step {epoch} due to reaching max kl: {approx_kl_div:.2f}")
                    break

                self.policy.optimizer.zero_grad()
                loss.backward()
                th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                self.policy.optimizer.step()

            self._n_updates += 1
            if not continue_training:
                break

        explained_var = explained_variance(self.rollout_buffer.values.flatten(), self.rollout_buffer.returns.flatten())
        self.logger.record("train/entropy_loss", np.mean(entropy_losses))
        self.logger.record("train/policy_gradient_loss", np.mean(pg_losses))
        self.logger.record("train/value_loss", np.mean(value_losses))
        self.logger.record("train/aux_loss", np.mean(aux_losses))
        self.logger.record("train/approx_kl", np.mean(approx_kl_divs))
        self.logger.record("train/clip_fraction", np.mean(clip_fractions))
        self.logger.record("train/loss", loss.item())
        self.logger.record("train/explained_variance", explained_var)
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/clip_range", clip_range)


def main() -> None:
    profile = copy.deepcopy(tdg.GROUP_A_PROFILE_PRESETS["default"])
    profile["env"]["leverage_cap"] = 0.20
    profile["env"]["inverse_cap"] = 0.30
    tickers = tdg.DEFAULT_GROUP_A_TICKERS

    print(f"Loading stock data {TRAIN_START}..{DOWNLOAD_END} for {tickers}")
    stock_data = tdg.load_stock_data_db_first(tickers, TRAIN_START, DOWNLOAD_END)

    env_kwargs = dict(profile["env"])
    env_kwargs.update(
        {
            "group_a_action_schema": "triplet_v2",
            "inverse_m_state_only": True,
            "inverse_max_holding_days": 5,
            "enable_pva_features": True,
            "enable_pva_sigmoid": True,
            "pva_weight": 0.32,
            "pva_j_state_weight": 0.19,
            "pva_m_state_weight": 1.0,
            "pva_drift_threshold": 0.06,
            "pva_target_vol": 0.012,
            "pva_min_leverage_scale": 0.4,
            "pva_inverse_hedge_budget": 0.3,
        }
    )

    train_panel = tdg._align_panel(stock_data, tickers, TRAIN_START, TRAIN_END, shared_feature_cols=None)
    print(f"Train panel: {train_panel['date'].min().date()}..{train_panel['date'].max().date()} ({len(train_panel)} rows)")
    aux_targets = compute_aux_targets(train_panel)

    raw_env = tdg.PortfolioEnv(train_panel, tickers, shared_feature_cols=None, initial_cash=1_000_000.0, **env_kwargs)
    wrapped_env = AuxTargetWrapper(raw_env, aux_targets)

    model = AuxPPO(
        AuxActorCriticPolicy,
        wrapped_env,
        learning_rate=3e-4,
        n_steps=profile["ppo"]["n_steps"],
        gamma=profile["ppo"]["gamma"],
        gae_lambda=profile["ppo"]["gae_lambda"],
        ent_coef=profile["ppo"]["ent_coef"],
        seed=SEED,
        verbose=1,
        aux_coef=AUX_COEF,
        rollout_buffer_class=AuxRolloutBuffer,
    )
    print(f"Training AuxPPO (aux_coef={AUX_COEF}, aux target=5d forward 0050 realized vol, standardized) for {TIMESTEPS} steps")
    model.learn(total_timesteps=TIMESTEPS)

    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{MODEL_NAME}.zip"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    print(f"Saved: {model_path}")

    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for label, start, end in WINDOWS:
        result = tdg._backtest_group(
            model,
            stock_data,
            tickers,
            "GroupA",
            shared_feature_cols=None,
            backtest_start=start,
            backtest_end=end,
            initial_cash=1_000_000.0,
            env_kwargs=env_kwargs,
        )
        out_path = results_dir / f"group_a_backtest_auxvol_{label}_20260909.json"
        out_path.write_text(json.dumps({"group_a": {"result": result}}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        written.append(str(out_path))
        m = result["rl_metrics"]
        print(f"  {label:18s} final={result['final_value']:>12,.0f}  sharpe={m.get('sharpe', float('nan')):7.4f}  mdd={m.get('max_drawdown', float('nan'))*100:7.2f}%")

    print("\nResult files:")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
