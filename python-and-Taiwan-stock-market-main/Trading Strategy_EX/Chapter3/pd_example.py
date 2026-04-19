import pandas as pd
import yfinance as yf

def calculate_technical_indicators(df: pd.DataFrame, period: int = 6) -> pd.DataFrame:
    """計算技術指標
    
    Args:
        df: 包含 High, Low 等欄位的股價 DataFrame
        period: 滾動窗口期（預設6）
    
    Returns:
        附加技術指標的 DataFrame
    """
    #rolling以6為單位位移並取最大值
    df['Highest_high'] = df['High'].rolling(period).max()
    #rolling以6為單位位移並取最小值
    df['Lowest_Low'] = df['Low'].rolling(period).min()
    #計算最高與最低的差異
    df['OCHIGH'] = df['High'].rolling(period).apply(lambda x: x[0] - x[-1])
    return df


#yfinance產出台積電股價資料
stock = yf.Ticker('2330.TW')
#獲取20170101-20210202
df = stock.history(start="2017-01-01", end="2021-02-02")

#使用統一的函數計算技術指標
df = calculate_technical_indicators(df)

#存成Excel來看一下結果
df.to_excel(r'D:\Trading Strategy_EX\Chapter3\final.xlsx')
print(df)
