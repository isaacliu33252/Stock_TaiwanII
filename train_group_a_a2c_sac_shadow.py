#!/usr/bin/env python3
"""Train Group A A2C/SAC shadow models from the Golden1 payload.

SAC in stable-baselines3 requires a continuous action space.  The local Group A
production environment is discrete, so the SAC shadow environment accepts a
continuous scalar and maps it to the nearest discrete Group A action.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces
from stable_baselines3 import A2C, SAC

from generate_dual_group_signal import _env_kwargs_from_payload, _llm_sentiment_path_from_payload
from train_dual_group_2024_2026 import (
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    attach_group_a_margin_shared_features_db_first,
    attach_group_a_market_margin_shared_features_db_first,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    attach_market_features_db_first,
    calculate_backtest_metrics,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_margin_features,
    payload_uses_group_a_margin_shared_features,
    payload_uses_group_a_market_margin_shared_features,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RESULT_JSON = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_a2c_sac_shadow_training_latest.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


class DiscreteToContinuousActionEnv(gym.Wrapper):
    """Expose a one-dimensional continuous action for SAC and discretize it."""

    def __init__(self, env: PortfolioEnv):
        super().__init__(env)
        self.discrete_n = int(env.action_space.n)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)

    def _to_discrete(self, action: Any) -> int:
        value = float(np.asarray(action, dtype=float).reshape(-1)[0])
        scaled = (np.clip(value, -1.0, 1.0) + 1.0) * 0.5 * (self.discrete_n - 1)
        return int(np.clip(round(scaled), 0, self.discrete_n - 1))

    def step(self, action: Any):
        return self.env.step(self._to_discrete(action))


class ContinuousWeightPortfolioEnv(PortfolioEnv):
    """SAC-compatible Group A env where actions are direct risk/cash weights."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.action_space = spaces.Box(low=-5.0, high=5.0, shape=(len(self.tickers) + 1,), dtype=np.float32)
        self._continuous_target_weights = self.weights.copy()

    def _weights_from_continuous_action(self, action: Any) -> np.ndarray:
        raw = np.asarray(action, dtype=float).reshape(-1)
        if len(raw) < len(self.tickers) + 1:
            padded = np.zeros(len(self.tickers) + 1, dtype=float)
            padded[: len(raw)] = raw
            raw = padded
        raw = np.clip(raw[: len(self.tickers) + 1], -5.0, 5.0)
        exp = np.exp(raw - np.max(raw))
        alloc = exp / max(float(exp.sum()), 1e-12)
        weights = alloc[: len(self.tickers)].astype(float)
        if self.group_a_triplet:
            idx_0050 = self.group_a_index_map["0050.TW"]
            idx_00631l = self.group_a_index_map["00631L.TW"]
            idx_00632r = self.group_a_index_map["00632R.TW"]
            leverage_spill = max(0.0, float(weights[idx_00631l]) - self.leverage_cap)
            inverse_spill = max(0.0, float(weights[idx_00632r]) - self.inverse_cap)
            weights[idx_00631l] = min(float(weights[idx_00631l]), self.leverage_cap)
            weights[idx_00632r] = min(float(weights[idx_00632r]), self.inverse_cap)
            weights[idx_0050] += 0.5 * (leverage_spill + inverse_spill)
        total = float(weights.sum())
        if total > 1.0:
            weights = weights / total
        return weights

    def _target_weights(self, action: int) -> np.ndarray:
        return self._continuous_target_weights.copy()

    def step(self, action: Any):
        self._continuous_target_weights = self._weights_from_continuous_action(action)
        return super().step(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--train-start", default=None)
    parser.add_argument("--train-end", default=None)
    parser.add_argument("--backtest-start", default="2025-06-01")
    parser.add_argument("--backtest-end", default="2026-06-03")
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--timesteps", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--skip-a2c", action="store_true")
    parser.add_argument("--skip-sac", action="store_true")
    parser.add_argument(
        "--sac-mode",
        choices=["discrete_scalar", "continuous_weights"],
        default="discrete_scalar",
        help="SAC action interface. continuous_weights trains a true portfolio-weight policy.",
    )
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_group_a_payload(result_json: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    group = dict(payload["group_a"])
    tickers = list(group.get("tickers") or TICKERS)
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    return payload, group, env_kwargs, shared_feature_cols


def _load_stock_data(
    payload: dict[str, Any],
    tickers: list[str],
    *,
    history_start: str,
    download_end: str,
    shared_feature_cols: list[str],
) -> dict[str, pd.DataFrame]:
    stock_data = load_stock_data_db_first(tickers, history_start, download_end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(stock_data, tickers, history_start, download_end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, history_start, download_end)
    if shared_feature_cols:
        llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if payload.get("group_a_use_llm_sentiment") else None
        stock_data = attach_market_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
            include_llm_sentiment=bool(payload.get("group_a_use_llm_sentiment", False)),
            llm_sentiment_path=llm_path,
        )
    return stock_data


def _make_env(
    panel: pd.DataFrame,
    tickers: list[str],
    shared_feature_cols: list[str],
    env_kwargs: dict[str, Any],
    initial_cash: float,
    *,
    continuous: bool = False,
    continuous_weights: bool = False,
) -> gym.Env:
    env_cls = ContinuousWeightPortfolioEnv if continuous_weights else PortfolioEnv
    env = env_cls(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **dict(env_kwargs),
    )
    return DiscreteToContinuousActionEnv(env) if continuous else env


def _run_model(
    model: Any,
    panel: pd.DataFrame,
    tickers: list[str],
    shared_feature_cols: list[str],
    env_kwargs: dict[str, Any],
    initial_cash: float,
    *,
    continuous: bool = False,
    continuous_weights: bool = False,
) -> dict[str, Any]:
    env = _make_env(
        panel,
        tickers,
        shared_feature_cols,
        env_kwargs,
        initial_cash,
        continuous=continuous,
        continuous_weights=continuous_weights,
    )
    obs, _ = env.reset()
    done = False
    info = {"weights": np.zeros(len(tickers))}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    base_env = env.env if isinstance(env, DiscreteToContinuousActionEnv) else env
    equity = [float(value) for value in base_env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    return {
        "actual_start": str(pd.Timestamp(panel["date"].min()).date()),
        "actual_end": str(pd.Timestamp(panel["date"].max()).date()),
        "rows": int(len(panel)),
        "final_value": float(equity[-1]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics.get("sharpe_ratio", metrics.get("sharpe", 0.0))),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_trades": int(base_env.trade_count),
        "fees_paid_estimate": float(base_env.fees_paid),
        "dca_purchase_count": int(base_env.dca_purchase_count),
        "dca_total_contributions": float(base_env.total_contributions),
        "final_weights": {ticker: float(weight) for ticker, weight in zip(tickers, info["weights"])},
        "equity_curve": equity,
        "dca_purchase_history": base_env.dca_purchase_history,
    }


def _train_a2c(train_env: gym.Env, *, timesteps: int, seed: int) -> A2C:
    model = A2C(
        "MlpPolicy",
        train_env,
        learning_rate=2e-4,
        n_steps=16,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.02,
        seed=seed,
        verbose=1,
    )
    model.learn(total_timesteps=timesteps)
    return model


def _train_sac(train_env: gym.Env, *, timesteps: int, seed: int) -> SAC:
    model = SAC(
        "MlpPolicy",
        train_env,
        learning_rate=2e-4,
        buffer_size=50_000,
        learning_starts=1_000,
        batch_size=64,
        gamma=0.99,
        tau=0.02,
        ent_coef="auto",
        seed=seed,
        verbose=1,
    )
    model.learn(total_timesteps=timesteps)
    return model


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    payload, group, env_kwargs, shared_feature_cols = _load_group_a_payload(result_json)
    tickers = list(group.get("tickers") or TICKERS)
    train_start = args.train_start or str(payload.get("train_start") or group.get("train_start") or "2020-01-01")
    train_end = args.train_end or str(payload.get("train_end") or group.get("train_end") or "2024-12-31")
    download_end = args.download_end or args.backtest_end
    history_start = str(payload.get("train_start") or group.get("train_start") or train_start)
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    stock_data = _load_stock_data(
        payload,
        tickers,
        history_start=history_start,
        download_end=download_end,
        shared_feature_cols=shared_feature_cols,
    )
    train_panel = _align_panel(stock_data, tickers, train_start, train_end, shared_feature_cols=shared_feature_cols)
    backtest_panel = _align_panel(stock_data, tickers, args.backtest_start, args.backtest_end, shared_feature_cols=shared_feature_cols)
    if len(train_panel) < 100:
        raise RuntimeError(f"Training rows too small: {len(train_panel)}")
    if len(backtest_panel) < 20:
        raise RuntimeError(f"Backtest rows too small: {len(backtest_panel)}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_dir = PROJECT_ROOT / "models" / "portfolio"
    model_dir.mkdir(parents=True, exist_ok=True)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "experiment": "GroupA_A2C_SAC_shadow_training",
        "method_note": (
            "No production promotion. A2C is trained on the same discrete Group A environment. "
            "SAC mode is recorded in sac_mode; continuous_weights means SAC directly emits portfolio/cash weights."
        ),
        "source_result_json": str(result_json.resolve()),
        "requested_window": {
            "train_start": train_start,
            "train_end": train_end,
            "backtest_start": args.backtest_start,
            "backtest_end": args.backtest_end,
            "download_end": download_end,
        },
        "actual_window": {
            "train_start": str(pd.Timestamp(train_panel["date"].min()).date()),
            "train_end": str(pd.Timestamp(train_panel["date"].max()).date()),
            "train_rows": int(len(train_panel)),
            "backtest_start": str(pd.Timestamp(backtest_panel["date"].min()).date()),
            "backtest_end": str(pd.Timestamp(backtest_panel["date"].max()).date()),
            "backtest_rows": int(len(backtest_panel)),
        },
        "tickers": tickers,
        "shared_feature_cols": shared_feature_cols,
        "env_kwargs": env_kwargs,
        "timesteps": int(args.timesteps),
        "seed": int(args.seed),
        "sac_mode": str(args.sac_mode),
        "models": {},
    }

    if not args.skip_a2c:
        print("Training Group A A2C shadow model...")
        a2c_env = _make_env(train_panel, tickers, shared_feature_cols, env_kwargs, initial_cash, continuous=False)
        a2c_model = _train_a2c(a2c_env, timesteps=int(args.timesteps), seed=int(args.seed))
        a2c_name = f"group_a_a2c_shadow_{stamp}"
        a2c_path = model_dir / a2c_name
        a2c_model.save(str(a2c_path))
        report["models"]["a2c"] = {
            "model_name": a2c_name,
            "model_path": str(a2c_path.with_suffix(".zip").resolve()),
            "backtest": _run_model(
                a2c_model,
                backtest_panel,
                tickers,
                shared_feature_cols,
                env_kwargs,
                initial_cash,
                continuous=False,
            ),
        }

    if not args.skip_sac:
        print("Training Group A SAC shadow model...")
        sac_continuous_weights = args.sac_mode == "continuous_weights"
        sac_env = _make_env(
            train_panel,
            tickers,
            shared_feature_cols,
            env_kwargs,
            initial_cash,
            continuous=not sac_continuous_weights,
            continuous_weights=sac_continuous_weights,
        )
        sac_model = _train_sac(sac_env, timesteps=int(args.timesteps), seed=int(args.seed) + 17)
        sac_suffix = "continuous_weights" if sac_continuous_weights else "discrete_scalar"
        sac_name = f"group_a_sac_{sac_suffix}_shadow_{stamp}"
        sac_path = model_dir / sac_name
        sac_model.save(str(sac_path))
        report["models"]["sac"] = {
            "model_name": sac_name,
            "model_path": str(sac_path.with_suffix(".zip").resolve()),
            "sac_mode": str(args.sac_mode),
            "backtest": _run_model(
                sac_model,
                backtest_panel,
                tickers,
                shared_feature_cols,
                env_kwargs,
                initial_cash,
                continuous=not sac_continuous_weights,
                continuous_weights=sac_continuous_weights,
            ),
        }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_rows = []
    for algo, item in report["models"].items():
        csv_rows.append({"strategy": algo, "model_path": item["model_path"], **item["backtest"]})
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for algo, item in report["models"].items():
        bt = item["backtest"]
        print(
            f"{algo.upper()}: final={bt['final_value']:.2f}, sharpe={bt['sharpe_ratio']:.4f}, "
            f"mdd={bt['max_drawdown']:.4%}, trades={bt['num_trades']}, fees={bt['fees_paid_estimate']:.2f}"
        )


if __name__ == "__main__":
    try:
        import numpy.core.numeric as _numpy_core_numeric

        sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
    except ImportError:
        pass
    main()
