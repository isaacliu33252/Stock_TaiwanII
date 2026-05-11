# FinRL 4 ETF PPO/DCA/PVA Strategy Handoff

## 交接目的

這份文件給接手者快速理解目前 FinRL 策略狀態、最佳參數、重現方式，以及如何從研究回測走到可控的實盤前 signal-only 流程。

目前策略定位：

- 這不是完整自動交易系統。
- 這是低頻 ETF 配置輔助策略。
- 模型輸出目標權重，實際下單應先人工確認。
- 未完成 paper trading 前，不建議大資金部署。

## 策略範圍

標的：

- `0050.TW`
- `0056.TW`
- `00713.TW`
- `00878.TW`

核心流程：

- PPO 強化學習決定 ETF 目標權重。
- DCA 每月固定投入。
- PVA/SJM overlay 只在 M 恐慌狀態介入。
- 低週轉限制，避免模型頻繁再平衡。
- 單檔權重有上下限，避免退化成單一 ETF。

## 目前最佳參數

來自正式 grid search：

```text
turnover_penalty = 0.08
min_rebalance_days = 60
min_weight = 0.05
max_weight = 0.70
enable_pva_sigmoid = true
pva_weight = 0.20
pva_drift_threshold = 0.08
enable_dca = true
dca_day = 26
dca_0050 = 5000
dca_0056 = 5000
dca_00713 = 5000
dca_00878 = 10000
timesteps = 20000
```

最佳化結果檔：

```text
results/optimize_portfolio_grid_20260511_054914.json
results/optimize_portfolio_grid_20260511_054914.csv
```

最佳組合跨 3 seeds 結果：

```text
mean_score_return = 99.71%
worst_score_return = 96.99%
best_score_return = 101.31%
mean_sharpe = 2.543
mean_max_drawdown = -21.48%
mean_trades = 7.67
rank_score = 98.74%
```

注意：DCA 策略有外部投入，不能只看 final value。比較策略時應優先看投入資本報酬率、Sharpe、MDD、交易次數。

## 主要檔案

```text
optimize_portfolio_grid.py
```

用途：正式 grid search 參數最佳化。會呼叫主訓練腳本，多 seed、多參數組合重跑，最後輸出 ranked JSON/CSV。

```text
train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py
```

用途：正式 4 ETF PPO 訓練與回測。接手者應優先從這個檔案理解策略、環境、DCA、PVA/SJM overlay。

```text
portfolio_data_loader.py
data/data_utils.py
```

用途：資料下載、快取、parquet 讀寫、日期正規化。已修正 timezone-aware / timezone-naive 日期比較問題。

```text
README.md
```

用途：紀錄歷次實驗、重算結果、最佳化流程與命令。

## 重現最佳單次回測

在 WSL/Linux shell 內執行：

```bash
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL

python3 train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py \
  --train-start 2009-01-01 \
  --train-end 2023-12-31 \
  --backtest-start 2024-01-01 \
  --backtest-end 2026-05-08 \
  --download-end 2026-05-09 \
  --timesteps 20000 \
  --seed 42 \
  --turnover-penalty 0.08 \
  --min-rebalance-days 60 \
  --min-weight 0.05 \
  --max-weight 0.70 \
  --enable-dca \
  --dca-day 26 \
  --dca-0050 5000 \
  --dca-0056 5000 \
  --dca-00713 5000 \
  --dca-00878 10000 \
  --enable-pva-sigmoid \
  --pva-weight 0.20 \
  --pva-drift-threshold 0.08 \
  --ppo-verbose 0
```

## 重跑正式 grid search

只有需要重新評估參數時才跑。這會花很久。

```bash
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL

python3 optimize_portfolio_grid.py \
  --include-baseline \
  --seeds 42,7,123 \
  --timesteps 20000 \
  --turnover-penalties 0.06,0.08,0.10 \
  --min-rebalance-days 45,60 \
  --max-weights 0.60,0.70 \
  --pva-weights 0.20,0.30,0.45 \
  --pva-drift-thresholds 0.03,0.05,0.08 \
  --ppo-verbose 0
```

## 實作建議

第一階段只做 signal-only，不做自動下單。

建議新增：

```text
generate_signal.py
```

最小功能：

1. 下載最新 `0050.TW`、`0056.TW`、`00713.TW`、`00878.TW` 資料。
2. 使用同一套 feature pipeline。
3. 載入最佳參數訓練出的 PPO model。
4. 根據最新 observation 輸出目標權重。
5. 合併目前持倉，輸出建議差異。
6. 只輸出 CSV，不下單。

建議輸出格式：

```csv
date,ticker,current_weight,target_weight,weight_diff,action_hint
2026-05-11,0050.TW,0.62,0.70,0.08,buy
2026-05-11,0056.TW,0.12,0.10,-0.02,hold
2026-05-11,00713.TW,0.12,0.10,-0.02,hold
2026-05-11,00878.TW,0.14,0.10,-0.04,sell
```

## 實盤前硬限制

接手者不要移除這些限制：

- 每 60 個交易日最多再平衡一次。
- 單檔最低權重 5%。
- 單檔最高權重 70%。
- 每月 DCA 日為 26 號，非交易日順延。
- 權重差異小於 8% 時不交易。
- PVA/SJM overlay 只允許 M 恐慌態觸發。
- 所有模型建議都要先人工確認。

建議風控：

- 若 live / paper MDD 超過 27%，暫停再平衡，只保留 DCA。
- 若策略相對 0050 B&H 落後超過 10%，暫停再平衡並做原因分析。
- 若資料下載異常、缺值、日期未更新，不產生交易建議。
- 若模型輸出權重不符合上下限，直接拒絕輸出。

## Paper Trading 要求

正式接券商 API 前，至少做 3 到 6 個月 paper trading。

paper trading 帳本至少記錄：

- 日期
- 當日價格
- 目前股數
- 目前權重
- 模型目標權重
- 實際模擬交易
- 模擬交易成本
- DCA 投入
- 資產總值
- 相對 0050 B&H 表現
- 相對等權 B&H 表現
- MDD

## 不建議立即做的事

- 不要直接接券商 API 自動下單。
- 不要為了近期績效再調 grid search 參數。
- 不要用 final value 宣稱策略打贏 benchmark，DCA 有外部投入。
- 不要拿 2024-2026 回測結果推論未來必然有效。
- 不要在沒有 paper trading 的情況下重倉。

## 接手者檢查清單

開始前：

- 能重跑最佳單次回測。
- 能讀取 `optimize_portfolio_grid_20260511_054914.csv`。
- 確認資料為 raw OHLC + explicit dividends cashflow。
- 確認交易成本與 ETF tax 有被計入。
- 確認 DCA 只在 evaluation/backtest 套用，不污染 PPO training reward。

做 signal-only 前：

- 建好目前持倉輸入格式。
- 建好 signal CSV 輸出格式。
- 有交易日判斷與資料更新檢查。
- 有權重上下限檢查。
- 有再平衡間隔檢查。

接近實盤前：

- 完成 3 到 6 個月 paper trading。
- Paper trading 沒有資料錯誤或不可解釋的異常交易。
- 策略 MDD 沒有超過預設暫停門檻。
- 實際交易人已理解 DCA、再平衡與 PVA/SJM 觸發條件。

## 最終判斷

目前結果可支持「小資金試行或 paper trading」，不支持「大資金全自動部署」。

最合理的實用形態：

```text
DCA + 低頻 PPO 權重建議 + PVA 恐慌態輔助 + 人工確認
```

