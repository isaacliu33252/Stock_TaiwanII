# ============================================================================
# Walk-Forward Analysis Framework - walk-forward 回測框架
# ============================================================================
"""
避免 overfitting 的穩健回測方法。

Walk-Forward 核心概念：
    - 訓練期（in-sample）：用於優化策略參數
    - 測試期（out-of-sample）：僅用於評估績效
    - 滑動視窗前進，重複多次

優點：
    1. 每個測試區間都是「未見過」的數據，杜絕 look-ahead bias
    2. 參數在歷史數據上優化，但績效在獨立數據上驗證
    3. 多次滾動的結果具有統計可信度

Monte Carlo 模擬：
    - 對每日報酬進行隨機重採樣，評估策略穩健性
    - 計算報酬率分佈，而非點估計
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WalkForwardResult:
    """單次 Walk-Forward 結果"""
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    total_return: float
    annual_return: float
    sharpe: float
    max_drawdown: float
    calmar: float
    win_rate: float
    num_trades: int
    n_test_days: int


@dataclass
class WalkForwardSummary:
    """整體匯總"""
    n_windows: int
    mean_return: float
    std_return: float
    mean_sharpe: float
    mean_mdd: float
    win_rate_overall: float
    p_value: float  # 統計顯著性（相對於 buy & hold）
    results: List[WalkForwardResult]


class WalkForwardBacktester:
    """
    Walk-Forward 回測器
    
    使用方式：
        1. 設定訓練/測試期比例與視窗大小
        2. 呼叫 run() 執行 walk-forward
        3. 呼叫 Monte Carlo 進行不確定性分析
        4. 呼叫 summary() 取得統計報告
    """

    def __init__(
        self,
        stock_data: dict,               # {ticker: DataFrame}
        holdings: dict,                 # PORTFOLIO_HOLDINGS
        train_window_years: float = 2.0,   # 訓練期長度（年）
        test_window_days: int = 60,        # 測試期長度（天）
        step_days: int = 20,              # 滑動步幅（天）
        risk_free_rate: float = 0.02,
        initial_value: float = None,
    ):
        self.stock_data = stock_data
        self.holdings = holdings
        self.train_years = train_window_years
        self.test_days = test_window_days
        self.step_days = step_days
        self.risk_free = risk_free_rate
        self.initial_value = initial_value

        self._build_aligned_data()
        self.results: List[WalkForwardResult] = []

    def _build_aligned_data(self):
        """對齊所有股票的交易日，取交集"""
        all_dates = set()
        for ticker, df in self.stock_data.items():
            if 'date' not in df.columns:
                continue
            all_dates.update(pd.to_datetime(df['date']).tolist())

        common_dates = sorted(all_dates)
        self.common_dates = pd.DatetimeIndex(common_dates)
        self.all_dates = common_dates

        # 計算每日持股總值
        portfolio_values = []
        for ticker, info in self.holdings.items():
            if ticker not in self.stock_data:
                continue
            df = self.stock_data[ticker].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()

            shares = info['shares']
            df['stock_value'] = df['close'] * shares
            df_aligned = df.reindex(self.common_dates, method='ffill')['stock_value']
            portfolio_values.append(df_aligned.rename(ticker))

        value_df = pd.concat(portfolio_values, axis=1).ffill().fillna(0)
        value_df['total'] = value_df.sum(axis=1)
        self.value_series = value_df['total']
        self.initial_value = self.initial_value or self.value_series.iloc[0]

    def _metrics_from_series(
        self,
        series: pd.Series,
        initial: float
    ) -> dict:
        """從價值序列計算績效指標"""
        total_ret = series.iloc[-1] / initial - 1
        n_days = len(series)
        ann_ret = (1 + total_ret) ** (252 / n_days) - 1 if n_days > 0 else 0

        daily_ret = series.pct_change().dropna()
        vol = daily_ret.std(ddof=1) * np.sqrt(252) if len(daily_ret) > 0 else 0
        sharpe = (ann_ret - self.risk_free) / (vol + 1e-10)

        cumulative = (1 + daily_ret).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_dd = drawdown.min()
        calmar = ann_ret / (abs(max_dd) + 1e-10)

        win_rate = (daily_ret > 0).mean()

        return {
            'total_return': total_ret,
            'annual_return': ann_ret,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'calmar': calmar,
            'win_rate': win_rate,
        }

    def run(self, output: bool = True) -> WalkForwardSummary:
        """
        執行 Walk-Forward 回測。
        
        滑動視窗：
            - 訓練期：用前 N 年數據（不參與最終績效計算）
            - 測試期：滾動前進 N 天
        """
        dates = self.common_dates
        if len(dates) < 300:
            raise ValueError("數據不足，請提供至少 300 天的歷史數據")

        # 訓練期天數
        train_days = int(self.train_years * 252)
        min_train_days = int(1.0 * 252)  # 至少訓練 1 年

        results = []
        window_idx = 0

        i = train_days
        while i + self.test_days <= len(dates):
            train_end_idx = i
            test_start_idx = i
            test_end_idx = i + self.test_days

            train_dates = dates[max(0, train_end_idx - train_days):train_end_idx]
            test_dates = dates[test_start_idx:test_end_idx]

            if len(train_dates) < min_train_days:
                i += self.step_days
                continue

            train_series = self.value_series.loc[train_dates]
            test_series = self.value_series.loc[test_dates]

            train_metrics = self._metrics_from_series(train_series, train_series.iloc[0])
            test_metrics = self._metrics_from_series(test_series, train_series.iloc[0])

            res = WalkForwardResult(
                train_start=str(train_dates[0].date()),
                train_end=str(train_dates[-1].date()),
                test_start=str(test_dates[0].date()),
                test_end=str(test_dates[-1].date()),
                total_return=test_metrics['total_return'],
                annual_return=test_metrics['annual_return'],
                sharpe=test_metrics['sharpe'],
                max_drawdown=test_metrics['max_drawdown'],
                calmar=test_metrics['calmar'],
                win_rate=test_metrics['win_rate'],
                num_trades=0,  # 純持股，不主動交易
                n_test_days=len(test_dates),
            )
            results.append(res)
            window_idx += 1

            if output:
                print(
                    f"  [{window_idx:2d}] "
                    f"Train: {res.train_start} ~ {res.train_end} | "
                    f"Test:  {res.test_start} ~ {res.test_end} | "
                    f"Return: {res.total_return*100:+6.1f}% | "
                    f"Sharpe: {res.sharpe:+.2f} | "
                    f"MDD: {res.max_drawdown*100:6.1f}%"
                )

            i += self.step_days

        self.results = results

        if output:
            print()

        return self._summarize(results)

    def _summarize(self, results: List[WalkForwardResult]) -> WalkForwardSummary:
        """計算匯總統計"""
        if not results:
            raise ValueError("沒有結果，請先呼叫 run()")

        returns = np.array([r.total_return for r in results])
        sharpes = np.array([r.sharpe for r in results])
        mdds = np.array([r.max_drawdown for r in results])

        # t-test：相對於零報酬
        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(returns, 0)

        std_ret = float(np.std([r.total_return for r in results]))

        return WalkForwardSummary(
            n_windows=len(results),
            mean_return=float(returns.mean()),
            std_return=std_ret,
            mean_sharpe=float(sharpes.mean()),
            mean_mdd=float(mdds.mean()),
            win_rate_overall=float((returns > 0).mean()),
            p_value=float(p_value),
            results=results,
        )

    def monte_carlo(
        self,
        n_simulations: int = 1000,
        initial_value: float = None,
        confidence: float = 0.95,
    ) -> dict:
        """
        Monte Carlo 模擬：對歷史日報酬隨機重採樣，評估不確定性。
        
        概念：
            將歷史日報酬視為獨立同分佈（i.i.d.），隨機抽樣重組，
            產生大量可能的未來路徑，計算報酬分佈。
        """
        if not self.results:
            raise ValueError("請先執行 run()")

        init = initial_value or self.initial_value

        # 收集所有測試期的日報酬
        all_daily_returns = []
        for ticker, info in self.holdings.items():
            if ticker not in self.stock_data:
                continue
            df = self.stock_data[ticker].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            shares = info['shares']
            val = df['close'] * shares
            ret = val.pct_change().dropna()
            all_daily_returns.extend(ret.tolist())

        daily_returns = np.array(all_daily_returns)
        # 去除極端值（5% 截尾）
        lower = np.percentile(daily_returns, 2.5)
        upper = np.percentile(daily_returns, 97.5)
        mask = (daily_returns >= lower) & (daily_returns <= upper)
        daily_returns = daily_returns[mask]

        # 模擬
        n_days = self.test_days
        final_values = []

        rng = np.random.default_rng(42)
        for _ in range(n_simulations):
            path_returns = rng.choice(daily_returns, size=n_days, replace=True)
            path = (1 + path_returns).cumprod() * init
            final_values.append(path[-1])

        final_values = np.array(final_values)

        # 計算分位數
        alpha = 1 - confidence
        lower_q = alpha / 2
        upper_q = 1 - alpha / 2

        return {
            'n_simulations': n_simulations,
            'n_test_days': n_days,
            'mean_final': float(final_values.mean()),
            'median_final': float(np.median(final_values)),
            'std_final': float(final_values.std()),
            'percentile_2_5': float(np.percentile(final_values, lower_q * 100)),
            'percentile_97_5': float(np.percentile(final_values, upper_q * 100)),
            'prob_loss': float((final_values < init).mean()),
            'var_95': float(np.percentile(final_values, 5)),
            'cvar_95': float(final_values[final_values <= np.percentile(final_values, 5)].mean()),
            'all_final_values': final_values,
        }

    def print_summary(self, summary: WalkForwardSummary):
        """輸出 Walker-Forward 結果報告"""
        print("=" * 65)
        print("  Walk-Forward Analysis 結果")
        print("=" * 65)
        print(f"  視窗數量      : {summary.n_windows}")
        print(f"  訓練期/測試期 : {self.train_years:.0f} 年 / {self.test_days} 天")
        print()
        print(f"  {'指標':<20} {'平均值':>12} {'標準差':>12} {'說明'}")
        print("  " + "-" * 60)
        print(f"  {'總報酬率':<20} {summary.mean_return*100:>+11.2f}% {self._fmt_std(summary.results, 'total_return'):>12s}  各測試期平均")
        print(f"  {'年化報酬':<20} {summary.mean_return*100:>+11.2f}%  (同總報酬)")
        print(f"  {'Sharpe Ratio':<20} {summary.mean_sharpe:>+12.3f}  (年化)")
        print(f"  {'最大回測':<20} {summary.mean_mdd*100:>+11.2f}%  平均")
        print(f"  {'勝率（正報酬）':<18} {summary.win_rate_overall*100:>+11.1f}%  {summary.win_rate_overall:.0%} 的測試期為正報酬")
        print()
        print(f"  統計顯著性    : p = {summary.p_value:.4f}  "
              f"{'(顯著)' if summary.p_value < 0.05 else '(不顯著，請謹慎解讀)'}")
        print()
        print("  分布概覽（各測試期總報酬）：")
        rets = np.array([r.total_return for r in summary.results])
        print(f"    {'最小':>8}: {rets.min()*100:+.1f}%")
        print(f"    {'25%':>8}: {np.percentile(rets, 25)*100:+.1f}%")
        print(f"    {'中位數':>8}: {np.median(rets)*100:+.1f}%")
        print(f"    {'75%':>8}: {np.percentile(rets, 75)*100:+.1f}%")
        print(f"    {'最大':>8}: {rets.max()*100:+.1f}%")
        print("=" * 65)

    def _fmt_std(self, results: list, attr: str) -> str:
        vals = getattr(results[0], attr)
        if vals is None:
            return "N/A"
        return f"{np.std([getattr(r, attr) for r in results])*100:+.1f}%"
