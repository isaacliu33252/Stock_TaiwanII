"""
================================================================================
PerformanceMetrics - 績效指標計算模組 (v2新版)
================================================================================
計算量化交易策略的績效指標：

主要指標：
    1. 報酬指標：
       - 總報酬率 (Total Return)
       - 年化報酬率 (Annualized Return)
       - 日均報酬率 (Daily Return)
       
    2. 風險指標：
       - 夏普比率 (Sharpe Ratio)
       - 索提諾比率 (Sortino Ratio)
       - 最大回撤 (Max Drawdown)
       - 波動率 (Volatility)
       
    3. 交易統計：
       - 勝率 (Win Rate)
       - 利潤因子 (Profit Factor)
       - 平均獲利/虧損 (Avg Win/Loss)
       - 總交易次數
       - 連續虧損最大次數

設計原則：
    - 所有指標都考慮無風險利率
    - 年化計算使用 252 交易日
    - 報酬率計算包含股息和拆股調整

台股特殊規則：
    - 涨跌停限制: ±10%
    - T+2 交割制度
    - 交易稅 0.3%（賣出時）

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass, field
from datetime import datetime


# =============================================================================
# 績效指標 dataclass
# =============================================================================

@dataclass
class PerformanceResult:
    """
    績效評估結果 dataclass
    
    包含所有績效指標的計算結果。
    """
    # 基本資訊
    strategy_name: str = ""
    backtest_period: str = ""
    initial_capital: float = 0.0
    final_capital: float = 0.0
    
    # 報酬指標
    total_return: float = 0.0          # 總報酬率 (%)
    annualized_return: float = 0.0     # 年化報酬率 (%)
    daily_return_mean: float = 0.0     # 日均報酬率 (%)
    daily_return_std: float = 0.0      # 日報酬標準差
    
    # 風險指標
    sharpe_ratio: float = 0.0          # 夏普比率
    sortino_ratio: float = 0.0         # 索提諾比率
    max_drawdown: float = 0.0          # 最大回撤 (%)
    max_drawdown_duration: int = 0     # 最大回撤持續天數
    volatility: float = 0.0            # 波動率 (年化)
    
    # 交易統計
    total_trades: int = 0              # 總交易次數
    winning_trades: int = 0            # 獲利交易次數
    losing_trades: int = 0             # 虧損交易次數
    win_rate: float = 0.0              # 勝率 (%)
    avg_win: float = 0.0               # 平均獲利
    avg_loss: float = 0.0              # 平均虧損
    profit_factor: float = 0.0         # 利潤因子
    largest_win: float = 0.0           # 最大單筆獲利
    largest_loss: float = 0.0          # 最大單筆虧損
    consecutive_wins: int = 0         # 最大連續獲利次數
    consecutive_losses: int = 0       # 最大連續虧損次數
    
    # 時間加權指標
    calmar_ratio: float = 0.0           # 卡爾瑪比率 (年化報酬/最大回撤)
    
    def to_dict(self) -> Dict:
        """轉換為字典"""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    def to_dataframe(self) -> pd.DataFrame:
        """轉換為 DataFrame"""
        return pd.DataFrame([self.to_dict()])
    
    def summary(self) -> str:
        """生成摘要報告"""
        lines = [
            "=" * 60,
            f"{self.strategy_name} - 績效報告",
            "=" * 60,
            f"回測期間: {self.backtest_period}",
            f"初始資金: {self.initial_capital:,.2f}",
            f"最終資金: {self.final_capital:,.2f}",
            "-" * 60,
            "【報酬指標】",
            f"  總報酬率: {self.total_return:.2f}%",
            f"  年化報酬率: {self.annualized_return:.2f}%",
            f"  日均報酬率: {self.daily_return_mean:.4f}%",
            "-" * 60,
            "【風險指標】",
            f"  夏普比率: {self.sharpe_ratio:.2f}",
            f"  索提諾比率: {self.sortino_ratio:.2f}",
            f"  最大回撤: {self.max_drawdown:.2f}%",
            f"  最大回撤持續: {self.max_drawdown_duration} 天",
            f"  波動率: {self.volatility:.2f}%",
            "-" * 60,
            "【交易統計】",
            f"  總交易次數: {self.total_trades}",
            f"  勝率: {self.win_rate:.2f}%",
            f"  利潤因子: {self.profit_factor:.2f}",
            f"  平均獲利: {self.avg_win:,.2f}",
            f"  平均虧損: {self.avg_loss:,.2f}",
            f"  最大單筆獲利: {self.largest_win:,.2f}",
            f"  最大單筆虧損: {self.largest_loss:,.2f}",
            "-" * 60,
            "【風險調整報酬】",
            f"  卡爾瑪比率: {self.calmar_ratio:.2f}",
            "=" * 60,
        ]
        return "\n".join(lines)


# =============================================================================
# 績效指標計算函數
# =============================================================================

def calculate_returns(equity_curve: pd.Series) -> pd.Series:
    """
    計算收益率序列
    
    參數:
        equity_curve: 淨值序列
        
    返回:
        收益率序列
    """
    returns = equity_curve.pct_change().fillna(0)
    return returns


def calculate_sharpe_ratio(
    returns: Union[pd.Series, np.ndarray],
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> float:
    """
    計算夏普比率 (Sharpe Ratio)
    
    夏普比率衡量每承受一單位風險所獲得的超額報酬。
    數值越高表示風險調整後的報酬越好。
    
    公式:
        Sharpe = (平均報酬 - 無風險利率) / 報酬標準差 × √252
        
    參數:
        returns: 報酬率序列（日報酬率）
        risk_free_rate: 年化無風險利率（預設 2%）
        periods_per_year: 每年交易日數（預設 252）
        
    返回:
        年化夏普比率
        
    參考值:
        - > 2.0: 優秀
        - 1.0 ~ 2.0: 良好
        - 0.5 ~ 1.0: 一般
        - < 0.5: 較差

    M6 (2026-07-02 Fable 5 audit): Group A+'s own `_metrics()` in
    `backtest_group_a_plus_switch_policy.py` uses risk_free_rate=0 (no
    subtraction) and reports every ratio/volatility as a decimal fraction,
    not a percentage. Passing the same equity curve through both systems'
    defaults yields Sharpe values that differ systematically by ~0.1-0.3 --
    not a bug in either system, just a different convention. Use
    `_metrics_finrl_comparable()` in `backtest_group_a_plus_switch_policy.py`
    (which calls these FinRL functions directly) to get a Group A+ curve's
    numbers under this module's convention before comparing.
    """
    returns = np.array(returns)

    if len(returns) < 2:
        return 0.0
    
    # 日無風險利率
    daily_rf = risk_free_rate / periods_per_year
    
    # 計算超額報酬
    excess_returns = returns - daily_rf
    
    # 計算統計量
    mean_excess = np.mean(excess_returns)
    std_excess = np.std(excess_returns, ddof=1)

    if std_excess == 0:
        return 0.0

    # 年化夏普比率
    sharpe = (mean_excess / std_excess) * np.sqrt(periods_per_year)
    
    return sharpe


def calculate_sortino_ratio(
    returns: Union[pd.Series, np.ndarray],
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
    target_return: float = 0.0
) -> float:
    """
    計算索提諾比率 (Sortino Ratio)

    索提諾比率只計算下行風險（負報酬的標準差），
    對於不對稱報酬分佈的策略更為合適。

    公式:
        Sortino = (年化超額報酬 - 年化目標報酬) / 年化下行標準差

    參數:
        returns: 報酬率序列（日報酬率）
        risk_free_rate: 年化無風險利率
        periods_per_year: 每年交易日數
        target_return: 年化目標報酬（通常為 0，表示要求報酬不低於無風險利率）

    返回:
        年化索提諾比率（正值=優於目標，負值=低於目標）
        - > 2.0: 優秀
        - 1.0 ~ 2.0: 良好
        - < 1.0: 一般
        - 負值: 策略表現不如目標

    備註:
        - target_return 為年化目標報酬，內部會轉換為日報酬用於下行判斷
        - 下行標準差只計算「低於目標」的報酬，而非所有負報酬
        - 當無負報酬時，返回 +inf（無下行風險的正報酬）
    """
    returns = np.array(returns)

    if len(returns) < 2:
        return 0.0

    # 日無風險利率
    daily_rf = risk_free_rate / periods_per_year

    # 計算超額報酬（超過無風險利率的部分）
    excess_returns = returns - daily_rf

    # BUG FIX (2026-07-25): target_return 是年化值，但之前被當作日值使用
    # 正確：將年化 target_return 轉換為日值，再用於下行判斷
    daily_target = target_return / periods_per_year

    # 年化下行標準差（只計算低於目標的報酬）
    downside_mask = excess_returns < daily_target
    negative_returns = excess_returns[downside_mask]

    if len(negative_returns) == 0:
        # 無負報酬：說明策略從未虧損，視為極優秀
        ann_return = np.mean(excess_returns) * periods_per_year
        ann_target = target_return
        if ann_return - ann_target > 0:
            return float('inf')  # 無下行風險的正報酬 = 無限大 Sortino
        return (ann_return - ann_target) / 0.001  # 除以極小值避免除零

    downside_std = np.std(negative_returns, ddof=1)
    if downside_std < 1e-10:
        # 負報酬標準差極小（接近零）：說明下行波動極低
        # 使用無風險利率作為回報基准，避免返回荒謬的巨大負數
        ann_return = np.mean(excess_returns) * periods_per_year
        ann_target = target_return
        if ann_return - ann_target > 0:
            return float('inf')  # 無下行風險的正報酬
        return 0.0  # 極小的下行標準差視為零風險，回報低於目標則返回 0

    ann_downside_std = downside_std * np.sqrt(periods_per_year)

    # 年化超額報酬 - 年化目標報酬
    ann_return = np.mean(excess_returns) * periods_per_year
    ann_target = target_return
    sortino = (ann_return - ann_target) / ann_downside_std

    return sortino


def calculate_max_drawdown(
    equity_curve: Union[pd.Series, np.ndarray],
    method: str = 'absolute'
) -> Tuple[float, int]:
    """
    計算最大回撤 (Maximum Drawdown)
    
    最大回撤衡量從歷史高點到最低點的最大跌幅，
    是評估策略風險的關鍵指標。
    
    公式:
        Drawdown = (Peak - Trough) / Peak × 100%
        
    參數:
        equity_curve: 淨值序列
        method: 'absolute'=絕對回撤, 'percentage'=百分比回撤
        
    返回:
        (max_drawdown, max_drawdown_duration)
        - max_drawdown: 最大回撤 (%)
        - max_drawdown_duration: 最大回撤持續天數
    """
    equity = np.array(equity_curve)
    
    if len(equity) < 2:
        return 0.0, 0
    
    # 計算累計最高點
    running_max = np.maximum.accumulate(equity)
    
    # 計算回撤
    drawdown = (running_max - equity) / running_max * 100  # 轉為百分比
    
    # 最大回撤
    max_dd = np.max(drawdown)
    
    # 計算最大回撤持續天數
    max_dd_duration = 0
    current_duration = 0
    in_drawdown = False
    
    for i in range(len(drawdown)):
        if drawdown[i] > 0:
            in_drawdown = True
            current_duration += 1
            max_dd_duration = max(max_dd_duration, current_duration)
        else:
            in_drawdown = False
            current_duration = 0
    
    return max_dd, max_dd_duration


def calculate_win_rate(trade_pnls: List[float]) -> float:
    """
    計算勝率 (Win Rate)
    
    勝率是獲利交易次數佔總交易次數的比例。
    
    參數:
        trade_pnls: 每筆交易的損益列表
        
    返回:
        勝率 (%)
    """
    if len(trade_pnls) == 0:
        return 0.0
    
    winning_trades = sum(1 for pnl in trade_pnls if pnl > 0)
    win_rate = winning_trades / len(trade_pnls) * 100
    
    return win_rate


def calculate_profit_factor(trade_pnls: List[float]) -> float:
    """
    計算利潤因子 (Profit Factor)
    
    利潤因子是總獲利除以總虧損的比值。
    > 1 表示策略盈利，< 1 表示策略虧損。
    
    公式:
        Profit Factor = Total Gross Profit / Total Gross Loss
        
    參數:
        trade_pnls: 每筆交易的損益列表
        
    返回:
        利潤因子
    """
    if len(trade_pnls) == 0:
        return 0.0
    
    gross_profit = sum(pnl for pnl in trade_pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in trade_pnls if pnl < 0))
    
    if gross_loss == 0:
        return 0.0
    
    profit_factor = gross_profit / gross_loss
    
    return profit_factor


def calculate_volatility(
    returns: Union[pd.Series, np.ndarray],
    periods_per_year: int = 252
) -> float:
    """
    計算波動率 (Volatility)
    
    波動率是報酬標準差的年化值，
    衡量策略的回報不確定性。
    
    公式:
        Volatility = Std(Returns) × √252
        
    參數:
        returns: 報酬率序列
        periods_per_year: 每年交易日數
        
    返回:
        年化波動率 (%)
    """
    returns = np.array(returns)
    
    if len(returns) < 2:
        return 0.0
    
    volatility = np.std(returns, ddof=1) * np.sqrt(periods_per_year) * 100
    
    return volatility


def calculate_return_skewness(
    returns: Union[pd.Series, np.ndarray],
    periods_per_year: int = 252
) -> Dict[str, Any]:
    """
    計算報酬偏態（Skewness）和相關風險指標
    
    偏態衡量報酬分佈的對稱性：
    - 正偏（右偏）: 大額收益較常見，大額損失罕見（適合趨勢策略）
    - 負偏（左偏）: 大額損失較常見，大額收益罕見（風險較高）
    - 零偏: 對稱分佈
    
    同時計算：
    - 偏態係數 (Skewness): 衡量分佈對稱性
    - 超額峰度 (Excess Kurtosis): 衡量尾部厚度
    - VaR 5%: 95% 信心水準的最大單日損失
    - CVaR 5%: 條件在險值（平均損失超過 VaR 的情況）
    
    參數:
        returns: 報酬率序列
        periods_per_year: 每年交易日數
        
    返回:
        包含 skewness, kurtosis, var_5, cvar_5 的字典
    """
    from scipy import stats
    
    returns = np.array(returns)
    
    if len(returns) < 4:
        return {
            'skewness': 0.0,
            'excess_kurtosis': 0.0,
            'var_5': 0.0,
            'cvar_5': 0.0,
            'skewness_interpretation': '樣本不足'
        }
    
    # 偏態和超額峰度
    skewness = stats.skew(returns)
    excess_kurtosis = stats.kurtosis(returns)  # scipy 返回超額峰度（不含 Fisher 修正）
    
    # VaR 和 CVaR (5% 尾部風險)
    var_5 = np.percentile(returns, 5)  # 5% 分位數（最大 5% 損失）
    cvar_5 = returns[returns <= var_5].mean() if len(returns[returns <= var_5]) > 0 else var_5
    
    # 解釋
    if skewness > 0.5:
        interpretation = '正偏（右偏）：大額收益常見，適合趨勢策略'
    elif skewness < -0.5:
        interpretation = '負偏（左偏）：大額損失常見，風險較高'
    else:
        interpretation = '近似對稱分佈'
    
    return {
        'skewness': float(skewness),
        'excess_kurtosis': float(excess_kurtosis),
        'var_5': float(var_5 * 100),      # 轉為百分比
        'cvar_5': float(cvar_5 * 100),   # 轉為百分比
        'skewness_interpretation': interpretation
    }


# =============================================================================
# 績效指標計算類別
# =============================================================================

class PerformanceMetrics:
    """
    績效指標計算器
    
    這個類別提供完整的績效評估功能，
    支援從交易歷史和權益曲線計算各種指標。
    
    使用範例:
        >>> from FinRL.v2.backtesting import PerformanceMetrics
        >>> 
        >>> # 假設有交易歷史
        >>> metrics = PerformanceMetrics()
        >>> 
        >>> # 計算績效
        >>> result = metrics.calculate(
        ...     equity_curve=equity_df['total_value'],
        ...     trade_pnls=trade_history['pnl'],
        ...     initial_capital=1_000_000,
        ...     strategy_name='PPO Strategy'
        ... )
        >>> 
        >>> # 打印摘要
        >>> print(result.summary())
    """
    
    def __init__(
        self,
        periods_per_year: int = 252,
        risk_free_rate: float = 0.02
    ):
        """
        初始化績效計算器
        
        參數:
            periods_per_year: 每年交易日數（預設 252）
            risk_free_rate: 年化無風險利率（預設 2%）
        """
        self.periods_per_year = periods_per_year
        self.risk_free_rate = risk_free_rate
    
    def calculate(
        self,
        equity_curve: pd.Series,
        trade_pnls: Optional[List[float]] = None,
        dates: Optional[pd.Series] = None,
        initial_capital: float = 1_000_000,
        strategy_name: str = "Strategy",
        backtest_period: str = ""
    ) -> PerformanceResult:
        """
        計算所有績效指標
        
        這是統一介面，一次計算所有指標。
        
        參數:
            equity_curve: 淨值序列（每日總市值）
            trade_pnls: 每筆交易的損益列表（可選）
            dates: 日期序列（可選）
            initial_capital: 初始資金
            strategy_name: 策略名稱
            backtest_period: 回測期間描述
            
        返回:
            PerformanceResult 物件
        """
        # 計算報酬率
        returns = calculate_returns(equity_curve)
        
        # 計算報酬指標
        total_return = (equity_curve.iloc[-1] - equity_curve.iloc[0]) / equity_curve.iloc[0] * 100
        
        # 年化報酬率
        if len(equity_curve) > 1:
            n_days = len(equity_curve)
            annualized_return = ((1 + total_return / 100) ** (self.periods_per_year / n_days) - 1) * 100
        else:
            annualized_return = 0.0
        
        daily_return_mean = returns.mean() * 100
        daily_return_std = returns.std(ddof=1) * 100
        
        # 計算風險指標
        sharpe = calculate_sharpe_ratio(returns, self.risk_free_rate, self.periods_per_year)
        sortino = calculate_sortino_ratio(returns, self.risk_free_rate, self.periods_per_year)
        max_drawdown, max_dd_duration = calculate_max_drawdown(equity_curve)
        volatility = calculate_volatility(returns, self.periods_per_year)
        
        # 計算交易統計
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        avg_win = 0.0
        avg_loss = 0.0
        profit_factor = 0.0
        largest_win = 0.0
        largest_loss = 0.0
        consecutive_wins = 0
        consecutive_losses = 0
        
        if trade_pnls and len(trade_pnls) > 0:
            total_trades = len(trade_pnls)
            winning_trades = sum(1 for pnl in trade_pnls if pnl > 0)
            losing_trades = sum(1 for pnl in trade_pnls if pnl < 0)
            
            win_rate = calculate_win_rate(trade_pnls)
            profit_factor = calculate_profit_factor(trade_pnls)
            
            wins = [pnl for pnl in trade_pnls if pnl > 0]
            losses = [abs(pnl) for pnl in trade_pnls if pnl < 0]
            
            if wins:
                avg_win = np.mean(wins)
                largest_win = max(wins)
            
            if losses:
                avg_loss = np.mean(losses)
                largest_loss = max(losses)
            
            # 計算最大連續獲利/虧損次數
            consecutive_wins, consecutive_losses = self._calculate_consecutive_trades(trade_pnls)
        
        # 計算卡爾瑪比率
        calmar_ratio = 0.0
        if max_drawdown > 0:
            calmar_ratio = annualized_return / max_drawdown
        
        # 構建結果
        result = PerformanceResult(
            strategy_name=strategy_name,
            backtest_period=backtest_period,
            initial_capital=initial_capital,
            final_capital=equity_curve.iloc[-1],
            total_return=total_return,
            annualized_return=annualized_return,
            daily_return_mean=daily_return_mean,
            daily_return_std=daily_return_std,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            volatility=volatility,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate if trade_pnls else 0.0,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            largest_win=largest_win,
            largest_loss=largest_loss,
            consecutive_wins=consecutive_wins,
            consecutive_losses=consecutive_losses,
            calmar_ratio=calmar_ratio,
        )
        
        return result
    
    def _calculate_consecutive_trades(self, trade_pnls: List[float]) -> Tuple[int, int]:
        """
        計算最大連續獲利/虧損次數
        
        參數:
            trade_pnls: 每筆交易的損益列表
            
        返回:
            (max_consecutive_wins, max_consecutive_losses)
        """
        if not trade_pnls:
            return 0, 0
        
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0
        
        for pnl in trade_pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0
        
        return max_wins, max_losses
    
    def compare_strategies(
        self,
        results: List[PerformanceResult]
    ) -> pd.DataFrame:
        """
        比較多個策略的績效
        
        參數:
            results: PerformanceResult 列表
            
        返回:
            比較表格 DataFrame
        """
        comparison_data = []
        
        for result in results:
            comparison_data.append({
                'Strategy': result.strategy_name,
                'Total Return (%)': result.total_return,
                'Annualized Return (%)': result.annualized_return,
                'Sharpe Ratio': result.sharpe_ratio,
                'Sortino Ratio': result.sortino_ratio,
                'Max Drawdown (%)': result.max_drawdown,
                'Win Rate (%)': result.win_rate,
                'Profit Factor': result.profit_factor,
                'Total Trades': result.total_trades,
            })
        
        df = pd.DataFrame(comparison_data)
        df = df.sort_values('Sharpe Ratio', ascending=False)
        
        return df


# =============================================================================
# 便捷函數
# =============================================================================

def calculate_all_metrics(
    equity_curve: pd.Series,
    trade_pnls: Optional[List[float]] = None,
    initial_capital: float = 1_000_000,
    strategy_name: str = "Strategy"
) -> PerformanceResult:
    """
    便捷函數：計算所有績效指標
    
    參數:
        equity_curve: 淨值序列
        trade_pnls: 每筆交易的損益列表
        initial_capital: 初始資金
        strategy_name: 策略名稱
        
    返回:
        PerformanceResult 物件
    """
    metrics = PerformanceMetrics()
    return metrics.calculate(
        equity_curve=equity_curve,
        trade_pnls=trade_pnls,
        initial_capital=initial_capital,
        strategy_name=strategy_name,
    )


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("PerformanceMetrics 測試")
    print("=" * 60)
    
    # 模擬資料
    print("\n[測試] 生成模擬資料...")
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')  # 交易日
    
    # 模擬淨值曲線（年化報酬 20%，波動 15%）
    n_days = len(dates)
    daily_returns = np.random.normal(0.0008, 0.015, n_days)
    equity = 1_000_000 * np.cumprod(1 + daily_returns)
    
    equity_curve = pd.Series(equity, index=dates)
    print(f"初始淨值: {equity_curve.iloc[0]:,.2f}")
    print(f"最終淨值: {equity_curve.iloc[-1]:,.2f}")
    
    # 計算績效
    print("\n[測試] 計算績效指標...")
    metrics = PerformanceMetrics()
    result = metrics.calculate(
        equity_curve=equity_curve,
        trade_pnls=None,  # 無交易歷史
        initial_capital=1_000_000,
        strategy_name='模擬策略',
        backtest_period='2023-01-01 ~ 2023-12-31'
    )
    
    # 打印摘要
    print(result.summary())
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)