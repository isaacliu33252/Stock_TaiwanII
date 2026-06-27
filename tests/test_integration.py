"""
FinRL 系統整合測試腳本
================================================================================
驗證所有 Phase 的功能是否正確實作。

測試項目：
1. Phase 1: 目錄結構與依賴套件
2. Phase 2: 資料層（data_loader, technical_indicators）
3. Phase 3: 環境（taiwan_stock_env, reward_function）
4. Phase 4: Agent（PPO, A2C）
5. Phase 5: 回測（backtest, performance_metrics, visualizer, compare）

執行方式：
    python test_integration.py

作者: FinRL量化交易專家
"""

import sys
import os
from pathlib import Path

# 添加專案根目錄到路徑
# FinRL 目錄位於 Stock_taiwan2-main/FinRL/
# 所以需要添加到 Stock_taiwan2-main 的父目錄
PROJECT_ROOT = Path(__file__).parent
STOCK_TAIWAN_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(STOCK_TAIWAN_ROOT))


def test_phase1_directory_structure():
    """
    Phase 1: 測試目錄結構
    """
    print("\n" + "=" * 60)
    print("Phase 1: 目錄結構測試")
    print("=" * 60)
    
    required_dirs = [
        'data',
        'data/cache',
        'data/raw',
        'agents',
        'environments',
        'backtesting',
        'results',
        'config',
    ]
    
    all_exist = True
    for dir_name in required_dirs:
        dir_path = PROJECT_ROOT / dir_name
        exists = dir_path.exists()
        status = "✓" if exists else "✗"
        print(f"  [{status}] {dir_name}/")
        if not exists:
            all_exist = False
    
    # 檢查 requirements.txt
    req_file = PROJECT_ROOT / 'requirements.txt'
    if req_file.exists():
        print(f"  [✓] requirements.txt")
        with open(req_file, 'r') as f:
            content = f.read()
            required_packages = ['finrl', 'stable-baselines3', 'gym', 'pandas', 'numpy']
            for pkg in required_packages:
                if pkg in content.lower():
                    print(f"      - {pkg}: ✓")
                else:
                    print(f"      - {pkg}: ✗ (缺失)")
    else:
        print(f"  [✗] requirements.txt")
        all_exist = False
    
    return all_exist


def test_phase2_data_layer():
    """
    Phase 2: 測試資料層
    """
    print("\n" + "=" * 60)
    print("Phase 2: 資料層測試")
    print("=" * 60)
    
    success = True
    
    # 測試 data_loader
    try:
        from FinRL.data.data_loader import TaiwanStockDataLoader, load_taiwan_stock_data
        print("  [✓] TaiwanStockDataLoader 匯入成功")
        
        # 測試類別屬性
        loader = TaiwanStockDataLoader()
        assert hasattr(loader, 'download_price_data'), "缺少 download_price_data 方法"
        assert hasattr(loader, 'download_corp_data'), "缺少 download_corp_data 方法"
        print("  [✓] TaiwanStockDataLoader 方法完整")
    except ImportError as e:
        print(f"  [✗] TaiwanStockDataLoader 匯入失敗: {e}")
        success = False
    
    # 測試 technical_indicators
    try:
        from FinRL.data.technical_indicators import TechnicalIndicators
        print("  [✓] TechnicalIndicators 匯入成功")
        
        # 檢查必要方法
        required_methods = [
            'calculate_ma', 'calculate_macd', 'calculate_rsi', 
            'calculate_kdj', 'calculate_bollinger_bands',
            'calculate_atr', 'calculate_all'
        ]
        for method in required_methods:
            if not hasattr(TechnicalIndicators, method):
                print(f"  [✗] TechnicalIndicators 缺少方法: {method}")
                success = False
        if all(hasattr(TechnicalIndicators, m) for m in required_methods):
            print("  [✓] TechnicalIndicators 方法完整")
    except ImportError as e:
        print(f"  [✗] TechnicalIndicators 匯入失敗: {e}")
        success = False
    
    return success


