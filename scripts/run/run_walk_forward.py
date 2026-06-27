#!/usr/bin/env python3
# ============================================================================
# Run Walk-Forward Analysis - 執行 Walk-Forward + Monte Carlo 回測
# ============================================================================
"""
執行 walk-forward 回測，評估投資組合的穩健性。

用法:
    python run_walk_forward.py --start 2015-01-01 --end 2026-04-28 --cash 1621741
    python run_walk_forward.py --windows 2 --test-days 60 --step 20 --mc 1000

Walk-Forward 分析的價值：
    - 傳統回測用單一區間，參數 overfit 風險高
    - Walk-Forward：用多個滾動窗口，每個窗口的「測試期」都是未見過的數據
    - Monte Carlo：對歷史日報酬隨機重採樣，評估不確定性範圍
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import PORTFOLIO_HOLDINGS, RISK_FREE_RATE
from portfolio_data_loader import download_all_stocks
from walk_forward import WalkForwardBacktester


def main():
    parser = argparse.ArgumentParser(description='Walk-Forward 投資組合分析')
    parser.add_argument('--start', type=str, default='2000-01-01',
                        help='資料開始日期')
    parser.add_argument('--end', type=str, default='2010-12-31',
                        help='資料結束日期（測試期終點）')
    parser.add_argument('--train-years', type=float, default=2.0,
                        help='訓練期長度（年），預設 2 年')
    parser.add_argument('--test-days', type=int, default=60,
                        help='測試期長度（天），預設 60 天')
    parser.add_argument('--step-days', type=int, default=20,
                        help='滑動步幅（天），預設 20 天')
    parser.add_argument('--mc', type=int, default=1000,
                        help='Monte Carlo 模擬次數，預設 1000')
    parser.add_argument('--output', action='store_true',
                        help='儲存結果到 results/ 目錄')
    args = parser.parse_args()

    tickers = list(PORTFOLIO_HOLDINGS.keys())
    print("=" * 65)
    print("  Walk-Forward 分析")
    print("=" * 65)
    print(f"  持股: {tickers}")
    print(f"  資料區間: {args.start} ~ {args.end}")
    print(f"  訓練期: {args.train_years:.0f} 年 | 測試期: {args.test_days} 天 | 滑動: {args.step_days} 天")
    print(f"  Monte Carlo: {args.mc} 次")
    print("=" * 65)

    # ── 1. 下載數據 ──────────────────────────────────────────────────
    print("\n[1/3] 下載歷史數據 ...")
    stock_data = download_all_stocks(
        tickers,
        args.start,
        args.end,
        cache_dir=str(PROJECT_ROOT / "data" / "portfolio_cache")
    )

    # ── 2. Walk-Forward ──────────────────────────────────────────────
    print("\n[2/3] 執行 Walk-Forward 回測 ...")
    wf = WalkForwardBacktester(
        stock_data=stock_data,
        holdings=PORTFOLIO_HOLDINGS,
        train_window_years=args.train_years,
        test_window_days=args.test_days,
        step_days=args.step_days,
        risk_free_rate=RISK_FREE_RATE,
    )

    summary = wf.run(output=True)

    print()
    wf.print_summary(summary)

    # ── 3. Monte Carlo ────────────────────────────────────────────────
    print("\n[3/3] Monte Carlo 模擬 ...")
    mc = wf.monte_carlo(n_simulations=args.mc, confidence=0.95)

    print(f"\n{'=' * 50}")
    print(f"  Monte Carlo 結果 ({args.mc:,} 次模擬, {mc['n_test_days']} 天)")
    print(f"{'=' * 50}")
    print(f"  初始值: {mc['mean_final'] / wf.initial_value * 100:+.1f}% (平均) → "
          f"{mc['median_final'] / wf.initial_value * 100:+.1f}% (中位數)")
    print(f"  最終值區間 (2.5%~97.5%): "
          f"{mc['percentile_2_5']:,.0f} ~ {mc['percentile_97_5']:,.0f}")
    print(f"  標準差: {mc['std_final']:,.0f}")
    print(f"  虧損機率: {mc['prob_loss']*100:.1f}%")
    print(f"  VaR 95%: {mc['var_95']:,.0f}")
    print(f"  CVaR 95%: {mc['cvar_95']:,.0f}")
    print(f"{'=' * 50}")

    # ── 儲存 ──────────────────────────────────────────────────────────
    if args.output:
        out_dir = PROJECT_ROOT / "results" / "walk_forward"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 儲存各 window 結果
        import pandas as pd
        rows = []
        for r in summary.results:
            rows.append({
                'train_start': r.train_start,
                'train_end': r.train_end,
                'test_start': r.test_start,
                'test_end': r.test_end,
                'total_return': f"{r.total_return*100:.2f}%",
                'annual_return': f"{r.annual_return*100:.2f}%",
                'sharpe': f"{r.sharpe:.3f}",
                'max_drawdown': f"{r.max_drawdown*100:.2f}%",
                'calmar': f"{r.calmar:.3f}",
                'win_rate': f"{r.win_rate*100:.1f}%",
                'n_test_days': r.n_test_days,
            })
        df = pd.DataFrame(rows)
        csv_path = out_dir / "walk_forward_results.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n結果已儲存: {csv_path}")

    print("\n✅ Walk-Forward 分析完成！")


if __name__ == "__main__":
    main()
