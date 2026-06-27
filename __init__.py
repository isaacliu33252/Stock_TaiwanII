"""
FinRL 台股量化交易系統 (FinRL Taiwan Stock Trading System)
================================================================================
本系統基於深度強化學習 (Deep Reinforcement Learning) 設計，用於台股自動化交易。

主要模組:
    - data: 數據處理與特徵工程
    - environments: Gym-style 交易環境
    - agents: PPO/A2C 代理模型
    - backtesting: 回測與績效評估
    - results: 訓練結果與模型儲存

台股特殊規則:
    - 涨跌停 10% 限制
    - T+2 交割制度
    - 最小交易單位 1000 股
    - 交易時間 09:00-13:30

版本: v1.0.0
作者: FinRL量化交易專家
"""

__version__ = "1.0.0"
__author__ = "FinRL Taiwan Team"

__all__ = ["data", "environments", "agents", "backtesting", "results"]

# Only eager-import subpackages when this file is imported as a real package.
# Pytest can also collect this root __init__.py as a standalone module, where
# relative imports have no parent package and would fail before tests run.
if __package__:
    from . import agents
    from . import backtesting
    from . import data
    from . import environments
    from . import results
