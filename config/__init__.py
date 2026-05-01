"""
config 模組 - 系統設定
================================================================================
存放所有系統配置參數，包括：
    - 台股交易規則設定
    - Agent 超參數配置
    - 資料路徑設定
    - 回測參數設定
"""

from .taiwan_stock_config import *
from .hyperparameters import (
    PPO_CONFIG, 
    A2C_CONFIG,
    SHARED_CONFIG,
    TRAINING_CONFIG,
    EVALUATION_CONFIG,
)

__all__ = [
    'TAIWAN_STOCK_CONFIG',
    'STATE_CONFIG',
    'ACTION_CONFIG',
    'DATA_CONFIG',
    'BACKTEST_CONFIG',
    'INDICATOR_CONFIG',
    'DATA_SOURCE_CONFIG',
    'PPO_CONFIG',
    'A2C_CONFIG',
    'SHARED_CONFIG',
    'TRAINING_CONFIG',
    'EVALUATION_CONFIG',
]
