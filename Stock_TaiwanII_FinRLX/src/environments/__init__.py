# src/environments/__init__.py
"""
Environment wrappers for FinRL-X台股系統

本目錄用於存放 Gymnasium/gym 環境包裝。
核心邏輯在 Stock_TaiwanII 的 FinRL/environments/ 目錄，
這裡只做介面轉接（import + 重新 export）。
"""
import sys
from pathlib import Path

# 指向既有的 Isaac 環境實作
_ORIGINAL_ENV_PATH = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_Taiwan2-main/FinRL/environments")
if _ORIGINAL_ENV_PATH.exists():
    sys.path.insert(0, str(_ORIGINAL_ENV_PATH.parent.parent))
    sys.modules["environments"] = __import__("environments")
else:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "FinRL"))
    from environments import *

__all__ = ["TaiwanStockTradingEnv", "DynamicRewardShaper", "SafeActorCriticPolicy"]