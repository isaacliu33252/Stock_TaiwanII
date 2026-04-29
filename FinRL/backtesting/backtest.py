# ============================================================================
# 回測引擎 (Backtest Engine)
# ============================================================================
"""
提供完整的回測功能，用於評估 RL 交易策略的歷史表現。

功能特色：
- 支援完整的回測流程（資料載入→環境初始化→逐步交易→記錄交易→計算指標）
- 正確處理台股規則（涨跌停、T+2、1000股單位）
- 計算完整績效指標（Sharpe、Sortino、Calmar、Win Rate、Profit Factor 等）
- 交易歷史追蹤與權益曲線產生

使用方式：
    from FinRL.backtesting.backtest import BacktestEngine
    
    bt = BacktestEngine(env, agent, initial_balance=1_000_000)
    result = bt.run(data)
    trades = bt.get_trade_history()
    equity = bt.get_equity_curve()

作者: FinRL量化交易專家
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import json
import os

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    TAIWAN_STOCK_CONFIG,
    BACKTEST_CONFIG,
    RESULTS_DIR,
    DATA_CONFIG
)


# ============================================================================
# 績效指標計算函式
# ============================================================================

def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
    """
    計算夏普比率 (Sharpe Ratio) - 風險調整後的報酬
    
    公式：夏普比率 = (投資組合報酬 - 無風險利率) / 投資組合標準差
    
    意義：
    - 衡量每承受一單位風險所獲得的超額報酬
    - 夏普比率 > 1 表示報酬戰勝風險
    - 夏普比率 > 2 表示優異的風險調整表現
    - 夏普比率 < 0 表示表現不如無風險資產
    
    參數：
        returns: 收益率序列（每日報酬率）
        risk_free_rate: 年化無風險利率（預設 2%）
    
    返回：
        夏普比率（年化）
    """
    if len(returns) < 2:
        return 0.0
    
    # 日化無風險利率
    daily_rf = risk_free_rate / 252
    
    # 計算超額報酬
    excess_returns = returns - daily_rf
    
    # 計算年化夏普比率
    mean_excess = np.mean(excess_returns)
    std_excess = np.std(excess_returns)
    
    if std_excess == 0:
        return 0.0
    
    sharpe = (mean_excess * np.sqrt(252)) / std_excess
    return sharpe


def calculate_max_drawdown(equity_curve: np.ndarray) -> Tuple[float, int, int]:
    """
    計算最大回撤 (Maximum Drawdown) - 最大跌幅
    
    公式：最大回撤 = max(Peak - Trough) / Peak
    
    意義：
    - 衡量投資組合從歷史高峰到低谷的最大跌幅
    - 代表投資者可能遭受的最大損失
    - 越小越好，通常 < 20% 為可接受水準
    
    參數：
        equity_curve: 權益曲線（投資組合價值序列）
    
    返回：
        (max_drawdown, peak_index, trough_index)
        - max_drawdown: 最大回撤（負值，表示虧損百分比）
        - peak_index: 峰值位置索引
        - trough_index: 谷值位置索引
    """
    if len(equity_curve) < 2:
        return 0.0, 0, 0
    
    # 計算累計最大值（歷史高點）
    running_max = np.maximum.accumulate(equity_curve)
    
    # 計算回撤（從高點跌幅）
    drawdowns = (equity_curve - running_max) / running_max
    
    # 找到最大回撤（最深的谷）
    max_dd_idx = np.argmin(drawdowns)
    max_dd = drawdowns[max_dd_idx]
    
    # 找到峰值位置（最大回撤開始的高點）
    peak_idx = np.argmax(equity_curve[:max_dd_idx]) if max_dd_idx > 0 else 0
    
    return max_dd, int(peak_idx), int(max_dd_idx)


def calculate_win_rate(trade_history: List[Dict]) -> float:
    """
    計算勝率 (Win Rate) - 盈利交易筆數 / 總交易筆數
    
    意義：
    - 衡量交易策略的準確率
    - 勝率 > 50% 是基本要求
    - 需配合平均獲利/平均虧損比率來評估整體表現
    
    參數：
        trade_history: 交易歷史列表，每筆記錄包含 'pnl' 欄位
    
    返回：
        勝率（0 到 1 之間）
    """
    if not trade_history:
        return 0.0
    
    # 只計算已平倉的交易（有 pnl 的記錄）
    closed_trades = [t for t in trade_history if 'pnl' in t and t['pnl'] != 0]
    
    if not closed_trades:
        return 0.0
    
    # 計算盈利交易數
    winning_trades = sum(1 for t in closed_trades if t['pnl'] > 0)
    
    win_rate = winning_trades / len(closed_trades)
    return win_rate


def calculate_profit_factor(trade_history: List[Dict]) -> float:
    """
    計算利潤因子 (Profit Factor) - 總盈利 / 總虧損
    
    公式：利潤因子 = Gross Profit / Gross Loss
    
    意義：
    - 衡量策略賺錢的能力
    - > 1 表示策略有正期望值
    - > 1.5 表示良好的交易系統
    - < 1 表示策略處於虧損狀態
    
    參數：
        trade_history: 交易歷史列表
    
    返回：
        利潤因子
    """
    if not trade_history:
        return 0.0
    
    # 只計算已平倉的交易
    closed_trades = [t for t in trade_history if 'pnl' in t and t['pnl'] != 0]
    
    if not closed_trades:
        return 0.0
    
    # 計算總盈利和總虧損
    gross_profit = sum(t['pnl'] for t in closed_trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in closed_trades if t['pnl'] < 0))
    
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    
    profit_factor = gross_profit / gross_loss
    return profit_factor


def calculate_calmar_ratio(annual_return: float, max_drawdown: float) -> float:
    """
    計算卡瑪比率 (Calmar Ratio) - 年化報酬 / 最大回撤
    
    公式：卡瑪比率 = 年化報酬率 / 最大回撤
    
    意義：
    - 衡量報酬與最大風險的比率
    - 卡瑪比率越高，表示承擔每單位回撤風險獲得的報酬越高
    - 通常要求 > 1，表示表現良好
    - 主要用於期貨 CTA 策略評估
    
    參數：
        annual_return: 年化報酬率（小數形式，如 0.15 表示 15%）
        max_drawdown: 最大回撤（小數形式，負值，如 -0.2 表示 20% 回撤）
    
    返回：
        卡瑪比率
    """
    if max_drawdown == 0 or max_drawdown == 0.0:
        return 0.0
    
    # 最大回撤取絕對值（因為是負數）
    calmar = annual_return / abs(max_drawdown)
    return calmar


def calculate_sortino_ratio(returns: np.ndarray, target: float = 0.0) -> float:
    """
    計算索提諾比率 (Sortino Ratio) - 只考慮下行風險
    
    公式：索提諾比率 = (投資組合報酬 - 目標報酬) / 下行標準差
    
    意義：
    - 與夏普比率類似，但只計算負報酬的波動（下行風險）
    - 不將上行波動視為風險，這是更合理風險衡量方式
    - Sortino > 1 表示良好的風險調整表現
    
    參數：
        returns: 收益率序列
        target: 目標報酬率（預設 0）
    
    返回：
        索提諾比率（年化）
    """
    if len(returns) < 2:
        return 0.0
    
    # 計算下行報酬（低於目標的部分）
    downside_returns = returns[returns < target]
    
    if len(downside_returns) == 0:
        return 0.0
    
    # 計算下行標準差
    downside_std = np.std(downside_returns)
    
    if downside_std == 0:
        return 0.0
    
    # 年化索提諾比率
    mean_return = np.mean(returns)
    sortino = (mean_return * np.sqrt(252)) / (downside_std * np.sqrt(252))
    
    return sortino


def calculate_annual_return(total_return: float, days: int) -> float:
    """
    計算年化報酬率 (Annual Return)
    
    公式：年化報酬 = (1 + 總報酬)^(252/交易天數) - 1
    
    意義：
    - 將不同投資期間的報酬标准化为一年期報酬
    - 方便比較不同投資策略的表現
    
    參數：
        total_return: 總報酬率（小數形式，如 0.20 表示 20%）
        days: 投資天數
    
    返回：
        年化報酬率（小數形式）
    """
    if days <= 0:
        return 0.0
    
    # 計算年化報酬
    years = days / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0
    
    return annual_return


def calculate_volatility(returns: np.ndarray) -> float:
    """
    計算波動率 (Volatility) - 報酬率標準差年化值
    
    意義：
    - 衡量報酬率的變動程度
    - 波動率越高，表示報酬不穩定，風險越大
    - 通常年化波動率 < 15% 視為低風險
    
    參數：
        returns: 收益率序列
    
    返回：
        年化波動率（小數形式）
    """
    if len(returns) < 2:
        return 0.0
    
    volatility = np.std(returns) * np.sqrt(252)
    return volatility


def calculate_win_loss_ratio(trade_history: List[Dict]) -> Tuple[float, float, float]:
    """
    計算平均獲利、平均虧損、獲利虧損比
    
    返回：
        (avg_win, avg_loss, win_loss_ratio)
    """
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


# ============================================================================
# 回測引擎類別
# ============================================================================

class BacktestEngine:
    """
    回測引擎 (Backtest Engine)
    
    用於在歷史資料上回測 RL 交易策略的表現。
    
    台股特殊規則處理：
    - 涨跌停限制：單日最大漲跌幅 10%
    - T+2 交割制度：當日買入股票，T+2 日才能賣出
    - 最小交易單位：1000 股（一張）
    - 最大持有：4000 股（4張）
    
    屬性：
        env: 交易環境 (TaiwanStockTradingEnv)
        agent: RL 代理 (PPO/A2C Agent)
        initial_balance: 初始資金
        trade_unit: 最小交易單位
        price_limit: 涨跌停限制
    
    使用範例：
        >>> env = TaiwanStockTradingEnv(df)
        >>> agent = PPOAgent(env)
        >>> agent.load('ppo_model.zip')
        >>> bt = BacktestEngine(env, agent, initial_balance=1_000_000)
        >>> result = bt.run(df)
    """
    
    def __init__(
        self,
        env,
        agent,
        initial_balance: float = TAIWAN_STOCK_CONFIG['initial_balance'],
        trade_unit: int = TAIWAN_STOCK_CONFIG['trade_unit'],
        price_limit: float = TAIWAN_STOCK_CONFIG['price_limit'],
        commission_rate: float = TAIWAN_STOCK_CONFIG['commission_rate'],
        tax_rate: float = TAIWAN_STOCK_CONFIG['tax_rate'],
        verbose: bool = True
    ):
        """
        初始化回測引擎
        
        參數：
            env: 交易環境 (Gymnasium 環境)
            agent: RL 代理（需有 predict() 方法）
            initial_balance: 初始資金（預設 100萬）
            trade_unit: 最小交易單位（預設 1000 股）
            price_limit: 涨跌停限制（預設 10%）
            commission_rate: 券商佣金（預設 0.15%）
            tax_rate: 證交稅（預設 0.3%，賣出時收取）
            verbose: 是否顯示詳細回測過程
        """
        self.env = env
        self.agent = agent
        self.initial_balance = initial_balance
        self.trade_unit = trade_unit
        self.price_limit = price_limit
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.verbose = verbose
        
        # 結果目錄
        self.results_dir = RESULTS_DIR
        os.makedirs(self.results_dir, exist_ok=True)
        
        # 回測結果儲存
        self.portfolio_values = []
        self.returns = []
        self.trade_history = []
        self.actions_history = []
        self.dates = []
        
        # 績效指標
        self.metrics = {}
        
        if self.verbose:
            print("=" * 70)
            print("                     FinRL 回測引擎初始化")
            print("=" * 70)
            print(f"  初始資金: {initial_balance:,.0f} TWD")
            print(f"  交易單位: {trade_unit} 股 (一張)")
            print(f"  涨跌停限制: {price_limit*100:.0f}%")
            print(f"  券商佣金: {commission_rate*100:.2f}%")
            print(f"  證交稅: {tax_rate*100:.1f}%")
            print("=" * 70)
    
    def run(self, data: pd.DataFrame, deterministic: bool = True) -> Dict[str, Any]:
        """
        執行回測流程
        
        回測步驟：
        1. 載入歷史資料
        2. 初始化環境（重置環境狀態）
        3. 逐步執行交易（每個時間步执行一步）
        4. 記錄每筆交易（買入/賣出時間、價格、數量）
        5. 計算績效指標
        
        參數：
            data: 歷史股票數據（需包含 OHLCV 欄位）
            deterministic: 是否使用確定性策略（True=不使用隨機探索）
        
        返回：
            回測結果字典，包含：
            - portfolio_values: 權益曲線
            - returns: 收益率序列
            - trade_history: 交易歷史
            - actions: 動作歷史
            - metrics: 績效指標
        """
        if self.verbose:
            print("\n" + "=" * 70)
            print("                     開始回測")
            print("=" * 70)
        
        # =========================================================
        # 步驟 1: 載入歷史資料
        # =========================================================
        self.env.df = data.reset_index(drop=True)
        self.env.max_steps = len(data) - 1
        
        if self.verbose:
            print(f"[步驟1] 載入歷史資料: {len(data)} 筆")
            print(f"        日期範圍: {data['date'].iloc[0]} ~ {data['date'].iloc[-1]}")
        
        # =========================================================
        # 步驟 2: 初始化環境
        # =========================================================
        obs, info = self.env.reset()
        
        # 重置內部狀態
        self.portfolio_values = [info.get('total_asset', self.initial_balance)]
        self.returns = []
        self.trade_history = []
        self.actions_history = []
        self.dates = [data['date'].iloc[0] if 'date' in data.columns else 0]
        
        if self.verbose:
            print(f"[步驟2] 環境初始化完成")
            print(f"        初始資金: {info.get('total_asset', self.initial_balance):,.0f} TWD")
            print(f"        初始持股: {info.get('position', 0)} 股")
        
        # =========================================================
        # 步驟 3: 逐步執行交易
        # =========================================================
        done = False
        truncated = False
        step = 0
        
        while not (done or truncated):
            # 取得模型預測動作
            action, _ = self.agent.predict(obs, deterministic=deterministic)
            
            # 記錄動作
            self.actions_history.append(action)
            
            # 執行交易
            obs, reward, terminated, truncated, info = self.env.step(action)
            done = terminated
            
            # 記錄狀態
            current_value = info.get('total_asset', 0)
            self.portfolio_values.append(current_value)
            
            # 記錄日期
            if 'date' in data.columns and step < len(data):
                self.dates.append(data['date'].iloc[step])
            else:
                self.dates.append(step)
            
            # 記錄報酬率
            if len(self.portfolio_values) >= 2:
                portfolio_return = (current_value - self.portfolio_values[-2]) / self.portfolio_values[-2]
                self.returns.append(portfolio_return)
            
            # 從環境的交易歷史同步到回測引擎
            if hasattr(self.env, 'trade_history') and self.env.trade_history:
                # 只記錄新的交易
                env_trades = self.env.trade_history
                existing_indices = set(t.get('step', -1) for t in self.trade_history)
                for trade in env_trades:
                    if trade.get('step', -1) not in existing_indices:
                        self.trade_history.append(trade)
            
            step += 1
            
            # 顯示進度
            if self.verbose and step % 100 == 0:
                print(f"        進度: {step}/{self.env.max_steps} ({step/self.env.max_steps*100:.1f}%)")
        
        # 第一筆報酬率設為 0
        self.returns.insert(0, 0.0)
        
        if self.verbose:
            print(f"[步驟3] 執行交易完成: 共 {step} 個時間步")
            print(f"        總交易次數: {len(self.trade_history)}")
        
        # =========================================================
        # 步驟 4: 記錄交易（已在步驟3中完成）
        # =========================================================
        if self.verbose:
            print(f"[步驟4] 交易記錄完成")
            buys = sum(1 for t in self.trade_history if t.get('action') == 1)
            sells = sum(1 for t in self.trade_history if t.get('action') == 2)
            print(f"        買入次數: {buys}, 賣出次數: {sells}")
        
        # =========================================================
        # 步驟 5: 計算績效指標
        # =========================================================
        self.metrics = self._calculate_metrics()
        
        if self.verbose:
            print(f"[步驟5] 績效指標計算完成")
        
        # 顯示結果
        if self.verbose:
            self._print_results()
        
        return self.get_results()
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """
        計算完整績效指標
        
        返回：
            績效指標字典
        """
        portfolio_values = np.array(self.portfolio_values)
        returns = np.array(self.returns)
        
        # 基本參數
        n = len(portfolio_values)
        days = n  # 交易天數
        
        # ============================================================
        # 報酬相關指標
        # ============================================================
        
        # 總收益率
        total_return = (portfolio_values[-1] - self.initial_balance) / self.initial_balance
        
        # 年化報酬率
        annual_return = calculate_annual_return(total_return, days)
        
        # 波動率
        volatility = calculate_volatility(returns)
        
        # ============================================================
        # 風險調整報酬指標
        # ============================================================
        
        # 夏普比率
        sharpe_ratio = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
        
        # 索提諾比率
        sortino_ratio = calculate_sortino_ratio(returns, target=0.0)
        
        # 卡瑪比率
        max_drawdown, _, _ = calculate_max_drawdown(portfolio_values)
        calmar_ratio = calculate_calmar_ratio(annual_return, max_drawdown)
        
        # ============================================================
        # 風險指標
        # ============================================================
        
        # 最大回撤
        # max_drawdown 已在上面計算過
        
        # 最大回撤持續天數
        max_dd_duration = self._calculate_max_drawdown_duration(portfolio_values)
        
        # ============================================================
        # 交易統計指標
        # ============================================================
        
        # 勝率
        win_rate = calculate_win_rate(self.trade_history)
        
        # 利潤因子
        profit_factor = calculate_profit_factor(self.trade_history)
        
        # 平均獲利/虧損
        avg_win, avg_loss, win_loss_ratio = calculate_win_loss_ratio(self.trade_history)
        
        # 交易次數統計
        total_trades = len(self.trade_history)
        buy_trades = sum(1 for t in self.trade_history if t.get('action') == 1)
        sell_trades = sum(1 for t in self.trade_history if t.get('action') == 2)
        
        # ============================================================
        # 其他指標
        # ============================================================
        
        # 平均持有天數
        avg_holding_days = self._calculate_avg_holding_days()
        
        # 最大連續虧損
        max_consecutive_loss = self._calculate_max_consecutive_loss()
        
        return {
            # 基本報酬指標
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            
            # 風險調整報酬指標
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            
            # 風險指標
            'max_drawdown': max_drawdown,
            'max_drawdown_duration': max_dd_duration,
            
            # 交易統計
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'win_loss_ratio': win_loss_ratio,
            
            # 其他
            'avg_holding_days': avg_holding_days,
            'max_consecutive_loss': max_consecutive_loss,
            
            # 最終狀態
            'final_value': portfolio_values[-1],
            'initial_balance': self.initial_balance,
            'total_days': days,
        }
    
    def _calculate_max_drawdown_duration(self, equity_curve: np.ndarray) -> int:
        """
        計算最大回撤持續天數
        
        意義：投資者需要承受多長時間的回撤
        """
        if len(equity_curve) < 2:
            return 0
        
        running_max = np.maximum.accumulate(equity_curve)
        in_drawdown = equity_curve < running_max
        
        # 找到連續回撤的最大長度
        max_duration = 0
        current_duration = 0
        
        for is_dd in in_drawdown:
            if is_dd:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0
        
        return max_duration
    
    def _calculate_avg_holding_days(self) -> float:
        """
        計算平均持有天數
        """
        if len(self.trade_history) < 2:
            return 0.0
        
        buy_trades = [t for t in self.trade_history if t.get('action') == 1]
        
        if not buy_trades:
            return 0.0
        
        holding_periods = []
        for i, buy_trade in enumerate(buy_trades):
            buy_step = buy_trade.get('step', 0)
            
            # 找對應的賣出交易
            for j in range(i + 1, len(self.trade_history)):
                sell_trade = self.trade_history[j]
                if sell_trade.get('action') in [2, 3]:  # SELL or CLOSE
                    sell_step = sell_trade.get('step', 0)
                    holding_periods.append(sell_step - buy_step)
                    break
        
        return np.mean(holding_periods) if holding_periods else 0.0
    
    def _calculate_max_consecutive_loss(self) -> float:
        """
        計算最大連續虧損金額
        """
        if not self.trade_history:
            return 0.0
        
        closed_trades = [t for t in self.trade_history if 'pnl' in t and t['pnl'] != 0]
        
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
    
    def _print_results(self):
        """顯示回測結果摘要"""
        print("\n" + "=" * 70)
        print("                     回測結果摘要")
        print("=" * 70)
        
        m = self.metrics
        
        print(f"\n【報酬指標】")
        print(f"  初始資金:       {m['initial_balance']:>15,.2f} TWD")
        print(f"  最終價值:       {m['final_value']:>15,.2f} TWD")
        print(f"  總報酬率:       {m['total_return']*100:>15.2f} %")
        print(f"  年化報酬率:     {m['annual_return']*100:>15.2f} %")
        print(f"  波動率:         {m['volatility']*100:>15.2f} %")
        
        print(f"\n【風險調整報酬指標】")
        print(f"  夏普比率:       {m['sharpe_ratio']:>15.3f}")
        print(f"  索提諾比率:     {m['sortino_ratio']:>15.3f}")
        print(f"  卡瑪比率:       {m['calmar_ratio']:>15.3f}")
        
        print(f"\n【風險指標】")
        print(f"  最大回撤:       {m['max_drawdown']*100:>15.2f} %")
        print(f"  最大回撤天數:   {m['max_drawdown_duration']:>15} 天")
        print(f"  最大連續虧損:   {m['max_consecutive_loss']:>15,.2f} TWD")
        
        print(f"\n【交易統計】")
        print(f"  總交易次數:     {m['total_trades']:>15}")
        print(f"  買入次數:       {m['buy_trades']:>15}")
        print(f"  賣出次數:       {m['sell_trades']:>15}")
        print(f"  勝率:           {m['win_rate']*100:>15.2f} %")
        print(f"  利潤因子:       {m['profit_factor']:>15.3f}")
        print(f"  平均獲利:       {m['avg_win']:>15,.2f} TWD")
        print(f"  平均虧損:       {m['avg_loss']:>15,.2f} TWD")
        print(f"  獲利/虧損比:    {m['win_loss_ratio']:>15.3f}")
        print(f"  平均持有天數:   {m['avg_holding_days']:>15.1f} 天")
        
        print("\n" + "=" * 70)
    
    def get_results(self) -> Dict[str, Any]:
        """
        取得回測結果
        
        返回：
            回測結果字典
        """
        return {
            'portfolio_values': np.array(self.portfolio_values),
            'returns': np.array(self.returns),
            'trade_history': self.trade_history,
            'actions': self.actions_history,
            'dates': self.dates,
            'metrics': self.metrics,
        }
    
    def get_trade_history(self) -> List[Dict]:
        """
        取得交易歷史
        
        返回：
            交易歷史列表
        """
        return self.trade_history
    
    def get_equity_curve(self) -> np.ndarray:
        """
        取得權益曲線
        
        返回：
            權益曲線陣列
        """
        return np.array(self.portfolio_values)
    
    def get_returns(self) -> np.ndarray:
        """
        取得收益率序列
        
        返回：
            收益率陣列
        """
        return np.array(self.returns)
    
    def save_results(self, filename: str = None) -> str:
        """
        儲存回測結果到檔案
        
        參數：
            filename: 檔案名稱（若為 None，則自動產生）
        
        返回：
            檔案路徑
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_results_{timestamp}.json"
        
        filepath = os.path.join(self.results_dir, filename)
        
        # 建立結果字典
        results = self.get_results()
        
        # 轉換 numpy array 為 list（JSON 不支援 numpy）
        results_serializable = {
            'portfolio_values': results['portfolio_values'].tolist(),
            'returns': results['returns'].tolist(),
            'trade_history': results['trade_history'],
            'actions': results['actions'],
            'dates': [str(d) for d in results['dates']],
            'metrics': results['metrics'],
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results_serializable, f, indent=2, ensure_ascii=False)
        
        print(f"[BacktestEngine] 回測結果已儲存至：{filepath}")
        return filepath
    
    def save_trades_csv(self, filename: str = None) -> str:
        """
        儲存交易歷史為 CSV 格式
        
        參數：
            filename: 檔案名稱
        
        返回：
            檔案路徑
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trades_{timestamp}.csv"
        
        filepath = os.path.join(self.results_dir, filename)
        
        if self.trade_history:
            df = pd.DataFrame(self.trade_history)
            df.to_csv(filepath, index=False)
            print(f"[BacktestEngine] 交易歷史已儲存至：{filepath}")
        else:
            print("[BacktestEngine] 無交易記錄")
        
        return filepath


# ============================================================================
工廠函式
# ============================================================================

def create_backtest_engine(
    env,
    agent,
    initial_balance: float = 1_000_000,
    **kwargs
) -> BacktestEngine:
    """
    便捷函式：建立回測引擎
    
    參數：
        env: 交易環境
        agent: RL 代理
        initial_balance: 初始資金
        **kwargs: 其他回測引擎參數
    
    返回：
        BacktestEngine 實例
    """
    return BacktestEngine(
        env=env,
        agent=agent,
        initial_balance=initial_balance,
        **kwargs
    )