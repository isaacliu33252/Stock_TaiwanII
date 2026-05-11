"""
config 模組 - 系統設定
================================================================================
存放所有系統配置參數，包括：
    - 台股交易規則設定
    - Agent 超參數配置
    - 資料路徑設定
    - 回測參數設定
"""

from .taiwan_stock_config import (
    TAIWAN_STOCK_CONFIG,
    BACKTEST_CONFIG,
    DATA_CONFIG,
    DATA_SOURCE_CONFIG,
    INDICATOR_CONFIG,
    STATE_CONFIG,
    ACTION_CONFIG,
)
from .hyperparameters import (
    PPO_CONFIG,
    A2C_CONFIG,
    SHARED_CONFIG,
    TRAINING_CONFIG,
    EVALUATION_CONFIG,
)

# Load config.py values dynamically for backwards compatibility
# Many internal scripts do `from config import X` which resolves to this package
# while the actual values are defined in the sibling FinRL/config.py
import os
import sys
from pathlib import Path

_config_py = Path(__file__).parent.parent / "config.py"
if _config_py.exists():
    _ns = {'os': os, 'sys': sys}
    with open(_config_py) as _f:
        _code = _f.read()
    try:
        exec(compile(_code, str(_config_py), 'exec'), _ns)
    except Exception as e:
        print(f"[config] Warning: could not load config.py: {e}")

    # Import public symbols into this module
    for _k, _v in _ns.items():
        if not _k.startswith('_') and _k not in ('os', 'sys'):
            globals()[_k] = _v

# Also handle PPO_CONFIG / A2C_CONFIG from hyperparameters.py
# (hyperparameters.py has type annotations that may conflict)
try:
    from . import hyperparameters
    for _k in dir(hyperparameters):
        if not _k.startswith('_') and _k not in ('Dict', 'Any'):
            globals()[_k] = getattr(hyperparameters, _k)
except Exception:
    pass

__all__ = [
    # taiwan_stock_config
    "TAIWAN_STOCK_CONFIG",
    "BACKTEST_CONFIG",
    "DATA_CONFIG",
    "DATA_SOURCE_CONFIG",
    "INDICATOR_CONFIG",
    "STATE_CONFIG",
    "ACTION_CONFIG",
    # hyperparameters
    "PPO_CONFIG",
    "A2C_CONFIG",
    "SHARED_CONFIG",
    "TRAINING_CONFIG",
    "EVALUATION_CONFIG",
]
