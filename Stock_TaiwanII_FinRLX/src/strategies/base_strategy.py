"""
Base Strategy Interface — FinRL-X weight-centric interface
===========================================================
所有策略（RL、規則、ML）都必須實作此介面，確保 backtest 與 live trading 一致。
從 AI4Finance-Foundation/FinRL-Trading/src/strategies/base_strategy.py 移植。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import pandas as pd


@dataclass
class StrategyResult:
    """
    策略輸出結構 — weight-centric 的核心。
    backtest_engine 和 trade_executor 都只認這個格式。
    """
    strategy_name: str
    weights: pd.DataFrame          # index=date, columns=tickers, values=weight (0~1)
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class StrategyConfig:
    """策略設定基底類別。"""
    name: str = "BaseStrategy"


class BaseStrategy:
    """
    所有策略的抽象基底。

    實作流程：
      1. __init__(config)       — 初始化設定
      2. generate_weights(data, target_date) → StrategyResult

    data 格式（由 data_loader 統一餵入）：
      Dict[str, pd.DataFrame] — key=ticker, value=OHLCV DataFrame
    """

    def __init__(self, config: StrategyConfig):
        self.config = config

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None
    ) -> StrategyResult:
        """
        給定市場數據，產生目標權重。

        Args:
            data: {ticker: df}，df 必須有 date/open/high/low/close/volume 欄位
            target_date: 計算日期（字串，YYYY-MM-DD）

        Returns:
            StrategyResult(weights=weights_df)
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement generate_weights()"
        )