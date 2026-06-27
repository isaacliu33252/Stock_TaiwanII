"""
RL Portfolio Strategy
=====================
提供兩種入口：
1. `RLPortfolioStrategy`：包裝既有 walk-forward 訓練流程
2. `RLCachedStrategy`：直接載入已訓練模型做推論，輸出 FinRL-X 介面的 StrategyResult
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from ..environments.taiwan_stock_env import TaiwanStockTradingEnv
from .base_strategy import BaseStrategy, StrategyConfig, StrategyResult

logger = logging.getLogger(__name__)

_WALK_FORWARD_MODULE_NAME = "finrl_walk_forward_v2_loaded"
_wf_module = None


def _discover_walk_forward_path() -> Optional[Path]:
    package_root = Path(__file__).resolve().parents[1]
    project_root = package_root.parent
    candidates = [
        package_root / "walk_forward_v2.py",
        project_root / "FinRL" / "walk_forward_v2.py",
        project_root / "Stock_taiwan2-main" / "FinRL" / "walk_forward_v2.py",
    ]
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return None


def _load_walk_forward_module():
    global _wf_module

    if _wf_module is not None:
        return _wf_module

    walk_forward_path = _discover_walk_forward_path()
    if walk_forward_path is None:
        raise RuntimeError("walk_forward_v2.py not found in the canonical FinRL repo.")

    wf_parent = str(walk_forward_path.parent)
    if wf_parent not in sys.path:
        sys.path.insert(0, wf_parent)

    spec = importlib.util.spec_from_file_location(
        _WALK_FORWARD_MODULE_NAME,
        walk_forward_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {walk_forward_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_WALK_FORWARD_MODULE_NAME] = module
    spec.loader.exec_module(module)
    _wf_module = module
    logger.info("Loaded walk_forward_v2 from %s", walk_forward_path)
    return _wf_module


@dataclass
class RLPortfolioConfig(StrategyConfig):
    """RL 投資組合策略設定。"""

    name: str = "RLPortfolio"
    train_window_years: float = 2.0
    test_window_days: int = 60
    timesteps: int = 50_000
    agent_type: str = "ppo"
    holdings: Optional[Dict[str, int]] = None
    reuse_models: bool = True
    experiment_tag: str = ""

    action_mode: str = "continuous"
    initial_balance: float = 1_000_000.0
    max_position: int = 40_000
    trade_unit: int = 1_000
    commission_rate: float = 0.001425
    tax_rate: float = 0.003
    lookback_window: int = 60
    include_dividends: bool = False
    deterministic: bool = True
    reward_func_factory: Optional[Any] = None
    env_kwargs: Dict[str, Any] = field(default_factory=dict)


class RLPortfolioStrategy(BaseStrategy):
    """包裝既有 EnhancedWalkForward，輸出 FinRL-X 介面。"""

    def __init__(self, config: RLPortfolioConfig):
        super().__init__(config)
        self.cfg: RLPortfolioConfig = config

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None,
    ) -> StrategyResult:
        processed_data = self._prepare_data(data)
        effective_target = target_date
        if effective_target is None:
            effective_target = min(
                pd.to_datetime(df.index).max() for df in processed_data.values()
            ).strftime("%Y-%m-%d")

        summary, weights_df, trades_df = self._run_walk_forward(processed_data)
        if weights_df.empty:
            weights_out = pd.DataFrame()
        elif pd.Timestamp(effective_target) in weights_df.index:
            weights_out = weights_df.loc[[pd.Timestamp(effective_target)]]
        else:
            weights_out = weights_df.loc[[weights_df.index[-1]]]

        prices = self._build_price_frame(processed_data)
        metadata = {
            "target_date": effective_target,
            "summary": summary,
            "weights_full": weights_df,
            "trades": trades_df,
            "prices": prices,
        }
        return StrategyResult(
            strategy_name=self.cfg.name,
            weights=weights_out,
            metadata=metadata,
        )

    def _prepare_data(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        processed: Dict[str, pd.DataFrame] = {}
        for ticker, df in data.items():
            local = df.copy()
            if "date" not in local.columns:
                local = local.reset_index()
                if "date" not in local.columns:
                    local = local.rename(columns={local.columns[0]: "date"})
            local["date"] = pd.to_datetime(local["date"]).dt.tz_localize(None)
            local = local.sort_values("date").set_index("date")
            if "tic" not in local.columns:
                local["tic"] = ticker
            processed[ticker] = local
        return processed

    def _build_price_frame(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        frames = []
        for ticker, df in data.items():
            if "close" not in df.columns:
                continue
            frames.append(df[["close"]].rename(columns={"close": ticker}))
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).sort_index()

    def _run_walk_forward(
        self,
        data: Dict[str, pd.DataFrame],
    ) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
        wf_module = _load_walk_forward_module()
        enhanced_walk_forward = wf_module.EnhancedWalkForward
        walk_forward_config = wf_module.WalkForwardConfig

        wf_config = walk_forward_config(
            train_window_years=self.cfg.train_window_years,
            test_window_days=self.cfg.test_window_days,
            timesteps=self.cfg.timesteps,
            agent_type=self.cfg.agent_type,
        )
        wf = enhanced_walk_forward(
            data,
            holdings=self.cfg.holdings or {},
            config=wf_config,
        )
        wf.run()

        summary = wf.summary()
        weights_list = []
        trades_list = []
        for result in getattr(wf, "test_results", []):
            if getattr(result, "weights_history", None) is not None:
                weights_list.append(result.weights_history)
            if getattr(result, "trades", None) is not None:
                trades_list.append(result.trades)

        weights_df = (
            pd.concat(weights_list, axis=0).sort_index()
            if weights_list
            else pd.DataFrame()
        )
        trades_df = (
            pd.concat(trades_list, axis=0).sort_index()
            if trades_list
            else pd.DataFrame()
        )

        if hasattr(summary, "to_dict"):
            summary_dict = summary.to_dict()
        elif isinstance(summary, dict):
            summary_dict = summary
        else:
            summary_dict = {"raw": str(summary)}

        return summary_dict, weights_df, trades_df


class RLCachedStrategy(RLPortfolioStrategy):
    """載入既有模型，直接產生每日權重歷史。"""

    _MODEL_LOADERS: Dict[str, Tuple[str, str]] = {
        "ppo": ("stable_baselines3", "PPO"),
        "a2c": ("stable_baselines3", "A2C"),
        "sac": ("stable_baselines3", "SAC"),
        "td3": ("stable_baselines3", "TD3"),
    }

    def __init__(
        self,
        config: RLPortfolioConfig,
        model_path: str,
    ):
        super().__init__(config)
        self.model_path = str(model_path)
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        algo_names = [self.cfg.agent_type.lower()]
        if algo_names[0] not in self._MODEL_LOADERS:
            algo_names = list(self._MODEL_LOADERS.keys())

        last_error: Optional[Exception] = None
        for algo_name in algo_names:
            module_name, class_name = self._MODEL_LOADERS[algo_name]
            try:
                module = __import__(module_name, fromlist=[class_name])
                model_cls = getattr(module, class_name)
                self._model = model_cls.load(self.model_path)
                logger.info("Loaded %s model from %s", algo_name.upper(), self.model_path)
                return self._model
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"Failed to load model {self.model_path}: {last_error}")

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None,
    ) -> StrategyResult:
        model = self._load_model()
        effective_target_date = self._resolve_target_date(data, target_date)
        prepared = self._prepare_inference_data(data, effective_target_date)

        weight_frames = []
        price_frames = []
        ticker_meta: Dict[str, Dict[str, Any]] = {}

        for ticker, df in prepared.items():
            ticker_weights, ticker_prices, meta = self._run_single_ticker_inference(
                ticker=ticker,
                df=df,
                model=model,
            )
            if not ticker_weights.empty:
                weight_frames.append(
                    ticker_weights[["weight"]].rename(columns={"weight": ticker})
                )
            if not ticker_prices.empty:
                price_frames.append(ticker_prices.rename(columns={"close": ticker}))
            ticker_meta[ticker] = meta

        if not weight_frames:
            raise ValueError("Inference produced no weights.")

        weights_full = pd.concat(weight_frames, axis=1).sort_index().ffill().fillna(0.0)
        weights_full = self._cap_total_exposure(weights_full)
        prices = (
            pd.concat(price_frames, axis=1).sort_index().ffill()
            if price_frames
            else pd.DataFrame()
        )

        return StrategyResult(
            strategy_name=self.cfg.name,
            weights=weights_full,
            metadata={
                "target_date": effective_target_date.strftime("%Y-%m-%d"),
                "weights_full": weights_full,
                "prices": prices,
                "model_path": self.model_path,
                "action_mode": self.cfg.action_mode,
                "per_ticker": ticker_meta,
            },
        )

    def _resolve_target_date(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str],
    ) -> pd.Timestamp:
        if target_date is not None:
            return pd.Timestamp(target_date).tz_localize(None)

        latest_dates = []
        for df in data.values():
            if "date" in df.columns:
                latest_dates.append(pd.to_datetime(df["date"]).max())
            else:
                latest_dates.append(pd.to_datetime(df.index).max())
        return pd.Timestamp(min(latest_dates)).tz_localize(None)

    def _prepare_inference_data(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: pd.Timestamp,
    ) -> Dict[str, pd.DataFrame]:
        prepared: Dict[str, pd.DataFrame] = {}
        for ticker, df in data.items():
            local = df.copy()
            if "date" not in local.columns:
                local = local.reset_index()
                if "date" not in local.columns:
                    local = local.rename(columns={local.columns[0]: "date"})
            local["date"] = pd.to_datetime(local["date"]).dt.tz_localize(None)
            local = (
                local[local["date"] <= target_date]
                .sort_values("date")
                .reset_index(drop=True)
            )
            if local.empty:
                continue

            required = {"open", "high", "low", "close", "volume"}
            missing = sorted(required - set(local.columns))
            if missing:
                raise ValueError(f"{ticker} is missing required columns: {missing}")
            prepared[ticker] = local
        return prepared

    def _build_env(self, df: pd.DataFrame) -> TaiwanStockTradingEnv:
        reward_func = (
            self.cfg.reward_func_factory()
            if callable(self.cfg.reward_func_factory)
            else None
        )
        env_kwargs = dict(self.cfg.env_kwargs)
        return TaiwanStockTradingEnv(
            df=df,
            initial_balance=self.cfg.initial_balance,
            max_position=self.cfg.max_position,
            trade_unit=self.cfg.trade_unit,
            commission_rate=self.cfg.commission_rate,
            tax_rate=self.cfg.tax_rate,
            lookback_window=self.cfg.lookback_window,
            include_dividends=self.cfg.include_dividends,
            reward_func=reward_func,
            action_mode=self.cfg.action_mode,
            **env_kwargs,
        )

    def _run_single_ticker_inference(
        self,
        ticker: str,
        df: pd.DataFrame,
        model: Any,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        env = self._build_env(df)
        obs, _ = env.reset()

        weight_records = []
        price_records = []
        last_info: Dict[str, Any] = {}

        while True:
            action, _ = model.predict(obs, deterministic=self.cfg.deterministic)
            obs, _, terminated, truncated, info = env.step(action)
            row_idx = min(env.current_step, len(env.df) - 1)
            date = pd.Timestamp(env.df.iloc[row_idx]["date"])
            close = float(env.df.iloc[row_idx]["close"])
            last_info = info

            weight_records.append(
                {
                    "date": date,
                    "weight": float(info.get("position_weight", 0.0)),
                    "portfolio_value": float(info.get("portfolio_value", 0.0)),
                }
            )
            price_records.append({"date": date, "close": close})

            if terminated or truncated:
                break

        weights = (
            pd.DataFrame(weight_records).set_index("date")
            if weight_records
            else pd.DataFrame(columns=["weight"])
        )
        prices = (
            pd.DataFrame(price_records).drop_duplicates("date").set_index("date")
            if price_records
            else pd.DataFrame(columns=["close"])
        )
        meta = {
            "final_weight": float(weights["weight"].iloc[-1]) if not weights.empty else 0.0,
            "final_portfolio_value": float(last_info.get("portfolio_value", 0.0)),
            "action_mode": self.cfg.action_mode,
        }
        return weights, prices, meta

    def _cap_total_exposure(self, weights: pd.DataFrame) -> pd.DataFrame:
        gross = weights.sum(axis=1)
        scale = gross.where(gross > 1.0, 1.0)
        return weights.div(scale, axis=0).fillna(0.0)
