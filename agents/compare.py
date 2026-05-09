# ============================================================================
# 比較腳本 (Compare FinRL vs Backtrader Strategies)
# ============================================================================
"""
比較 FinRL 強化學習策略與現有 Backtrader 傳統策略的表現。

比較項目：
- 總報酬率 (Total Return)
- 年化報酬率 (Annual Return)
- 夏普比率 (Sharpe Ratio)
- 最大回撤 (Max Drawdown)
- 勝率 (Win Rate)
- 利潤因子 (Profit Factor)

現有 Backtrader 策略：
- tech1_ma_strategy.py: MA 均線交叉策略 (fast=3, slow=60)
- tech2_highest.py: 最高價突破策略
- tech3_macd_ma.py: MACD + MA 複合策略

使用方式：
    python FinRL/agents/compare.py --stock 2330 --finrl_agent ppo \\
        --backtest_start 2022-01-01 --backtest_end 2024-12-31

作者: FinRL量化交易專家
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 添加路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from FinRL.backtesting.backtest import BacktestEngine, calculate_sharpe_ratio, calculate_max_drawdown
from FinRL.backtesting.performance_metrics import calculate_all_metrics
from FinRL.results.result_tracker import ResultTracker
from FinRL.results.plotter import TradingPlotter


# ============================================================================
# Backtrader MA 策略回測
# ============================================================================

def run_backtrader_ma_strategy(
    symbol: str,
    start_date: str,
    end_date: str,
    initial_balance: float = 1_000_000,
    fast_period: int = 3,
    slow_period: int = 60
) -> Dict:
    """
    執行 Backtrader MA 交叉策略回測
    
    策略規則：
    - 當快速 MA 上穿慢速 MA → 買入
    - 當快速 MA 下穿慢速 MA → 賣出
    
    參數：
        symbol: 股票代碼
        start_date: 開始日期
        end_date: 結束日期
        initial_balance: 初始資金
        fast_period: 快速 MA 期間
        slow_period: 慢速 MA 期間
    
    返回：
        回測結果字典
    """
    print("\n" + "=" * 70)
    print(f"          Backtrader MA 策略回測 (MA{fast_period}/{slow_period})")
    print("=" * 70)
    
    try:
        import backtrader as bt
        import yfinance as yf
    except ImportError:
        print("[Compare] Backtrader 或 yfinance 未安裝")
        return {}
    
    # 下載數據
    yf_symbol = symbol if '.TW' in symbol else f"{symbol}.TW"
    print(f"[Backtrader] 下載 {yf_symbol}...")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        data = ticker.history(start=start_date, end=end_date)
        
        if data.empty:
            print(f"[Backtrader] 無資料")
            return {}
    except Exception as e:
        print(f"[Backtrader] 下載失敗: {e}")
        return {}
    
    # 建立策略
    class MAStrategy(bt.Strategy):
        params = (
            ('fast_period', fast_period),
            ('slow_period', slow_period),
        )
        
        def __init__(self):
            self.dataclose = self.datas[0].close
            self.order = None
            
            # MA 指標
            self.sma_fast = bt.ind.SMA(self.datas[0].close, period=self.params.fast_period)
            self.sma_slow = bt.ind.SMA(self.datas[0].close, period=self.params.slow_period)
            
            # 交叉信號
            self.crossover = bt.ind.CrossOver(self.sma_fast, self.sma_slow)
        
        def notify_order(self, order):
            if order.status in [order.Submitted, order.Accepted]:
                return
            
            if order.status in [order.Completed]:
                if order.isbuy():
                    pass
                else:
                    pass
            
            self.order = None
        
        def next(self):
            if self.order:
                return
            
            if not self.position:
                # 沒有持倉，檢查買入信號
                if self.crossover > 0:  # 金叉
                    self.order = self.buy()
            else:
                # 有持倉，檢查賣出信號
                if self.crossover < 0:  # 死叉
                    self.order = self.sell()
    
    # 執行回測
    cerebro = bt.Cerebro()
    cerebro.addstrategy(MAStrategy, fast_period=fast_period, slow_period=slow_period)
    
    # 添加數據
    data_feed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(data_feed)
    
    # 設置經紀商
    cerebro.broker.setcash(initial_balance)
    cerebro.broker.setcommission(commission=0.0015)  # 0.15% 佣金
    cerebro.addsizer(bt.sizers.SizerFix, stake=1000)  # 1000 股為單位
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    # 執行
    print(f"[Backtrader] 初始資金: {initial_balance:,.0f}")
    results = cerebro.run()
    strat = results[0]
    
    # 取得最終價值
    final_value = cerebro.broker.getvalue()
    print(f"[Backtrader] 最終價值: {final_value:,.0f}")
    
    # 計算指標
    portfolio_values = strat._results[0].get('portfolio_value', [initial_balance])
    returns = strat._results[0].get('returns', [])
    
    # 從 PyFolio 分析器取得詳細結果
    pyfoliozer = strat.analyzers.getbyname('pyfolio')
    returns_series, positions, transactions, gross_lev = pyfoliozer.get_pf_items()
    
    # 計算績效指標
    total_return = (final_value - initial_balance) / initial_balance
    
    # 計算最大回撤
    equity_curve = np.array([initial_balance * (1 + r) for r in returns_series])
    max_dd, _, _ = calculate_max_drawdown(equity_curve)
    
    # 夏普比率
    sharpe = calculate_sharpe_ratio(np.array(returns_series))
    
    metrics = {
        'total_return': total_return,
        'final_value': final_value,
        'max_drawdown': max_dd,
        'sharpe_ratio': sharpe,
        'volatility': np.std(returns_series, ddof=1) * np.sqrt(252),
    }
    
    return {
        'portfolio_values': equity_curve,
        'returns': np.array(returns_series),
        'metrics': metrics,
        'name': f'Backtrader_MA{fast_period}_{slow_period}',
    }


# ============================================================================
# FinRL 策略回測
# ============================================================================

def run_finrl_strategy(
    symbol: str,
    start_date: str,
    end_date: str,
    agent_type: str = 'ppo',
    model_path: Optional[str] = None,
    initial_balance: float = 1_000_000
) -> Dict:
    """
    執行 FinRL 策略回測
    
    參數：
        symbol: 股票代碼
        start_date: 開始日期
        end_date: 結束日期
        agent_type: Agent 類型 ('ppo' 或 'a2c')
        model_path: 模型檔案路徑（若為 None，使用預設模型）
        initial_balance: 初始資金
    
    返回：
        回測結果字典
    """
    print("\n" + "=" * 70)
    print(f"          FinRL {agent_type.upper()} 策略回測")
    print("=" * 70)
    
    try:
        from stable_baselines3 import PPO, A2C
        from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
        from FinRL.data.data_loader import TaiwanStockDataLoader
        from FinRL.data.technical_indicators import add_technical_indicators
    except ImportError as e:
        print(f"[FinRL] 導入模組失敗: {e}")
        return {}
    
    # 載入數據
    print(f"[FinRL] 載入數據 {symbol}...")
    loader = TaiwanStockDataLoader()
    df = loader.download_price_data(symbol, start=start_date, end=end_date)
    
    if df.empty:
        print(f"[FinRL] 無資料")
        return {}
    
    # 添加技術指標
    df = add_technical_indicators(df)
    
    # 建立環境
    env = TaiwanStockTradingEnv(
        df,
        initial_balance=initial_balance,
        reward_func=None
    )
    
    # 建立或載入模型
    if model_path and os.path.exists(model_path):
        print(f"[FinRL] 載入模型: {model_path}")
        if agent_type.lower() == 'ppo':
            agent = PPO.load(model_path)
        else:
            agent = A2C.load(model_path)
    else:
        # 使用預設模型（如果存在的話）
        print(f"[FinRL] 使用新訓練的模型")
        # 這裡需要根據實際情況調整
        from FinRL.agents.ppo_agent import PPOAgent
        
        agent_wrapper = PPOAgent(env)
        agent = agent_wrapper.get_model()
    
    # 建立回測引擎
    bt_engine = BacktestEngine(
        env=env,
        agent=agent,
        initial_balance=initial_balance,
        verbose=True
    )
    
    # 執行回測
    result = bt_engine.run(df, deterministic=True)
    
    result['name'] = f'FinRL_{agent_type.upper()}'
    
    return result


# ============================================================================
# 比較分析
# ============================================================================

def compare_strategies(
    results: List[Dict],
    output_dir: Optional[str] = None
) -> pd.DataFrame:
    """
    比較多個策略的回測結果
    
    參數：
        results: 回測結果列表
        output_dir: 輸出目錄
    
    返回：
        比較 DataFrame
    """
    print("\n" + "=" * 80)
    print("                         策略比較報告")
    print("=" * 80)
    
    comparison_data = []
    
    for result in results:
        name = result.get('name', 'Unknown')
        metrics = result.get('metrics', {})
        
        row = {
            '策略': name,
            '總報酬率': f"{metrics.get('total_return', 0)*100:.2f}%",
            '年化報酬': f"{metrics.get('annual_return', 0)*100:.2f}%",
            '夏普比率': f"{metrics.get('sharpe_ratio', 0):.3f}",
            '最大回撤': f"{metrics.get('max_drawdown', 0)*100:.2f}%",
            '卡瑪比率': f"{metrics.get('calmar_ratio', 0):.3f}",
            '勝率': f"{metrics.get('win_rate', 0)*100:.1f}%",
            '利潤因子': f"{metrics.get('profit_factor', 0):.2f}",
            '總交易次數': metrics.get('total_trades', 0),
            '最終價值': f"{metrics.get('final_value', 0):,.0f}",
        }
        comparison_data.append(row)
    
    df = pd.DataFrame(comparison_data)
    
    # 顯示表格
    print(df.to_string(index=False))
    
    print("\n" + "=" * 80)
    
    # 如果有兩個以上的策略，顯示贏家
    if len(results) >= 2:
        # 按總報酬排序
        sorted_results = sorted(results, key=lambda x: x.get('metrics', {}).get('total_return', 0), reverse=True)
        
        print("\n【贏家分析】")
        print(f"  最高報酬: {sorted_results[0]['name']} ({sorted_results[0]['metrics'].get('total_return', 0)*100:.2f}%)")
        
        # 按夏普比率排序
        sorted_by_sharpe = sorted(results, key=lambda x: x.get('metrics', {}).get('sharpe_ratio', 0), reverse=True)
        print(f"  最高夏普: {sorted_by_sharpe[0]['name']} ({sorted_by_sharpe[0]['metrics'].get('sharpe_ratio', 0):.3f})")
        
        # 按最大回撤排序（越小越好）
        sorted_by_mdd = sorted(results, key=lambda x: x.get('metrics', {}).get('max_drawdown', 0))
        print(f"  最低回撤: {sorted_by_mdd[0]['name']} ({sorted_by_mdd[0]['metrics'].get('max_drawdown', 0)*100:.2f}%)")
    
    # 繪製比較圖
    if output_dir:
        _plot_comparison(results, output_dir)
    
    return df


def _plot_comparison(results: List[Dict], output_dir: str):
    """繪製策略比較圖"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. 權益曲線比較
    ax1 = axes[0, 0]
    for result in results:
        name = result.get('name', 'Unknown')
        equity = result.get('portfolio_values', np.array([]))
        if len(equity) > 0:
            ax1.plot(equity, label=name, linewidth=1.5)
    
    ax1.set_title('權益曲線比較', fontsize=12, fontweight='bold')
    ax1.set_xlabel('時間')
    ax1.set_ylabel('價值 (TWD)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
    
    # 2. 報酬率 Bar 圖
    ax2 = axes[0, 1]
    names = [r.get('name', 'Unknown') for r in results]
    returns = [r.get('metrics', {}).get('total_return', 0) * 100 for r in results]
    colors = ['green' if r >= 0 else 'red' for r in returns]
    ax2.bar(names, returns, color=colors, alpha=0.7)
    ax2.set_title('總報酬率比較 (%)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('報酬率 (%)')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    for i, (name, ret) in enumerate(zip(names, returns)):
        ax2.text(i, ret + (1 if ret >= 0 else -3), f'{ret:.1f}%', ha='center', fontsize=10)
    
    # 3. 風險調整報酬指標
    ax3 = axes[1, 0]
    metrics_names = ['sharpe_ratio', 'sortino_ratio', 'calmar_ratio']
    x = np.arange(len(metrics_names))
    width = 0.35
    
    for i, result in enumerate(results):
        name = result.get('name', 'Unknown')
        values = [result.get('metrics', {}).get(m, 0) for m in metrics_names]
        ax3.bar(x + i * width, values, width, label=name, alpha=0.7)
    
    ax3.set_title('風險調整報酬指標', fontsize=12, fontweight='bold')
    ax3.set_xticks(x + width)
    ax3.set_xticklabels(['夏普', '索提諾', '卡瑪'])
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis='y')
    
    # 4. 關鍵指標雷達圖
    ax4 = axes[1, 1]
    ax4.axis('off')
    
    # 顯示摘要文字
    summary_text = "【關鍵指標摘要】\n\n"
    for result in results:
        name = result.get('name', 'Unknown')
        m = result.get('metrics', {})
        summary_text += f"{name}:\n"
        summary_text += f"  報酬率: {m.get('total_return', 0)*100:.1f}%\n"
        summary_text += f"  夏普: {m.get('sharpe_ratio', 0):.2f}\n"
        summary_text += f"  回撤: {m.get('max_drawdown', 0)*100:.1f}%\n"
        summary_text += f"  勝率: {m.get('win_rate', 0)*100:.0f}%\n\n"
    
    ax4.text(0.1, 0.9, summary_text, transform=ax4.transAxes, fontsize=11,
            verticalalignment='top', family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = os.path.join(output_dir, f'comparison_{timestamp}.png')
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\n[Compare] 比較圖表已儲存至：{save_path}")
    
    plt.close()


# ============================================================================
# 主程式
# ============================================================================

def parse_args():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description='比較 FinRL vs Backtrader 策略表現'
    )
    
    parser.add_argument(
        '--stock', type=str, default='2330',
        help='股票代碼 (預設: 2330)'
    )
    
    parser.add_argument(
        '--finrl_agent', type=str, default='ppo',
        choices=['ppo', 'a2c'],
        help='FinRL Agent 類型 (預設: ppo)'
    )
    
    parser.add_argument(
        '--backtest_start', type=str, default='2022-01-01',
        help='回測開始日期 (預設: 2022-01-01)'
    )
    
    parser.add_argument(
        '--backtest_end', type=str, default='2024-12-31',
        help='回測結束日期 (預設: 2024-12-31)'
    )
    
    parser.add_argument(
        '--initial_balance', type=float, default=1_000_000,
        help='初始資金 (預設: 1,000,000)'
    )
    
    parser.add_argument(
        '--finrl_model', type=str, default=None,
        help='FinRL 模型路徑 (可選)'
    )
    
    parser.add_argument(
        '--ma_fast', type=int, default=3,
        help='MA 快速期間 (預設: 3)'
    )
    
    parser.add_argument(
        '--ma_slow', type=int, default=60,
        help='MA 慢速期間 (預設: 60)'
    )
    
    parser.add_argument(
        '--output_dir', type=str, default='./results/comparison',
        help='輸出目錄 (預設: ./results/comparison)'
    )
    
    parser.add_argument(
        '--skip_backtrader', action='store_true',
        help='跳過 Backtrader 策略'
    )
    
    parser.add_argument(
        '--skip_finrl', action='store_true',
        help='跳過 FinRL 策略'
    )
    
    return parser.parse_args()


def main():
    """主程式"""
    args = parse_args()
    
    print("=" * 80)
    print("           FinRL vs Backtrader 策略比較")
    print("=" * 80)
    print(f"  股票代碼:      {args.stock}")
    print(f"  回測期間:      {args.backtest_start} ~ {args.backtest_end}")
    print(f"  初始資金:      {args.initial_balance:,.0f} TWD")
    print(f"  FinRL Agent:   {args.finrl_agent}")
    print(f"  MA 參數:       {args.ma_fast} / {args.ma_slow}")
    print("=" * 80)
    
    # 確保輸出目錄存在
    os.makedirs(args.output_dir, exist_ok=True)
    
    results = []
    
    # 執行 Backtrader 策略
    if not args.skip_backtrader:
        bt_result = run_backtrader_ma_strategy(
            symbol=args.stock,
            start_date=args.backtest_start,
            end_date=args.backtest_end,
            initial_balance=args.initial_balance,
            fast_period=args.ma_fast,
            slow_period=args.ma_slow
        )
        if bt_result:
            results.append(bt_result)
    
    # 執行 FinRL 策略
    if not args.skip_finrl:
        finrl_result = run_finrl_strategy(
            symbol=args.stock,
            start_date=args.backtest_start,
            end_date=args.backtest_end,
            agent_type=args.finrl_agent,
            model_path=args.finrl_model,
            initial_balance=args.initial_balance
        )
        if finrl_result:
            results.append(finrl_result)
    
    # 比較結果
    if results:
        comparison_df = compare_strategies(results, args.output_dir)
        
        # 儲存比較結果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        comparison_file = os.path.join(args.output_dir, f'comparison_{timestamp}.csv')
        comparison_df.to_csv(comparison_file, index=False, encoding='utf-8-sig')
        print(f"\n[Compare] 比較結果已儲存至：{comparison_file}")
    else:
        print("\n[Compare] 沒有可比較的結果")
    
    print("\n" + "=" * 80)
    print("                      比較完成")
    print("=" * 80)


if __name__ == '__main__':
    main()