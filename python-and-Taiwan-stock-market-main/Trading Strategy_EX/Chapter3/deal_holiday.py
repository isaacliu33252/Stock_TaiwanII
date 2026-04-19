#import必要套件
from pathlib import Path
import pandas as pd
import datetime

#動態取得腳本所在目錄
SCRIPT_DIR = Path(__file__).resolve().parent

def process_holiday_schedule(csv_path: Path = None, output_path: Path = None) -> pd.DataFrame:
    """處理休市日schedule CSV 並輸出 holiday.xlsx
    
    Args:
        csv_path: 輸入的 CSV 檔案路徑（預設使用同目錄的 holidaySchedule.csv）
        output_path: 輸出的 Excel 檔案路徑（預設使用同目錄的 holiday.xlsx）
    
    Returns:
        處理後的日期 Series
    """
    if csv_path is None:
        csv_path = SCRIPT_DIR / 'holidaySchedule.csv'
    if output_path is None:
        output_path = SCRIPT_DIR / 'holiday.xlsx'
    
    #讀取下載的csv檔案，skiprows可以讓你跳過第一列
    x = pd.read_csv(csv_path, encoding='big5', skiprows=[0])
    
    #today獲取今天的日期
    today = datetime.date.today()
    #透過strftime只留下年
    convert_today = today.strftime('%Y')
    
    #針對日期apply，將2021加上年與原先的日期
    x['日期'] = x['日期'].apply(lambda d: convert_today + '年' + d)
    #一樣對日期做apply，並且replace年月為/，日為空白
    x['日期'] = x['日期'].str.replace('年', '/').str.replace('月', '/').str.replace('日', '')
    
    print(x['日期'])
    
    #儲存成名為holiday.xlsx的檔案
    x['日期'].to_excel(output_path, columns=['日期'])
    return x['日期']


if __name__ == '__main__':
    process_holiday_schedule()