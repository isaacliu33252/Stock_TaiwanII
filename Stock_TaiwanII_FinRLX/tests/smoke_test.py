#!/usr/bin/env python3
"""
Smoke test — 驗證 Stock_TaiwanII_FinRLX 核心模組可以正常 import。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

print("=== Stock_TaiwanII_FinRLX Smoke Test ===\n")

tests = []

# 1. Config
try:
    from src.config.settings import get_config, Settings
    cfg = get_config()
    print(f"OK Config loaded  (env={cfg.environment}, data={cfg.get_data_dir()})")
    tests.append(True)
except Exception as e:
    print(f"FAIL Config: {e}")
    tests.append(False)

# 2. Base Strategy
try:
    from src.strategies.base_strategy import BaseStrategy, StrategyResult, StrategyConfig
    import pandas as pd
    result = StrategyResult(
        strategy_name="test",
        weights=pd.DataFrame({"0050.TW": [0.6], "0056.TW": [0.4]}, index=pd.to_datetime(["2025-01-01"])),
        metadata={"sharpe": 1.5},
    )
    print(f"OK StrategyResult (weights shape={result.weights.shape})")
    tests.append(True)
except Exception as e:
    print(f"FAIL StrategyResult: {e}")
    tests.append(False)

# 3. Backtest Engine (import only)
try:
    from src.backtest.backtest_engine import BacktestEngine, BacktestConfig
    be_cfg = BacktestConfig(start_date="2024-01-01", end_date="2024-12-31")
    be = BacktestEngine(be_cfg)
    print(f"OK BacktestEngine (start={be_cfg.start_date})")
    tests.append(True)
except Exception as e:
    print(f"FAIL BacktestEngine: {e}")
    tests.append(False)

# 4. Alpaca Manager (import only, no real API call)
try:
    from src.trading.alpaca_manager import AlpacaManager, AlpacaAccount
    print("OK AlpacaManager imported")
    tests.append(True)
except Exception as e:
    print(f"FAIL AlpacaManager: {e}")
    tests.append(False)

# 5. RL Portfolio Strategy (import + path check)
try:
    from src.strategies.rl_portfolio_strategy import RLPortfolioStrategy, RLPortfolioConfig
    cfg2 = RLPortfolioConfig(name="test", holdings={"0050.TW": 1000})
    wf_path = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_Taiwan2-main/FinRL/walk_forward_v2.py")
    print(f"OK RLPortfolioStrategy (walk_forward_v2 exists: {wf_path.exists()})")
    tests.append(True)
except Exception as e:
    print(f"FAIL RLPortfolioStrategy: {e}")
    tests.append(False)

# 6. Data Loader (import only)
try:
    from src.data.data_loader import TaiwanDataLoader
    print("OK TaiwanDataLoader imported")
    tests.append(True)
except Exception as e:
    print(f"FAIL TaiwanDataLoader: {e}")
    tests.append(False)

print(f"\n{'='*40}")
print(f"Result: {sum(tests)}/{len(tests)} passed")
if all(tests):
    print("All checks passed!")
else:
    print("Some checks failed.")
    print("\nNote: Missing deps (pydantic, bt, alpaca) are OK — install with:")
    print("  pip install pydantic pydantic-settings bt  requests")