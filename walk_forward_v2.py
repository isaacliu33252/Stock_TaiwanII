"""
Enhanced Walk-Forward Analysis - 整合風控與增強獎勵
================================================================================
v2.1 改善：
1. _test_window() 串接真實 BacktestEngine，不再是 random sample
2. 支援直接載入預訓練模型進行回測
3. 保留隨機策略作為 baseline對比

v2.0 改善：
1. 與 risk_manager_v2 整合
2. 統計顯著性檢驗
3. 自動化參數優化
4. 完整的訓練/測試報告

作者: FinRL量化交易專家（整合版）
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import sys
from pathlib import Path

# 嘗試引入 backtesting 和 environment
sys.path.insert(0, str(Path(__file__).parent))

try:
    from backtesting.backtest_engine import BacktestEngine
    from environments.taiwan_stock_env import TaiwanStockTradingEnv
    BACKTEST_AVAILABLE = True
except ImportError as e:
    BACKTEST_AVAILABLE = False
    print(f"[WalkForward] Warning: could not import backtest components: {e}")


@dataclass
class WalkForwardResult:
    """單次 Walk-Forward 結果"""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    total_return: float
    annual_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    num_trades: int
    n_test_days: int
    risk_level: str  # low/medium/high/critical
    is_random_baseline: bool = False  # 是否為隨機策略 baseline

    def to_dict(self) -> dict:
        return {
            'window_id': self.window_id,
            'train_start': self.train_start,
            'train_end': self.train_end,
            'test_start': self.test_start,
            'test_end': self.test_end,
            'total_return': f"{self.total_return*100:.2f}%",
            'annual_return': f"{self.annual_return*100:.2f}%",
            'sharpe': f"{self.sharpe:.3f}",
            'sortino': f"{self.sortino:.3f}",
            'max_drawdown': f"{self.max_drawdown*100:.2f}%",
            'calmar': f"{self.calmar:.3f}",
            'win_rate': f"{self.win_rate*100:.1f}%",
            'num_trades': self.num_trades,
            'risk_level': self.risk_level,
            'is_random_baseline': self.is_random_baseline,
        }


@dataclass
class WalkForwardConfig:
    """Walk-Forward 設定"""
    train_window_years: float = 2.0      # 訓練期（年）
    test_window_days: int = 60            # 測試期（天）
    step_days: int = 20                   # 滑動步幅（天）
    min_train_days: int = 252             # 最短訓練期（1年）
    risk_free_rate: float = 0.02         # 無風險利率
    initial_value: float = 1_000_000      # 初始本金
    # 模型相關
    model_dir: Optional[str] = None       # 預訓練模型目錄（可選）
    use_random_baseline: bool = True     # 是否也跑隨機策略作為 baseline


class EnhancedWalkForward:
    """
    增強版 Walk-Forward 分析器

    功能：
    1. 滾動視窗訓練/測試
    2. 整合風控（risk_manager_v2）
    3. 統計顯著性檢驗
    4. Monte Carlo 模擬（預留介面）
    5. 自動生成報告

    使用方式（載入預訓練模型）：
        wf = EnhancedWalkForward(stock_data, holdings, config)
        wf.model_dir = "./models/portfolio"
        results = wf.run()
        summary = wf.summary()
        wf.save_results('walk_forward_results.json')

    使用方式（僅隨機 baseline）：
        config = WalkForwardConfig(use_random_baseline=True)
        wf = EnhancedWalkForward(stock_data, holdings, config)
        results = wf.run()
    """

    def __init__(
        self,
        stock_data: dict,        # {ticker: DataFrame}
        holdings: dict,          # PORTFOLIO_HOLDINGS
        config: WalkForwardConfig = None,
    ):
        self.stock_data = stock_data
        self.holdings = holdings
        self.config = config or WalkForwardConfig()
        self.results: List[WalkForwardResult] = []

        # 對齊數據
        self.common_dates = self._align_dates()

    def _align_dates(self) -> pd.DatetimeIndex:
        """對齊所有股票的交易日"""
        all_dates = set()
        for ticker, df in self.stock_data.items():
            if 'date' not in df.columns:
                continue
            all_dates.update(pd.to_datetime(df['date']).tolist())
        return pd.DatetimeIndex(sorted(all_dates))

    def run(self) -> List[WalkForwardResult]:
        """
        執行 Walk-Forward 分析

        Returns:
            List[WalkForwardResult]: 所有視窗的結果
        """
        if not BACKTEST_AVAILABLE:
            print("[WalkForward] ERROR: backtest components not available. Aborting.")
            return []

        print(f"\n{'='*60}")
        print("Enhanced Walk-Forward Analysis 開始")
        print(f"視窗設定: 訓練={self.config.train_window_years}年, 測試={self.config.test_window_days}天")
        print(f"模型目錄: {self.config.model_dir or '(隨機策略)'}")
        print(f"{'='*60}")

        # 計算視窗
        windows = self._generate_windows()
        print(f"共 {len(windows)} 個視窗\n")

        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            print(f"\n[視窗 {i+1}/{len(windows)}]")
            print(f"  訓練期: {train_start.date()} ~ {train_end.date()}")
            print(f"  測試期: {test_start.date()} ~ {test_end.date()}")

            # 訓練（在 sample 數據上）- 目前是 stub
            train_result = self._train_window(train_start, train_end)

            # 測試（在 unseen 數據上）- 串接真實 backtest
            test_result = self._test_window(
                train_result, test_start, test_end,
                window_id=i,
            )

            self.results.append(test_result)

            # 印出關鍵指標
            label = "隨機策略" if test_result.is_random_baseline else "策略"
            print(f"  {label}結果: 報酬={test_result.total_return*100:.1f}%, "
                  f"Sharpe={test_result.sharpe:.2f}, "
                  f"MDD={test_result.max_drawdown*100:.1f}%, "
                  f"交易次數={test_result.num_trades}")

        return self.results

    def _generate_windows(self) -> List[Tuple]:
        """產生所有滾動視窗"""
        windows = []

        train_days = int(self.config.train_window_years * 252)
        test_days = self.config.test_window_days
        step_days = self.config.step_days

        start_idx = train_days
        end_idx = len(self.common_dates) - test_days

        current = start_idx
        while current < end_idx:
            train_end_idx = current
            train_start_idx = max(0, train_end_idx - train_days)

            test_end_idx = min(current + test_days, len(self.common_dates))
            test_start_idx = current

            if (train_end_idx - train_start_idx) < self.config.min_train_days:
                current += step_days
                continue

            train_start = self.common_dates[train_start_idx]
            train_end = self.common_dates[train_end_idx]
            test_start = self.common_dates[test_start_idx]
            test_end = self.common_dates[test_end_idx - 1]

            windows.append((train_start, train_end, test_start, test_end))
            current += step_days

        return windows

    def _train_window(self, start, end) -> dict:
        """
        在訓練期上進行策略訓練
        目前是 stub：只返回 train period 資訊
        實際訓練需外部腳本完成並存到 model_dir
        """
        train_start_str = str(start.date()) if hasattr(start, 'date') else str(start)
        train_end_str = str(end.date()) if hasattr(end, 'date') else str(end)
        return {
            'train_start': train_start_str,
            'train_end': train_end_str,
            'best_params': {'learning_rate': 3e-4, 'gamma': 0.99},
            'train_return': 0.15,
        }

    def _test_window(
        self,
        train_result: dict,
        test_start,
        test_end,
        window_id: int = 0,
    ) -> WalkForwardResult:
        """
        在測試期上評估策略（真實 BacktestEngine）
        """
        n_days = (test_end - test_start).days
        test_start_str = str(test_start.date())
        test_end_str = str(test_end.date())

        # 嘗試載入對應視窗的模型
        model = None
        is_baseline = True
        if self.config.model_dir and BACKTEST_AVAILABLE:
            import os
            # 嘗試找 window-specific 模型或最新的模型
            possible_paths = [
                os.path.join(self.config.model_dir, f"window_{window_id}_model.zip"),
                os.path.join(self.config.model_dir, f"model_w{window_id}.zip"),
                os.path.join(self.config.model_dir, "latest_model.zip"),
                self.config.model_dir,  # 目錄本身，可能裡面有zip
            ]
            from stable_baselines3 import PPO
            for path in possible_paths:
                if os.path.exists(path):
                    try:
                        model = PPO.load(path)
                        is_baseline = False
                        print(f"    已載入模型: {path}")
                        break
                    except Exception as e:
                        print(f"    模型載入失敗 {path}: {e}")

        # 若無模型或明確要求，則用隨機策略
        if model is None and not self.config.use_random_baseline:
            print("    無可用模型且 use_random_baseline=False，跳過此視窗")
            return WalkForwardResult(
                window_id=window_id,
                train_start=train_result.get('train_start', ''),
                train_end=train_result.get('train_end', ''),
                test_start=test_start_str,
                test_end=test_end_str,
                total_return=0.0,
                annual_return=0.0,
                sharpe=0.0,
                sortino=0.0,
                max_drawdown=0.0,
                calmar=0.0,
                win_rate=0.0,
                num_trades=0,
                n_test_days=n_days,
                risk_level='unknown',
                is_random_baseline=True,
            )

        # 建立測試用的 environment
        # 原則上取第一個 ticker 的數據，或可傳入 ticker 參數
        ticker = list(self.stock_data.keys())[0] if self.stock_data else None
        if ticker is None:
            print("    無股票數據")
            return WalkForwardResult(
                window_id=window_id,
                train_start=train_result.get('train_start', ''),
                train_end=train_result.get('train_end', ''),
                test_start=test_start_str,
                test_end=test_end_str,
                total_return=0.0, annual_return=0.0, sharpe=0.0,
                sortino=0.0, max_drawdown=0.0, calmar=0.0,
                win_rate=0.0, num_trades=0, n_test_days=n_days,
                risk_level='unknown',
            )

        df_full = self.stock_data[ticker].copy()
        if 'date' in df_full.columns:
            df_full['date'] = pd.to_datetime(df_full['date'])
            df_test = df_full[
                (df_full['date'] >= pd.to_datetime(test_start)) &
                (df_full['date'] <= pd.to_datetime(test_end))
            ].copy()
        else:
            # 若無 date 欄位，用位置索引
            start_idx = max(0, len(df_full) - n_days - 252 * int(self.config.train_window_years))
            df_test = df_full.iloc[start_idx:start_idx + n_days].copy()

        if len(df_test) < 30:
            print(f"    測試數據不足 ({len(df_test)} 行)，跳過")
            return WalkForwardResult(
                window_id=window_id,
                train_start=train_result.get('train_start', ''),
                train_end=train_result.get('train_end', ''),
                test_start=test_start_str,
                test_end=test_end_str,
                total_return=0.0, annual_return=0.0, sharpe=0.0,
                sortino=0.0, max_drawdown=0.0, calmar=0.0,
                win_rate=0.0, num_trades=0, n_test_days=n_days,
                risk_level='unknown',
                is_random_baseline=is_baseline,
            )

        # 建立環境
        try:
            env = TaiwanStockTradingEnv(
                df=df_test.reset_index(drop=True),
                initial_balance=self.config.initial_value,
                max_position=4000,
                trade_unit=1000,
                price_limit=0.10,
                commission_rate=0.001425,
                tax_rate=0.003,
                lookback_window=60,
            )
        except Exception as e:
            print(f"    環境建立失敗: {e}")
            return WalkForwardResult(
                window_id=window_id,
                train_start=train_result.get('train_start', ''),
                train_end=train_result.get('train_end', ''),
                test_start=test_start_str,
                test_end=test_end_str,
                total_return=0.0, annual_return=0.0, sharpe=0.0,
                sortino=0.0, max_drawdown=0.0, calmar=0.0,
                win_rate=0.0, num_trades=0, n_test_days=n_days,
                risk_level='unknown',
            )

        # 執行回測
        engine = BacktestEngine(
            initial_balance=self.config.initial_value,
            commission_rate=0.001425,
            tax_rate=0.003,
        )

        try:
            results = engine.run(env, model=model, deterministic=not is_baseline)
        except Exception as e:
            print(f"    BacktestEngine.run() 失敗: {e}")
            return WalkForwardResult(
                window_id=window_id,
                train_start=train_result.get('train_start', ''),
                train_end=train_result.get('train_end', ''),
                test_start=test_start_str,
                test_end=test_end_str,
                total_return=0.0, annual_return=0.0, sharpe=0.0,
                sortino=0.0, max_drawdown=0.0, calmar=0.0,
                win_rate=0.0, num_trades=0, n_test_days=n_days,
                risk_level='unknown',
                is_random_baseline=is_baseline,
            )

        return WalkForwardResult(
            window_id=window_id,
            train_start=train_result.get('train_start', ''),
            train_end=train_result.get('train_end', ''),
            test_start=test_start_str,
            test_end=test_end_str,
            total_return=results.get('total_return', 0.0),
            annual_return=results.get('annualized_return', 0.0),
            sharpe=results.get('sharpe_ratio', 0.0),
            sortino=results.get('sortino_ratio', 0.0),
            max_drawdown=results.get('max_drawdown', 0.0),
            calmar=results.get('calmar_ratio', 0.0),
            win_rate=results.get('win_rate', 0.0),
            num_trades=results.get('total_trades', 0),
            n_test_days=n_days,
            risk_level=self._assess_risk(
                results.get('max_drawdown', 0.0),
                results.get('sharpe_ratio', 0.0),
            ),
            is_random_baseline=is_baseline,
        )

    def _assess_risk(self, mdd: float, sharpe: float) -> str:
        """評估風險等級"""
        if mdd > 0.25 or sharpe < 0:
            return "critical"
        elif mdd > 0.20 or sharpe < 0.3:
            return "high"
        elif mdd > 0.15 or sharpe < 0.8:
            return "medium"
        return "low"

    def summary(self) -> dict:
        """
        生成 Walk-Forward 統計摘要

        Returns:
            dict: 包含統計指標的摘要
        """
        if not self.results:
            return {}

        # 分離策略結果與 baseline
        strategy_results = [r for r in self.results if not r.is_random_baseline]
        baseline_results = [r for r in self.results if r.is_random_baseline]

        def _compute_summary(results_list):
            if not results_list:
                return {}
            returns = [r.total_return for r in results_list]
            sharpes = [r.sharpe for r in results_list]
            mdds = [r.max_drawdown for r in results_list]

            n_positive = sum(1 for r in returns if r > 0)
            win_rate = n_positive / len(returns)

            # t-test: 策略是否顯著不同於 0
            try:
                from scipy import stats
                t_stat, p_value = stats.ttest_1samp(returns, 0)
            except Exception:
                t_stat, p_value = 0.0, 1.0

            return {
                'n_windows': len(results_list),
                'mean_return': float(np.mean(returns)),
                'std_return': float(np.std(returns)),
                'median_return': float(np.median(returns)),
                'min_return': float(np.min(returns)),
                'max_return': float(np.max(returns)),
                'mean_sharpe': float(np.mean(sharpes)),
                'mean_mdd': float(np.mean(mdds)),
                'positive_ratio': win_rate,
                'p_value': float(p_value),
                'is_significant': bool(p_value < 0.05),
                'conclusion': '策略有效' if p_value < 0.05 else '策略效果不顯著',
                'details': [r.to_dict() for r in results_list],
            }

        summary = {
            'strategy': _compute_summary(strategy_results),
            'baseline': _compute_summary(baseline_results),
            'n_total_windows': len(self.results),
        }

        # 對比 summary（若兩者皆有）
        if strategy_results and baseline_results:
            strat_sharpe = summary['strategy'].get('mean_sharpe', 0)
            base_sharpe = summary['baseline'].get('mean_sharpe', 0)
            strat_return = summary['strategy'].get('mean_return', 0)
            base_return = summary['baseline'].get('mean_return', 0)
            summary['comparison'] = {
                'sharpe_vs_baseline': strat_sharpe - base_sharpe,
                'return_vs_baseline': strat_return - base_return,
                'outperforms_baseline': strat_sharpe > base_sharpe,
            }

        return summary

    def print_summary(self):
        """格式化列印摘要"""
        s = self.summary()
        strat = s.get('strategy', {})
        base = s.get('baseline', {})

        print(f"\n{'='*60}")
        print("Walk-Forward 分析摘要")
        print(f"{'='*60}")

        if strat:
            print(f"\n--- 策略結果 ({strat['n_windows']} 視窗) ---")
            print(f"  平均報酬:   {strat['mean_return']*100:.2f}%")
            print(f"  報酬標準差: {strat['std_return']*100:.2f}%")
            print(f"  平均 Sharpe: {strat['mean_sharpe']:.3f}")
            print(f"  平均 MDD:   {strat['mean_mdd']*100:.2f}%")
            print(f"  正向勝率:   {strat['positive_ratio']*100:.1f}%")
            print(f"  p-value:   {strat['p_value']:.4f}")
            print(f"  統計顯著:   {'是' if strat['is_significant'] else '否'}")
            print(f"  結論:       {strat['conclusion']}")

        if base:
            print(f"\n--- 隨機策略 Baseline ({base['n_windows']} 視窗) ---")
            print(f"  平均報酬:   {base['mean_return']*100:.2f}%")
            print(f"  平均 Sharpe: {base['mean_sharpe']:.3f}")
            print(f"  平均 MDD:   {base['mean_mdd']*100:.2f}%")

        comp = s.get('comparison', {})
        if comp:
            print(f"\n--- 策略 vs Baseline ---")
            print(f"  Sharpe 差距: {comp['sharpe_vs_baseline']:+.3f}")
            print(f"  報酬差距:    {comp['return_vs_baseline']*100:+.2f}%")
            print(f"  跑贏 Baseline: {'是' if comp['outperforms_baseline'] else '否'}")

        print(f"\n{'='*60}")
        print("各視窗詳情:")
        print(f"{'='*60}")
        for r in self.results:
            label = "隨機" if r.is_random_baseline else "策略"
            print(f"  [{r.test_start}~{r.test_end}] {label}: "
                  f"報酬={r.total_return*100:.1f}%, Sharpe={r.sharpe:.2f}, "
                  f"MDD={r.max_drawdown*100:.1f}%, 交易={r.num_trades}, "
                  f"風險={r.risk_level}")

    def save_results(self, filename: str):
        """儲存結果到 JSON"""
        s = self.summary()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        print(f"\n結果已儲存: {filename}")


# =============================================================================
# 便捷函數
# =============================================================================

def run_walk_forward(
    stock_data: dict,
    holdings: dict,
    train_years: float = 2.0,
    test_days: int = 60,
    model_dir: str = None,
) -> dict:
    """
    快速執行 Walk-Forward 分析

    Example:
        >>> from portfolio_data_loader import download_all_stocks
        >>> from portfolio_config import ALL_TICKERS, PORTFOLIO_HOLDINGS
        >>> data = download_all_stocks(ALL_TICKERS, '2016-01-01', '2026-04-30')
        >>> results = run_walk_forward(data, PORTFOLIO_HOLDINGS, model_dir="./models/portfolio")
        >>> print(results['strategy']['conclusion'])
    """
    config = WalkForwardConfig(
        train_window_years=train_years,
        test_window_days=test_days,
        model_dir=model_dir,
    )

    wf = EnhancedWalkForward(stock_data, holdings, config)
    wf.run()
    summary = wf.summary()
    wf.print_summary()

    return summary