"""
RL Portfolio Strategy — 包裝 Isaac 既有的 walk_forward_v2 訓練邏輯
====================================================================
實作 FinRL-X 的 BaseStrategy 介面（weight-centric），
包裝 EnhancedWalkForward，把回測結果轉成 StrategyResult。

目標：現有 walk_forward_v2 的所有訓練邏輯不動，
      只在外面包一層 interface，滿足 FinRL-X 的統一介面。
"""
from __future__ import annotations
import sys
import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, StrategyConfig, StrategyResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 嘗試從既有的 Stock_TaiwanII 滙入 walk_forward_v2 核心
# ─────────────────────────────────────────────────────────────────────────────
_WALK_FORWARD_V2_PATH = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_Taiwan2-main/FinRL/walk_forward_v2.py"
_WALK_FORWARD_MODULE_NAME = "walk_forward_v2_loaded"

_loaded = False
_wf_module = None

try:
    if Path(_WALK_FORWARD_V2_PATH).exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location(_WALK_FORWARD_MODULE_NAME, _WALK_FORWARD_V2_PATH)
        _wf_module = importlib.util.module_from_spec(spec)
        sys.modules[_WALK_FORWARD_MODULE_NAME] = _wf_module
        spec.loader.exec_module(_wf_module)
        _loaded = True
        logger.info(f"Loaded walk_forward_v2 from {_WALK_FORWARD_V2_PATH}")
