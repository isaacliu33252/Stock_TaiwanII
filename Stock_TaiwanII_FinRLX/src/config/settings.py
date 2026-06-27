"""
Configuration Settings — FinRL-X 台股系統
=========================================
移植 FinRL-X 的 Pydantic BaseSettings 結構，
保留 Isaac 既有的所有參數（台股規則、PPO 超參數、技術指標）。
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import SecretStr


# ─────────────────────────────────────────────────────────────────────────────
# 一、台股交易規則（從 Isaac config.py 移植）
# ─────────────────────────────────────────────────────────────────────────────
PRICE_LIMIT_PERCENT = 10.0          # 漲跌停限制（%）
MIN_TRADE_UNIT = 1000                # 最小交易單位（1000股 = 1張）
MAX_DAILY_TRADE_RATIO = 0.5         # 單日最大交易量比例
SETTLEMENT_DAYS = 2                  # T+2 交割
TRANSACTION_TAX_RATE = 0.003        # 交易稅（賣出收取，0.3%）
BROKERAGE_FEE_RATE = 0.001425       # 券商手續費（買賣皆收）
MIN_BROKERAGE_FEE = 20.0            # 每次最低手續費

# ─────────────────────────────────────────────────────────────────────────────
# 二、技術指標參數
# ─────────────────────────────────────────────────────────────────────────────
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
MA_SHORT = 5
MA_MEDIUM = 20
MA_LONG = 60
ATR_PERIOD = 14
KD_PERIOD = 9
KD_SMOOTH_K = 3
KD_SMOOTH_D = 3

# ─────────────────────────────────────────────────────────────────────────────
# 三、PPO 超參數（預設值，可被 yaml/args 覆寫）
# ─────────────────────────────────────────────────────────────────────────────
PPO_CONFIG = {
    "learning_rate": 3e-4,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "clip_range": 0.2,
    "clip_range_vf": None,
    "ent_coef": 0.0,
    "vf_coef": 0.5,
    "max_grad_norm": 0.5,
    "target_kl": None,
    "verbose": 1,
}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Settings（FinRL-X 結構，擴展支援台股）
# ─────────────────────────────────────────────────────────────────────────────

class DataSettings(BaseSettings):
    """資料目錄設定。"""
    base_dir: str = "./data"
    cache_dir: str = "./data/cache"
    processed_dir: str = "./data/processed"
    raw_dir: str = "./data/raw"
    cache_ttl_hours: int = 24
    max_cache_size_mb: int = 1000

    class Config:
        env_prefix = "DATA_"
        extra = "allow"

    def get_database_path(self) -> Path:
        return Path(self.base_dir) / "finrl_trading.db"


class AlpacaSettings(BaseSettings):
    """Alpaca API 設定。"""
    api_key: Optional[str] = Field(default=None, env="APCA_API_KEY")
    api_secret: Optional[str] = Field(default=None, env="APCA_API_SECRET")
    base_url: str = Field(default="https://paper-api.alpaca.markets", env="APCA_BASE_URL")
    use_paper_trading: bool = True

    class Config:
        env_prefix = "APCA_"
        extra = "allow"


class StrategySettings(BaseSettings):
    """策略全域設定。"""
    default_rebalance_freq: str = "Q"
    max_weight_per_stock: float = 0.3
    max_sector_weight: float = 0.5
    max_turnover: float = 0.5
    risk_free_rate: float = 0.02
    benchmark_tickers: List[str] = ["0050.TW", "0056.TW"]
    # 台股特有
    price_limit_percent: float = PRICE_LIMIT_PERCENT
    min_trade_unit: int = MIN_TRADE_UNIT
    max_daily_trade_ratio: float = MAX_DAILY_TRADE_RATIO

    class Config:
        env_prefix = "STRATEGY_"
        extra = "allow"


class LoggingSettings(BaseSettings):
    """日誌設定。"""
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    class Config:
        env_prefix = "LOG_"
        extra = "allow"


class Settings(BaseSettings):
    """FinRL-X 台股系統總設定。"""

    # Meta
    version: str = "0.1.0"
    environment: str = Field(default="paper", env="ENVIRONMENT")  # paper | live

    # Sub-sections
    data: DataSettings = Field(default_factory=DataSettings)
    alpaca: AlpacaSettings = Field(default_factory=AlpacaSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # Derived
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

    # ──────────────────────────── helpers ──────────────────────────────────

    def get_data_dir(self) -> Path:
        return self.project_root / self.data.base_dir

    def get_model_dir(self) -> Path:
        return self.project_root / "models"

    def is_paper(self) -> bool:
        return self.environment.lower() == "paper"


# ─────────────────────────────────────────────────────────────────────────────
#  Singleton accessor（與 FinRL-X main.py API 保持一致）
# ─────────────────────────────────────────────────────────────────────────────
_settings_instance: Optional[Settings] = None


def get_config() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance