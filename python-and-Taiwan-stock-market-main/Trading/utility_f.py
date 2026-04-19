import requests
import json
import pandas as pd
import sys
from pathlib import Path
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from AES_Encryption.encrype_process import *
import datetime
from functools import lru_cache
from typing import Optional

# 動態取得腳本所在目錄
SCRIPT_DIR = Path(__file__).resolve().parent

# 休市日快取，全域變數
_holiday_dates: Optional[set] = None


def _load_holiday_dates() -> set:
    """載入休市日資料並快取為 set"""
    global _holiday_dates
    if _holiday_dates is None:
        hd = pd.read_excel(SCRIPT_DIR / 'holiday.xlsx')
        hd_date = pd.to_datetime(hd['日期']).tolist()
        _holiday_dates = {d.strftime('%Y%m%d') for d in hd_date}
    return _holiday_dates


#是否開盤用函數，返回字串Y、N，Y代表有開盤，N反之
'''
target_date = 傳入datetime格式日期，為需要判定是否開盤的日期
'''
def is_open(target_date: datetime.date) -> str:
    """判斷目標日期是否為台股開盤日"""
    # 檢查是否為週末
    day = target_date.weekday()
    if day == 5 or day == 6:
        return 'N'
    
    # 檢查是否為國定假日（使用快取的 set 進行 O(1) 查找）
    str_date = target_date.strftime('%Y%m%d')
    hd_dates = _load_holiday_dates()
    if str_date in hd_dates:
        return 'N'
    
    return 'Y'


def reload_holiday_cache() -> None:
    """重新載入休市日快取（供測試或更新使用）"""
    global _holiday_dates
    _holiday_dates = None

#三大法人買賣超日報，返回一份dataframe
'''
r_date = 字串格式日期，為需要查詢三大法人買賣超日報的目標日期
'''
def twse_data(r_date: str) -> pd.DataFrame:
    """取得三大法人買賣超日報"""
    try:
        url = f'https://www.twse.com.tw/fund/T86?response=json&date={r_date}&selectType=ALLBUT0999&_=1614316365630'
        data = requests.get(url, timeout=10)
        data.raise_for_status()
        data_json = json.loads(data.text)
        
        if 'data' not in data_json:
            return pd.DataFrame()
        
        data_store = pd.DataFrame(data_json['data'], columns=data_json['fields'])
        return data_store
    except requests.RequestException as e:
        print(f"TWSE API 請求失敗: {e}")
        return pd.DataFrame()

#寄信函數
'''
mail_list = 列表，需要寄信的清單
subject = 字串，標題
body = 字串，內容
mode = 字串，支援text跟html兩種寄信模式
file_path = 列表，想要寄出的檔案的位置
file_name = 列表，希望收件者看到的檔名
'''
def send_mail(
    mail_list: list,
    subject: str,
    body: str,
    mode: str,
    file_path: Optional[list],
    file_name: Optional[list]
) -> bool:
    """寄送電子郵件
    
    Returns:
        bool: 寄送是否成功
    """
    #決定金鑰跟config檔位置
    key_path = str(SCRIPT_DIR.parent / 'key') + '/'
    config_path = str(SCRIPT_DIR.parent / 'config') + '/'
    # 如果上层目录没有key/config，尝试当前目录
    if not Path(key_path).exists():
        key_path = str(SCRIPT_DIR / 'key') + '/'
    if not Path(config_path).exists():
        config_path = str(SCRIPT_DIR / 'config') + '/'
    # 確保路徑存在
    Path(key_path).mkdir(parents=True, exist_ok=True)
    Path(config_path).mkdir(parents=True, exist_ok=True)
    #引用加解密的主要程式check_encrype
    try:
        user_id, password = check_encrype('gmail', key_path, config_path)
    except Exception as e:
        print(f"取得帳號密碼失敗: {e}")
        return False
    
    #創建一個MIMEMultipart()類
    msg = MIMEMultipart()
    #對它傳入三個基本信息: 寄件者(From)、收件者(To)、標題(Subject)
    msg['From'] = user_id
    #使用join將list中的元素以逗號黏起來
    msg['To'] = ",".join(mail_list)
    msg['Subject'] = subject
    #呼叫Attach，並傳入content信件內容
    if mode == 'html':
        msg.attach(MIMEText(body, mode))
    else:
        msg.attach(MIMEText(body))
    
    #if else條件判斷使用者傳入的是否為None
    if file_path is not None and file_name is not None:
        if len(file_path) != len(file_name):
            print("檔案路徑與檔名數量不一致")
            return False
        for path, name in zip(file_path, file_name):
            try:
                with open(path, 'rb') as opened:
                    openedfile = opened.read()
                attachedfile = MIMEApplication(openedfile)
                attachedfile.add_header('content-disposition', 'attachment', filename=name)
                msg.attach(attachedfile)
            except IOError as e:
                print(f"讀取附件失敗 {path}: {e}")
                return False
    
    #設定smtp server，以gmail當例子
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(user_id, password)
        text = msg.as_string()
        server.sendmail(user_id, mail_list, text)
        server.quit()
        return True
    except smtplib.SMTPException as e:
        print(f"SMTP 寄信失敗: {e}")
        return False

#取得目表股票新聞函數
'''
stock = 字串，目標股票
target_page = 整數，要抓取的頁數
'''
def get_yahoo_news(stock: str, target_page: int) -> pd.DataFrame:
    """取得 Yahoo 財經新聞"""
    try:
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # 新版 Yahoo 財經新聞 URL
        url = f"https://tw.stock.yahoo.com/quote/{stock}/news"
        data = requests.get(url, headers=headers, timeout=10)
        data.raise_for_status()
        soup = BeautifulSoup(data.text, 'html.parser')

        # 取得所有文章 li.js-stream-content
        articles = soup.find_all('li', {'class': 'js-stream-content'})

        title, url_list, date_store = [], [], []
        for article in articles:
            h3 = article.find('h3')
            title.append(h3.get_text(strip=True) if h3 else '')
            
            # 找主要連結（排除 comment link）
            links = article.find_all('a')
            main_link = ''
            for link in links:
                href = link.get('href', '')
                if href and '/news/' in href and 'bcmt' not in href:
                    main_link = href
                    break
            if not main_link and links:
                main_link = links[0].get('href', '')
            url_list.append(main_link)
            date_store.append('')

        result = pd.DataFrame({
            'title': title,
            'url': url_list,
            'date': date_store
        })
    except requests.RequestException as e:
        print(f"取得新聞失敗 {stock}: {e}")
        result = pd.DataFrame({
            'title': ['Error'],
            'url': ['Error'],
            'date': ['Error']
        })
    return result
