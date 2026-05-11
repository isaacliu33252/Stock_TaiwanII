# ============================================================================
# 回測主執行腳本 (Run Backtest)
# ============================================================================
"""
執行 FinRL 策略回測的主腳本。

功能：
- 載入預訓練的 RL 模型或建立新 Agent
- 下載歷史股價數據
- 執行回測
- 生成績效報告和圖表

使用方式：
    # 基本用法（使用預設參數）
    python FinRL/run_backtest.py --agent ppo --stock 2330

    # 指定日期範圍
    python FinRL/run_backtest.py --agent ppo --stock 2330 --start 2020-01-01 --end 2024-12-31

    # 指定模型路徑
    python FinRL/run_backtest.py --agent ppo --stock 2330 --model ./results/models/ppo_model.zip

    # 顯示詳細輸出
    python FinRL/run_backtest.py --agent ppo --stock 2330 --verbose

作者: FinRL量化交易專家
"""

import argparse
import sys
import os
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Any

# 添加路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from FinRL.config import TAIWAN_STOCK_CONFIG, RESULTS_DIR, DATA_CONFIG
from FinRL.data.data_loader import TaiwanStockDataLoader
from FinRL.data.technical_indicators import add_technical_indicators
from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
from FinRL.backtesting.backtest import BacktestEngine
from FinRL.results.plotter import TradingPlotter
from FinRL.results.result_tracker import ResultTracker


