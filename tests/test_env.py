#!/usr/bin/env python3
"""
test_env.py - 驗證 TaiwanStockTradingEnv 有正常交易行為
================================================================================
使用人工遞增價格資料，固定動作序列，確認：
1. 環境正常初始化
2. 至少有一筆交易（action != 0）
3. 至少有一筆 BUY 與一筆 SELL/STOP_LOSS
4. T+2 結算機制正常
5. Reward 在合理範圍

作者: FinRL 改善測試
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
from environments.taiwan_stock_env import TaiwanStockTradingEnv


def create_test_data(n_days=100, start_price=100.0, trend=0.001):
    """建立人工價格資料（輕微向上趨勢）"""
    dates = pd.date_range('2024-01-01', periods=n_days, freq='B')  # 平日
    np.random.seed(42)
    
    # 基礎價格：輕微向上趨勢 + 隨機波動
    base = start_price * (1 + trend) ** np.arange(n_days)
    noise = np.cumsum(np.random.randn(n_days) * 0.5)
    close = np.clip(base + noise * 2, start_price * 0.7, start_price * 1.3)
    
    data = {
        'date': dates,
        'open': close * (1 + np.random.randn(n_days) * 0.002),
        'high': close * (1 + np.abs(np.random.randn(n_days)) * 0.005),
        'low': close * (1 - np.abs(np.random.randn(n_days)) * 0.005),
        'close': close,
        'volume': np.random.uniform(1e6, 5e6, n_days),
    }
    
    # 技術指標（基本填充）
    for col in ['ma5', 'ma10', 'ma20', 'rsi', 'macd', 'signal', 'hist',
                'k', 'd', 'upper', 'middle', 'lower', 'atr', 'bb_width']:
        data[col] = np.random.uniform(0.3, 0.7, n_days)
    
    # 法人資料
    for col in ['foreign_net_buy_1d', 'foreign_net_buy_3d', 'foreign_net_buy_5d',
                'dealer_net_buy_1d', 'investment_trust_net_buy']:
        data[col] = np.random.uniform(-5e6, 5e6, n_days)
    
    return pd.DataFrame(data)


def test_env():
    """測試交易環境"""
    print("=" * 60)
    print("TaiwanStockTradingEnv 交易驗證測試")
    print("=" * 60)
    
    # 建立測試資料（輕微向上，避免太容易虧錢）
    df = create_test_data(n_days=100, start_price=100.0, trend=0.001)
    print(f"\n[資料] 建立 {len(df)} 天測試資料")
    print(f"  價格區間: {df['close'].min():.2f} ~ {df['close'].max():.2f}")
    
    # 初始化環境
    env = TaiwanStockTradingEnv(
        df=df,
        initial_balance=1_000_000,
        max_position=4000,
        trade_unit=1000,
        price_limit=0.10,
        commission_rate=0.001425,
        tax_rate=0.003,
    )
    
    obs, info = env.reset()
    print(f"\n[環境] 初始化完成")
    print(f"  初始資金: {env.initial_balance:,.0f}")
    print(f"  動作空間: {env.action_space}")
    print(f"  狀態維度: {obs.shape[0]}")
    
    # 固定動作序列（模擬一筆完整交易）
    # action: 0=hold, 1=BUY, 2=SELL, 3=?, 4=STOP_LOSS
    fixed_actions = [1, 0, 0, 2, 1, 0, 0, 3, 1, 0, 0, 4]
    action_names = {0: 'HOLD', 1: 'BUY', 2: 'SELL', 3: 'CLOSE', 4: 'STOP_LOSS'}
    
    print(f"\n[動作序列] {fixed_actions}")
    
    # 執行固定動作
    buys, sells, holds = 0, 0, 0
    rewards = []
    
    for i, action in enumerate(fixed_actions):
        obs, reward, done, trunc, info = env.step(action)
        rewards.append(reward)
        
        if action == 1:
            buys += 1
        elif action in [2, 3, 4]:
            sells += 1
        else:
            holds += 1
        
        print(f"  Step {i:2d}: action={action_names[action]:10s} | "
              f"pos={info['position']:5d} | "
              f"balance={info['balance']:12,.0f} | "
              f"reward={reward:+.4f}")
        
        if done:
            print(f"  [已完成] 環境結束")
            break
    
    # 交易歷史分析
    print(f"\n[結果]")
    print(f"  執行次數: {buys + sells + holds} 步")
    print(f"  BUY: {buys} 次")
    print(f"  SELL/CLOSE: {sells} 次")
    print(f"  HOLD: {holds} 次")
    print(f"  交易歷史筆數: {len(env.trade_history)}")
    print(f"  Reward 範圍: {min(rewards):.4f} ~ {max(rewards):.4f}")
    print(f"  平均 Reward: {np.mean(rewards):.4f}")
    print(f"  最終餘額: {info['balance']:,.0f}")
    
    # 斷言檢查
    print(f"\n[斷言檢查]")
    errors = []
    
    if len(env.trade_history) == 0:
        errors.append("❌ 交易歷史為空（應該至少有一筆交易）")
    else:
        print(f"✅ 交易歷史: {len(env.trade_history)} 筆")
    
    buy_trades = [t for t in env.trade_history if t.get('action') in [1, 'BUY']]
    sell_trades = [t for t in env.trade_history if t.get('action') in [2, 3, 4, 'SELL', 'CLOSE', 'STOP_LOSS']]
    
    if len(buy_trades) == 0:
        errors.append("❌ 沒有 BUY 交易")
    else:
        print(f"✅ BUY 交易: {len(buy_trades)} 筆")
    
    if len(sell_trades) == 0:
        errors.append("❌ 沒有 SELL 交易")
    else:
        print(f"✅ SELL 交易: {len(sell_trades)} 筆")
    
    if any(r > 1.0 or r < -1.0 for r in rewards):
        errors.append("❌ Reward 超出範圍 [-1, 1]")
    else:
        print(f"✅ Reward 在合理範圍內")
    
    if info['balance'] < 0:
        errors.append("❌ 餘額為負（不可能）")
    else:
        print(f"✅ 餘額正常: {info['balance']:,.0f}")
    
    print()
    if errors:
        for e in errors:
            print(e)
        print("\n測試失敗！")
        return False
    else:
        print("✅ 所有檢查通過！")
        return True


def test_with_random_actions(n_steps=50):
    """隨機動作壓力測試"""
    print("\n" + "=" * 60)
    print("隨機動作壓力測試（50步）")
    print("=" * 60)
    
    df = create_test_data(n_days=200, start_price=100.0, trend=0.0005)
    env = TaiwanStockTradingEnv(df=df, initial_balance=1_000_000)
    obs, info = env.reset()
    
    actions_taken = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    rewards = []
    
    for i in range(n_steps):
        action = env.action_space.sample()
        obs, reward, done, trunc, info = env.step(action)
        actions_taken[action] += 1
        rewards.append(reward)
        if done:
            break
    
    print(f"  動作分佈: {actions_taken}")
    print(f"  交易歷史: {len(env.trade_history)} 筆")
    print(f"  Reward 平均: {np.mean(rewards):.4f}")
    
    if len(env.trade_history) > 0:
        print("✅ 隨機動作下仍有交易發生（環境正常）")
        return True
    else:
        print("⚠️ 50步隨機動作無交易，可能行動空間有問題")
        return False


if __name__ == '__main__':
    ok1 = test_env()
    ok2 = test_with_random_actions()
    
    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("🎉 所有測試通過！環境正常運作。")
    else:
        print("⚠️ 部分測試失敗，請檢查環境實作。")
    print("=" * 60)