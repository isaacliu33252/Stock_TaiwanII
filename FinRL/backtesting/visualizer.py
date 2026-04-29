"""
Visualizer - 回測結果視覺化
================================================================================
提供回測結果的圖表視覺化功能。

圖表類型:
    - Equity Curve: 權益曲線
    - Drawdown Chart: 回撤圖
    - Returns Distribution: 報酬分佈
    - Trade Analysis: 交易分析
    - Metrics Summary: 指標摘要

作者: FinRL量化交易專家
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from typing import Dict, Optional, List, Tuple, Any
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# 嘗試設置中文字體
try:
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
except:
    pass

# 預設配色
COLORS = {
    'primary': '#1f77b4',
    'secondary': '#ff7f0e',
    'positive': '#2ca02c',
    'negative': '#d62728',
    'benchmark': '#7f7f7f',
}


class Visualizer:
    """
    回測結果視覺化器
    
    Example:
        >>> viz = Visualizer()
        >>> fig = viz.plot_equity_curve(portfolio_history)
        >>> viz.plot_drawdown(portfolio_history)
        >>> viz.save_all('./results/plots')
    """
    
    def __init__(
        self,
        figsize: Tuple[int, int] = (12, 8),
        style: str = 'seaborn-v0_8-darkgrid'
    ):
        """
        初始化視覺化器
        
        Args:
            figsize: 圖形大小
            style: matplotlib 樣式
        """
        self.figsize = figsize
        
        try:
            plt.style.use(style)
        except:
            plt.style.use('default')
    
    def plot_equity_curve(
        self,
        portfolio_history: pd.DataFrame,
        benchmark_values: Optional[pd.Series] = None,
        title: str = "Equity Curve",
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        繪製權益曲線
        
        Args:
            portfolio_history: 投資組合歷史
            benchmark_values: Benchmark 價值序列
            title: 圖標題
            save_path: 儲存路徑
        
        Returns:
            matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        
        # 提取數據
        if isinstance(portfolio_history, pd.DataFrame):
            if 'step' in portfolio_history.columns and 'portfolio_value' in portfolio_history.columns:
                steps = portfolio_history['step']
                values = portfolio_history['portfolio_value']
            else:
                steps = range(len(portfolio_history))
                values = portfolio_history.iloc[:, 0]
        else:
            steps = range(len(portfolio_history))
            values = portfolio_history
        
        # 繪製權益曲線
        ax.plot(steps, values, color=COLORS['primary'], linewidth=2, label='Portfolio')
        
        # 如果有 Benchmark
        if benchmark_values is not None:
            ax.plot(steps, benchmark_values, color=COLORS['benchmark'], 
                    linewidth=1.5, linestyle='--', label='Benchmark')
        
        # 添加初始資金線
        ax.axhline(y=values.iloc[0] if hasattr(values, 'iloc') else values[0], 
                   color='gray', linestyle=':', alpha=0.7, label='Initial')
        
        ax.set_xlabel('Trading Days')
        ax.set_ylabel('Portfolio Value (TWD)')
        ax.set_title(title)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        
        # 格式化 y 軸
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[Visualizer] 權益曲線已儲存: {save_path}")
        
        return fig
    
    def plot_drawdown(
        self,
        portfolio_history: pd.DataFrame,
        title: str = "Drawdown",
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        繪製回撤圖
        
        Args:
            portfolio_history: 投資組合歷史
            title: 圖標題
            save_path: 儲存路徑
        
        Returns:
            matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        
        # 提取數據
        if isinstance(portfolio_history, pd.DataFrame):
            values = portfolio_history['portfolio_value']
        else:
            values = portfolio_history
        
        # 計算回撤
        peak = np.maximum.accumulate(values)
        drawdown = (values - peak) / peak * 100  # 轉換為百分比
        
        # 繪製回撤
        ax.fill_between(range(len(drawdown)), drawdown, 0, 
                        color=COLORS['negative'], alpha=0.3)
        ax.plot(drawdown, color=COLORS['negative'], linewidth=1)
        
        # 標記最大回撤
        max_dd_idx = np.argmin(drawdown)
        ax.axvline(x=max_dd_idx, color='red', linestyle='--', alpha=0.7)
        ax.scatter([max_dd_idx], [drawdown[max_dd_idx]], color='red', s=100, zorder=5)
        ax.annotate(f"Max DD: {drawdown[max_dd_idx]:.1f}%", 
                    xy=(max_dd_idx, drawdown[max_dd_idx]),
                    xytext=(max_dd_idx + 10, drawdown[max_dd_idx] - 5),
                    fontsize=10, color='red')
        
        ax.set_xlabel('Trading Days')
        ax.set_ylabel('Drawdown (%)')
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[Visualizer] 回撤圖已儲存: {save_path}")
        
        return fig
    
    def plot_returns_distribution(
        self,
        returns: np.ndarray,
        title: str = "Returns Distribution",
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        繪製報酬分佈
        
        Args:
            returns: 報酬率陣列
            title: 圖標題
            save_path: 儲存路徑
        
        Returns:
            matplotlib Figure
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        
        # 直方圖
        ax1.hist(returns, bins=50, color=COLORS['primary'], alpha=0.7, edgecolor='black')
        ax1.axvline(x=np.mean(returns), color='red', linestyle='--', linewidth=2, label=f'Mean: {np.mean(returns):.4f}')
        ax1.axvline(x=0, color='gray', linestyle='-', linewidth=1)
        ax1.set_xlabel('Daily Return')
        ax1.set_ylabel('Frequency')
        ax1.set_title('Returns Histogram')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # QQ 圖 (檢驗常態性)
        from scipy import stats
        stats.probplot(returns, dist="norm", plot=ax2)
        ax2.set_title('Q-Q Plot (Normal Distribution)')
        ax2.grid(True, alpha=0.3)
        
        fig.suptitle(title, fontsize=14)
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[Visualizer] 報酬分佈圖已儲存: {save_path}")
        
        return fig
    
    def plot_trade_analysis(
        self,
        trade_history: pd.DataFrame,
        title: str = "Trade Analysis",
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        繪製交易分析圖
        
        Args:
            trade_history: 交易歷史
            title: 圖標題
            save_path: 儲存路徑
        
        Returns:
            matplotlib Figure
        """
        if trade_history.empty:
            print("[Visualizer] 交易歷史為空，跳過交易分析圖")
            return None
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 提取 PnL
        if 'pnl' in trade_history.columns:
            pnls = trade_history['pnl'].values
            
            # 1. 累計盈虧
            ax1 = axes[0, 0]
            cumulative_pnl = np.cumsum(pnls)
            colors = [COLORS['positive'] if p > 0 else COLORS['negative'] for p in pnls]
            ax1.bar(range(len(pnls)), pnls, color=colors, alpha=0.7)
            ax1.plot(np.cumsum(pnls), color='black', linewidth=1.5)
            ax1.axhline(y=0, color='gray', linestyle='-', linewidth=1)
            ax1.set_xlabel('Trade Number')
            ax1.set_ylabel('PnL (TWD)')
            ax1.set_title('Cumulative PnL by Trade')
            ax1.grid(True, alpha=0.3)
            
            # 2. PnL 分佈
            ax2 = axes[0, 1]
            ax2.hist(pnls, bins=30, color=COLORS['primary'], alpha=0.7, edgecolor='black')
            ax2.axvline(x=0, color='red', linestyle='--', linewidth=2)
            ax2.set_xlabel('PnL (TWD)')
            ax2.set_ylabel('Frequency')
            ax2.set_title('PnL Distribution')
            ax2.grid(True, alpha=0.3)
            
            # 3. 買賣時機
            ax3 = axes[1, 0]
            if 'step' in trade_history.columns and 'price' in trade_history.columns:
                buys = trade_history[trade_history['action'] == 1]
                sells = trade_history[trade_history['action'].isin([2, 3, 4])]
                
                ax3.scatter(buys['step'], buys['price'], color=COLORS['positive'], 
                           marker='^', s=100, alpha=0.7, label='Buy')
                ax3.scatter(sells['step'], sells['price'], color=COLORS['negative'], 
                           marker='v', s=100, alpha=0.7, label='Sell')
                ax3.set_xlabel('Trading Days')
                ax3.set_ylabel('Price')
                ax3.set_title('Buy/Sell Timing')
                ax3.legend()
                ax3.grid(True, alpha=0.3)
            
            # 4. 交易頻率
            ax4 = axes[1, 1]
            if 'step' in trade_history.columns:
                trade_counts = trade_history.groupby('action').size()
                action_names = ['HOLD', 'BUY', 'SELL', 'CLOSE', 'STOP']
                colors = [COLORS['benchmark'], COLORS['positive'], COLORS['negative'], 
                         COLORS['secondary'], COLORS['negative']]
                ax4.bar([action_names[i] for i in trade_counts.index], 
                       trade_counts.values, color=[colors[i] for i in trade_counts.index])
                ax4.set_xlabel('Action')
                ax4.set_ylabel('Count')
                ax4.set_title('Action Distribution')
                ax4.grid(True, alpha=0.3, axis='y')
        
        fig.suptitle(title, fontsize=14)
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[Visualizer] 交易分析圖已儲存: {save_path}")
        
        return fig
    
    def plot_metrics_summary(
        self,
        metrics: Dict[str, float],
        title: str = "Performance Metrics Summary",
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        繪製指標摘要
        
        Args:
            metrics: 績效指標字典
            title: 圖標題
            save_path: 儲存路徑
        
        Returns:
            matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # 選擇要顯示的指標
        display_metrics = {
            'Total Return': metrics.get('total_return', 0) * 100,
            'Annualized Return': metrics.get('annualized_return', 0) * 100,
            'Sharpe Ratio': metrics.get('sharpe_ratio', 0),
            'Max Drawdown': metrics.get('max_drawdown', 0) * 100,
            'Win Rate': metrics.get('win_rate', 0) * 100,
        }
        
        names = list(display_metrics.keys())
        values = list(display_metrics.values())
        colors = ['green' if v >= 0 else 'red' for v in values]
        
        bars = ax.barh(names, values, color=colors, alpha=0.7)
        
        # 添加數值標籤
        for bar, val in zip(bars, values):
            if 'Ratio' in bar.get_text() or 'Rate' in bar.get_text():
                label = f'{val:.2f}'
            else:
                label = f'{val:.1f}%'
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                   label, va='center', fontsize=10)
        
        ax.axvline(x=0, color='gray', linestyle='-', linewidth=1)
        ax.set_xlabel('Value')
        ax.set_title(title)
        ax.grid(True, alpha=0.3, axis='x')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[Visualizer] 指標摘要圖已儲存: {save_path}")
        
        return fig
    
    def save_all(
        self,
        output_dir: str,
        portfolio_history: Optional[pd.DataFrame] = None,
        trade_history: Optional[pd.DataFrame] = None,
        metrics: Optional[Dict[str, float]] = None,
        prefix: str = ''
    ) -> Dict[str, str]:
        """
        儲存所有圖表
        
        Args:
            output_dir: 輸出目錄
            portfolio_history: 投資組合歷史
            trade_history: 交易歷史
            metrics: 績效指標
            prefix: 檔名稱前缀
        
        Returns:
            儲存路徑字典
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        paths = {}
        prefix = f"{prefix}_" if prefix else ""
        
        if portfolio_history is not None:
            # 權益曲線
            path = output_dir / f"{prefix}equity_curve.png"
            self.plot_equity_curve(portfolio_history, save_path=str(path))
            paths['equity_curve'] = str(path)
            
            # 回撤圖
            path = output_dir / f"{prefix}drawdown.png"
            self.plot_drawdown(portfolio_history, save_path=str(path))
            paths['drawdown'] = str(path)
            
            # 計算報酬用於分佈圖
            if 'portfolio_value' in portfolio_history.columns:
                returns = portfolio_history['portfolio_value'].pct_change().dropna().values
                path = output_dir / f"{prefix}returns_distribution.png"
                self.plot_returns_distribution(returns, save_path=str(path))
                paths['returns_distribution'] = str(path)
        
        if trade_history is not None and not trade_history.empty:
            path = output_dir / f"{prefix}trade_analysis.png"
            self.plot_trade_analysis(trade_history, save_path=str(path))
            paths['trade_analysis'] = str(path)
        
        if metrics is not None:
            path = output_dir / f"{prefix}metrics_summary.png"
            self.plot_metrics_summary(metrics, save_path=str(path))
            paths['metrics_summary'] = str(path)
        
        print(f"[Visualizer] 所有圖表已儲存到: {output_dir}")
        
        return paths
