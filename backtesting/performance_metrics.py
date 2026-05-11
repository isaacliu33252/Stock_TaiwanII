# ============================================================================
# 績效指標模組 (Performance Metrics)
# ============================================================================
"""
提供完整的績效指標計算功能。

指標類別：
1. 報酬指標：總報酬率、年化報酬、波動率
2. 風險調整報酬指標：夏普比率、索提諾比率、卡瑪比率
3. 風險指標：最大回撤、最大回撤持續天數
4. 交易統計指標：勝率、利潤因子、獲利/虧損比

使用方式：
    from backtesting.performance_metrics import calculate_all_metrics
    
    metrics = calculate_all_metrics(returns, equity_curve, trade_history)

作者: FinRL量化交易專家
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple


def calculate_sharpe_ratio(
    returns: np.ndarray,
    risk_free_rate: float = 0.02
) -> float:
    """計算夏普比率 (Sharpe Ratio)"""
    if len(returns) < 2:
        return 0.0
    
    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    
    mean_excess = np.mean(excess_returns)
    std_excess = np.std(excess_returns, ddof=1)
    
    if std_excess == 0:
        return 0.0
    
    return (mean_excess * np.sqrt(252)) / std_excess


def calculate_sortino_ratio(
    returns: np.ndarray,
    target: float = 0.0
) -> float:
    """計算索提諾比率 (Sortino Ratio)"""
    if len(returns) < 2:
        return 0.0
    
    downside_returns = returns[returns < target]
    
    if len(downside_returns) == 0:
        return 0.0
    
    downside_std = np.std(downside_returns, ddof=1)
    
    if downside_std == 0:
        return 0.0
    
    mean_return = np.mean(returns)
    return (mean_return * np.sqrt(252)) / (downside_std * np.sqrt(252))


def calculate_max_drawdown(
    equity_curve: np.ndarray
) -> Tuple[float, int, int]:
    """計算最大回撤 (Maximum Drawdown)"""
    if len(equity_curve) < 2:
        return 0.0, 0, 0
    
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - running_max) / running_max
    
    max_dd_idx = np.argmin(drawdowns)
    max_dd = drawdowns[max_dd_idx]
    peak_idx = np.argmax(equity_curve[:max_dd_idx]) if max_dd_idx > 0 else 0
    
    return max_dd, int(peak_idx), int(max_dd_idx)


def calculate_calmar_ratio(
    annual_return: float,
    max_drawdown: float
) -> float:
    """計算卡瑪比率 (Calmar Ratio)"""
    if max_drawdown == 0 or max_drawdown == 0.0:
        return 0.0
    
    return annual_return / abs(max_drawdown)


def calculate_annual_return(
    total_return: float,
    days: int
) -> float:
    """計算年化報酬率 (Annual Return)"""
    if days <= 0:
        return 0.0
    
    years = days / 252
    return (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0


def calculate_volatility(returns: np.ndarray) -> float:
    """計算波動率 (Volatility)"""
    if len(returns) < 2:
        return 0.0
    
    return np.std(returns, ddof=1) * np.sqrt(252)


def calculate_win_rate(trade_history: List[Dict]) -> float:
    """計算勝率 (Win Rate)"""
    if not trade_history:
        return 0.0
    
    closed_trades = [t for t in trade_history if 'pnl' in t and t['pnl'] != 0]
    
    if not closed_trades:
        return 0.0
    
    winning_trades = sum(1 for t in closed_trades if t['pnl'] > 0)
    return winning_trades / len(closed_trades)


def calculate_profit_factor(trade_history: List[Dict]) -> float:
    """計算利潤因子 (Profit Factor)"""
    if not trade_history:
        return 0.0
    
    closed_trades = [t for t in trade_history if 'pnl' in t and t['pnl'] != 0]
    
    if not closed_trades:
        return 0.0
    
    gross_profit = sum(t['pnl'] for t in closed_trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in closed_trades if t['pnl'] < 0))
    
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    
    return gross_profit / gross_loss


def calculate_win_loss_stats(trade_history: List[Dict]) -> Tuple[float, float, float]:
    """計算平均獲利、平均虧損、獲利虧損比"""
    if not trade_history:
        return 0.0, 0.0, 0.0
    
    closed_trades = [t for t in trade_history if 'pnl' in t and t['pnl'] != 0]
    
    if not closed_trades:
        return 0.0, 0.0, 0.0
    
    wins = [t['pnl'] for t in closed_trades if t['pnl'] > 0]
    losses = [abs(t['pnl']) for t in closed_trades if t['pnl'] < 0]
    
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    
    if avg_loss == 0:
        win_loss_ratio = float('inf') if avg_win > 0 else 0.0
    else:
        win_loss_ratio = avg_win / avg_loss
    
    return avg_win, avg_loss, win_loss_ratio


def calculate_max_drawdown_duration(equity_curve: np.ndarray) -> int:
    """計算最大回撤持續天數"""
    if len(equity_curve) < 2:
        return 0
    
    running_max = np.maximum.accumulate(equity_curve)
    in_drawdown = equity_curve < running_max
    
    max_duration = 0
    current_duration = 0
    
    for is_dd in in_drawdown:
        if is_dd:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0
    
    return max_duration


def calculate_max_consecutive_loss(trade_history: List[Dict]) -> float:
    """計算最大連續虧損金額"""
    if not trade_history:
        return 0.0
    
    closed_trades = [t for t in trade_history if 'pnl' in t and t['pnl'] != 0]
    
    if not closed_trades:
        return 0.0
    
    max_loss = 0.0
    current_loss = 0.0
    
    for trade in closed_trades:
        if trade['pnl'] < 0:
            current_loss += trade['pnl']
            max_loss = min(max_loss, current_loss)
        else:
            current_loss = 0.0
    
    return abs(max_loss)


def calculate_avg_holding_days(trade_history: List[Dict]) -> float:
    """計算平均持有天數"""
    if len(trade_history) < 2:
        return 0.0
    
    buy_trades = [t for t in trade_history if t.get('action') == 1]
    
    if not buy_trades:
        return 0.0
    
    holding_periods = []
    for i, buy_trade in enumerate(buy_trades):
        buy_step = buy_trade.get('step', 0)
        
        for j in range(i + 1, len(trade_history)):
            sell_trade = trade_history[j]
            if sell_trade.get('action') in [2, 3]:
                sell_step = sell_trade.get('step', 0)
                holding_periods.append(sell_step - buy_step)
                break
    
    return np.mean(holding_periods) if holding_periods else 0.0


def calculate_all_metrics(
    equity_curve: np.ndarray,
    returns: np.ndarray,
    trade_history: List[Dict],
    initial_balance: float = 1_000_000,
    risk_free_rate: float = 0.02
) -> Dict[str, Any]:
    """
    計算所有績效指標
    
    這是主要的使用接口，一次計算所有指標。
    
    Args:
        equity_curve: 權益曲線陣列
        returns: 收益率序列
        trade_history: 交易歷史列表
        initial_balance: 初始資金
        risk_free_rate: 無風險利率（年化）
    
    Returns:
        包含所有指標的字典
    """
    n = len(equity_curve)
    
    total_return = (equity_curve[-1] - initial_balance) / initial_balance
    annual_return = calculate_annual_return(total_return, n)
    volatility = calculate_volatility(returns)
    
    sharpe_ratio = calculate_sharpe_ratio(returns, risk_free_rate)
    sortino_ratio = calculate_sortino_ratio(returns, target=0.0)
    max_drawdown, _, _ = calculate_max_drawdown(equity_curve)
    calmar_ratio = calculate_calmar_ratio(annual_return, max_drawdown)
    
    win_rate = calculate_win_rate(trade_history)
    profit_factor = calculate_profit_factor(trade_history)
    avg_win, avg_loss, win_loss_ratio = calculate_win_loss_stats(trade_history)
    
    total_trades = len(trade_history)
    buy_trades = sum(1 for t in trade_history if t.get('action') == 1)
    sell_trades = sum(1 for t in trade_history if t.get('action') in [2, 3])
    
    max_dd_duration = calculate_max_drawdown_duration(equity_curve)
    max_consecutive_loss = calculate_max_consecutive_loss(trade_history)
    avg_holding_days = calculate_avg_holding_days(trade_history)
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'volatility': volatility,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'calmar_ratio': calmar_ratio,
        'max_drawdown': max_drawdown,
        'max_drawdown_duration': max_dd_duration,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'win_loss_ratio': win_loss_ratio,
        'total_trades': total_trades,
        'buy_trades': buy_trades,
        'sell_trades': sell_trades,
        'max_consecutive_loss': max_consecutive_loss,
        'avg_holding_days': avg_holding_days,
    }
