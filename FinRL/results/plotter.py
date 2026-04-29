# ============================================================================
# 繪圖模組 (Plotter)
# ============================================================================
"""
提供各種視覺化功能，用於展示回測結果和交易分析。

功能特色：
- 權益曲線（Equity Curve）繪製
- 回撤曲線（Drawdown Chart）繪製
- 報酬分佈（Returns Distribution）繪製
- 交易歷史標記（Buy/Sell 標記在價格圖上）
- PyFolio 風格 tearsheet 產生
- 績效指標儀表板

使用方式：
    from FinRL.results.plotter import TradingPlotter
    
    plotter = TradingPlotter()
    plotter.plot_equity_curve(equity_curve)
    plotter.plot_drawdown(equity_curve)
    plotter.plot_trade_history(trades, price_data)
    plotter.generate_tearsheet(backtest_result)

作者: FinRL量化交易專家
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import warnings

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLOT_STYLE, PLOT_DPI, PLOT_FIGSIZE, RESULTS_DIR

# 忽略警告
warnings.filterwarnings('ignore')

# 嘗試導入 pyfolio（用於 tearsheet）
try:
    import pyfolio as pf
    PYFOLIO_AVAILABLE = True
except ImportError:
    PYFOLIO_AVAILABLE = False
    print("[TradingPlotter] PyFolio 未安裝，tearsheet 功能將受限")


class TradingPlotter:
    """
    交易策略視覺化工具
    
    提供完整的圖表繪製功能，用於分析交易策略表現。
    
    屬性：
        style: 繪圖風格
        dpi: 圖表解析度
        figsize: 預設圖表大小
        results_dir: 結果儲存目錄
    
    使用範例：
        >>> plotter = TradingPlotter()
        >>> plotter.plot_equity_curve(equity_curve, dates=dates)
        >>> plotter.plot_drawdown(equity_curve)
        >>> plotter.generate_tearsheet(backtest_result)
    """
    
    def __init__(
        self,
        style: str = PLOT_STYLE,
        dpi: int = PLOT_DPI,
        figsize: tuple = PLOT_FIGSIZE,
        results_dir: str = RESULTS_DIR
    ):
        """
        初始化繪圖器
        
        參數：
            style: 繪圖風格（預設使用 config.py 中的設定）
            dpi: 圖表解析度
            figsize: 預設圖表大小
            results_dir: 結果儲存目錄
        """
        self.style = style
        self.dpi = dpi
        self.figsize = figsize
        self.results_dir = results_dir
        
        # 設定繪圖風格
        try:
            plt.style.use(style)
        except Exception:
            plt.style.use('default')
        
        # 確保結果目錄存在
        os.makedirs(self.results_dir, exist_ok=True)
        
        # 顏色配置
        self.colors = {
            'primary': '#2E86AB',
            'secondary': '#A23B72',
            'positive': '#28A745',
            'negative': '#DC3545',
            'neutral': '#6C757D',
            'grid': '#E0E0E0',
        }
    
    def plot_equity_curve(
        self,
        equity_curve: np.ndarray,
        dates: Optional[List] = None,
        benchmark: Optional[np.ndarray] = None,
        benchmark_name: str = "買入並持有",
        title: str = "權益曲線",
        save_path: Optional[str] = None,
        show: bool = True
    ) -> plt.Figure:
        """
        繪製權益曲線（Equity Curve）
        
        權益曲線顯示投資組合價值隨時間的變化，
        是評估策略整體表現的核心圖表。
        
        參數：
            equity_curve: 權益曲線陣列
            dates: 日期列表（可選）
            benchmark: 基準指標曲線（如買入並持有）
            benchmark_name: 基準名稱
            title: 圖表標題
            save_path: 儲存路徑
            show: 是否顯示圖表
        
        返回：
            matplotlib Figure 物件
        """
        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)
        
        # 設定 x 軸
        if dates is not None:
            x = dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            plt.xticks(rotation=45)
        else:
            x = range(len(equity_curve))
        
        # 繪製權益曲線
        ax.plot(x, equity_curve, linewidth=1.5, color=self.colors['primary'], label='投資組合')
        
        # 繪製基準（如果提供）
        if benchmark is not None:
            if dates is not None:
                ax.plot(dates, benchmark, linewidth=1, alpha=0.7, 
                       color=self.colors['neutral'], label=benchmark_name)
            else:
                ax.plot(range(len(benchmark)), benchmark, linewidth=1, alpha=0.7,
                       color=self.colors['neutral'], label=benchmark_name)
        
        # 計算並標註最終價值
        final_value = equity_curve[-1]
        initial_value = equity_curve[0]
        total_return = (final_value - initial_value) / initial_value * 100
        
        ax.set_title(f'{title}\n最終價值: {final_value:,.0f} | 報酬率: {total_return:.2f}%', 
                    fontsize=14, fontweight='bold')
        ax.set_xlabel('時間', fontsize=12)
        ax.set_ylabel('價值 (TWD)', fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # 格式化 y 軸
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            print(f"[TradingPlotter] 圖表已儲存至：{save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return fig
    
    def plot_drawdown(
        self,
        equity_curve: np.ndarray,
        dates: Optional[List] = None,
        title: str = "回撤分析",
        save_path: Optional[str] = None,
        show: bool = True
    ) -> plt.Figure:
        """
        繪製回撤曲線（Drawdown Chart）
        
        回撤曲線顯示投資組合從歷史高峰到低谷的跌幅，
        是風險管理的關鍵指標。
        
        參數：
            equity_curve: 權益曲線
            dates: 日期列表
            title: 圖表標題
            save_path: 儲存路徑
            show: 是否顯示
        
        返回：
            matplotlib Figure 物件
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=self.figsize, dpi=self.dpi, 
                                       gridspec_kw={'height_ratios': [2, 1]})
        
        # 設定 x 軸
        if dates is not None:
            x = dates
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        else:
            x = range(len(equity_curve))
        
        # ========================================
        # 上圖：投資組合價值
        # ========================================
        ax1.plot(x, equity_curve, linewidth=1.5, color=self.colors['primary'])
        
        # 標註歷史高點
        running_max = np.maximum.accumulate(equity_curve)
        ax1.plot(x, running_max, linewidth=1, color=self.colors['neutral'], 
                alpha=0.7, linestyle='--', label='歷史高點')
        ax1.fill_between(x, equity_curve, running_max, alpha=0.3, color=self.colors['secondary'])
        
        ax1.set_title('投資組合價值', fontsize=12)
        ax1.set_ylabel('價值 (TWD)', fontsize=10)
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
        
        # ========================================
        # 下圖：回撤百分比
        # ========================================
        # 計算回撤
        cumulative = equity_curve / equity_curve[0] if equity_curve[0] > 0 else equity_curve
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max * 100  # 轉換為百分比
        
        ax2.fill_between(x, drawdowns, 0, alpha=0.3, color=self.colors['negative'])
        ax2.plot(x, drawdowns, color=self.colors['negative'], linewidth=1)
        
        # 標註最大回撤
        max_dd_idx = np.argmin(drawdowns)
        max_dd = drawdowns[max_dd_idx]
        
        ax2.scatter([x[max_dd_idx]], [max_dd], color='red', s=100, zorder=5)
        ax2.annotate(
            f'最大回撤: {max_dd:.2f}%',
            xy=(x[max_dd_idx], max_dd),
            xytext=(10, -20),
            textcoords='offset points',
            arrowprops=dict(arrowstyle='->', color='black'),
            fontsize=10,
        )
        
        ax2.set_title('回撤 (%)', fontsize=12)
        ax2.set_xlabel('時間', fontsize=10)
        ax2.set_ylabel('回撤 (%)', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        plt.suptitle(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            print(f"[TradingPlotter] 圖表已儲存至：{save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return fig
    
    def plot_returns_distribution(
        self,
        returns: np.ndarray,
        title: str = "報酬分佈",
        save_path: Optional[str] = None,
        show: bool = True
    ) -> plt.Figure:
        """
        繪製報酬分佈圖（Returns Distribution）
        
        報酬分佈顯示策略報酬率的統計分佈，
        有助於了解報酬的特徵（正/負偏態、肥尾等）。
        
        參數：
            returns: 收益率序列
            title: 圖表標題
            save_path: 儲存路徑
            show: 是否顯示
        
        返回：
            matplotlib Figure 物件
        """
        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)
        
        # 轉換為百分比
        returns_pct = returns * 100
        
        # 繪製直方圖
        n, bins, patches = ax.hist(returns_pct, bins=50, alpha=0.7, 
                                   edgecolor='black', density=True)
        
        # 著色（正/負報酬）
        for i, patch in enumerate(patches):
            bin_center = (bins[i] + bins[i+1]) / 2
            if bin_center < 0:
                patch.set_facecolor(self.colors['negative'])
            else:
                patch.set_facecolor(self.colors['positive'])
        
        # 標註統計數據
        mean_return = np.mean(returns_pct)
        median_return = np.median(returns_pct)
        std_return = np.std(returns_pct)
        
        ax.axvline(mean_return, color='red', linestyle='--', linewidth=2, 
                  label=f'平均值: {mean_return:.2f}%')
        ax.axvline(median_return, color='green', linestyle='--', linewidth=2,
                  label=f'中位數: {median_return:.2f}%')
        
        # 添加機率密度曲線
        from scipy import stats
        x_range = np.linspace(returns_pct.min(), returns_pct.max(), 100)
        kde = stats.gaussian_kde(returns_pct)
        ax.plot(x_range, kde(x_range), color='blue', linewidth=2, alpha=0.7, label='KDE')
        
        ax.set_title(f'{title}\n標準差: {std_return:.2f}%', fontsize=14, fontweight='bold')
        ax.set_xlabel('日報酬率 (%)', fontsize=12)
        ax.set_ylabel('密度', fontsize=12)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 添加統計摘要文字框
        textstr = f'Mean: {mean_return:.2f}%\nMedian: {median_return:.2f}%\nStd: {std_return:.2f}%\nSkew: {stats.skew(returns_pct):.2f}\nKurt: {stats.kurtosis(returns_pct):.2f}'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
        ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
                verticalalignment='top', bbox=props)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            print(f"[TradingPlotter] 圖表已儲存至：{save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return fig
    
    def plot_trade_history(
        self,
        trades: List[Dict],
        price_data: pd.DataFrame,
        title: str = "交易記錄",
        save_path: Optional[str] = None,
        show: bool = True
    ) -> plt.Figure:
        """
        繪製交易歷史（Buy/Sell 標記在價格圖上）
        
        此圖表將所有買入/賣出動作標記在價格圖上，
        有助於視覺化檢視交易策略的進出點。
        
        參數：
            trades: 交易歷史列表
            price_data: 價格數據 DataFrame（需包含 'date', 'close' 欄位）
            title: 圖表標題
            save_path: 儲存路徑
            show: 是否顯示
        
        返回：
            matplotlib Figure 物件
        """
        fig, ax = plt.subplots(figsize=(14, 7), dpi=self.dpi)
        
        # 繪製價格曲線
        if 'date' in price_data.columns:
            dates = price_data['date'].values
            ax.plot(dates, price_data['close'].values, linewidth=1, 
                   color=self.colors['primary'], label='收盤價')
            
            # 標註交易
            buy_steps = []
            sell_steps = []
            
            for trade in trades:
                action = trade.get('action', 0)
                step = trade.get('step', 0)
                
                if action == 1:  # BUY
                    buy_steps.append(step)
                elif action in [2, 3]:  # SELL or CLOSE
                    sell_steps.append(step)
            
            # 繪製買入標記
            if buy_steps:
                buy_prices = price_data['close'].iloc[buy_steps].values
                ax.scatter(buy_steps, buy_prices, color=self.colors['positive'], 
                         marker='^', s=150, label='買入', zorder=5, edgecolors='black')
            
            # 繪製賣出標記
            if sell_steps:
                sell_prices = price_data['close'].iloc[sell_steps].values
                ax.scatter(sell_steps, sell_prices, color=self.colors['negative'],
                         marker='v', s=150, label='賣出', zorder=5, edgecolors='black')
            
            # 格式化 x 軸
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            plt.xticks(rotation=45)
        
        else:
            # 無日期索引
            close = price_data['close'].values
            ax.plot(close, linewidth=1, color=self.colors['primary'], label='收盤價')
            
            # 標註交易
            for trade in trades:
                action = trade.get('action', 0)
                step = trade.get('step', 0)
                
                if step >= len(close):
                    continue
                
                price = close[step]
                
                if action == 1:  # BUY
                    ax.scatter([step], [price], color=self.colors['positive'],
                             marker='^', s=150, zorder=5, edgecolors='black')
                elif action in [2, 3]:  # SELL
                    ax.scatter([step], [price], color=self.colors['negative'],
                             marker='v', s=150, zorder=5, edgecolors='black')
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('時間', fontsize=12)
        ax.set_ylabel('價格 (TWD)', fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            print(f"[TradingPlotter] 圖表已儲存至：{save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return fig
    
    def plot_monthly_returns(
        self,
        returns: np.ndarray,
        dates: Optional[List] = None,
        title: str = "月度報酬熱力圖",
        save_path: Optional[str] = None,
        show: bool = True
    ) -> plt.Figure:
        """
        繪製月度報酬熱力圖
        
        顯示每個月的報酬表現，幫助識別季節性模式。
        
        參數：
            returns: 收益率序列
            dates: 日期列表
            title: 圖表標題
            save_path: 儲存路徑
            show: 是否顯示
        
        返回：
            matplotlib Figure 物件
        """
        # 創建月度報酬 DataFrame
        if dates is not None:
            df = pd.DataFrame({'date': dates, 'return': returns})
            df['date'] = pd.to_datetime(df['date'])
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
        else:
            df = pd.DataFrame({'return': returns})
            df['year'] = df.index // 12 + 1
            df['month'] = df.index % 12 + 1
        
        # 計算月度報酬
        monthly_returns = df.groupby(['year', 'month'])['return'].sum().unstack(fill_value=0)
        
        # 繪製熱力圖
        fig, ax = plt.subplots(figsize=(12, 8), dpi=self.dpi)
        
        im = ax.imshow(monthly_returns.values, cmap='RdYlGn', aspect='auto', vmin=-0.1, vmax=0.1)
        
        # 設置標籤
        ax.set_xticks(np.arange(monthly_returns.shape[1]))
        ax.set_yticks(np.arange(monthly_returns.shape[0]))
        ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][:monthly_returns.shape[1]])
        ax.set_yticklabels(monthly_returns.index)
        
        # 添加數值標註
        for i in range(monthly_returns.shape[0]):
            for j in range(monthly_returns.shape[1]):
                value = monthly_returns.values[i, j]
                color = 'white' if abs(value) > 0.05 else 'black'
                ax.text(j, i, f'{value*100:.1f}%', ha='center', va='center', color=color, fontsize=9)
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('月份', fontsize=12)
        ax.set_ylabel('年份', fontsize=12)
        
        # 添加 colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('報酬率', fontsize=10)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            print(f"[TradingPlotter] 圖表已儲存至：{save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return fig
    
    def plot_metrics_dashboard(
        self,
        metrics: Dict[str, Any],
        title: str = "績效指標儀表板",
        save_path: Optional[str] = None,
        show: bool = True
    ) -> plt.Figure:
        """
        繪製績效指標儀表板
        
        以視覺化方式呈現所有關鍵績效指標。
        
        參數：
            metrics: 績效指標字典
            title: 圖表標題
            save_path: 儲存路徑
            show: 是否顯示
        
        返回：
            matplotlib Figure 物件
        """
        fig = plt.figure(figsize=(16, 10), dpi=self.dpi)
        gs = GridSpec(3, 4, figure=fig, hspace=0.3, wspace=0.3)
        
        # ========================================
        # 1. 報酬指標（大型文字展示）
        # ========================================
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.axis('off')
        
        total_return = metrics.get('total_return', 0) * 100
        annual_return = metrics.get('annual_return', 0) * 100
        final_value = metrics.get('final_value', 0)
        initial_balance = metrics.get('initial_balance', 1_000_000)
        
        return_text = f"""
        總報酬率: {total_return:.2f}%
        年化報酬: {annual_return:.2f}%
        最終價值: {final_value:,.0f} TWD
        """
        ax1.text(0.5, 0.5, return_text, transform=ax1.transAxes, fontsize=20,
                verticalalignment='center', horizontalalignment='center',
                bbox=dict(boxstyle='round', facecolor=self.colors['primary'], alpha=0.3),
                family='monospace')
        ax1.set_title('報酬摘要', fontsize=14, fontweight='bold')
        
        # ========================================
        # 2. 風險指標
        # ========================================
        ax2 = fig.add_subplot(gs[0, 2:])
        ax2.axis('off')
        
        max_drawdown = metrics.get('max_drawdown', 0) * 100
        sharpe = metrics.get('sharpe_ratio', 0)
        sortino = metrics.get('sortino_ratio', 0)
        calmar = metrics.get('calmar_ratio', 0)
        
        risk_text = f"""
        最大回撤: {max_drawdown:.2f}%
        夏普比率: {sharpe:.3f}
        索提諾: {sortino:.3f}
        卡瑪比率: {calmar:.3f}
        """
        ax2.text(0.5, 0.5, risk_text, transform=ax2.transAxes, fontsize=20,
                verticalalignment='center', horizontalalignment='center',
                bbox=dict(boxstyle='round', facecolor=self.colors['negative'], alpha=0.3),
                family='monospace')
        ax2.set_title('風險指標', fontsize=14, fontweight='bold')
        
        # ========================================
        # 3. 交易統計
        # ========================================
        ax3 = fig.add_subplot(gs[1, :2])
        ax3.axis('off')
        
        total_trades = metrics.get('total_trades', 0)
        win_rate = metrics.get('win_rate', 0) * 100
        profit_factor = metrics.get('profit_factor', 0)
        
        trade_text = f"""
        總交易次數: {total_trades}
        勝率: {win_rate:.1f}%
        利潤因子: {profit_factor:.2f}
        """
        ax3.text(0.5, 0.5, trade_text, transform=ax3.transAxes, fontsize=18,
                verticalalignment='center', horizontalalignment='center',
                bbox=dict(boxstyle='round', facecolor=self.colors['positive'], alpha=0.3),
                family='monospace')
        ax3.set_title('交易統計', fontsize=14, fontweight='bold')
        
        # ========================================
        # 4. 平均獲利/虧損
        # ========================================
        ax4 = fig.add_subplot(gs[1, 2:])
        ax4.axis('off')
        
        avg_win = metrics.get('avg_win', 0)
        avg_loss = metrics.get('avg_loss', 0)
        win_loss_ratio = metrics.get('win_loss_ratio', 0)
        
        wl_text = f"""
        平均獲利: {avg_win:,.0f} TWD
        平均虧損: {avg_loss:,.0f} TWD
        獲利/虧損比: {win_loss_ratio:.2f}
        """
        ax4.text(0.5, 0.5, wl_text, transform=ax4.transAxes, fontsize=18,
                verticalalignment='center', horizontalalignment='center',
                bbox=dict(boxstyle='round', facecolor=self.colors['secondary'], alpha=0.3),
                family='monospace')
        ax4.set_title('獲利/虧損分析', fontsize=14, fontweight='bold')
        
        # ========================================
        # 5. 報酬率分佈（迷你版）
        # ========================================
        ax5 = fig.add_subplot(gs[2, :])
        
        # 這個需要在外部有 returns 數據，這裡只顯示一個 placeholder
        ax5.text(0.5, 0.5, '請使用 plot_returns_distribution() 查看詳細分佈', 
                transform=ax5.transAxes, fontsize=14, verticalalignment='center',
                horizontalalignment='center', style='italic', color='gray')
        ax5.set_title('報酬分佈', fontsize=14, fontweight='bold')
        
        plt.suptitle(title, fontsize=18, fontweight='bold', y=1.02)
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            print(f"[TradingPlotter] 圖表已儲存至：{save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return fig
    
    def generate_tearsheet(
        self,
        backtest_result: Dict[str, Any],
        benchmark_returns: Optional[np.ndarray] = None,
        save_dir: Optional[str] = None,
        show: bool = True
    ) -> str:
        """
        產生 PyFolio 風格 Tearsheet
        
        這是一個完整的回測分析報告，包含：
        - 權益曲線
        - 回撤分析
        - 報酬分佈
        - 交易統計
        - 月度報酬
        
        參數：
            backtest_result: 回測結果字典（包含 returns, trades, metrics 等）
            benchmark_returns: 基準收益率序列（可選）
            save_dir: 儲存目錄
            show: 是否顯示
        
        返回：
            報告儲存路徑
        """
        if not PYFOLIO_AVAILABLE:
            print("[TradingPlotter] PyFolio 未安裝，使用自訂 tearsheet")
            return self._generate_custom_tearsheet(backtest_result, save_dir, show)
        
        returns = backtest_result.get('returns', np.array([]))
        dates = backtest_result.get('dates', None)
        
        # 建立 returns Series
        if dates is not None and len(dates) == len(returns):
            returns_series = pd.Series(returns, index=pd.to_datetime(dates))
        else:
            returns_series = pd.Series(returns)
        
        if save_dir is None:
            save_dir = self.results_dir
        
        os.makedirs(save_dir, exist_ok=True)
        
        # 使用 PyFolio 產生 tearsheet
        try:
            pf.create_full_tear_sheet(
                returns_series,
                benchmark_returns=benchmark_returns,
                live_start_date=None,
                cone=None,
                style=None,
                Berkshire=None,
            )
            print(f"[TradingPlotter] PyFolio tearsheet 已產生")
        except Exception as e:
            print(f"[TradingPlotter] PyFolio tearsheet 產生失敗: {e}")
            return self._generate_custom_tearsheet(backtest_result, save_dir, show)
        
        return save_dir
    
    def _generate_custom_tearsheet(
        self,
        backtest_result: Dict[str, Any],
        save_dir: Optional[str],
        show: bool
    ) -> str:
        """
        產生自訂 Tearsheet（當 PyFolio 不可用時使用）
        """
        if save_dir is None:
            save_dir = self.results_dir
        
        os.makedirs(save_dir, exist_ok=True)
        
        equity_curve = backtest_result.get('portfolio_values', np.array([]))
        returns = backtest_result.get('returns', np.array([]))
        dates = backtest_result.get('dates', None)
        metrics = backtest_result.get('metrics', {})
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. 權益曲線
        self.plot_equity_curve(
            equity_curve, dates,
            save_path=os.path.join(save_dir, f'equity_curve_{timestamp}.png'),
            show=False
        )
        
        # 2. 回撤分析
        self.plot_drawdown(
            equity_curve, dates,
            save_path=os.path.join(save_dir, f'drawdown_{timestamp}.png'),
            show=False
        )
        
        # 3. 報酬分佈
        self.plot_returns_distribution(
            returns,
            save_path=os.path.join(save_dir, f'returns_dist_{timestamp}.png'),
            show=False
        )
        
        # 4. 績效儀表板
        self.plot_metrics_dashboard(
            metrics,
            save_path=os.path.join(save_dir, f'metrics_dashboard_{timestamp}.png'),
            show=False
        )
        
        print(f"[TradingPlotter] 自訂 tearsheet 已儲存至：{save_dir}")
        
        return save_dir
    
    def save_all_plots(
        self,
        backtest_result: Dict[str, Any],
        name: str = "backtest",
        save_dir: Optional[str] = None
    ) -> str:
        """
        儲存所有圖表
        
        參數：
            backtest_result: 回測結果字典
            name: 實驗名稱
            save_dir: 儲存目錄
        
        返回：
            儲存目錄路徑
        """
        if save_dir is None:
            save_dir = self.results_dir
        
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        equity_curve = backtest_result.get('portfolio_values', np.array([]))
        returns = backtest_result.get('returns', np.array([]))
        dates = backtest_result.get('dates', None)
        trades = backtest_result.get('trade_history', [])
        metrics = backtest_result.get('metrics', {})
        
        # 1. 權益曲線
        self.plot_equity_curve(
            equity_curve, dates,
            save_path=os.path.join(save_dir, f'{name}_equity_{timestamp}.png'),
            show=False
        )
        
        # 2. 回撤分析
        self.plot_drawdown(
            equity_curve, dates,
            save_path=os.path.join(save_dir, f'{name}_drawdown_{timestamp}.png'),
            show=False
        )
        
        # 3. 報酬分佈
        if len(returns) > 10:
            self.plot_returns_distribution(
                returns,
                save_path=os.path.join(save_dir, f'{name}_returns_{timestamp}.png'),
                show=False
            )
        
        # 4. 交易記錄（如果提供價格數據）
        # 需要單獨調用
        
        # 5. 績效儀表板
        self.plot_metrics_dashboard(
            metrics,
            save_path=os.path.join(save_dir, f'{name}_dashboard_{timestamp}.png'),
            show=False
        )
        
        print(f"[TradingPlotter] 所有圖表已儲存至：{save_dir}")
        return save_dir


# ============================================================================
# 工廠函式
# ============================================================================

def create_plotter(
    style: str = PLOT_STYLE,
    dpi: int = PLOT_DPI,
    figsize: tuple = PLOT_FIGSIZE,
    **kwargs
) -> TradingPlotter:
    """
    便捷函式：建立繪圖器
    
    參數：
        style: 繪圖風格
        dpi: 圖表解析度
        figsize: 預設圖表大小
        **kwargs: 其他參數
    
    返回：
        TradingPlotter 實例
    """
    return TradingPlotter(style=style, dpi=dpi, figsize=figsize, **kwargs)