import sys
from pathlib import Path

# 動態取得 Chapter3 目錄
SCRIPT_DIR = Path(__file__).resolve().parent
# 將 Trading 目錄加入路徑
TRADING_DIR = SCRIPT_DIR.parent.parent / 'Trading'
sys.path.insert(0, str(TRADING_DIR))

from utility_f import is_open
import pandas as pd
import datetime

# 向後兼容：重新導出 is_open 函數
__all__ = ['is_open']


def _reload_holiday_for_chapter3():
    """為 Chapter3 專用的休市日載入函數（向後兼容）"""
    # 讀取 Chapter3 目錄下的 holiday.xlsx
    holiday_path = SCRIPT_DIR / 'holiday.xlsx'
    if holiday_path.exists():
        hd = pd.read_excel(holiday_path)
        hd_date = pd.to_datetime(hd['日期']).tolist()
        return {d.strftime('%Y%m%d') for d in hd_date}
    return set()


def is_open_chapter3(target_date: datetime.date) -> str:
    """Chapter3 版本的 is_open（使用本地 holiday.xlsx）
    
    此版本用於當 Trading 目錄的 utility_f.py 不存在時。
    建議優先使用 utility_f.is_open()。
    """
    hd_dates = _reload_holiday_for_chapter3()
    day = target_date.weekday()
    if day == 5 or day == 6:
        return 'N'
    str_date = target_date.strftime('%Y%m%d')
    if str_date in hd_dates:
        return 'N'
    return 'Y'