except Exception as e:
    logger.warning(f"Could not load walk_forward_v2: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Config
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RLPortfolioConfig(StrategyConfig):
    """RL 投資組合策略設定。"""
    name: str = "RLPortfolio"

    # Walk-forward window 參數
    train_window_years: float = 2.0
    test_window_days: int = 60
    timesteps: int = 50_000
    agent_type: str = "ppo"

    # 目標持倉（ticker → 張數）
    holdings: Optional[Dict[str, int]] = None

    # 模型快取：是否重用已訓練模型（避免每次都重train）
    reuse_models: bool = True

    # 這次 walk-forward 的 ID（用於 cache key）
    experiment_tag: str = ""


@dataclass
class TrainedModelCache:
    """已訓練模型的記憶體快取。"""
    models: Dict[str, Any] = field(default_factory=dict)
    configs: Dict[str, Dict] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# RL Portfolio Strategy
# ─────────────────────────────────────────────────────────────────────────────

class RLPortfolioStrategy(BaseStrategy):
    """
    包裝 Isaac 的 EnhancedWalkForward，實作 FinRL-X BaseStrategy 介面。

    使用方式：
        config = RLPortfolioConfig(
            name="portfolio_0050_0056",
            holdings={"0050.TW": 1000, "0056.TW": 2000},
            train_window_years=2.0,
            test_window_days=60,
            timesteps=50_000,
        )
        strategy = RLPortfolioStrategy(config)

        data = {"0050.TW": df_0050, "0056.TW": df_0056}   # OHLCV DataFrames
        result = strategy.generate_weights(data, target_date="2025-01-15")

        # result.weights 是 pd.DataFrame，指數為日期，直列為 ticker，值為權重
        # result.metadata 包含完整 walk-forward 回測指標
    """

    def __init__(self, config: RLPortfolioConfig):
        super().__init__(config)
        self.cfg: RLPortfolioConfig = config
        self._model_cache = TrainedModelCache()
        self._last_train_end: Optional[str] = None  # 快取追蹤

    # ─────────────────────────── BaseStrategy 實作 ────────────────────────

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None,
    ) -> StrategyResult:
        """
        給定 OHLCV 數據，產生 RL 優化後的投資組合權重。

        流程：
          1. 根據 target_date 找出 train/test 視窗
          2. 訓練（或重用）PPO 模型
          3. 在 test 視窗跑回測，計算每日倉位
          4. 回傳最後一天的目標權重 + 完整回測 metadata
        """
        if not _loaded or _wf_module is None:
            raise RuntimeError(
                "walk_forward_v2.py not loaded. "
                f"Check path {_WALK_FORWARD_V2_PATH}"
            )

        # ── 1. 資料格式轉換 ────────────────────────────────────────────
        # data: {ticker: df} → walk_forward_v2 格式
        processed_data = self._prepare_data(data)

        # ── 2. 決定訓練截止日期（target_date 或 today）───────────────────
        if target_date is None:
            target_date = datetime.today().strftime("%Y-%m-%d")

        # ── 3. 執行 walk-forward（內部會訓練 + 回測）──────────────────
        summary, weights_df, trades_df = self._run_walk_forward(
            processed_data, target_date
        )

        # ── 4. 轉成 StrategyResult ───────────────────────────────────────
        # 取 target_date 當天的權重（沒有的話取最近）
        if weights_df.empty:
            weights_out = pd.DataFrame()
        else:
            if target_date in weights_df.index:
                weights_out = weights_df.loc[[target_date]]
            else:
                # 取最近
                last_date = weights_df.index[-1]
                weights_out = weights_df.loc[[last_date]]

        metadata = {
            "target_date": target_date,
            "summary": summary,           # WalkForwardResult dict
            "weights_full": weights_df,   # 完整權重時間序列
            "trades": trades_df,          # 交易記錄
        }

        return StrategyResult(
            strategy_name=self.cfg.name,
            weights=weights_out,
            metadata=metadata,
        )

    # ─────────────────────────── 內部方法 ─────────────────────────────────

    def _prepare_data(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        確保 data 格式與 walk_forward_v2 相容：
        - 欄位：date, open, high, low, close, volume, tic
        - date 為 index 或普通欄位皆可
        """
        processed = {}
        for ticker, df in data.items():
            df = df.copy()
            if "date" not in df.columns and df.index.name == "date":
                df = df.reset_index()
            if "tic" not in df.columns:
                df["tic"] = ticker
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
            processed[ticker] = df
        return processed

    def _run_walk_forward(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: str,
    ) -> Tuple[Dict, pd.DataFrame, pd.DataFrame]:
        """
        實際呼叫 walk_forward_v2 的 EnhancedWalkForward。
        回傳 (summary, weights_df, trades_df)。
        """
        EnhancedWalkForward = _wf_module.EnhancedWalkForward
        WalkForwardConfig = _wf_module.WalkForwardConfig

        wf_config = WalkForwardConfig(
            train_window_years=self.cfg.train_window_years,
            test_window_days=self.cfg.test_window_days,
            timesteps=self.cfg.timesteps,
            agent_type=self.cfg.agent_type,
        )

        wf = EnhancedWalkForward(
            data,
            holdings=self.cfg.holdings or {},
            config=wf_config,
        )

        try:
            wf.run()
            summary = wf.summary()
            wf.print_summary()
        except Exception as e:
            logger.error(f"Walk-forward failed: {e}")
            raise

        # 從 wf 取 weights 和 trades
        # walk_forward_v2 內部以 self.test_results[i].weights_history 儲存
        weights_list = []
        trades_list = []

        for res in getattr(wf, "test_results", []):
            if hasattr(res, "weights_history") and res.weights_history is not None:
                weights_list.append(res.weights_history)
            if hasattr(res, "trades") and res.trades is not None:
                trades_list.append(res.trades)

        if weights_list:
            weights_df = pd.concat(weights_list, axis=0)
        else:
            weights_df = pd.DataFrame()

        if trades_list:
            trades_df = pd.concat(trades_list, axis=0)
        else:
            trades_df = pd.DataFrame()

        # summary → dict
        if hasattr(summary, "to_dict"):
            summary_dict = summary.to_dict()
        elif isinstance(summary, dict):
            summary_dict = summary
        else:
            summary_dict = {"raw": str(summary)}

        return summary_dict, weights_df, trades_df


# ─────────────────────────────────────────────────────────────────────────────
# 簡化版本：用已訓練模型直接預測（不重train，Phase 2/3 用）
# ─────────────────────────────────────────────────────────────────────────────

class RLCachedStrategy(RLPortfolioStrategy):
    """
    讀取既有的已訓練模型，不重train，直接做 inference。
    適用於日常自動交易（每天先生成 weights，再對接 Alpaca）。

    使用方式：
        strategy = RLCachedStrategy(
            model_path="FinRL/models/portfolio/best_model",
            tickers=["0050.TW", "0056.TW"],
        )
        result = strategy.generate_weights(data, target_date="2025-06-01")
    """

    def __init__(
        self,
        config: RLPortfolioConfig,
        model_path: str,
    ):
        super().__init__(config)
        self.model_path = model_path
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from stable_baselines3 import PPO
            self._model = PPO.load(self.model_path)
            logger.info(f"Loaded model from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None,
    ) -> StrategyResult:
        """
        直接用已訓練模型預測，不重train。
        """
        self._load_model()
        # TODO: 呼叫 env.predict(model, obs) 取得 action → 轉 weight
        # 實作細節取決於 taiwan_stock_env 的 action space 設計
        raise NotImplementedError(
            "RLCachedStrategy.generate_weights() — "
            "需依據 taiwan_stock_env 的 action space 實作"
        )