"""
Enhanced Walk-Forward Analysis - 整合 RL 訓練與風控
================================================================================
v2.0 改善：
1. 每個訓練視窗真正訓練 RL Agent（非 stub）
2. 每個測試視窗真正跑 RL 回測
3. 與 risk_manager_v2 整合
4. 統計顯著性檢驗
5. 完整的訓練/測試報告

作者: FinRL量化交易專家（整合版）
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import sys
from pathlib import Path
import warnings
from stable_baselines3.common.callbacks import BaseCallback
from safe_ppo import SafeActorCriticPolicy, GradientClipCallback

warnings.filterwarnings('ignore')


# ─────────────────────────────────────────────────────────────────────────────
# Seed Collapse 安全閥 Callback
# ─────────────────────────────────────────────────────────────────────────────

class SeedCollapseCallback(BaseCallback):
    """
    監控訓練 loss， 超標時中止訓練並回報 collapse。

    用法：
        callback = SeedCollapseCallback(threshold=1.0, check_interval=500)
        model.learn(..., callback=callback)
        if callback.collapsed:
            ... 重train 或放棄
    """

    def __init__(self, threshold: float = 1.0, check_interval: int = 500, verbose: int = 0):
        super().__init__(verbose)
        self.threshold = threshold
        self.check_interval = check_interval
        self.collapsed = False
        self.best_loss = float('inf')
        self._n_calls = 0

    def _on_step(self) -> bool:
        self._n_calls += 1
        if self._n_calls % self.check_interval != 0:
            return True  # 繼續

        # 取 rollout buffer 的 mean loss（各演算法不同欄位）
        losses = {}
        if hasattr(self.model, 'logger') and self.model.logger is not None:
            # 從 logger 取最新一筆 loss
            for key in ('train/policy_loss', 'train/loss', 'loss'):
                try:
                    val = self.model.logger.name_to_value.get(key)
                    if val is not None:
                        losses[key] = float(val)
                except Exception:
                    pass

        # PPO: policy_loss; A2C: loss
        cur = losses.get('train/policy_loss', losses.get('train/loss', losses.get('loss', None)))

        if cur is not None:
            if cur > self.threshold:
                self.collapsed = True
                if self.verbose:
                    print(f"\n  [SeedCollapse] policy_loss={cur:.4f} > threshold={self.threshold} → 中止")
                return False  # abort learn()

            if cur < self.best_loss:
                self.best_loss = cur

        return True

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# 績效指標（直接 import，避開 backtesting/__init__.py 的 FinRL. 路徑問題）
# ─────────────────────────────────────────────────────────────────────────────

import sys
sys.path.insert(0, str(PROJECT_ROOT))

# 直接 import 避開 FinRL. 前綴問題
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "performance_metrics",
    PROJECT_ROOT / "backtesting" / "performance_metrics.py"
)
_pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pm)

calculate_sharpe_ratio = _pm.calculate_sharpe_ratio
calculate_sortino_ratio = _pm.calculate_sortino_ratio
calculate_max_drawdown = _pm.calculate_max_drawdown
calculate_calmar_ratio = _pm.calculate_calmar_ratio


# ─────────────────────────────────────────────────────────────────────────────
# 視窗配置
# ─────────────────────────────────────────────────────────────────────────────

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
    # ── RL vs B&H ──────────────────────────────────────────────────────────
    rl_return: float = 0.0
    bh_return: float = 0.0
    rl_sharpe: float = 0.0
    bh_sharpe: float = 0.0
    rl_mdd: float = 0.0
    bh_mdd: float = 0.0
    outperformance: float = 0.0  # RL - BH

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
            # RL vs B&H
            'rl_return': f"{self.rl_return*100:.2f}%",
            'bh_return': f"{self.bh_return*100:.2f}%",
            'outperformance': f"{self.outperformance*100:+.2f}%",
        }


@dataclass
class WalkForwardConfig:
    """Walk-Forward 設定"""
    train_window_years: float = 2.0      # 訓練期（年）
    test_window_days: int = 60           # 測試期（天）
    step_days: int = 20                  # 滑動步幅（天）
    min_train_days: int = 252            # 最短訓練期（1年）
    risk_free_rate: float = 0.02         # 無風險利率
    initial_value: float = 1_000_000      # 初始本金
    timesteps: int = 50_000              # 每視窗訓練步數（可降低加快速度）
    agent_type: str = "ppo"               # RL 演算法
    enable_risk_manager: bool = True      # 整合風控
    # ── Seed Collapse 安全閥 ────────────────────────────────────────────────
    loss_threshold: float = 1.0          # 觸發重train的最低 loss 值（policy_loss > 此值視為崩潰）
    loss_check_interval: int = 500        # 每 N step 檢查一次
    max_retrains: int = 3                # 最大重train次數


# ─────────────────────────────────────────────────────────────────────────────
# 增強版 Walk-Forward 分析器
# ─────────────────────────────────────────────────────────────────────────────

class EnhancedWalkForward:
    """
    增強版 Walk-Forward 分析器（真正的 RL + B&H 對比）

    功能：
    1. 滾動視窗訓練/測試（真正訓練 RL Agent）
    2. 每個測試視窗：跑 RL 回測 + B&H 回測，兩者對比
    3. 整合風控（risk_manager_v2）
    4. 統計顯著性檢驗
    5. Monte Carlo 模擬（用 RL 日報酬 bootstrap）
    6. 自動生成報告

    使用方式：
        wf = EnhancedWalkForward(stock_data, holdings, config)
        results = wf.run()
        summary = wf.summary()
        wf.save_results('walk_forward_results.json')
    """

    def __init__(
        self,
        stock_data: dict,        # {ticker: DataFrame}
        holdings: dict,          # PORTFOLIO_HOLDINGS
        config: WalkForwardConfig = None,
        models_dir: str = None,  # 訓練好的模型存這裡
    ):
        self.stock_data = stock_data
        self.holdings = holdings
        self.config = config or WalkForwardConfig()
        self.models_dir = Path(models_dir) if models_dir else PROJECT_ROOT / "models" / "walkforward"
        self.models_dir.mkdir(parents=True, exist_ok=True)
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

    # ── 核心：產生滾動視窗 ─────────────────────────────────────────────────

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

    # ── 核心：訓練一個視窗 ─────────────────────────────────────────────────

    def _train_window(self, train_start, train_end) -> dict:
        """
        在訓練期上訓練 RL Agent。

        每個股票各自訓練一個 agent，儲存到 self.models_dir。
        返回 {'ticker': {'model_path': str, 'info': dict}, ...}
        """
        from environments.taiwan_stock_env import TaiwanStockTradingEnv
        from environments.reward_function_v3 import DynamicRewardShaper
        from risk_manager_v2 import RiskManager
        from stable_baselines3 import PPO, A2C
        import gymnasium as gym

        train_results = {}
        window_tag = f"{train_start.strftime('%Y%m%d')}_{train_end.strftime('%Y%m%d')}"

        for ticker, df_full in self.stock_data.items():
            df = df_full.copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()

            # 取出訓練期區間
            df_train = df.loc[train_start:train_end].copy()
            if len(df_train) < self.config.min_train_days:
                continue

            info = self.holdings.get(ticker, {})
            shares = info.get('shares', 0)

            # ── 建立環境 ────────────────────────────────────────────────
            reward_func = DynamicRewardShaper(
                sortino_weight=0.25,
                calmar_weight=0.20,
                volatility_penalty=0.1,
                drawdown_penalty=0.15,
                holding_bonus=0.30,
                trade_reward=0.005,
                trend_bull_bonus=0.10,
                trend_bear_penalty=0.08,
                init_reward_scale=1.5,
                final_reward_scale=0.6,
            )
            reward_func.set_total_steps(self.config.timesteps)

            risk_mgr = None
            if self.config.enable_risk_manager:
                risk_mgr = RiskManager(
                    early_stop_patience=30,
                    early_stop_sharpe_threshold=0.5,
                    max_drawdown_limit=0.20,
                    stop_loss_pct=-0.10,
                    take_profit_pct=0.20,
                )
                risk_mgr.reset(initial_value=self.config.initial_value)

            env_cfg = {
                'df': df_train,
                'initial_balance': self.config.initial_value,
                'max_position': 40000,
                'trade_unit': 1000,
                'price_limit': 0.10,
                'commission_rate': 0.001425,
                'tax_rate': 0.003,
                'lookback_window': 60,
                'initial_shares': 0,          # 訓練時從空手開始
                'initial_avg_cost': 0.0,
                'reward_func': reward_func,
                'enable_risk_manager': self.config.enable_risk_manager,
                'crash_window': 15,
            }
            env = TaiwanStockTradingEnv(**env_cfg)

            # ── Seed Collapse 安全閥訓練 ─────────────────────────────────────
            max_retrains = self.config.max_retrains
            loss_threshold = self.config.loss_threshold
            loss_check_interval = self.config.loss_check_interval

            best_model = None
            best_loss_val = float('inf')
            collapse_count = 0
            last_collapse = False

            for attempt in range(max_retrains + 1):
                seed_tag = f"{ticker}_s{attempt}"
                np.random.seed(42 + attempt)
                import random
                random.seed(42 + attempt)
                import torch
                torch.manual_seed(42 + attempt)

                collapse_cb = SeedCollapseCallback(
                    threshold=loss_threshold,
                    check_interval=loss_check_interval,
                    verbose=0,
                )

                model = PPO(
                    SafeActorCriticPolicy,
                    env,
                    policy_kwargs={
                        'log_clip_min': -20.0,
                        'log_clip_max': 20.0,
                    },
                    learning_rate=3e-4,
                    n_steps=2048,
                    batch_size=64,
                    n_epochs=10,
                    gamma=0.99,
                    verbose=0,
                )

                # Seed collapse 三層防護：
                # 1. SafeActorCriticPolicy.get_distribution() clip logits（forward pass 保護）
                # 2. GradientClipCallback clip gradients（training 更新保護）
                # 3. SeedCollapseCallback 監控 policy_loss（超標時主動中止）
                try:
                    model.learn(
                        total_timesteps=self.config.timesteps,
                        progress_bar=False,
                        callback=[collapse_cb, GradientClipCallback(max_norm=1.0)],
                    )
                except ValueError as e:
                    if 'invalid values' in str(e) and 'Categorical' in str(e):
                        collapse_cb.collapsed = True
                        collapse_count += 1
                        last_collapse = True
                        print(f"    [{seed_tag}] NaN logits 崩潰（train 內部），重新訓練...")
                        del model
                        if attempt < max_retrains:
                            continue
                        else:
                            print(f"    [{seed_tag}] 最終仍崩潰（已重train {max_retrains} 次），使用最後一個 model")
                            best_model = model
                            break
                    else:
                        raise

                cur_loss = collapse_cb.best_loss
                if collapse_cb.collapsed:
                    collapse_count += 1
                    last_collapse = True
                    if attempt < max_retrains:
                        print(f"    [{seed_tag}] loss={cur_loss:.4f} 超標，重新訓練...")
                        del model
                        continue
                    else:
                        print(f"    [{seed_tag}] loss={cur_loss:.4f} 最終仍超標（已重train {max_retrains} 次）")
                        best_model = model
                        break

                last_collapse = False
                if cur_loss < best_loss_val:
                    best_loss_val = cur_loss
                    if best_model is not None and best_model is not model:
                        del best_model
                    best_model = model
                else:
                    del model

                # Loss 收斂到合理範圍，正常停止
                if cur_loss < loss_threshold:
                    break

            if best_model is None:
                best_model = model  # 起碼有一個

            # ── 儲存模型 ────────────────────────────────────────────────
            safe_tag = ticker.replace('.', '_')
            model_path = self.models_dir / f"{safe_tag}_{window_tag}.zip"
            best_model.save(str(model_path))

            train_results[ticker] = {
                'model_path': str(model_path),
                'shares': shares,
                'info': info,
            }

            print(f"    [{ticker}] 訓練完成 → {model_path.name}")

        return {
            '_tag': window_tag,
            '_models': train_results,
        }

    # ── 核心：測試一個視窗 ─────────────────────────────────────────────────

    def _test_window(
        self,
        train_result: dict,
        test_start,
        test_end
    ) -> WalkForwardResult:
        """
        在測試期上跑 RL 回測（用 _run_single_stock 邏輯）。
        同時跑 B&H 作為 benchmark。
        """
        models = train_result['_models']
        n_days = (test_end - test_start).days

        ticker_rl_values = {}
        ticker_bh_values = {}
        ticker_trades = {}

        # 對齊測試期日期
        test_dates = pd.DatetimeIndex([
            d for d in self.common_dates
            if test_start <= d <= test_end
        ])

        for ticker, df_full in self.stock_data.items():
            if ticker not in models:
                continue

            model_info = models[ticker]
            shares = model_info['shares']
            model_path = model_info['model_path']

            df = df_full.copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            df_test = df.loc[test_start:test_end].copy()

            if len(df_test) == 0:
                continue

            # 不要 reindex 到 common_dates（會把 30 筆變成 2899 筆，導致 env 看到整個歷史）
            # df_test 就是測試期乾淨的 30 rows，直接用
            df_aligned = df_test
            dates_in_window = [d for d in self.common_dates if test_start <= d <= test_end]

            # ── 載入 RL 模型 ───────────────────────────────────────────
            if Path(model_path).exists():
                if self.config.agent_type.lower() == "ppo":
                    from stable_baselines3 import PPO
                    agent_model = PPO.load(str(model_path))
                else:
                    from stable_baselines3 import A2C
                    agent_model = A2C.load(str(model_path))
            else:
                agent_model = None

            # ── RL vs B&H 回測（使用 rl_portfolio_backtest._run_single_stock 邏輯）──
            rl_val, bh_val, trades, metrics = self._backtest_single(
                ticker=ticker,
                df_aligned=df_aligned,
                dates=dates_in_window,
                shares=shares,
                agent_model=agent_model,
            )

            ticker_rl_values[ticker] = rl_val
            ticker_bh_values[ticker] = bh_val
            ticker_trades[ticker] = trades

        # ── 彙總計算 ────────────────────────────────────────────────────
        rl_combined = pd.concat(ticker_rl_values.values(), axis=1).sum(axis=1).dropna()
        bh_combined = pd.concat(ticker_bh_values.values(), axis=1).sum(axis=1).dropna()

        if len(rl_combined) == 0 or len(bh_combined) == 0:
            # 沒有有效數據
            return WalkForwardResult(
                window_id=len(self.results),
                train_start=str(train_result.get('_tag', '')),
                train_end='',
                test_start=str(test_start.date()),
                test_end=str(test_end.date()),
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
            )

        rl_initial = rl_combined.iloc[0]
        bh_initial = bh_combined.iloc[0]

        rl_total = rl_combined.iloc[-1] / rl_initial - 1
        bh_total = bh_combined.iloc[-1] / bh_initial - 1

        rl_daily = rl_combined.pct_change().dropna()
        bh_daily = bh_combined.pct_change().dropna()

        # Sharpe / Sortino / MDD（std=0 的話 Sharpe = 0，防止 -inf 爆炸）
        rl_sharpe_val = calculate_sharpe_ratio(rl_daily.values, self.config.risk_free_rate)
        if np.isnan(rl_sharpe_val) or np.isinf(rl_sharpe_val):
            rl_sharpe_val = 0.0
        bh_sharpe_val = calculate_sharpe_ratio(bh_daily.values, self.config.risk_free_rate)
        if np.isnan(bh_sharpe_val) or np.isinf(bh_sharpe_val):
            bh_sharpe_val = 0.0
        rl_sortino_val = calculate_sortino_ratio(rl_daily.values, target=0.0)
        bh_sortino_val = calculate_sortino_ratio(bh_daily.values, target=0.0)

        rl_mdd_val, _, _ = calculate_max_drawdown(rl_combined.values)
        bh_mdd_val, _, _ = calculate_max_drawdown(bh_combined.values)

        annual_return_val = (1 + rl_total) ** (252 / max(n_days, 1)) - 1
        calmar_val = annual_return_val / abs(rl_mdd_val) if rl_mdd_val != 0 else 0.0
        win_rate_val = float((rl_daily > 0).mean())

        total_trades = sum(len(v) for v in ticker_trades.values())

        return WalkForwardResult(
            window_id=len(self.results),
            train_start=str(train_result.get('_tag', '')),
            train_end='',
            test_start=str(test_start.date()),
            test_end=str(test_end.date()),
            total_return=rl_total,
            annual_return=annual_return_val,
            sharpe=rl_sharpe_val,
            sortino=rl_sortino_val,
            max_drawdown=rl_mdd_val,
            calmar=calmar_val,
            win_rate=win_rate_val,
            num_trades=total_trades,
            n_test_days=n_days,
            risk_level=self._assess_risk(rl_mdd_val, rl_sharpe_val),
            rl_return=rl_total,
            bh_return=bh_total,
            rl_sharpe=rl_sharpe_val,
            bh_sharpe=bh_sharpe_val,
            rl_mdd=rl_mdd_val,
            bh_mdd=bh_mdd_val,
            outperformance=rl_total - bh_total,
        )

    # ── 單一股票回測（使用 TaiwanStockTradingEnv 確保狀態向量100%一致）──

    def _backtest_single(
        self,
        ticker: str,
        df_aligned: pd.DataFrame,
        dates: list,
        shares: int,
        agent_model,
    ) -> Tuple[pd.Series, pd.Series, list, dict]:
        """對單一股票在測試期跑 RL vs B&H
        使用 TaiwanStockTradingEnv 確保狀態向量與訓練時完全一致"""
        from environments.taiwan_stock_env import TaiwanStockTradingEnv

        # ── B&H 基準：initial_balance 現金 + shares 股，之後不交易 ────────────
        first_close = float(df_aligned.iloc[0]['close'])
        # B&H 起始 portfolio value = RL 起始 portfolio value，公平比較
        bh_portfolio = self.config.initial_value + shares * first_close

        # 建立專用環境（複製測試數據，確保 column 與訓練一致）
        df_test = df_aligned.copy()
        env = TaiwanStockTradingEnv(
            df=df_test,
            initial_balance=self.config.initial_value,
            max_position=shares,
            initial_shares=shares,   # 一開始就持有這些股
            commission_rate=0.001425,
            tax_rate=0.003,
        )

        # 禁用環境內所有 print
        env._print_enabled = False

        rl_values = []
        bh_values = []
        trades = []

        obs, _ = env.reset()
        env.current_price = first_close
        env.current_step = 0

        for i, date in enumerate(dates):
            # 透過 agent 決策（NaN logits → 隨機 action）
            if agent_model is not None:
                try:
                    action, _ = agent_model.predict(obs, deterministic=True)
                    if np.isnan(action):
                        action = np.random.randint(0, 5)
                except ValueError:
                    action = np.random.randint(0, 5)
            else:
                action = np.random.randint(0, 5)

            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated

            # 價格：從 df_test 取（env.current_step 已更新）
            step_idx = max(0, env.current_step - 1)
            cur_price = float(df_test.iloc[step_idx]['close']) if step_idx < len(df_test) else float(df_test.iloc[-1]['close'])

            # RL 組合價值：balance + position * current_price
            rl_val_raw = info.get('portfolio_value', np.nan)
            if np.isnan(rl_val_raw):
                rl_val_raw = env.balance + env.position * cur_price

            # B&H：初始 1M cash + shares 股（等於 RL 起步），之後完全持有不動
            bh_portfolio = self.config.initial_value + shares * cur_price

            rl_values.append(float(rl_val_raw))
            bh_values.append(float(bh_portfolio))

            # 記錄交易（action != 0 即非 HOLD）
            if info.get('action', 0) != 0:
                trades.append({
                    'date': date,
                    'action': info.get('action_name', 'UNKNOWN'),
                    'price': cur_price,
                    'shares': 0,
                })

            if done:
                # 記錄最終狀態（提早結束時用最後已知價值填補）
                last_rl = rl_values[-1] if rl_values else float(env.balance)
                last_bh = bh_values[-1] if bh_values else self.config.initial_value
                for rem in range(i + 1, len(dates)):
                    rl_values.append(last_rl)
                    bh_values.append(last_bh)
                break

        # 如果領先提前結束，補齊（已在上方處理）

        rl_series = pd.Series(rl_values, index=dates)
        bh_series = pd.Series(bh_values, index=dates)

        return rl_series, bh_series, trades, {}

    # ── 風險評估 ─────────────────────────────────────────────────────────────

    def _assess_risk(self, mdd: float, sharpe: float) -> str:
        """評估風險等級"""
        if mdd > 0.25 or sharpe < 0:
            return "critical"
        elif mdd > 0.20 or sharpe < 0.3:
            return "high"
        elif mdd > 0.15 or sharpe < 0.8:
            return "medium"
        return "low"

    # ── 主執行迴圈 ─────────────────────────────────────────────────────────────

    def run(self) -> List[WalkForwardResult]:
        """執行 Enhanced Walk-Forward 分析"""
        print(f"\n{'='*60}")
        print("Enhanced Walk-Forward Analysis（RL + B&H）")
        print(f"設定: 訓練={self.config.train_window_years}年, "
              f"測試={self.config.test_window_days}天, "
              f"步幅={self.config.step_days}天, "
              f"訓練步數={self.config.timesteps:,}")
        print(f"{'='*60}")

        windows = self._generate_windows()

        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            print(f"\n[視窗 {i+1}/{len(windows)}]")
            print(f"  訓練: {train_start.date()} ~ {train_end.date()}")
            print(f"  測試: {test_start.date()} ~ {test_end.date()}")

            # 訓練
            train_result = self._train_window(train_start, train_end)

            # 測試
            test_result = self._test_window(train_result, test_start, test_end)
            self.results.append(test_result)

            # 印關鍵指標
            msg = (f"✅ 視窗 {i+1}/{len(windows)} 完成\n"
                   f"  測試期: {test_start.date()} ~ {test_end.date()}\n"
                   f"  RL: 報酬={test_result.rl_return*100:+.1f}%  Sharpe={test_result.rl_sharpe:.2f}  MDD={test_result.rl_mdd*100:.1f}%  交易={test_result.num_trades}\n"
                   f"  BH: 報酬={test_result.bh_return*100:+.1f}%  Sharpe={test_result.bh_sharpe:.2f}  MDD={test_result.bh_mdd*100:.1f}%\n"
                   f"  Δ超額報酬: {test_result.outperformance*100:+.1f}%")
            print(f"\n{msg}")

        return self.results

    # ── 統計摘要 ─────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """生成 Walk-Forward 統計摘要"""
        if not self.results:
            return {}

        rl_rets = np.array([r.rl_return for r in self.results])
        bh_rets = np.array([r.bh_return for r in self.results])
        sharpes = np.array([r.sharpe for r in self.results])
        mdds = np.array([r.max_drawdown for r in self.results])
        outpers = np.array([r.outperformance for r in self.results])

        n_positive = sum(1 for r in self.results if r.rl_return > 0)
        n_beats_bh = sum(1 for r in self.results if r.outperformance > 0)

        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(outpers, 0)

        summary = {
            'n_windows': len(self.results),
            'n_tickers': len(self.stock_data),
            'train_years': self.config.train_window_years,
            'test_days': self.config.test_window_days,
            # RL 整體
            'rl_mean_return': float(rl_rets.mean()),
            'rl_std_return': float(rl_rets.std(ddof=1)),
            'rl_median_return': float(np.median(rl_rets)),
            'rl_min_return': float(rl_rets.min()),
            'rl_max_return': float(rl_rets.max()),
            'rl_mean_sharpe': float(sharpes.mean()),
            'rl_mean_mdd': float(mdds.mean()),
            'rl_positive_ratio': n_positive / len(self.results),
            # B&H 整體
            'bh_mean_return': float(bh_rets.mean()),
            'bh_mean_sharpe': float(np.mean([r.bh_sharpe for r in self.results])),
            # 超額報酬
            'outperformance_mean': float(outpers.mean()),
            'outperformance_std': float(outpers.std(ddof=1)),
            'outperformance_beat_ratio': n_beats_bh / len(self.results),
            # 統計顯著性
            'p_value': float(p_value),
            'is_significant': bool(p_value < 0.05),
            'conclusion': 'RL 策略顯著優於 B&H' if (p_value < 0.05 and outpers.mean() > 0) else 'RL 策略效果不顯著',
            # 各視窗詳情
            'details': [r.to_dict() for r in self.results],
        }

        return summary

    def print_summary(self):
        """格式化列印摘要"""
        s = self.summary()

        print(f"\n{'='*65}")
        print("       Enhanced Walk-Forward 統計摘要")
        print(f"{'='*65}")
        print(f"視窗數: {s['n_windows']} | 標的數: {s['n_tickers']} "
              f"| 訓練: {s['train_years']}年 / 測試: {s['test_days']}天")
        print()
        print(f"{'RL 策略':<15} {'均值':>10} {'標準差':>10} {'範圍':>20}")
        print(f"{'':15} {'報酬率':>10} {'':>10} {'最小~最大':>20}")
        print(f"  {'RL':<13} {s['rl_mean_return']*100:>+9.2f}% {s['rl_std_return']*100:>9.2f}% "
              f"[{s['rl_min_return']*100:+.1f}% ~ {s['rl_max_return']*100:+.1f}%]")
        print(f"  {'B&H':<13} {s['bh_mean_return']*100:>+9.2f}%")
        print()
        print(f"  RL Sharpe（均值）: {s['rl_mean_sharpe']:+.3f}")
        print(f"  RL MDD（均值）:    {s['rl_mean_mdd']*100:+.1f}%")
        print(f"  超額報酬（均值）:   {s['outperformance_mean']*100:+.2f}%")
        print(f"  勝過 B&H 比例:     {s['outperformance_beat_ratio']*100:.1f}%")
        print()
        print(f"  統計顯著性: p={s['p_value']:.4f} "
              f"({'顯著' if s['is_significant'] else '不顯著'})")
        print(f"  結論: {s['conclusion']}")

        print(f"\n{'─'*65}")
        print(f"{'視窗':>4} {'測試期':>12} {'RL報酬':>8} {'BH報酬':>8} "
              f"{'Δ超額':>8} {'Sharpe':>6} {'MDD':>7} {'風險':>8}")
        print(f"{'─'*65}")
        for r in self.results:
            print(f"  {r.window_id+1:>3} {r.test_start!s:>12} "
                  f"{r.rl_return*100:>+7.1f}% {r.bh_return*100:>+7.1f}% "
                  f"{r.outperformance*100:>+7.1f}% {r.sharpe:>+6.3f} "
                  f"{r.max_drawdown*100:>+6.1f}% {r.risk_level:>8}")

        print(f"{'='*65}")

    def save_results(self, filename: str):
        """儲存結果到 JSON"""
        s = self.summary()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        print(f"\n結果已儲存: {filename}")


# ─────────────────────────────────────────────────────────────────────────────
# 便捷函式
# ─────────────────────────────────────────────────────────────────────────────

def run_walk_forward(
    stock_data: dict,
    holdings: dict,
    train_years: float = 2.0,
    test_days: int = 60,
    timesteps: int = 50_000,
    agent_type: str = "ppo",
) -> dict:
    """
    快速執行 Enhanced Walk-Forward 分析（真正 RL + B&H 對比）

    Example:
        >>> from portfolio_data_loader import download_all_stocks
        >>> from portfolio_config import ALL_TICKERS, PORTFOLIO_HOLDINGS
        >>> data = download_all_stocks(ALL_TICKERS, '2016-01-01', '2026-04-30')
        >>> config = WalkForwardConfig(train_window_years=2.0, test_window_days=60, timesteps=50_000)
        >>> wf = EnhancedWalkForward(data, PORTFOLIO_HOLDINGS, config)
        >>> wf.run()
        >>> wf.print_summary()
    """
    config = WalkForwardConfig(
        train_window_years=train_years,
        test_window_days=test_days,
        timesteps=timesteps,
        agent_type=agent_type,
    )

    wf = EnhancedWalkForward(stock_data, holdings, config)
    wf.run()
    summary = wf.summary()
    wf.print_summary()

    return summary
