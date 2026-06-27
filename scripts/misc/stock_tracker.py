#!/usr/bin/env python3
"""股票價格追蹤提醒"""
import yfinance as yf
import pandas as pd
import sys
sys.path.insert(0, '/Users/isaacliu33252/Stock_TaiwanII')

from portfolio_config import ALL_TICKERS, _TICKER_MAP

# 讀取建議檔案
df = pd.read_excel('/Users/isaacliu33252/Stock_TaiwanII/stock_recommendations_20260501.xlsx')

tickers_map = {
    '0050': '0050.TW', '0056': '0056.TW', '00646': '00646.TW',
    '00679B': '00679B.TWO', '00713': '00713.TW', '00751B': '00751B.TWO',
    '00878': '00878.TW', '2884': '2884.TW'
}

alerts = []
for idx, row in df.iterrows():
    code = row['代號']
    name = row['名稱']
    buy_price = row['買進價']
    sell_price = row['賣出價']
    hold_price = row['持有價以下']
    
    ticker = tickers_map.get(code)
    if not ticker:
        continue
        
    try:
        price = yf.Ticker(ticker).history(period='1d')['Close'].iloc[-1]
        
        # 檢查信號
        if price <= buy_price:
            alerts.append(f"🟢【買入提醒】{code} {name} 現價${price:.2f} <= 買進價${buy_price}")
        elif price >= sell_price:
            alerts.append(f"🔴【賣出提醒】{code} {name} 現價${price:.2f} >= 賣出價${sell_price}")
        elif price <= hold_price:
            alerts.append(f"🟡【持有警告】{code} {name} 現價${price:.2f} < 持有價${hold_price}（考慮減碼）")
    except Exception as e:
        print(f"Error checking {code}: {e}")

# 輸出結果
if alerts:
    print("\n".join(alerts))
    print(f"\n提醒時間: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
else:
    print("✅ 所有股票均在合理區間，無需提醒")