"""
================================================================================
Visualizer - 視覺化模組 (v2新版)
================================================================================
提供績效視覺化功能：

主要功能：
    1. 淨值曲線 (Equity Curve)
    2. 回撤曲線 (Drawdown Chart)
    3. 報酬分佈 (Returns Distribution)
    4. 月報表 (Monthly Returns)

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, List, Dict
from pathlib import Path
import warnings

# 嘗試導入視覺化庫
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False

try:
    import seaborn as sns
    SNS_AVAILABLE = True
except ImportError:
    SNS_AVAILABLE = False


# =============================================================================
# 視覺化配置
# =============================================================================

# 設定中文字體（如果可用）
if MPL_AVAILABLE:
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False  # 處理負號


# =============================================================================
# 視覺化函數
# =============================================================================

def plot_equity_curve(
    equity_curve: pd.Series,
    save_path: Optional[str] = None,
    title: str = "Equity Curve",
    figsize: Tuple[int, int] = (12, 6),
    show_drawdown: bool = True,
) -> Optional['plt.Figure']:
    """
    繪製淨值曲線
    
    參數:
        equity_curve: 淨值序列
        save_path: 保存路徑
        title: 圖表標題
        figsize: 圖表大小
        show_drawdown: 是否顯示回撤
        
    返回:
        matplotlib Figure（如果可用）
    """
    if not MPL_AVAILABLE:
        warnings.warn("matplotlib 未安裝，無法繪圖")
        return None
    
    fig, axes = plt.subplots(2 if show_drawdown else 1, 1, figsize=figsize, sharex=True)
    
    if not show_drawdown:
        axes = [axes]
    
    # 淨值曲線
    ax = axes[0]
    ax.plot(equity_curve.index, equity_curve.values, 'b-', linewidth=1.5)
    ax.fill_between(equity_curve.index, equity_curve.values, alpha=0.3)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_ylabel('Portfolio Value (TWD)', fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(equity_curve.index[0], equity_curve.index[-1])
    
    # 格式化 y 軸
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    
    # 回撤曲線
    if show_drawdown:
        ax2 = axes[1]
        
        # 計算回撤
        running_max = equity_curve.cummax()
        drawdown = (equity_curve - running_max) / running_max * 100
        
        ax2.fill_between(drawdown.index, drawdown.values, 0, alpha=0.3, color='red')
        ax2.plot(drawdown.index, drawdown.values, 'r-', linewidth=0.5)
        ax2.set_ylabel('Drawdown (%)', fontsize=12)
        ax2.set_xlabel('Date', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(drawdown.index[0], drawdown.index[-1])
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Visualizer] 圖表已保存: {save_path}")
    
    return fig


def plot_drawdown(
    equity_curve: pd.Series,
    save_path: Optional[str] = None,
    title: str = "Drawdown",
    figsize: Tuple[int, int] = (12, 4),
) -> Optional['plt.Figure']:
    """
    繪製回撤曲線
    
    參數:
        equity_curve: 淨值序列
        save_path: 保存路徑
        title: 圖表標題
        figsize: 圖表大小
        
    返回:
        matplotlib Figure
    """
    if not MPL_AVAILABLE:
        warnings.warn("matplotlib 未安裝，無法繪圖")
        return None
    
    fig, ax = plt.subplots(figsize=figsize)
    
    # 計算回撤
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max * 100
    
    # 繪製
    ax.fill_between(drawdown.index, drawdown.values, 0, alpha=0.5, color='red')
    ax.plot(drawdown.index, drawdown.values, 'r-', linewidth=0.8)
    
    # 標記最大回撤
    max_dd_idx = drawdown.idxmin()
    max_dd_value = drawdown.min()
    
    ax.annotate(
        f'Max DD: {max_dd_value:.1f}%',
        xy=(max_dd_idx, max_dd_value),
        xytext=(10, -20),
        textcoords='offset points',
        fontsize=10,
        color='darkred',
        arrowprops=dict(arrowstyle='->', color='darkred', lw=1),
    )
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Drawdown (%)', fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(drawdown.index[0], drawdown.index[-1])
    ax.set_ylim(min(drawdown.min() * 1.1, 0), 5)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Visualizer] 圖表已保存: {save_path}")
    
    return fig


def plot_returns_distribution(
    returns: pd.Series,
    save_path: Optional[str] = None,
    title: str = "Returns Distribution",
    figsize: Tuple[int, int] = (10, 6),
    bins: int = 50,
) -> Optional['plt.Figure']:
    """
    繪製報酬分佈直方圖
    
    參數:
        returns: 報酬率序列
        save_path: 保存路徑
        title: 圖表標題
        figsize: 圖表大小
        bins: 直方圖 bins 數
        
    返回:
        matplotlib Figure
    """
    if not MPL_AVAILABLE:
        warnings.warn("matplotlib 未安裝，無法繪圖")
        return None
    
    if SNS_AVAILABLE:
        sns.set_style('whitegrid')
    
    fig, ax = plt.subplots(figsize=figsize)
    
    # 移除極端值用於顯示
    returns_clean = returns.dropna()
    display_returns = returns_clean[np.abs(returns_clean) < 5 * returns_clean.std(ddof=1)]
    
    # 繪製直方圖
    n, bins_arr, patches = ax.hist(
        display_returns,
        bins=bins,
        alpha=0.7,
        color='steelblue',
        edgecolor='white',
    )
    
    # 添加統計線
    mean_return = display_returns.mean()
    std_return = display_returns.std(ddof=1)
    
    ax.axvline(mean_return, color='green', linestyle='--', linewidth=2, label=f'Mean: {mean_return:.4f}')
    ax.axvline(mean_return + std_return, color='orange', linestyle=':', linewidth=1.5, label=f'+1 Std: {std_return:.4f}')
    ax.axvline(mean_return - std_return, color='orange', linestyle=':', linewidth=1.5, label=f'-1 Std: {std_return:.4f}')
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Daily Return', fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3, axis='y')
    
    # 添加統計資訊
    stats_text = f"Mean: {mean_return:.4f}\nStd: {std_return:.4f}\nSkew: {display_returns.skew():.2f}\nKurt: {display_returns.kurtosis():.2f}"
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Visualizer] 圖表已保存: {save_path}")
    
    return fig


def plot_monthly_returns(
    equity_curve: pd.Series,
    save_path: Optional[str] = None,
    title: str = "Monthly Returns",
    figsize: Tuple[int, int] = (14, 6),
) -> Optional['plt.Figure']:
    """
    繪製月度報酬熱力圖
    
    參數:
        equity_curve: 淨值序列
        save_path: 保存路徑
        title: 圖表標題
        figsize: 圖表大小
        
    返回:
        matplotlib Figure
    """
    if not MPL_AVAILABLE or not SNS_AVAILABLE:
        warnings.warn("matplotlib/seaborn 未安裝，無法繪圖")
        return None
    
    # 計算月度報酬
    monthly_returns = equity_curve.resample('M').last().pct_change()
    
    # 整理成 每年 x 每月 的矩陣
    df_monthly = monthly_returns.to_frame('return')
    df_monthly['year'] = df_monthly.index.year
    df_monthly['month'] = df_monthly.index.month
    
    pivot = df_monthly.pivot_table(values='return', index='year', columns='month') * 100
    
    # 創建圖表
    fig, ax = plt.subplots(figsize=figsize)
    
    # 繪製熱力圖
    sns.heatmap(
        pivot,
        annot=True,
        fmt='.1f',
        cmap='RdYlGn',
        center=0,
        ax=ax,
        cbar_kws={'label': 'Return (%)'},
        linewidths=0.5,
    )
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Month', fontsize=12)
    ax.set_ylabel('Year', fontsize=12)
    
    # 設定月份標籤
    month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    ax.set_xticklabels(month_labels, rotation=45)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Visualizer] 圖表已保存: {save_path}")
    
    return fig


def plot_trade_history(
    trades: pd.DataFrame,
    equity_curve: pd.Series,
    save_path: Optional[str] = None,
    title: str = "Trade History",
    figsize: Tuple[int, int] = (14, 8),
) -> Optional['plt.Figure']:
    """
    繪製交易歷史
    
    參數:
        trades: 交易記錄 DataFrame
        equity_curve: 淨值序列
        save_path: 保存路徑
        title: 圖表標題
        figsize: 圖表大小
        
    返回:
        matplotlib Figure
    """
    if not MPL_AVAILABLE:
        warnings.warn("matplotlib 未安裝，無法繪圖")
        return None
    
    fig, axes = plt.subplots(2, 1, figsize=figsize, gridspec_kw={'height_ratios': [3, 1]})
    
    # 淨值曲線 + 交易標記
    ax = axes[0]
    ax.plot(equity_curve.index, equity_curve.values, 'b-', linewidth=1, label='Equity')
    
    if not trades.empty and 'date' in trades.columns:
        trades['date'] = pd.to_datetime(trades['date'])
        
        # 標記買入
        buys = trades[trades['shares'] > 0]
        ax.scatter(buys['date'], equity_curve.loc[buys['date'].values].values,
                  marker='^', color='green', s=100, label='Buy', zorder=5)
        
        # 標記賣出
        sells = trades[trades['shares'] < 0]
        ax.scatter(sells['date'], equity_curve.loc[sells['date'].values].values,
                  marker='v', color='red', s=100, label='Sell', zorder=5)
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_ylabel('Portfolio Value (TWD)', fontsize=12)
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # 持股變化
    ax2 = axes[1]
    if not trades.empty and 'date' in trades.columns:
        position_history = trades.set_index('date')['position_after'].sort_index()
        ax2.fill_between(position_history.index, position_history.values, alpha=0.3, color='purple')
        ax2.plot(position_history.index, position_history.values, 'purple', linewidth=1)
    
    ax2.set_title('Position', fontsize=12)
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Shares', fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Visualizer] 圖表已保存: {save_path}")
    
    return fig


# =============================================================================
# Visualizer 類別
# =============================================================================

class Visualizer:
    """
    視覺化工具類別
    
    提供高層次的視覺化介面。
    
    使用範例:
        >>> from FinRL.v2.backtesting import Visualizer
        >>> 
        >>> viz = Visualizer(results)
        >>> 
        >>> # 繪製所有圖表
        >>> viz.plot_all()
        >>> 
        >>> # 單獨繪製
        >>> viz.plot_equity_curve()
        >>> viz.plot_drawdown()
        >>> viz.plot_returns_distribution()
    """
    
    def __init__(
        self,
        equity_curve: pd.Series,
        trades: Optional[pd.DataFrame] = None,
        results=None,
        save_dir: str = None,
    ):
        """
        初始化 Visualizer
        
        參數:
            equity_curve: 淨值序列
            trades: 交易記錄 DataFrame（可選）
            results: 績效結果物件（可選）
            save_dir: 圖表保存目錄
        """
        self.equity_curve = equity_curve
        self.trades = trades
        self.results = results
        self.figures = []
        
        if save_dir is None:
            self.save_dir = Path('results') / 'plots'
        else:
            self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
    
    def plot_all(self):
        """繪製所有圖表"""
        print("[Visualizer] 開始繪圖...")
        
        self.plot_equity_curve()
        self.plot_drawdown()
        self.plot_returns_distribution()
        
        if self.trades is not None and not self.trades.empty:
            self.plot_trade_history()
        
        print("[Visualizer] 繪圖完成")
    
    def plot_equity_curve(self, save: bool = True) -> Optional['plt.Figure']:
        """繪製淨值曲線"""
        save_path = self.save_dir / 'equity_curve.png' if save else None
        fig = plot_equity_curve(
            self.equity_curve,
            save_path=save_path,
            title=f'Equity Curve - {self.results.strategy_name if self.results else "Strategy"}',
        )
        self.figures.append(fig)
        return fig
    
    def plot_drawdown(self, save: bool = True) -> Optional['plt.Figure']:
        """繪製回撤曲線"""
        save_path = self.save_dir / 'drawdown.png' if save else None
        fig = plot_drawdown(
            self.equity_curve,
            save_path=save_path,
        )
        self.figures.append(fig)
        return fig
    
    def plot_returns_distribution(self, save: bool = True) -> Optional['plt.Figure']:
        """繪製報酬分佈"""
        returns = self.equity_curve.pct_change().dropna()
        save_path = self.save_dir / 'returns_distribution.png' if save else None
        fig = plot_returns_distribution(
            returns,
            save_path=save_path,
        )
        self.figures.append(fig)
        return fig
    
    def plot_trade_history(self, save: bool = True) -> Optional['plt.Figure']:
        """繪製交易歷史"""
        if self.trades is None or self.trades.empty:
            return None
        save_path = self.save_dir / 'trade_history.png' if save else None
        fig = plot_trade_history(
            self.trades,
            self.equity_curve,
            save_path=save_path,
        )
        self.figures.append(fig)
        return fig
    
    def save_dashboard(self, filename: str = 'dashboard.png'):
        """保存儀表板（所有圖表合併）"""
        if not MPL_AVAILABLE:
            return
        
        n_figs = len(self.figures)
        if n_figs == 0:
            return
        
        n_rows = (n_figs + 1) // 2
        fig, axes = plt.subplots(n_rows, 2, figsize=(16, 5 * n_rows))
        axes = axes.flatten() if n_figs > 1 else [axes]
        
        for i, fig in enumerate(self.figures):
            if fig is not None:
                axes[i].cla()
                for ax in fig.axes:
                    ax.remove()
                    ax.figure = fig
                    axes[i]. figures.append(ax)
                    ax.set_position(ax.get_position())
        
        plt.tight_layout()
        
        save_path = self.save_dir / filename
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Visualizer] 儀表板已保存: {save_path}")
    
    def close_all(self):
        """關閉所有圖表"""
        plt.close('all')
        self.figures = []


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Visualizer 測試")
    print("=" * 60)
    
    if MPL_AVAILABLE:
        print("[Visualizer] matplotlib 可用")
        
        # 測試繪圖
        print("\n[測試] 生成模擬資料...")
        dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')
        equity = 1_000_000 * np.cumprod(1 + np.random.normal(0.0008, 0.015, len(dates)))
        equity_curve = pd.Series(equity, index=dates)
        
        print("\n[測試] 繪製淨值曲線...")
        fig = plot_equity_curve(equity_curve, title="測試策略")
        
        if fig:
            print("  繪圖成功")
        
        print("\n[測試] 繪製回撤曲線...")
        fig = plot_drawdown(equity_curve)
        
        if fig:
            print("  繪圖成功")
    else:
        print("[Visualizer] matplotlib 未安裝")
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)