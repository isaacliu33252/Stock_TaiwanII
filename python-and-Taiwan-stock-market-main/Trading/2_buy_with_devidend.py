#import需要的套件
from pathlib import Path
import yfinance as yf
import pandas as pd
import numpy as np
import time
import datetime
import traceback
import utility_f as uf
try:
    #讀取台股列表
    # 動態取得 Trading 目錄
    SCRIPT_DIR = Path(__file__).resolve().parent
    stock_list = pd.read_excel(SCRIPT_DIR / 'stock_list.xlsx')
    #獲取所有的股票代號
    all_stock = stock_list['代號'].values

    #儲存每支股票的殖利率
    dividend_store = []
    stock_store = []
    #計數用
    count = 0
    #迴圈loop每一支股票
    for i in all_stock:
        #我們來計算一下每一筆處理的時間，在開頭記錄一個start時間點
        start = time.time()
        #計數用參數
        count+=1
        #yfinance呼叫該股Ticker類
        stock = yf.Ticker(f'{i}.TW')
        #info中具備殖利率信息，拿來使用，並排除None
        try:
            # 取殖利率：優先用 dividendYield，None 時改用 trailingDividends 計算
            d_y = stock.info.get('dividendYield')
            if d_y is None or d_y == 0:
                try:
                    td = stock.trailingDividends
                    if td:
                        annual_div = sum(td.values()) if isinstance(td, dict) else 0
                        cur_price = stock.info.get('regularMarketPrice') or stock.info.get('currentPrice')
                        if annual_div and cur_price:
                            d_y = annual_div / cur_price
                except Exception:
                    d_y = None
            # 有時候 yfinance 回傳的資料有異常需做排除，如果值不是 0 且大於 0.05（5%）的才儲存
            if d_y is not None and d_y >= 0.05:
                stock_store.append(i)
                dividend_store.append(d_y)
            #記錄每一筆結束時間
            end = time.time()
            #將進度print出來
            print(f'Dealing: {count} | All: {len(all_stock)} | Stock: {i} | DY: {d_y} | Cost Time: {end-start}s')
        except Exception:
            print(f'Error Stock ! Dealing: {count} | All: {len(all_stock)} | Stock: {i}')
    data = pd.DataFrame()
    data['代號'] = stock_store
    data['殖利率'] = dividend_store
    data.to_excel(SCRIPT_DIR / 'dividend_list.xlsx')
except SystemExit:
    print('Its OK')
except Exception:
    today = datetime.date.today()
    #收件名單
    mail_list = ['a*****@gmail.com','0*****@gm.scu.edu.tw']
    #標題我們加上日期，淺顯易懂
    subject = f'{today}  小幫手高配息名單篩選異常'
    #內容就是剛才篩選完成的股票
    body = traceback.format_exc()
    #寄信
    uf.send_mail(mail_list, subject, body,'text', None, None)
    
	
