"""
BacktestEngine - 回測引擎
================================================================================
提供完整的回測框架，用於評估 RL 交易策略的績效表現。

功能:
    - 歷史數據回測
    - 績效指標計算
    - 交易記錄分析
    - 與 Benchmark 比較

績效指標:
    - Total Return: 總報酬率
    - Sharpe Ratio: 夏普比率
    - Max Drawdown: 最大回撒
    - Win Rate: 勝率
    - Profit Factor: 利潤因子
    - Calmar Ratio: 卡爾瑪比率
    - Annual Return: 年化報酬率

作者: FinRL量化交易專家
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path
import json
import warnings

warnings.filterwarnings('ignore')


class BacktestEngine:
    """
    回測引擎
    
    用於回測交易策略並計算績效指標。
    
    Attributes:
        initial_balance: 初始資金
        commission_rate: 佣金率
        tax_rate: 證交稅率
    
    Example:
        >>> engine = BacktestEngine(initial_balance=1_000_000)
        >>> results = engine.run(env, model)
        >>> engine.print_results(results)
    """
    
    def __init__(
        self,
        initial_balance: float = 1_000_000,
        commission_rate: float = 0.0015,
        tax_rate: float = 0.003
    ):
        """
        初始化回測引擎
        
        Args:
            initial_balance: 初始資金
            commission_rate: 券商佣金
            tax_rate: 證交稅
        """
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        
        # 回測結果
        self.results = None
        self.trade_history = []
        self.portfolio_history = []
    
    def run(
        self,
        env,
        model=None,
        deterministic: bool = True
    ) -> Dict[str, Any]:
        """
        執行回測
        
        Args:
            env: 交易環境
            model: 訓練好的模型 (若為 None，使用隨機策略)
            deterministic: 是否使用確定性策略
        
        Returns:
            回測結果字典
        """
        print("[BacktestEngine] 開始回測...")
        
        # 重置環境
        state, info = env.reset()
        done = False
        truncated = False
        
        # 記錄
        self.trade_history = []
        self.portfolio_history = []
        
        # 取得初始資金
        if 'initial_balance' in info:
            self.initial_balance = info['initial_balance']
        
        step = 0
        
        while not (done or truncated):
            # 選擇動作
            if model is not None:
                action, _ = model.predict(state, deterministic=deterministic)
            else:
                action = env.action_space.sample()
            
            # 執行交易
            prev_state = state.copy()
            state, reward, done, truncated, info = env.step(action)
            
            # 記錄
            self.portfolio_history.append({
                'step': step,
                'action': action,
                'action_name': ['HOLD', 'BUY_1000', 'SELL_1000', 'CLOSE_POSITION', 'STOP_LOSS'][action],
                'portfolio_value': info.get('portfolio_value', 0),
                'balance': info.get('balance', 0),
                'position': info.get('position', 0),
                'price': info.get('price', 0),
                'reward': reward,
            })
            
            # 記錄交易
            if action != 0:  # 非 HOLD 動作
                self.trade_history.append({
                    'step': step,
                    'action': action,
                    'action_name': ['HOLD', 'BUY_1000', 'SELL_1000', 'CLOSE_POSITION', 'STOP_LOSS'][action],
                    'price': info.get('price', 0),
                    'position': info.get('position', 0),
                    'message': info.get('message', ''),
                    'portfolio_value': info.get('portfolio_value', 0),
                })
            
            step += 1
            
            if step % 100 == 0:
                print(f"  Step {step}: Portfolio = {info.get('portfolio_value', 0):,.0f}")
        
        # 計算績效指標
        self.results = self._calculate_metrics()
        
        print(f"[BacktestEngine] 回測完成")
        print(f"  - 總交易次數: {len(self.trade_history)}")
        print(f"  - 最終資金: {self.results['final_value']:,.0f}")
        print(f"  - 總報酬率: {self.results['total_return']:.2%}")
        
        return self.results
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """
        計算績效指標
        
        Returns:
            績效指標字典
        """
        if not self.portfolio_history:
            return {}
        
        # 轉換為 DataFrame 方便計算
        df = pd.DataFrame(self.portfolio_history)
        
        # 基本指標
        initial_value = self.initial_balance
        final_value = df['portfolio_value'].iloc[-1]
        total_return = (final_value - initial_value) / initial_value
        
        # =====================================================================
        # 年化報酬率
        # =====================================================================
        # 根據資料長度估算交易日數
        n_days = len(df)
        years = n_days / 252  # 假設每年 252 交易日
        if years > 0:
            annualized_return = (1 + total_return) ** (1 / years) - 1
        else:
            annualized_return = 0
        
        # =====================================================================
        # 夏普比率 (Sharpe Ratio)
        # =====================================================================
        # Sharpe Ratio = (平均報酬 - 無風險利率) / 報酬標準差
        daily_returns = df['portfolio_value'].pct_change().dropna()
        
        risk_free_rate = 0.02 / 252  # 日化無風險利率
        excess_returns = daily_returns - risk_free_rate
        
        if len(excess_returns) > 1 and excess_returns.std() > 0:
            sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # =====================================================================
        # 最大回撒 (Max Drawdown)
        # =====================================================================
        df['peak'] = df['portfolio_value'].cummax()
        df['drawdown'] = (df['portfolio_value'] - df['peak']) / df['peak']
        max_drawdown = df['drawdown'].min()  # 負值
        max_drawdown_pct = abs(max_drawdown)
        
        # 找到最大回撒發生的位置
        max_dd_idx = df['drawdown'].idxmin()
        
        # =====================================================================
        # Sortino 比率 (只用於下行風險)
        # =====================================================================
        # Sortino = (平均報酬 - 目標報酬) / 下行標準差
        downside_returns = daily_returns[daily_returns < target_return]
        if len(downside_returns) > 1 and downside_returns.std() > 0:
            excess_return = daily_returns.mean() - target_return
            sortino_ratio = excess_return / downside_returns.std() * np.sqrt(252)
        else:
            sortino_ratio = 0
        
        # =====================================================================
        # Calmar 比率 (卡爾瑪比率)
        # =====================================================================
        # Calmar = 年化報酬率 / 最大回撒
        if max_drawdown_pct > 0:
            calmar_ratio = annualized_return / max_drawdown_pct
        else:
            calmar_ratio = 0
        
        # =====================================================================
        # 勝率與利潤因子
        # =====================================================================
        trades_df = pd.DataFrame(self.trade_history)
        
        if len(trades_df) > 0:
            # 識別買入和賣出交易
            buy_trades = trades_df[trades_df['action'] == 1]
            sell_trades = trades_df[trades_df['action'].isin([2, 3, 4])]
            
            # 計算交易次數
            total_trades = len(trades_df)
            n_wins = len([t for t in self.trade_history if t.get('pnl', 0) > 0])
            n_losses = len([t for t in self.trade_history if t.get('pnl', 0) < 0])
            
            win_rate = n_wins / total_trades if total_trades > 0 else 0
            
            # 利潤因子
            gross_profit = sum([t.get('pnl', 0) for t in self.trade_history if t.get('pnl', 0) > 0])
            gross_loss = abs(sum([t.get('pnl', 0) for t in self.trade_history if t.get('pnl', 0) < 0]))
            
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
            
            # 平均獲利/平均虧損
            avg_win = gross_profit / n_wins if n_wins > 0 else 0
            avg_loss = gross_loss / n_losses if n_losses > 0 else 0
            avg_win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        else:
            total_trades = 0
            n_wins = 0
            n_losses = 0
            win_rate = 0
            gross_profit = 0
            gross_loss = 0
            profit_factor = 0
            avg_win = 0
            avg_loss = 0
            avg_win_loss_ratio = 0
        
        # =====================================================================
        # 組裝結果
        # =====================================================================
        results = {
            # 基本指標
            'initial_balance': initial_value,
            'final_value': final_value,
            'total_return': total_return,
            'total_profit': final_value - initial_value,
            
            # 報酬指標
            'annualized_return': annualized_return,
            'n_trading_days': n_days,
            'n_years': years,
            
            # 風險指標
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'max_drawdown': max_drawdown_pct,
            'max_drawdown_value': max_drawdown_pct * initial_value,
            
            # 交易統計
            'total_trades': total_trades,
            'n_wins': n_wins,
            'n_losses': n_losses,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_win_loss_ratio': avg_win_loss_ratio,
            
            # 其他
            'avg_trade_return': total_return / total_trades if total_trades > 0 else 0,
        }
        
        return results
    
    def get_trade_history(self) -> pd.DataFrame:
        """
        取得交易歷史
        
        Returns:
            交易歷史 DataFrame
        """
        return pd.DataFrame(self.trade_history)
    
    def get_portfolio_history(self) -> pd.DataFrame:
        """
        取得投資組合價值歷史
        
        Returns:
            投資組合歷史 DataFrame
        """
        return pd.DataFrame(self.portfolio_history)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """
        取得權益曲線
        
        Returns:
            包含權益曲線的 DataFrame
        """
        df = pd.DataFrame(self.portfolio_history)
        if 'step' in df.columns and 'portfolio_value' in df.columns:
            return df[['step', 'portfolio_value']]
        return df
    
    def get_drawdown_series(self) -> pd.Series:
        """
        取得回撤序列
        
        Returns:
            回撤 Series
        """
        df = pd.DataFrame(self.portfolio_history)
        df['peak'] = df['portfolio_value'].cummax()
        df['drawdown'] = (df['portfolio_value'] - df['peak']) / df['peak']
        return df['drawdown']
    
    def print_results(self, results: Optional[Dict] = None):
        """
        印出回測結果
        
        Args:
            results: 結果字典 (若為 None，使用 self.results)
        """
        if results is None:
            results = self.results
        
        if not results:
            print("無回測結果")
            return
        
        print("\n" + "=" * 60)
        print("              FinRL 台股策略回測報告")
        print("=" * 60)
        
        print("\n【基本資訊】")
        print(f"  初始資金:     {results['initial_balance']:>15,.0f} TWD")
        print(f"  最終價值:     {results['final_value']:>15,.0f} TWD")
        print(f"  總報酬率:     {results['total_return']:>15.2%}")
        print(f"  總獲利:       {results['total_profit']:>15,.0f} TWD")
        
        print("\n【報酬分析】")
        print(f"  年化報酬率:   {results['annualized_return']:>15.2%}")
        print(f"  交易日數:     {results['n_trading_days']:>15} 天")
        print(f"  投資年數:     {results['n_years']:>15.2f} 年")
        
        print("\n【風險指標】")
        print(f"  夏普比率:     {results['sharpe_ratio']:>15.2f}")
        print(f"  Sortino 比率: {results['sortino_ratio']:>15.2f}")
        print(f"  卡爾瑪比率:   {results['calmar_ratio']:>15.2f}")
        print(f"  最大回撒:     {results['max_drawdown']:>15.2%}")
        print(f"  最大回撒金額: {results['max_drawdown_value']:>15,.0f} TWD")
        
        print("\n【交易統計】")
        print(f"  總交易次數:   {results['total_trades']:>15}")
        print(f"  獲利次數:     {results['n_wins']:>15}")
        print(f"  虧損次數:     {results['n_losses']:>15}")
        print(f"  勝率:         {results['win_rate']:>15.2%}")
        print(f"  利潤因子:     {results['profit_factor']:>15.2f}")
        print(f"  平均獲利:     {results['avg_win']:>15,.0f} TWD")
        print(f"  平均虧損:     {results['avg_loss']:>15,.0f} TWD")
        print(f"  獲虧比:       {results['avg_win_loss_ratio']:>15.2f}")
        
        print("\n" + "=" * 60)
    
    def save_results(self, path: str, results: Optional[Dict] = None):
        """
        儲存回測結果到 JSON 檔案
        
        Args:
            path: 儲存路徑
            results: 結果字典 (若為 None，使用 self.results)
        """
        if results is None:
            results = self.results
        
        if not results:
            print("無回測結果可儲存")
            return
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 轉換 numpy 類型為 Python 原生類型
        results_save = {}
        for k, v in results.items():
            if isinstance(v, (np.integer, np.floating)):
                results_save[k] = float(v)
            else:
                results_save[k] = v
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(results_save, f, indent=2, ensure_ascii=False)
        
        print(f"[BacktestEngine] 結果已儲存: {path}")
    
    def compare_with_benchmark(
        self,
        benchmark_returns: pd.Series,
        results: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        與 Benchmark 比較
        
        Args:
            benchmark_returns: Benchmark 報酬率序列
            results: 本策略結果
        
        Returns:
            比較結果字典
        """
        if results is None:
            results = self.results
        
        # 計算 Benchmark 的指標
        bench_total_return = (1 + benchmark_returns).prod() - 1
        bench_sharpe = benchmark_returns.mean() / benchmark_returns.std() * np.sqrt(252) if benchmark_returns.std() > 0 else 0
        
        # 比較
        comparison = {
            'strategy_return': results['total_return'],
            'benchmark_return': bench_total_return,
            'excess_return': results['total_return'] - bench_total_return,
            'strategy_sharpe': results['sharpe_ratio'],
            'benchmark_sharpe': bench_sharpe,
            'alpha': results['total_return'] - bench_total_return,
        }
        
        print(f"\n【與 Benchmark 比較】")
        print(f"  策略報酬率:   {comparison['strategy_return']:.2%}")
        print(f"  Benchmark:   {comparison['benchmark_return']:.2%}")
        print(f"  超額報酬 (α): {comparison['excess_return']:.2%}")
        print(f"  策略夏普:     {comparison['strategy_sharpe']:.2f}")
        print(f"  Benchmark 夏普: {comparison['benchmark_sharpe']:.2f}")
        
        return comparison