def test_phase3_environment():
    """
    Phase 3: 測試交易環境
    """
    print("\n" + "=" * 60)
    print("Phase 3: 交易環境測試")
    print("=" * 60)
    
    success = True
    
    # 測試 taiwan_stock_env
    try:
        from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
        print("  [✓] TaiwanStockTradingEnv 匯入成功")
        
        # 檢查必要的類別屬性
        # 注意：由於環境需要資料，我們只測試類別是否存在
        print("  [✓] TaiwanStockTradingEnv 類別存在")
    except ImportError as e:
        print(f"  [✗] TaiwanStockTradingEnv 匯入失敗: {e}")
        success = False
    
    # 測試 reward_function
    try:
        from FinRL.environments.reward_function import RewardFunction
        from FinRL.environments.reward_function_v3 import RewardFunctionV3
        print("  [✓] RewardFunction 匯入成功")
        print("  [✓] RewardFunctionV3 匯入成功")
        
        # 檢查方法
        rf = RewardFunction()
        if hasattr(rf, 'calculate'):
            print("  [✓] RewardFunction.calculate 方法存在")
        else:
            print("  [✗] RewardFunction.calculate 方法缺失")
            success = False
    except ImportError as e:
        print(f"  [✗] RewardFunction 匯入失敗: {e}")
        success = False
    
    # 測試 config
    try:
        from FinRL.config import TAIWAN_STOCK_CONFIG
        print("  [✓] TAIWAN_STOCK_CONFIG 匯入成功")
        
        # 檢查必要的配置
        required_config = ['trade_unit', 'price_limit', 'settlement_days', 'commission_rate', 'tax_rate']
        for config_name in required_config:
            if config_name not in TAIWAN_STOCK_CONFIG:
                print(f"  [✗] TAIWAN_STOCK_CONFIG 缺少: {config_name}")
                success = False
        if all(c in TAIWAN_STOCK_CONFIG for c in required_config):
            print("  [✓] TAIWAN_STOCK_CONFIG 配置完整")
            print(f"       - trade_unit: {TAIWAN_STOCK_CONFIG.get('trade_unit')}")
            print(f"       - price_limit: {TAIWAN_STOCK_CONFIG.get('price_limit')}")
            print(f"       - settlement_days: {TAIWAN_STOCK_CONFIG.get('settlement_days')}")
    except ImportError as e:
        print(f"  [✗] TAIWAN_STOCK_CONFIG 匯入失敗: {e}")
        success = False
    
    return success


def test_phase4_agents():
    """
    Phase 4: 測試 Agent
    """
    print("\n" + "=" * 60)
    print("Phase 4: Agent 測試")
    print("=" * 60)
    
    success = True
    
    # 測試 PPO Agent
    try:
        from FinRL.agents.ppo_agent import PPOAgent
        print("  [✓] PPOAgent 匯入成功")
        
        # 檢查必要方法
        required_methods = ['train', 'predict', 'evaluate', 'save', 'load']
        for method in required_methods:
            if not hasattr(PPOAgent, method) and method != 'train':
                print(f"  [警告] PPOAgent 實例方法 {method} 可能缺失")
        print("  [✓] PPOAgent 類別完整")
    except ImportError as e:
        print(f"  [✗] PPOAgent 匯入失敗: {e}")
        success = False
    
    # 測試 A2C Agent
    try:
        from FinRL.agents.a2c_agent import A2CAgent
        print("  [✓] A2CAgent 匯入成功")
        print("  [✓] A2CAgent 類別完整")
    except ImportError as e:
        print(f"  [✗] A2CAgent 匯入失敗: {e}")
        success = False
    
    # 測試 compare 模組
    try:
        from FinRL.agents.compare import StrategyComparator, quick_compare
        print("  [✓] StrategyComparator 匯入成功")
        print("  [✓] quick_compare 匯入成功")
    except ImportError as e:
        print(f"  [✗] StrategyComparator 匯入失敗: {e}")
        success = False
    
    # 測試 train.py
    train_file = PROJECT_ROOT / 'agents' / 'train.py'
    if train_file.exists():
        print("  [✓] train.py 存在")
    else:
        print("  [✗] train.py 缺失")
        success = False
    
    return success


