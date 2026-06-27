"""
Base Strategy Interface — FinRL-X weight-centric interface
===========================================================
所有策略（RL、規則、ML）都可透過這個結構輸出權重，讓 backtest 與 live/trade
executor 共用同一個介面。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class StrategyResult:
    """
    策略輸出結構。

    `weights`:
        index=date, columns=tickers, values=weight
    """

    strategy_name: str
    weights: pd.DataFrame
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class StrategyConfig:
    name: str = "BaseStrategy"


class BaseStrategy:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None,
    ) -> StrategyResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement generate_weights()"
        )
