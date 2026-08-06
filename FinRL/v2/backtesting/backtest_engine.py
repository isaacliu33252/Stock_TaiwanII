"""
================================================================================
BacktestEngine - 回測引擎 (v2新版)
================================================================================
事件驅動的回測引擎，支援策略評估和歷史回測。

主要功能：
    1. 事件驅動回測（避免 look-ahead bias）
    2. 支援多種策略（A2C, PPO, 傳統技術分析）
    3. 完整的交易成本建模
    4. 績效指標計算

台股特殊規則：
    - 涨跌停限制: ±10%
    - T+2 交割制度
    - 交易稅 0.3%（賣出時）
    - 手續費 0.15%（券商折扣）

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import warnings

from .performance_metrics import PerformanceMetrics, PerformanceResult


# =============================================================================
# 回測配置
# =============================================================================

@dataclass
class BacktestConfig:
    """
    回測配置
    
    定義回測引擎的各項參數。
    """
    # 初始資金
    initial_capital: float = 1_000_000
    
    # 交易成本
    brokerage_fee_rate: float = 0.0015  # 手續費 0.15%
    transaction_tax_rate: float = 0.003   # 交易稅 0.3%（賣出時）
    
    # 持倉限制
    max_position: int = 40000              # 最大持股數
    min_trade_unit: int = 1000            # 最小交易單位
    
    # 涨跌停限制
    limit_up_ratio: float = 0.10          # 漲停 10%
    limit_down_ratio: float = 0.10         # 跌停 10%
    
    # 回測模式
    use_adjusted_prices: bool = True       # 使用復權價格
    allow_limit_up_trade: bool = False    # 是否允許涨跌停買賣
    allow_short_selling: bool = False      # 是否允許放空
    
    # 輸出設定
    save_trades: bool = True              # 保存交易記錄
    verbose: bool = True                  # 詳細輸出


@dataclass
class TradeRecord:
    """
    交易記錄 dataclass
    """
    date: str
    action: int
    price: float
    shares: int
    turnover: float
    commission: float
    tax: float
    position_after: int
    cash_after: float
    pnl_realized: float = 0.0
    pnl_unrealized: float = 0.0


@dataclass
class DailyRecord:
    """
    每日記錄 dataclass
    """
    date: str
    close: float
    position: int
    cash: float
    total_value: float
    daily_return: float
    unrealized_pnl: float


# =============================================================================
# 回測引擎類別
# =============================================================================

class BacktestEngine:
    """
    回測引擎
    
    事件驅動的回測引擎，模擬真實交易環境。
    
    特性：
        - 完整的交易成本建模
        - 涨跌停限制
        - T+2 交割（簡化版）
        - 詳細的交易記錄
        - 績效指標計算
        
    使用範例:
        >>> from FinRL.v2.backtesting import BacktestEngine, BacktestConfig
        >>> 
        >>> config = BacktestConfig(initial_capital=1_000_000)
        >>> engine = BacktestEngine(df, config)
        >>> 
        >>> # 使用 RL 模型回測
        >>> results = engine.run_with_model(agent)
        >>> 
        >>> # 使用策略函數回測
        >>> def my_strategy(state, history):
        ...     # 簡單均線策略
        ...     if state['ma5'] > state['ma20']:
        ...         return 'buy'
        ...     else:
        ...         return 'sell'
        >>> 
        >>> results = engine.run_with_strategy(my_strategy)
        >>> 
        >>> # 查看結果
        >>> print(results.summary())
    """
    
    def __init__(
        self,
        df: pd.DataFrame,
        config: BacktestConfig = None,
        name: str = "Backtest"
    ):
        """
        初始化回測引擎
        
        參數:
            df: 包含 OHLCV 的 DataFrame
            config: 回測配置
            name: 回測名稱
        """
        self.df = df.copy()
        self.config = config or BacktestConfig()
        self.name = name
        
        # 確保按日期排序
        self.df = self.df.sort_values('date').reset_index(drop=True)
        
        # 初始化結果
        self.trade_records: List[TradeRecord] = []
        self.daily_records: List[DailyRecord] = []
        
        # 內部狀態
        self.current_step = 0
        self.cash = self.config.initial_capital
        self.position = 0
        self.avg_cost = 0.0
        self.prev_close = 0.0  # 前一日收盤價（用於涨跌停判斷）
        
        # 初始化計算器
        self.metrics_calculator = PerformanceMetrics()
    
    def reset(self):
        """重置回測狀態"""
        self.current_step = 0
        self.cash = self.config.initial_capital
        self.position = 0
        self.avg_cost = 0.0
        self.prev_close = 0.0
        self.trade_records = []
        self.daily_records = []
    
    def _get_state(self, step: int) -> Dict:
        """
        獲取指定時間步的狀態
        
        參數:
            step: 時間步
            
        返回:
            狀態字典
        """
        row = self.df.iloc[step]
        return {
            'date': row.get('date', ''),
            'open': row.get('open', 0),
            'high': row.get('high', 0),
            'low': row.get('low', 0),
            'close': row.get('close', 0),
            'volume': row.get('volume', 0),
            'position': self.position,
            'cash': self.cash,
        }
    
    def _execute_trade(
        self,
        action: str,
        price: float,
        date: str,
        target_shares: int = 0
    ) -> Tuple[int, float, float, float]:
        """
        執行交易
        
        參數:
            action: 'buy', 'sell', 'close', 'hold'
            price: 成交價格
            date: 交易日期
            target_shares: 目標買入股數（用於大額買入，如 action 5=BUY_3000, 7=BUY_5000）
            
        返回:
            (shares, turnover, commission, tax)
        """
        shares = 0
        turnover = 0.0
        commission = 0.0
        tax = 0.0

        # 涨跌停檢查（台股规则：±10%）
        if self.current_step > 0:
            limit_up = self.prev_close * (1 + self.config.limit_up_ratio)
            limit_down = self.prev_close * (1 - self.config.limit_down_ratio)
            if price > limit_up or price < limit_down:
                if not self.config.allow_limit_up_trade:
                    # 超出涨跌停，不允許交易
                    return shares, turnover, commission, tax

        if action == 'buy':
            # 計算最大可買數量
            max_shares_by_cash = int(self.cash / (price * (1 + self.config.brokerage_fee_rate)))
            max_shares_by_limit = self.config.max_position - self.position
            # 如果有指定目標股數，使用目標；否則預設 1000 股
            base_shares = target_shares if target_shares > 0 else 1000
            shares = min(base_shares, max_shares_by_cash, max_shares_by_limit)
            
            if shares > 0:
                turnover = shares * price
                commission = turnover * self.config.brokerage_fee_rate
                
                # 更新持股
                total_shares = self.position + shares
                total_cost = self.position * self.avg_cost + turnover
                self.avg_cost = total_cost / total_shares if total_shares > 0 else 0
                self.position += shares  # BUG FIX: missing position update
                
                self.cash -= (turnover + commission)
                
        elif action == 'sell':
            # 計算最大可賣數量
            max_shares_by_position = self.position
            # 如果有指定目標股數，使用目標；否則預設 1000 股
            base_shares = target_shares if target_shares > 0 else 1000
            shares = -min(base_shares, max_shares_by_position)  # 負值表示賣出
            
            if shares < 0:
                turnover = abs(shares) * price
                commission = turnover * self.config.brokerage_fee_rate
                tax = turnover * self.config.transaction_tax_rate
                
                # 計算已實現損益
                cost_basis = abs(shares) * self.avg_cost
                net_proceeds = turnover - commission - tax
                
                # 更新持股
                self.position += shares  # shares 為負值
                
                self.cash += net_proceeds
                
                # 重置平均成本（如果全賣完）
                if self.position == 0:
                    self.avg_cost = 0
                    
        elif action == 'close':
            if self.position > 0:
                shares = -self.position
                turnover = abs(shares) * price
                commission = turnover * self.config.brokerage_fee_rate
                tax = turnover * self.config.transaction_tax_rate

                self.cash += (turnover - commission - tax)
                self.position = 0
                self.avg_cost = 0

        elif action == 'stop_loss':
            # 停損：賣出全部持股
            # 注意：台灣股票交易稅（0.3%）適用於所有賣出交易，無論盈虧
            if self.position > 0:
                shares = -self.position
                turnover = abs(shares) * price
                commission = turnover * self.config.brokerage_fee_rate
                tax = turnover * self.config.transaction_tax_rate  # 交易稅需計入（台股規則）

                self.cash += (turnover - commission - tax)
                self.position = 0
                self.avg_cost = 0

        return shares, turnover, commission, tax
    
    def run_with_model(self, model, deterministic: bool = True) -> PerformanceResult:
        """
        使用 RL 模型回測
        
        參數:
            model: RL 模型（需要有 predict 方法）
            deterministic: 是否使用确定性策略
            
        返回:
            PerformanceResult
        """
        self.reset()
        
        from FinRL.v2.environments import TaiwanStockTradingEnv
        env = TaiwanStockTradingEnv(self.df)
        
        obs, _ = env.reset()
        
        for step in range(len(self.df)):
            action, _ = model.predict(obs, deterministic=deterministic)
            
            current_data = self.df.iloc[step]
            price = current_data['close']
            
            # 更新 current_step（用於涨跌停判斷等內部狀態追蹤）
            self.current_step = step
            
            # 執行交易 - 轉換 RL action 為交易動作
            # Action: 0=HOLD, 1=BUY_1000, 2=SELL_1000, 3=CLOSE, 4=STOP_LOSS, 5=BUY_3000, 6=SELL_3000, 7=BUY_5000, 8=SELL_5000
            trade_action = 'hold'
            target_shares = 0
            
            if action == 0:
                trade_action = 'hold'
            elif action == 1:  # BUY_1000
                trade_action = 'buy'
                target_shares = 1000
            elif action == 5:  # BUY_3000
                trade_action = 'buy'
                target_shares = 3000
            elif action == 7:  # BUY_5000
                trade_action = 'buy'
                target_shares = 5000
            elif action == 2:  # SELL_1000
                trade_action = 'sell'
                target_shares = 1000
            elif action == 6:  # SELL_3000
                trade_action = 'sell'
                target_shares = 3000
            elif action == 8:  # SELL_5000
                trade_action = 'sell'
                target_shares = 5000
            elif action == 3:  # CLOSE_POSITION
                trade_action = 'close'
            elif action == 4:  # STOP_LOSS
                trade_action = 'stop_loss'
            
            shares, turnover, commission, tax = self._execute_trade(
                trade_action, price, str(current_data['date']), target_shares
            )
            
            # 記錄交易
            if shares != 0:
                trade = TradeRecord(
                    date=str(current_data['date']),
                    action=action,
                    price=price,
                    shares=shares,
                    turnover=turnover,
                    commission=commission,
                    tax=tax,
                    position_after=self.position,
                    cash_after=self.cash,
                )
                self.trade_records.append(trade)
            
            # 記錄每日狀態
            total_value = self.cash + self.position * price
            if step == 0:
                # 第一天：相對於初始資金的回报率
                daily_return = (total_value - self.config.initial_capital) / self.config.initial_capital
            else:
                daily_return = (total_value - self._get_prev_value()) / self._get_prev_value()
            
            daily = DailyRecord(
                date=str(current_data['date']),
                close=price,
                position=self.position,
                cash=self.cash,
                total_value=total_value,
                daily_return=daily_return,
                unrealized_pnl=self.position * (price - self.avg_cost) if self.position > 0 else 0,
            )
            self.daily_records.append(daily)

            # 更新前一日收盤價（用於下一日的涨跌停判斷）
            self.prev_close = price

            obs, _, terminated, _, _ = env.step(action)
            
            if terminated:
                break
        
        return self._calculate_results()
    
    def run_with_strategy(
        self,
        strategy_func,
        **kwargs
    ) -> PerformanceResult:
        """
        使用策略函數回測
        
        參數:
            strategy_func: 策略函數，簽名為 (state, history) -> action
            **kwargs: 傳遞給策略函數的其他參數
            
        返回:
            PerformanceResult
        """
        self.reset()
        
        history = []
        
        for step in range(len(self.df)):
            state = self._get_state(step)
            
            # 獲取歷史數據（用於策略計算）
            if len(history) > 0:
                state['history'] = history[-20:]  # 最近20筆
            
            # 調用策略函數
            action = strategy_func(state, **kwargs)
            
            current_data = self.df.iloc[step]
            price = current_data['close']
            
            # 執行交易
            shares, turnover, commission, tax = self._execute_trade(
                action, price, str(current_data['date'])
            )
            
            # 記錄交易
            if shares != 0:
                trade = TradeRecord(
                    date=str(current_data['date']),
                    action=0,  # 簡化，不區分具體動作
                    price=price,
                    shares=shares,
                    turnover=turnover,
                    commission=commission,
                    tax=tax,
                    position_after=self.position,
                    cash_after=self.cash,
                )
                self.trade_records.append(trade)
            
            # 記錄每日狀態
            total_value = self.cash + self.position * price
            if step == 0:
                # 第一天：相對於初始資金的回报率
                daily_return = (total_value - self.config.initial_capital) / self.config.initial_capital
            else:
                daily_return = (total_value - self._get_prev_value()) / self._get_prev_value()
            
            daily = DailyRecord(
                date=str(current_data['date']),
                close=price,
                position=self.position,
                cash=self.cash,
                total_value=total_value,
                daily_return=daily_return,
                unrealized_pnl=self.position * (price - self.avg_cost) if self.position > 0 else 0,
            )
            self.daily_records.append(daily)

            # 更新前一日收盤價（用於下一日的涨跌停判斷）
            self.prev_close = price

            # 更新歷史
            history.append(state)

        return self._calculate_results()
    
    def _get_prev_value(self) -> float:
        """獲取前一日總市值"""
        if len(self.daily_records) > 0:
            return self.daily_records[-1].total_value
        return self.config.initial_capital
    
    def _calculate_results(self) -> PerformanceResult:
        """計算績效結果"""
        # 構建淨值曲線
        equity_curve = pd.Series(
            [d.total_value for d in self.daily_records],
            index=pd.to_datetime([d.date for d in self.daily_records])
        )
        
        # 提取交易損益
        trade_pnls = [t.pnl_realized for t in self.trade_records if t.pnl_realized != 0]
        
        # 計算績效
        result = self.metrics_calculator.calculate(
            equity_curve=equity_curve,
            trade_pnls=trade_pnls if trade_pnls else None,
            initial_capital=self.config.initial_capital,
            strategy_name=self.name,
            backtest_period=f"{self.daily_records[0].date} ~ {self.daily_records[-1].date}" if self.daily_records else "",
        )
        
        return result
    
    def get_equity_curve(self) -> pd.DataFrame:
        """獲取淨值曲線"""
        df = pd.DataFrame([
            {
                'date': d.date,
                'close': d.close,
                'position': d.position,
                'cash': d.cash,
                'total_value': d.total_value,
                'daily_return': d.daily_return,
                'unrealized_pnl': d.unrealized_pnl,
            }
            for d in self.daily_records
        ])
        return df
    
    def get_trade_history(self) -> pd.DataFrame:
        """獲取交易歷史"""
        if not self.trade_records:
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {
                'date': t.date,
                'action': t.action,
                'price': t.price,
                'shares': t.shares,
                'turnover': t.turnover,
                'commission': t.commission,
                'tax': t.tax,
                'position_after': t.position_after,
                'cash_after': t.cash_after,
            }
            for t in self.trade_records
        ])
        return df
    
    def save_results(self, path: str):
        """保存回測結果"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存每日記錄
        equity_df = self.get_equity_curve()
        equity_df.to_csv(path.parent / f'{path.stem}_equity.csv', index=False)
        
        # 保存交易記錄
        trades_df = self.get_trade_history()
        if not trades_df.empty:
            trades_df.to_csv(path.parent / f'{path.stem}_trades.csv', index=False)
        
        # 保存績效結果
        result = self._calculate_results()
        result_dict = result.to_dict()
        
        with open(path.parent / f'{path.stem}_results.json', 'w') as f:
            json.dump(result_dict, f, indent=2)
        
        print(f"[BacktestEngine] 結果已保存到 {path.parent}")


# =============================================================================
# 便捷函數
# =============================================================================

def run_backtest(
    df: pd.DataFrame,
    model_or_func,
    initial_capital: float = 1_000_000,
    strategy_name: str = "Backtest",
    **kwargs
) -> Tuple[PerformanceResult, pd.DataFrame, pd.DataFrame]:
    """
    便捷函數：執行回測
    
    參數:
        df: 股價數據
        model_or_func: RL 模型或策略函數
        initial_capital: 初始資金
        strategy_name: 策略名稱
        **kwargs: 其他參數
        
    返回:
        (results, equity_curve, trades)
    """
    config = BacktestConfig(initial_capital=initial_capital)
    engine = BacktestEngine(df, config, strategy_name)
    
    # 判斷是模型還是函數
    if hasattr(model_or_func, 'predict'):
        result = engine.run_with_model(model_or_func)
    else:
        result = engine.run_with_strategy(model_or_func, **kwargs)
    
    equity = engine.get_equity_curve()
    trades = engine.get_trade_history()
    
    return result, equity, trades


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("BacktestEngine 測試")
    print("=" * 60)
    print("[BacktestEngine] 模組已載入")
    print("=" * 60)