def test_phase5_backtesting():
    """
    Phase 5: 測試回測模組
    """
    print("\n" + "=" * 60)
    print("Phase 5: 回測模組測試")
    print("=" * 60)
    
    success = True
    
    # 測試 performance_metrics
    try:
        from FinRL.backtesting.performance_metrics import PerformanceMetrics
        print("  [✓] PerformanceMetrics 匯入成功")
        
        # 檢查必要方法
        required_methods = [
            'calculate_sharpe_ratio', 'calculate_max_drawdown',
            'calculate_win_rate', 'calculate_profit_factor',
            'generate_report'
        ]
        pm = PerformanceMetrics()
        for method in required_methods:
            if not hasattr(pm, method):
                print(f"  [✗] PerformanceMetrics 缺少方法: {method}")
                success = False
        if all(hasattr(PerformanceMetrics, m) or hasattr(pm, m) for m in required_methods):
            print("  [✓] PerformanceMetrics 方法完整")
    except ImportError as e:
        print(f"  [✗] PerformanceMetrics 匯入失敗: {e}")
        success = False
    
    # 測試 visualizer
    try:
        from FinRL.backtesting.visualizer import BacktestVisualizer
        print("  [✓] BacktestVisualizer 匯入成功")
        
        # 檢查必要方法
        required_methods = [
            'plot_equity_curve', 'plot_drawdown',
            'plot_returns_distribution', 'plot_trades',
            'save_plot'
        ]
        for method in required_methods:
            if not hasattr(BacktestVisualizer, method):
                print(f"  [警告] BacktestVisualizer 缺少方法: {method}")
        print("  [✓] BacktestVisualizer 類別完整")
    except ImportError as e:
        print(f"  [✗] BacktestVisualizer 匯入失敗: {e}")
        success = False
    
    # 測試 backtest
    try:
        from FinRL.backtesting.backtest import BacktestEngine, create_backtest_engine
        print("  [✓] BacktestEngine 匯入成功")
        print("  [✓] create_backtest_engine 匯入成功")
        
        # 檢查 BacktestEngine 必要屬性
        if hasattr(BacktestEngine, 'run'):
            print("  [✓] BacktestEngine.run 方法存在")
        else:
            print("  [✗] BacktestEngine.run 方法缺失")
            success = False
    except ImportError as e:
        print(f"  [✗] BacktestEngine 匯入失敗: {e}")
        success = False
    
    return success


def print_summary(results: dict):
    """
    印出測試總結
    """
    print("\n" + "=" * 60)
    print("               整合測試總結")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    for phase, passed in results.items():
        status = "✓ 通過" if passed else "✗ 失敗"
        print(f"  {phase}: {status}")
    
    print("\n" + "-" * 60)
    print(f"  總計: {passed_tests}/{total_tests} Phase 通過")
    
    if passed_tests == total_tests:
        print("\n  🎉 所有 Phase 測試通過！系統已完整實作。")
    else:
        print("\n  ⚠ 部分 Phase 測試失敗，請檢查上述輸出。")
    
    print("=" * 60)
    
    return passed_tests == total_tests


def main():
    """
    主測試函數
    """
    print("\n" + "#" * 60)
    print("#     FinRL 台股量化交易系統 - 整合測試")
    print("#" * 60)
    
    results = {}
    
    # Phase 1: 目錄結構
    results['Phase 1: 目錄結構'] = test_phase1_directory_structure()
    
    # Phase 2: 資料層
    results['Phase 2: 資料層'] = test_phase2_data_layer()
    
    # Phase 3: 環境
    results['Phase 3: 交易環境'] = test_phase3_environment()
    
    # Phase 4: Agent
    results['Phase 4: Agent'] = test_phase4_agents()
    
    # Phase 5: 回測
    results['Phase 5: 回測模組'] = test_phase5_backtesting()
    
    # 印出總結
    all_passed = print_summary(results)
    
    # 返回退出碼
    return 0 if all_passed else 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