def parse_args():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description='執行 FinRL 台股策略回測',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python FinRL/run_backtest.py --agent ppo --stock 2330
  python FinRL/run_backtest.py --agent ppo --stock 2330 --start 2020-01-01 --end 2024-12-31
  python FinRL/run_backtest.py --agent a2c --stock 2330 --model ./results/models/a2c.zip --verbose
        """
    )
    
    # Agent 設定
    parser.add_argument(
        '--agent', type=str, default='ppo',
        choices=['ppo', 'a2c'],
        help='Agent 類型 (預設: ppo)'
    )
    
    # 股票設定
    parser.add_argument(
        '--stock', type=str, default='2330',
        help='股票代碼 (預設: 2330)'
    )
    
    # 日期範圍
    parser.add_argument(
        '--start', type=str, default='2000-01-01',
        help='回測開始日期 (預設: 2000-01-01)'
    )
    
    parser.add_argument(
        '--end', type=str, default='2010-12-31',
        help='回測結束日期 (預設: 2010-12-31)'
    )
    
    # 初始資金
    parser.add_argument(
        '--initial_balance', type=float, 
        default=TAIWAN_STOCK_CONFIG['initial_balance'],
        help=f'初始資金 (預設: {TAIWAN_STOCK_CONFIG["initial_balance"]:,})'
    )
    
    # 模型設定
    parser.add_argument(
        '--model', type=str, default=None,
        help='模型檔案路徑 (若為 None，使用新建立的 Agent)'
    )
    
    # 輸出設定
    parser.add_argument(
        '--output_dir', type=str, default=RESULTS_DIR,
        help=f'輸出目錄 (預設: {RESULTS_DIR})'
    )
    parser.add_argument(
        '--output_uuid', type=str, default=None,
        help='UUID suffix for isolated output files'
    )
    
    # 其他設定
    parser.add_argument(
        '--lookback', type=int, default=60,
        help='狀態回看窗口 (預設: 60)'
    )
    
    parser.add_argument(
        '--verbose', action='store_true',
        help='顯示詳細輸出'
    )
    
    return parser.parse_args()


def load_or_create_agent(
    agent_type: str,
    env,
    model_path: Optional[str] = None
):
    """
    載入或建立 Agent
    
    參數：
        agent_type: Agent 類型 ('ppo' 或 'a2c')
        env: 交易環境
        model_path: 模型檔案路徑（可選）
    
    返回：
        Agent 實例
    """
    print(f"\n[Agent] 初始化 {agent_type.upper()} Agent...")
    
    if agent_type.lower() == 'ppo':
        try:
            from FinRL.agents.ppo_agent import PPOAgent
            from stable_baselines3 import PPO
            
            if model_path and os.path.exists(model_path):
                print(f"[Agent] 載入模型: {model_path}")
                agent = PPO.load(model_path)
            else:
                print(f"[Agent] 建立新 PPO Agent")
                agent = PPO(
                    policy='MlpPolicy',
                    env=env,
                    n_steps=2048,
                    batch_size=64,
                    n_epochs=10,
                    gamma=0.99,
                    learning_rate=3e-4,
                    verbose=0
                )
            
            # 包裝為我們的格式
            class AgentWrapper:
                def __init__(self, model):
                    self.model = model
                
                def predict(self, state, deterministic=True):
                    return self.model.predict(state, deterministic=deterministic)
                
                def get_model(self):
                    return self.model
            
            return AgentWrapper(agent)
            
        except Exception as e:
            print(f"[Agent] PPO Agent 建立失敗: {e}")
            return None
    
    elif agent_type.lower() == 'a2c':
        try:
            from FinRL.agents.a2c_agent import A2CAgent
            from stable_baselines3 import A2C
            
            if model_path and os.path.exists(model_path):
                print(f"[Agent] 載入模型: {model_path}")
                agent = A2C.load(model_path)
            else:
                print(f"[Agent] 建立新 A2C Agent")
                agent = A2C(
                    policy='MlpPolicy',
                    env=env,
                    n_steps=2048,
                    gamma=0.99,
                    learning_rate=3e-4,
                    verbose=0
                )
            
            class AgentWrapper:
                def __init__(self, model):
                    self.model = model
                
                def predict(self, state, deterministic=True):
                    return self.model.predict(state, deterministic=deterministic)
                
                def get_model(self):
                    return self.model
            
            return AgentWrapper(agent)
            
        except Exception as e:
            print(f"[Agent] A2C Agent 建立失敗: {e}")
            return None
    
    else:
        print(f"[Agent] 不支援的 Agent 類型: {agent_type}")
        return None


def load_data(
    symbol: str,
    start_date: str,
    end_date: str,
    cache_dir: str = './data/cache'
) -> Optional:
    """
    載入股票數據
    
    參數：
        symbol: 股票代碼
        start_date: 開始日期
        end_date: 結束日期
        cache_dir: 快取目錄
    
    返回：
        處理過的 DataFrame 或 None
    """
    print(f"\n[Data] 載入股票數據 {symbol}...")
    
    # 建立數據載入器
    loader = TaiwanStockDataLoader(cache_dir=cache_dir)
    
    # 往前延伸足夠多天，避免 TA 計算後資料筆數為零
    # MA240 需要 240 個 data points (約 1 年交易日)
    from datetime import datetime, timedelta
    lookback_days = 600
    start_dt = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=lookback_days)
    extended_start = start_dt.strftime('%Y-%m-%d')
    
    # 下載數據（往回延伸）
    df = loader.download_price_data(
        symbol=symbol,
        start=extended_start,
        end=end_date,
        use_cache=True
    )
    
    if df.empty:
        print(f"[Data] 無法載入數據")
        return None
    
    print(f"[Data] 取得 {len(df)} 筆資料（擴展下載: {extended_start} ~ {end_date}）")
    
    # 添加技術指標
    print(f"[Data] 計算技術指標...")
    df = add_technical_indicators(df)
    
    # 取原本指定的日期範圍（避免擴展的資料影響回測）
    orig_start = start_date
    orig_end = end_date
    if 'date' in df.columns:
        df['ds'] = df['date'].astype(str)
        df = df[(df['ds'] >= orig_start) & (df['ds'] <= orig_end)].copy()
        df = df.drop(columns=['ds'])
    
    print(f"[Data] 技術指標計算完成")
    print(f"       欄位數: {len(df.columns)}")
    print(f"       有效筆數: {len(df)}")
    
    return df


def run_backtest(
    agent,
    env,
    df,
    initial_balance: float,
    lookback: int,
    verbose: bool
) -> Dict[str, Any]:
    """
    執行回測
    
    參數：
        agent: RL Agent
        env: 交易環境
        df: 股票數據
        initial_balance: 初始資金
        lookback: 回看窗口
        verbose: 是否詳細輸出
    
    返回：
        回測結果
    """
    print(f"\n[Backtest] 初始化回測引擎...")
    
    # 建立回測引擎
    bt_engine = BacktestEngine(
        env=env,
        agent=agent,
        initial_balance=initial_balance,
        verbose=verbose
    )
    
    # 執行回測
    print(f"[Backtest] 開始回測...")
    result = bt_engine.run(df, deterministic=True)
    
    return result


def generate_reports(
    result: Dict[str, Any],
    stock: str,
    agent_type: str,
    output_dir: str,
    save_plots: bool = True,
    output_uuid: str = None,
):
    """
    產生回測報告和圖表
    
    參數：
        result: 回測結果
        stock: 股票代碼
        agent_type: Agent 類型
        output_dir: 輸出目錄
        save_plots: 是否儲存圖表
    """
    print(f"\n[Report] 產生回測報告...")
    
    # 建立繪圖器
    plotter = TradingPlotter(results_dir=output_dir)
    
    # 取得資料
    equity_curve = result.get('portfolio_values', np.array([]))
    returns = result.get('returns', np.array([]))
    dates = result.get('dates', None)
    metrics = result.get('metrics', {})
    
    # 1. 儲存文字結果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_uuid:
        timestamp = f"{timestamp}_{output_uuid}"
    result_file = os.path.join(output_dir, f'backtest_{stock}_{agent_type}_{timestamp}.json')
    
    import json
    result_serializable = {
        'stock': stock,
        'agent': agent_type,
        'timestamp': timestamp,
        'metrics': {k: float(v) if isinstance(v, (np.floating, np.integer)) else v 
                   for k, v in metrics.items()},
        'total_trades': len(result.get('trade_history', [])),
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result_serializable, f, indent=2, ensure_ascii=False)
    
    print(f"[Report] 結果已儲存: {result_file}")
    
    # 2. 儲存交易記錄
    trades = result.get('trade_history', [])
    if trades:
        trades_file = os.path.join(output_dir, f'trades_{stock}_{agent_type}_{timestamp}.csv')
        import pandas as pd
        df = pd.DataFrame(trades)
        df.to_csv(trades_file, index=False, encoding='utf-8-sig')
        print(f"[Report] 交易記錄已儲存: {trades_file}")
    
    # 3. 繪製圖表
    if save_plots and len(equity_curve) > 0:
        print(f"[Report] 繪製圖表...")
        
        # 權益曲線
        plotter.plot_equity_curve(
            equity_curve, dates,
            save_path=os.path.join(output_dir, f'equity_{stock}_{agent_type}_{timestamp}.png'),
            show=False
        )
        
        # 回撤分析
        plotter.plot_drawdown(
            equity_curve, dates,
            save_path=os.path.join(output_dir, f'drawdown_{stock}_{agent_type}_{timestamp}.png'),
            show=False
        )
        
        # 報酬分佈
        if len(returns) > 10:
            plotter.plot_returns_distribution(
                returns,
                save_path=os.path.join(output_dir, f'returns_{stock}_{agent_type}_{timestamp}.png'),
                show=False
            )
        
        # 績效儀表板
        plotter.plot_metrics_dashboard(
            metrics,
            save_path=os.path.join(output_dir, f'dashboard_{stock}_{agent_type}_{timestamp}.png'),
            show=False
        )
        
        print(f"[Report] 圖表已儲存至: {output_dir}")
    
    # 4. 顯示績效摘要
    print("\n" + "=" * 70)
    print("                     回測結果摘要")
    print("=" * 70)
    
    print(f"\n  股票代碼:     {stock}")
    print(f"  Agent:        {agent_type.upper()}")
    print(f"  總交易次數:   {len(trades)}")
    
    if metrics:
        print(f"\n  總報酬率:     {metrics.get('total_return', 0)*100:.2f} %")
        print(f"  年化報酬率:   {metrics.get('annual_return', 0)*100:.2f} %")
        print(f"  夏普比率:     {metrics.get('sharpe_ratio', 0):.3f}")
        print(f"  最大回撤:     {metrics.get('max_drawdown', 0)*100:.2f} %")
        print(f"  勝率:         {metrics.get('win_rate', 0)*100:.1f} %")
        print(f"  利潤因子:     {metrics.get('profit_factor', 0):.3f}")
    
    print("\n" + "=" * 70)


def main():
    """主程式"""
    # 解析參數
    args = parse_args()
    
    # 顯示歡迎訊息
    print("\n" + "=" * 70)
    print("           FinRL 台股策略回測系統")
    print("=" * 70)
    print(f"  Stock:       {args.stock}")
    print(f"  Agent:       {args.agent.upper()}")
    print(f"  Period:       {args.start} ~ {args.end}")
    print(f"  Initial:      {args.initial_balance:,} TWD")
    print(f"  Output:       {args.output_dir}")
    print("=" * 70)
    
    # 確保輸出目錄存在
    os.makedirs(args.output_dir, exist_ok=True)
    
    # ============================================================
    # 步驟 1: 載入數據
    # ============================================================
    df = load_data(
        symbol=args.stock,
        start_date=args.start,
        end_date=args.end,
        cache_dir=DATA_CONFIG.get('cache_dir', './data/cache')
    )
    
    if df is None:
        print("[Error] 數據載入失敗，程式終止")
        return 1
    
    # ============================================================
    # 步驟 2: 建立環境
    # ============================================================
    print(f"\n[Environment] 建立交易環境...")
    
    env = TaiwanStockTradingEnv(
        df,
        initial_balance=args.initial_balance,
        lookback_window=args.lookback,
        reward_func=None
    )
    
    print(f"[Environment] 環境建立完成")
    print(f"               狀態維度: {env.state_dim}")
    print(f"               動作空間: {env.action_space.n} 類離散動作")
    
    # ============================================================
    # 步驟 3: 建立/載入 Agent
    # ============================================================
    agent = load_or_create_agent(
        agent_type=args.agent,
        env=env,
        model_path=args.model
    )
    
    if agent is None:
        print("[Error] Agent 初始化失敗，程式終止")
        return 1
    
    # ============================================================
    # 步驟 4: 執行回測
    # ============================================================
    result = run_backtest(
        agent=agent,
        env=env,
        df=df,
        initial_balance=args.initial_balance,
        lookback=args.lookback,
        verbose=args.verbose
    )
    
    # ============================================================
    # 步驟 5: 產生報告
    # ============================================================
    generate_reports(
        result=result,
        stock=args.stock,
        agent_type=args.agent,
        output_dir=args.output_dir,
        save_plots=True,
        output_uuid=args.output_uuid,
    )
    
    # ============================================================
    # 步驟 6: 儲存結果到 ResultTracker
    # ============================================================
    tracker = ResultTracker(results_dir=args.output_dir)
    
    config = {
        'agent': args.agent,
        'stock': args.stock,
        'start': args.start,
        'end': args.end,
        'initial_balance': args.initial_balance,
        'lookback': args.lookback,
    }
    
    tracker.save_result(result, config=config, name=f"{args.stock}_{args.agent}")
    
    print("\n" + "=" * 70)
    print("                      回測完成")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())