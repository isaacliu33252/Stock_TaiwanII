# ============================================================================
# Portfolio Backtester - 投資組合回測引擎
# ============================================================================
"""
用你現有的持股進行投資組合回測

功能:
    1. 根據你的實際持倉計算歷史表現
    2. 多檔股票組合格化
    3. 計算投資報酬、風險指標
    4. 與 benchmark (0050) 比較
    5. 產出視覺化報告
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import (
    ALL_TICKERS, PORTFOLIO_HOLDINGS,
    BACKTEST_INITIAL_CASH, BACKTEST_START, BACKTEST_END,
    COMMISSION_RATE, TRANSACTION_TAX_RATE, ETF_TAX_RATE,
    RISK_FREE_RATE, BENCHMARK_TICKER,
    ETF_TICKERS, TRADE_UNIT
)
from portfolio_data_loader import download_all_stocks


class PortfolioBacktester:
    """
    投資組合回測器

    根據用戶持有的股票和數量，計算歷史投資績效。
    """

    def __init__(
        self,
        holdings: dict = None,
        initial_cash: float = 1_000_000,
        start_date: str = None,
        end_date: str = None,
        commission: float = 0.001425,
        tax: float = 0.003
    ):
        self.holdings = holdings or PORTFOLIO_HOLDINGS
        self.initial_cash = initial_cash
        self.start_date = start_date or BACKTEST_START
        self.end_date = end_date or BACKTEST_END
        self.commission = commission
        self.tax = tax

        self.stock_data = {}
        self.portfolio_value = None
        self.returns = None
        self.metrics = {}

    def download_data(self):
        """下載所有持股的歷史數據"""
        print("=" * 60)
        print("投資組合回測 - 資料下載")
        print("=" * 60)
        print(f"持股: {list(self.holdings.keys())}")
        print(f"日期: {self.start_date} ~ {self.end_date}")

        tickers = list(self.holdings.keys())
        self.stock_data = download_all_stocks(
            tickers,
            self.start_date,
            self.end_date,
            cache_dir=str(PROJECT_ROOT / "data" / "portfolio_cache")
        )

        return self.stock_data

    def calculate_portfolio_value(self) -> pd.DataFrame:
        """
        根據持股數和歷史股價，計算投資組合價值變化
        """
        if not self.stock_data:
            self.download_data()

        # 收集所有日期 (取共同交易日)
        all_dates = set()
        for ticker, df in self.stock_data.items():
            if 'date' in df.columns:
                all_dates.update(pd.to_datetime(df['date']).tolist())

        all_dates = sorted(all_dates)
        common_dates = pd.to_datetime(all_dates)

        # 計算每支股票的價值
        portfolio_values = []
        for ticker, info in self.holdings.items():
            if ticker not in self.stock_data:
                print(f"  警告: {ticker} 無數據")
                continue

            df = self.stock_data[ticker].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()

            shares = info['shares']
            df['stock_value'] = df['close'] * shares

            # 對齊到共同日期
            df_aligned = df.reindex(common_dates, method='ffill')
            portfolio_values.append(df_aligned['stock_value'].rename(ticker))

        # 合併所有股票
        value_df = pd.concat(portfolio_values, axis=1)
        value_df = value_df.ffill().fillna(0)

        # 總組合價值
        value_df['total'] = value_df.sum(axis=1)

        # 加上現金 (假設初始資金投入組合)
        # 計算初始總成本
        first_valid = value_df.iloc[0]
        initial_investment = first_valid.sum()
        cash = self.initial_cash - initial_investment

        value_df['cash'] = cash
        value_df['portfolio_total'] = value_df['total'] + cash

        # 計算每日報酬率
        value_df['daily_return'] = value_df['portfolio_total'].pct_change()

        # 累計報酬率
        value_df['cumulative_return'] = (
            value_df['portfolio_total'] / self.initial_cash - 1
        )

        self.portfolio_value = value_df

        print(f"\n資料範圍: {value_df.index[0].date()} ~ {value_df.index[-1].date()}")
        print(f"初始投資: {initial_investment:,.0f} (持股) + {cash:,.0f} (現金)")
        print(f"初始總值: {self.initial_cash:,.0f}")

        return value_df

    def calculate_metrics(self) -> dict:
        """計算績效指標"""
        if self.portfolio_value is None:
            self.calculate_portfolio_value()

        df = self.portfolio_value

        total_return = df['portfolio_total'].iloc[-1] / self.initial_cash - 1
        annual_return = (1 + total_return) ** (252 / len(df)) - 1

        # 波動率 (年化)
        daily_returns = df['daily_return'].dropna()
        volatility = daily_returns.std() * np.sqrt(252)

        # Sharpe Ratio
        sharpe = (annual_return - RISK_FREE_RATE) / (volatility + 1e-10)

        # 最大回測 (MDD)
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Calmar Ratio
        calmar = annual_return / (abs(max_drawdown) + 1e-10)

        # Win rate
        win_days = (daily_returns > 0).sum()
        total_days = len(daily_returns)
        win_rate = win_days / total_days if total_days > 0 else 0

        # 月化報酬
        monthly = df['portfolio_total'].resample('ME').last()
        monthly_returns = monthly.pct_change().dropna()
        monthly_win_rate = (monthly_returns > 0).sum() / len(monthly_returns) if len(monthly_returns) > 0 else 0

        self.metrics = {
            "期間": f"{df.index[0].date()} ~ {df.index[-1].date()}",
            "總報酬率": f"{total_return*100:.2f}%",
            "年化報酬": f"{annual_return*100:.2f}%",
            "年化波動率": f"{volatility*100:.2f}%",
            "Sharpe Ratio": f"{sharpe:.3f}",
            "最大回測 (MDD)": f"{max_drawdown*100:.2f}%",
            "Calmar Ratio": f"{calmar:.3f}",
            "勝率 (日)": f"{win_rate*100:.1f}%",
            "勝率 (月)": f"{monthly_win_rate*100:.1f}%",
            "最終市值": f"{df['portfolio_total'].iloc[-1]:,.0f}",
        }

        return self.metrics

    def print_report(self):
        """輸出績效報告"""
        if not self.metrics:
            self.calculate_metrics()

        print("\n" + "=" * 60)
        print("  投資組合回測報告")
        print("=" * 60)

        for key, value in self.metrics.items():
            print(f"  {key:12s}: {value}")

        print("=" * 60)

        # 個股表現
        print("\n各檔股票表現:")
        if self.portfolio_value is not None:
            df = self.portfolio_value
            final_values = df.iloc[-1]
            initial_values = df.iloc[0]

            print(f"  {'代碼':10s} {'名稱':20s} {'持有股數':>8s} {'初始價值':>12s} {'最終價值':>12s} {'報酬率':>8s}")
            print("  " + "-" * 75)

            for ticker, info in self.holdings.items():
                if ticker in final_values.index:
                    init_val = initial_values[ticker]
                    final_val = final_values[ticker]
                    ret = (final_val / init_val - 1) * 100 if init_val > 0 else 0
                    shares = info['shares']
                    name = info.get('name', '')[:20]
                    print(f"  {ticker:10s} {name:20s} {shares:>8,} {init_val:>12,.0f} {final_val:>12,.0f} {ret:>7.1f}%")

        print()

    def plot_results(self, save_path: str = None):
        """繪製結果圖表"""
        if self.portfolio_value is None:
            self.calculate_portfolio_value()

        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates

            df = self.portfolio_value.copy()
            df.index = pd.to_datetime(df.index)

            fig, axes = plt.subplots(3, 1, figsize=(14, 12))

            # 1. 組合價值曲線
            ax1 = axes[0]
            ax1.plot(df.index, df['portfolio_total'], label='投資組合', linewidth=2)
            ax1.axhline(self.initial_cash, color='gray', linestyle='--', label='初始資金')
            ax1.set_title('投資組合價值', fontsize=14)
            ax1.set_ylabel('價值 (TWD)')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

            # 2. 累計報酬率
            ax2 = axes[1]
            ax2.fill_between(df.index, 0, df['cumulative_return']*100,
                             where=df['cumulative_return'] >= 0,
                             color='green', alpha=0.3, label='獲利')
            ax2.fill_between(df.index, 0, df['cumulative_return']*100,
                             where=df['cumulative_return'] < 0,
                             color='red', alpha=0.3, label='虧損')
            ax2.axhline(0, color='black', linewidth=0.5)
            ax2.set_title('累計報酬率', fontsize=14)
            ax2.set_ylabel('報酬率 (%)')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

            # 3. 回測
            ax3 = axes[2]
            cumulative = (1 + df['daily_return'].fillna(0)).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max * 100
            ax3.fill_between(df.index, 0, drawdown, color='red', alpha=0.3)
            ax3.set_title('回測 (Drawdown)', fontsize=14)
            ax3.set_ylabel('回測 (%)')
            ax3.grid(True, alpha=0.3)
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)

            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=150, bbox_inches='tight')
                print(f"圖表已儲存: {save_path}")

            plt.close()

        except ImportError:
            print("警告: 需要 matplotlib 才能繪圖")

    def save_results(self, output_dir: str = None):
        """儲存結果到檔案"""
        if output_dir is None:
            output_dir = PROJECT_ROOT / "results" / "portfolio_backtest"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # 儲存組合價值
        if self.portfolio_value is not None:
            value_file = output_dir / "portfolio_value.csv"
            self.portfolio_value.to_csv(value_file)
            print(f"數據已儲存: {value_file}")

        # 儲存報告
        report_file = output_dir / "backtest_report.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("  投資組合回測報告\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"回測日期: {datetime.now()}\n")
            f.write(f"期間: {self.metrics.get('期間', 'N/A')}\n")
            f.write(f"初始資金: {self.initial_cash:,.0f}\n\n")

            for key, value in self.metrics.items():
                f.write(f"  {key}: {value}\n")

            f.write("\n持股明細:\n")
            for ticker, info in self.holdings.items():
                f.write(f"  {ticker} ({info.get('name', '')}): {info['shares']} 股\n")

        print(f"報告已儲存: {report_file}")

        # 繪圖
        chart_file = output_dir / "backtest_chart.png"
        self.plot_results(str(chart_file))


# =============================================================================
# 主程式
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='投資組合回測')
    parser.add_argument('--start', type=str, default=BACKTEST_START,
                        help='回測開始日期')
    parser.add_argument('--end', type=str, default=BACKTEST_END,
                        help='回測結束日期')
    parser.add_argument('--cash', type=float, default=BACKTEST_INITIAL_CASH,
                        help='初始資金')
    parser.add_argument('--save', action='store_true',
                        help='儲存結果')
    args = parser.parse_args()

    print("=" * 60)
    print("  投資組合回測系統")
    print("=" * 60)
    print(f"你的持股:")
    for ticker, info in PORTFOLIO_HOLDINGS.items():
        print(f"  {ticker} ({info['name']}): {info['shares']:,} 股")
    print("=" * 60)

    # 建立回測器
    backtester = PortfolioBacktester(
        initial_cash=args.cash,
        start_date=args.start,
        end_date=args.end
    )

    # 下載數據
    backtester.download_data()

    # 計算
    backtester.calculate_portfolio_value()
    backtester.calculate_metrics()

    # 報告
    backtester.print_report()

    # 儲存
    if args.save:
        backtester.save_results()
