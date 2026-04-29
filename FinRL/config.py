# ============================================================================
# FinRL 台股交易系統 - 全域設定檔
# ============================================================================
# 本檔案包含所有系統所需的設定參數
# 修改此檔案即可調整系統行為，無需更動其他程式碼

# ============================================================================
# 一、台股交易規則設定 (Taiwan Stock Trading Rules)
# ============================================================================

# 漲跌停限制（百分比）
# 台灣股市一般漲跌停為 10%，但部分情況可能不同
PRICE_LIMIT_PERCENT = 10.0

# 最小交易單位（股數）
# 台股以 1000 股為一個交易單位（"一張"）
MIN_TRADE_UNIT = 1000

# 每日最大交易量限制（比例）
# 防止單日過度交易，這裡設定為庫存的 50% 上限
MAX_DAILY_TRADE_RATIO = 0.5

# T+2 交割制度
# 台灣股票在成交後第 2 個營業日進行交割
# 此參數目前用於記錄，不影響即時交易邏輯
SETTLEMENT_DAYS = 2

# 交易成本設定
# -----------------------------------------------------------------------------
# 交易稅（賣出時收取，%)
# 台灣股票交易稅為 0.3%（ETF 可能較低）
TRANSACTION_TAX_RATE = 0.003

# 券商手續費（買賣皆收，通常有折扣）
# 此為原始費率，實際費率會在經紀商設定中調整
BROKERAGE_FEE_RATE = 0.001425

# 最小手續費（每次交易最低收取金額）
MIN_BROKERAGE_FEE = 20.0

# ============================================================================
# 二、資料路徑設定 (Data Paths)
# ============================================================================

# 根目錄設定
# 所有資料都會以 ROOT_DIR 為基礎進行存取
import os

# 嘗試自動偵測專案根目錄
try:
    # 取得目前檔案所在目錄
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(_current_dir)
except Exception:
    # 若失敗則使用預設路徑
    ROOT_DIR = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main"

# 資料目錄
DATA_DIR = os.path.join(ROOT_DIR, "FinRL", "data")
RESULTS_DIR = os.path.join(ROOT_DIR, "FinRL", "results")
MODELS_DIR = os.path.join(ROOT_DIR, "FinRL", "models")

# 確保目錄存在
for _dir in [DATA_DIR, RESULTS_DIR, MODELS_DIR]:
    os.makedirs(_dir, exist_ok=True)

# 資料檔案名稱
TRAIN_DATA_FILE = "train_data.csv"
TEST_DATA_FILE = "test_data.csv"
HISTORICAL_DATA_FILE = "historical_data.csv"

# ============================================================================
# 三、技術指標參數設定 (Technical Indicators Parameters)
# ============================================================================

# RSI 相關參數
RSI_PERIOD = 14                  # RSI 計算週期
RSI_OVERBOUGHT = 70              # RSI 超買門檻
RSI_OVERSOLD = 30                # RSI 超賣門檻

# MACD 相關參數
MACD_FAST = 12                   # MACD 快速 EMA 週期
MACD_SLOW = 26                   # MACD 慢速 EMA 週期
MACD_SIGNAL = 9                  # MACD Signal 線週期

# Bollinger Bands 相關參數
BB_PERIOD = 20                   # BB 計算週期
BB_STD = 2                       # BB 標準差倍數

# 移動平均線參數
MA_SHORT = 5                     # 短期均線週期
MA_MEDIUM = 20                   # 中期均線週期
MA_LONG = 60                     # 長期均線週期

# ATR (Average True Range) 參數
ATR_PERIOD = 14                  # ATR 計算週期

# KD 指標參數
KD_PERIOD = 9                    # KD 計算週期
KD_SMOOTH_K = 3                  # K 值平滑週期
KD_SMOOTH_D = 3                  # D 值平滑週期

# ============================================================================
# 四、Agent 超參數預設值 (Agent Hyperparameters)
# ============================================================================

# -----------------------------------------------------------------------------
# PPO (Proximal Policy Optimization) 超參數
# -----------------------------------------------------------------------------
PPO_CONFIG = {
    "learning_rate": 3e-4,           # 學習率
    "n_steps": 2048,                 # 每次更新前收集的步數
    "batch_size": 64,                # 批次大小
    "n_epochs": 10,                  # 每次更新的 epoch 數
    "gamma": 0.99,                   # 折扣因子
    "gae_lambda": 0.95,              # GAE lambda 參數
    "clip_range": 0.2,               # PPO clip 範圍
    "clip_range_vf": None,           # Value Function clip 範圍 (None 表示不 clip)
    "ent_coef": 0.0,                 # 熵係數 (探索獎勵)
    "vf_coef": 0.5,                  # Value Function 損失係數
    "max_grad_norm": 0.5,            # 梯度裁剪最大值
    "target_kl": None,               # 目標 KL 散度 (None 表示不限制)
    "verbose": 1,                    # 輸出詳細程度 (0=寂靜, 1=標準)
}

