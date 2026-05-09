"""
evaluate.py - 模型評估腳本
================================================================================
評估訓練好的 RL 模型並計算各種績效指標。

支援的指標:
- 報酬類: 總報酬、年化報酬、夏普比率
- 風險類: 最大回撒、波動率、VaR/CVaR
- 交易類: 勝率、Profit Factor、Expectancy

使用方法:
    >>> python evaluate.py --model ./results/models/ppo_best.zip --stock 2330
    >>> python evaluate.py --agent ppo --stock 2330 --n_episodes 20

作者: FinRL量化交易專家
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# 添加專案根目錄到路徑
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    """
    解析命令列參數
    """
    parser = argparse.ArgumentParser(
        description='FinRL 台股量化交易系統 - 模型評估',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # 模型相關
    parser.add_argument(
        '--model', 
        type=str, 
        default=None,
        help='模型路徑 (.zip 檔案)'
    )
    parser.add_argument(
        '--agent', 
        type=str, 
        default='ppo',
        choices=['ppo', 'a2c'],
        help='Agent 類型 (用於建立模型)'
    )
    parser.add_argument(
        '--stock', 
        type=str, 
        default='2330',
        help='股票代碼'
    )
    
    # 評估相關
    parser.add_argument(
        '--n_episodes', 
        type=int, 
        default=10,
        help='評估 episode 數 (預設: 10)'
    )
    parser.add_argument(
        '--data_start', 
        type=str, 
        default='2023-01-01',
        help='評估數據開始日期'
    )
    parser.add_argument(
        '--data_end', 
        type=str, 
        default='2024-12-31',
        help='評估數據結束日期'
    )
    parser.add_argument(
        '--deterministic', 
        action='store_true',
        default=True,
        help='使用確定性策略'
    )
    
    # 輸出相關
    parser.add_argument(
        '--output', 
        type=str, 
        default=None,
        help='輸出報告路徑'
    )
    parser.add_argument(
        '--verbose', 
        type=int, 
        default=1,
        help='詳細程度'
    )
    
    return parser.parse_args()


def load_environment(stock, start_date, end_date):
    """
    建立評估環境
    
    Args:
        stock: 股票代碼
        start_date: 開始日期
        end_date: 結束日期
    
    Returns:
        TaiwanStockTradingEnv: 交易環境
    """
    from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
    from FinRL.environments.reward_function import RewardFunction
    from FinRL.data.data_loader import TaiwanStockDataLoader
    from FinRL.data.technical_indicators import TechnicalIndicators
    
    print(f"載入 {stock} 數據 ({start_date} ~ {end_date})...")
    
    # 載入數據
    loader = TaiwanStockDataLoader(cache_dir='./data/cache', data_dir='./data/raw')
    symbol = stock if stock.endswith('.TW') else stock + '.TW'
    
    df = loader.download_price_data(
        symbol=symbol,
        start=start_date,
        end=end_date,
        interval='1d'
    )
    
    if df.empty:
        raise ValueError(f"無法載入 {stock} 的數據")
    
    print(f"  載入 {len(df)} 筆數據")
    
    # 計算技術指標
    ti = TechnicalIndicators(df, lookback_window=60)
    df = ti.calculate_all()
    
    # 建立環境
    reward_func = RewardFunction()
    env = TaiwanStockTradingEnv(
        df=df,
        initial_balance=1_000_000,
        max_position=4000,
        trade_unit=1000,
        price_limit=0.10,
        commission_rate=0.0015,
        tax_rate=0.003,
        lookback_window=60,
        reward_func=reward_func
    )
    
    return env


def load_model(model_path, agent_type, env):
    """
    載入模型
    
    Args:
        model_path: 模型路徑
        agent_type: Agent 類型 ('ppo' 或 'a2c')
        env: 環境
    
    Returns:
        Agent: 載入的 Agent
    """
    from FinRL.agents.ppo_agent import PPOAgent
    from FinRL.agents.a2c_agent import A2CAgent
    
    if agent_type.lower() == 'ppo':
        agent = PPOAgent(env)
    else:
        agent = A2CAgent(env)
    
    if model_path and Path(model_path).exists():
        agent.load(model_path)
        print(f"模型已載入: {model_path}")
    else:
        print("[警告] 未指定模型或模型不存在，將使用未訓練的模型")
    
    return agent


def evaluate_model(agent, env, num_episodes=10, deterministic=True):
    """
    評估模型績效
    
    計算各種績效指標:
    - Sharpe Ratio: 風險調整後報酬
    - Max Drawdown: 最大回撒
    - Win Rate: 勝率
    - Profit Factor: 盈虧比
    - Calmar Ratio: 卡爾瑪比率
    
    Args:
        agent: Agent 實例
        env: 評估環境
        num_episodes: 評估 episode 數
        deterministic: 是否使用確定性策略
    
    Returns:
        dict: 評估結果
    """
    print(f"\n開始評估 (n_episodes={num_episodes}, deterministic={deterministic})...")
    
    episode_results = []
    
    for episode in range(num_episodes):
        state, info = env.reset()
        done = False
        truncated = False
        
        episode_reward = 0
        episode_length = 0
        
        portfolio_values = [info.get('portfolio_value', info.get('initial_balance', 1_000_000))]
        actions = []
        rewards = []
        
        while not (done or truncated):
            # 預測動作
            action, _ = agent.predict(state, deterministic=deterministic)
            
            # 執行動作
            state, reward, done, truncated, info = env.step(action)
            
            episode_reward += reward
            episode_length += 1
            
            actions.append(action)
            rewards.append(reward)
            portfolio_values.append(info.get('portfolio_value', 0))
        
        # 計算 episode 結果
        initial_value = portfolio_values[0]
        final_value = portfolio_values[-1]
        total_return = (final_value - initial_value) / initial_value
        
        # 記錄交易
        trades = env.trade_history
        
        episode_result = {
            'episode': episode + 1,
            'initial_value': initial_value,
            'final_value': final_value,
            'total_return': total_return,
            'return_pct': total_return * 100,
            'episode_reward': episode_reward,
            'episode_length': episode_length,
            'portfolio_values': portfolio_values,
            'actions': actions,
            'trades': trades,
        }
        
        episode_results.append(episode_result)
        
        if num_episodes <= 10 or (episode + 1) % 5 == 0:
            print(f"  Episode {episode+1}/{num_episodes}: return={total_return:.2%}, length={episode_length}, reward={episode_reward:.2f}")
    
    return episode_results


def calculate_performance_metrics(episode_results, risk_free_rate=0.02, trading_days=252):
    """
    計算績效指標
    
    指標說明:
    - Sharpe Ratio: (平均報酬 - 無風險利率) / 報酬標準差
    - Max Drawdown: 歷史最高點到最低點的最大跌幅
    - Win Rate: 正報酬 episode 比例
    - Profit Factor: 總獲利 / 總虧損
    - Calmar Ratio: 年化報酬 / 最大回撒
    
    Args:
        episode_results: episode 結果列表
        risk_free_rate: 無風險利率 (年化)
        trading_days: 每年交易日數
    
    Returns:
        dict: 績效指標
    """
    import numpy as np
    
    # 提取各項數據
    returns = [r['total_return'] for r in episode_results]
    rewards = [r['episode_reward'] for r in episode_results]
    lengths = [r['episode_length'] for r in episode_results]
    
    # 計算基礎統計
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    min_return = np.min(returns)
    max_return = np.max(returns)
    
    # 年化報酬
    avg_length = np.mean(lengths)
    avg_trading_days = avg_length  # 假設每天一個 step
    annualized_return = mean_return * (trading_days / avg_trading_days) if avg_trading_days > 0 else 0
    
    # Sharpe Ratio
    daily_rf = risk_free_rate / trading_days
    excess_returns = np.array(returns) - daily_rf
    if np.std(excess_returns, ddof=1) > 0:
        sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns, ddof=1) * np.sqrt(trading_days)
    else:
        sharpe_ratio = 0
    
    # Max Drawdown (從 episode 的 portfolio values)
    all_drawdowns = []
    for ep in episode_results:
        values = ep['portfolio_values']
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)
        all_drawdowns.append(max_dd)
    
    max_drawdown = np.max(all_drawdowns) if all_drawdowns else 0
    avg_drawdown = np.mean(all_drawdowns)
    
    # Win Rate
    wins = [r for r in returns if r > 0]
    win_rate = len(wins) / len(returns) if returns else 0
    
    # Profit Factor (從交易記錄)
    all_pnls = []
    for ep in episode_results:
        for trade in ep['trades']:
            if 'pnl' in trade and trade['pnl'] != 0:
                all_pnls.append(trade['pnl'])
    
    if all_pnls:
        gross_profit = sum(p for p in all_pnls if p > 0)
        gross_loss = abs(sum(p for p in all_pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        total_pnl = sum(all_pnls)
        avg_pnl = np.mean(all_pnls)
        n_trades = len(all_pnls)
    else:
        profit_factor = 0
        total_pnl = 0
        avg_pnl = 0
        n_trades = 0
    
    # Sortino Ratio
    downside_returns = [r for r in returns if r < 0]
    if len(downside_returns) > 0 and np.std(downside_returns, ddof=1) > 0:
        sortino_ratio = mean_return / np.std(downside_returns, ddof=1) * np.sqrt(trading_days)
    else:
        sortino_ratio = 0
    
    # Calmar Ratio
    calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0
    
    # 整理結果
    metrics = {
        # 基本統計
        'n_episodes': len(episode_results),
        'mean_return': mean_return,
        'std_return': std_return,
        'min_return': min_return,
        'max_return': max_return,
        
        # 年化指標
        'annualized_return': annualized_return,
        
        # 風險指標
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'calmar_ratio': calmar_ratio,
        'max_drawdown': max_drawdown,
        'avg_drawdown': avg_drawdown,
        
        # 交易統計
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'n_trades': n_trades,
        'n_wins': len(wins),
        'n_losses': len(returns) - len(wins),
        
        # 其他
        'avg_episode_length': np.mean(lengths),
        'avg_reward': np.mean(rewards),
    }
    
    return metrics


def print_metrics(metrics):
    """
    印出績效指標報告
    
    Args:
        metrics: 績效指標字典
    """
    print("\n" + "=" * 60)
    print("               模型評估報告")
    print("=" * 60)
    
    print("\n【基本統計】")
    print(f"  評估 episode 數:  {metrics['n_episodes']}")
    print(f"  平均報酬率:       {metrics['mean_return']:>10.2%}")
    print(f"  報酬率標準差:     {metrics['std_return']:>10.2%}")
    print(f"  最小報酬率:       {metrics['min_return']:>10.2%}")
    print(f"  最大報酬率:       {metrics['max_return']:>10.2%}")
    print(f"  年化報酬率:       {metrics['annualized_return']:>10.2%}")
    
    print("\n【風險指標】")
    print(f"  夏普比率:         {metrics['sharpe_ratio']:>10.2f}")
    print(f"  Sortino 比率:     {metrics['sortino_ratio']:>10.2f}")
    print(f"  卡爾瑪比率:       {metrics['calmar_ratio']:>10.2f}")
    print(f"  最大回撒:         {metrics['max_drawdown']:>10.2%}")
    print(f"  平均回撒:         {metrics['avg_drawdown']:>10.2%}")
    
    print("\n【交易統計】")
    print(f"  勝率:             {metrics['win_rate']:>10.1%}")
    print(f"  盈虧比:           {metrics['profit_factor']:>10.2f}")
    print(f"  總損益:           {metrics['total_pnl']:>15,.0f}")
    print(f"  平均每筆損益:     {metrics['avg_pnl']:>15,.0f}")
    print(f"  總交易筆數:       {metrics['n_trades']:>10}")
    print(f"  獲利筆數:         {metrics['n_wins']:>10}")
    print(f"  虧損筆數:         {metrics['n_losses']:>10}")
    
    print("\n【訓練效率】")
    print(f"  平均 episode 長度: {metrics['avg_episode_length']:>10.1f}")
    print(f"  平均 reward:       {metrics['avg_reward']:>10.2f}")
    
    print("\n" + "=" * 60)


def save_results(metrics, episode_results, output_path):
    """
    保存評估結果到 JSON 檔案
    
    Args:
        metrics: 績效指標
        episode_results: episode 結果列表
        output_path: 輸出路徑
    """
    import json
    
    # 只保存必要的資訊，避免過大
    episode_summary = []
    for ep in episode_results:
        episode_summary.append({
            'episode': ep['episode'],
            'initial_value': ep['initial_value'],
            'final_value': ep['final_value'],
            'total_return': ep['total_return'],
            'return_pct': ep['return_pct'],
            'episode_length': ep['episode_length'],
            'n_trades': len(ep['trades'])
        })
    
    results = {
        'metrics': metrics,
        'episodes': episode_summary,
        'timestamp': datetime.now().isoformat()
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n結果已保存: {output_path}")


def main():
    """主評估流程"""
    args = parse_args()
    
    print("=" * 60)
    print("         FinRL 台股量化交易系統 - 模型評估")
    print("=" * 60)
    print(f"  股票代碼:    {args.stock}")
    print(f"  Agent類型:   {args.agent.upper()}")
    print(f"  模型路徑:    {args.model or '未指定 (將使用未訓練模型)'}")
    print(f"  評估集數:    {args.n_episodes}")
    print(f"  數據區間:    {args.data_start} ~ {args.data_end}")
    print("=" * 60)
    
    try:
        # 載入環境
        env = load_environment(args.stock, args.data_start, args.data_end)
        print(f"  環境狀態維度: {env.state_dim}")
        print(f"  環境動作數: {env.action_space.n}")
        
        # 載入模型
        agent = load_model(args.model, args.agent, env)
        
        # 評估模型
        episode_results = evaluate_model(
            agent, 
            env, 
            num_episodes=args.n_episodes,
            deterministic=args.deterministic
        )
        
        # 計算績效指標
        metrics = calculate_performance_metrics(episode_results)
        
        # 印出結果
        print_metrics(metrics)
        
        # 保存結果
        if args.output:
            save_results(metrics, episode_results, args.output)
        else:
            # 自動產生輸出路徑
            output_dir = Path('./results/evaluation')
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = output_dir / f'eval_{args.agent}_{args.stock}_{timestamp}.json'
            save_results(metrics, episode_results, str(output_path))
        
        print("\n評估完成!")
        
    except Exception as e:
        print(f"\n[錯誤] 評估失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main()) or 0