# -----------------------------------------------------------------------------
# A2C (Advantage Actor-Critic) 超參數
# -----------------------------------------------------------------------------
A2C_CONFIG = {
    "learning_rate": 7e-4,           # 學習率
    "n_steps": 5,                     # 每次更新前收集的步數
    "gamma": 0.99,                   # 折扣因子
    "gae_lambda": 1.0,                # GAE lambda 參數
    "ent_coef": 0.0,                 # 熵係數
    "vf_coef": 0.5,                  # Value Function 損失係數
    "max_grad_norm": 0.5,            # 梯度裁剪最大值
    "verbose": 1,                    # 輸出詳細程度
}

# -----------------------------------------------------------------------------
# SAC (Soft Actor-Critic) 超參數
# -----------------------------------------------------------------------------
SAC_CONFIG = {
    "learning_rate": 3e-4,           # 學習率
    "buffer_size": 100000,           # Replay Buffer 大小
    "learning_starts": 100,          # 開始學習前的收集步數
    "batch_size": 256,               # 批次大小
    "tau": 0.005,                    # 目標網路更新係數
    "gamma": 0.99,                   # 折扣因子
    "train_freq": 1,                 # 訓練頻率（每隔幾步訓練一次）
    "gradient_steps": 1,             # 每次訓練的梯度步數
    "ent_coef": "auto",              # 熵係數 ("auto" 表示自動調整)
    "target_update_interval": 1,     # 目標網路更新間隔
    "verbose": 1,                    # 輸出詳細程度
}

# -----------------------------------------------------------------------------
# DDPG (Deep Deterministic Policy Gradient) 超參數
# -----------------------------------------------------------------------------
DDPG_CONFIG = {
    "learning_rate": 3e-4,           # 學習率
    "buffer_size": 100000,           # Replay Buffer 大小
    "learning_starts": 100,          # 開始學習前的收集步數
    "batch_size": 256,               # 批次大小
    "tau": 0.005,                    # 目標網路更新係數
    "gamma": 0.99,                   # 折扣因子
    "train_freq": 1,                 # 訓練頻率
    "gradient_steps": 1,             # 梯度步數
    "action_noise": "normal",        # 動作噪聲類型
    "verbose": 1,                    # 輸出詳細程度
}

# ============================================================================
# 五、訓練相關設定 (Training Settings)
# ============================================================================

# 訓練參數
TRAIN_START_DATE = "2015-01-01"      # 訓練資料起始日期
TRAIN_END_DATE = "2020-12-31"       # 訓練資料結束日期

# 測試參數
TEST_START_DATE = "2021-01-01"      # 測試資料起始日期
TEST_END_DATE = "2023-12-31"        # 測試資料結束日期

# 訓練相關
MAX_TRAINING_TIMESTEPS = 500000     # 最大訓練步數
SAVE_FREQUENCY = 10000              # 模型儲存頻率（每 N 步儲存一次）
EVAL_FREQUENCY = 5000               # 評估頻率（每 N 步評估一次）

# 環境相關
WINDOW_SIZE = 10                    # 觀察視窗大小（使用過去 N 天的資料）
N_ENVS = 1                          # 並行環境數量

# 初始資金
INITIAL_CASH = 1000000.0            # 初始資金（新台幣）

# ============================================================================
# 六、回測相關設定 (Backtesting Settings)
# ============================================================================

# 回測模式
BACKTEST_INITIAL_CASH = 1000000.0   # 回測初始資金
BACKTEST_COMMISSION = 0.001425      # 回測手續費率
BACKTEST_SLIPPAGE = 0.0005          # 滑價設定（成交價與預期價的差異）

# 風險管理
MAX_POSITION_SIZE = 1.0             # 最大倉位比例（1.0 = 100% 資金）
STOP_LOSS_PERCENT = 5.0             # 停損百分比
TAKE_PROFIT_PERCENT = 10.0          # 停利百分比

# ============================================================================
# 七、資料處理相關設定 (Data Processing Settings)
# ============================================================================

# 標準化方法
NORMALIZATION_METHOD = "zscore"     # "zscore" 或 "minmax"

# 特徵欄位（用於模型輸入）
FEATURE_COLUMNS = [
    "open", "high", "low", "close", "volume",  # 基本 OHLCV 資料
    "returns", "log_returns",                    # 收益率
    "RSI", "MACD", "MACD_signal", "MACD_hist",  # MACD 指標
    "BB_upper", "BB_middle", "BB_lower",         # Bollinger Bands
    "MA_short", "MA_medium", "MA_long",          # 移動平均線
    "ATR",                                        # ATR 指標
    "KD_K", "KD_D",                              # KD 指標
]

# 目標欄位（用於計算 reward）
TARGET_COLUMN = "close"

# ============================================================================
# 八、輸出與日誌設定 (Output and Logging Settings)
# ============================================================================

# 日誌設定
LOG_LEVEL = "INFO"                 # 日誌級別：DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 圖表設定
PLOT_STYLE = "seaborn"             # 繪圖風格
PLOT_DPI = 150                     # 圖表解析度
PLOT_FIGSIZE = (12, 8)            # 預設圖表大小

# 結果輸出設定
SAVE_PLOTS = True                  # 是否儲存圖表
SAVE_STATS = True                  # 是否儲存統計資料
