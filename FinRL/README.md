# FinRL 台股強化學習交易系統

## 2026-05-10 自動最佳化流程

新增 `optimize_portfolio_grid.py`，用來自動掃描 4 ETF PPO/DCA/PVA 參數並以多 seed 排名。這個腳本不改交易環境本身，而是呼叫既有 `train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py`，確保最佳化與正式回測走同一套資料、reward、DCA 與 PVA/SJM overlay。

快速 smoke test：

```bash
python optimize_portfolio_grid.py --seeds 42 --timesteps 16 --turnover-penalties 0.08 --min-rebalance-days 60 --max-weights 0.60 --pva-weights 0.30 --pva-drift-thresholds 0.05 --ppo-verbose 0
```

正式搜尋範例：

```bash
python optimize_portfolio_grid.py --include-baseline --seeds 42,7,123 --timesteps 20000 --turnover-penalties 0.06,0.08,0.10 --min-rebalance-days 45,60 --max-weights 0.60,0.70 --pva-weights 0.20,0.30,0.45 --pva-drift-thresholds 0.03,0.05,0.08 --ppo-verbose 0
```

輸出：

- `results/optimize_portfolio_grid_*.json`
- `results/optimize_portfolio_grid_*.csv`

排名預設使用 `robust_return`：平均投入資本報酬率扣掉 0.5 倍跨 seed 標準差。DCA 開啟時用投入資本報酬率排名；若加 `--disable-dca`，則改用策略總報酬。

同時修正 `data/data_utils.py` 的快取日期驗證：parquet 快取讀到 timezone-aware 日期時，現在會先轉成 timezone-naive normalized date，再做起訖日期比較與切片，避免 `Cannot compare tz-naive and tz-aware timestamps` 阻斷訓練。

## 2026-05-10 除權息價格修正檢查與修正

檢查後發現：先前資料下載器使用 yfinance 預設價格，`close/open/high/low` 實際為已調整價；同時回測環境又在 `--include-dividends` 時把 `dividends * shares` 加到現金。這會造成含息回測有重複計算股息的風險。

已修正 `portfolio_data_loader.py`：

- yfinance 下載改為 `auto_adjust=False, actions=True`
- 後續新快取改用 `_raw_v1.parquet` 檔名，避免讀到舊的調整價快取
- `close/open/high/low` 改用未調整原始價格
- `dividends` 欄位仍保留，含息回測時才加到現金

抽樣確認：

- 0056 在 `2024-01-17` close 為 raw close `35.19`，dividends `0.70`
- 00878 在 `2024-02-27` close 為 raw close `21.85`，dividends `0.40`
- 0050 在 `2024-01-17` close 為 raw close `31.8625`，dividends `0.75`

重要影響：本 README 前面所有標示「含息」且使用 yfinance 調整價再加 dividends 的結果，都可能高估。修正後若要公平比較，應重新訓練/回測主要策略，尤其是 0056、00878、MVO、TD3 低週轉版本。

## 2026-05-10 PPO/TD3 低週轉比較：raw OHLC 重算

依照「重算」要求，已用修正後的 raw OHLC + dividends 現金流重新訓練/回測。這次不再使用 yfinance 調整價再加股息，因此可避免股息重複計算。

補充：第一次重算只跑 TD3，沒有納入 PPO。已追加修正四 ETF PPO 腳本，讓 PPO 也使用 raw OHLC + dividends 現金流，並補跑同區間比較。

第二次補強：新增 PPO constrained 版本，限制每檔最低 5%、單檔最高 60%、最短 60 個交易日再平衡，避免 PPO 退化成 100% 0050。

第三次補強：PPO 與 SAC/TD3 投組回測輸出新增 `holding_time_stats` 與 `weight_history`，可檢查平均再平衡間隔、再平衡日期、各 ETF 實際持有天數與連續持有段。

第四次補強：新增 RSI 衍生特徵，但改為選配，需用 `--use-rsi-features` 明確開啟。測試後發現 RSI 版本績效低於等權 B&H，因此目前不列為主策略預設特徵。

TD3 執行：

```bash
python portfolio_mvo_sac_td3.py --mode td3 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05
```

PPO 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 20000 --seed 42
```

PPO constrained 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05 --max-weight 0.60
```

PPO constrained + RSI 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05 --max-weight 0.60 --use-rsi-features
```

PPO constrained 50k 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 50000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05 --max-weight 0.60
```

DCA + PPO constrained 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05 --max-weight 0.60 --enable-dca --dca-day 26 --dca-0050 5000 --dca-0056 5000 --dca-00713 5000 --dca-00878 10000
```

DCA + PPO constrained + range harvest 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05 --max-weight 0.60 --enable-dca --dca-day 26 --dca-0050 5000 --dca-0056 5000 --dca-00713 5000 --dca-00878 10000 --enable-range-harvest --range-drift-threshold 0.05
```

DCA + PPO constrained + PVA Sigmoid 執行：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --download-end 2026-05-09 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05 --max-weight 0.60 --enable-dca --dca-day 26 --dca-0050 5000 --dca-0056 5000 --dca-00713 5000 --dca-00878 10000 --enable-pva-sigmoid --pva-weight 0.30 --pva-drift-threshold 0.05
```

DCA 規則：

- 每月排程日：26 號。
- 若 26 號不是交易日，或當月 26 號後沒有交易日，順延到下一個可交易日。
- 每月買入：0050 5,000、0056 5,000、00713 5,000、00878 10,000。
- DCA 只套用在回測，不放進 PPO 訓練 reward，避免外部投入污染訓練報酬。
- DCA 與 PPO 共用同一套資金與持倉；DCA 買入後會進入同一個 portfolio，後續 PPO 再平衡會對整體持倉一起調整，不是兩個分開帳戶。
- Range harvest 震盪收割目標權重為 0050/0056/00713/00878 = 40%/20%/20%/20%，只有判定為震盪且偏離目標超過門檻時才覆蓋 PPO 權重。
- PVA/SJM overlay 使用價格位置 P、速度 V、加速度 A 的 rolling z-score 判定 S/J/M 三態；目前正式交易只允許 M 恐慌態觸發，J 貪婪態先保留為 observation 特徵，不覆蓋 PPO。
- SJM 判定：`M = A_z < -2 或 V_z < -2`，`J = V_z > 1 且 A_z > 0`，其餘為 `S`。P 使用 0050 相對 MA120 的偏離，V 使用 0050 動能，A 使用 V 的 20 日變化。

因 00878 上市較晚，4 ETF 共同資料實際區間仍為：

- Train: `2020-07-10` 到 `2023-12-29`，共 850 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

輸出：

- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_115730.json`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_115730.png`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_115730_drawdown.png`
- `models/portfolio/portfolio_0050_0056_00713_00878_td3_continuous_20090101_20231231_dji57_dividend_turnover0.08_minreb60_minw0.05`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_20260510_123143.json`
- `models/portfolio/portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_features_v4_reduced`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_20260510_133124.json`
- `models/portfolio/portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_features_v4_reduced_turnover0.08_minreb60_minw0.05_maxw0.6`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_20260510_143642.json`
- `models/portfolio/portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_features_v4_rsi_turnover0.08_minreb60_minw0.05_maxw0.6_steps20000`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_20260510_144720.json`
- `models/portfolio/portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_features_v4_reduced_turnover0.08_minreb60_minw0.05_maxw0.6_steps50000`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_dca_20260510_145734.json`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_dca_range_20260510_151547.json`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_dca_pva_20260510_153139.json`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_dca_pva_20260510_154228.json`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_dca_pva_20260510_160205.json`
- `results/training_portfolio_0050_0056_00713_00878_20090101_20231231_ppo_raw_dividend_backtest_20240101_20260508_turnover0.08_minreb60_minw0.05_maxw0.6_dca_pva_20260510_162552.json`
- `results/compare_dca_ppo_pva_sjm_multiseed_20260510_163103.json`
- `results/compare_dca_ppo_pva_sjm_multiseed_20260510_163103.csv`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 再平衡 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| PPO raw 20k | 2,254,990 | 125.50% | 43.81% | 1.543 | -28.35% | 22 | 38,469 |
| PPO constrained raw 20k | 2,074,201 | 107.42% | 38.54% | 1.598 | -24.27% | 10 | 8,421 |
| PPO constrained raw 50k | 1,901,884 | 90.19% | 33.27% | 1.430 | -24.38% | 9 | 8,363 |
| PPO constrained + RSI raw 20k | 1,782,755 | 78.28% | 29.48% | 1.461 | -22.12% | 10 | 2,430 |
| TD3 raw + 低週轉 + 每檔最低 5% | 1,891,961 | 89.20% | 32.96% | 1.559 | -21.44% | 80 | 14,921 |
| MVO raw | 1,285,828 | 28.58% | 11.89% | 0.802 | -13.87% | 0 | 0 |
| 等權 B&H raw 含息 | 1,798,958 | 79.90% | 30.00% | 1.536 | -21.07% | 0 | 0 |
| 0050 B&H raw 含息 | 2,966,197 | 196.62% | 62.55% | 1.990 | -26.63% | 0 | 0 |

注意：下表 DCA 版本有每月外部投入，不能直接用 `Final Value` 和非 DCA 策略比較，應看總投入、淨利與投入資本報酬率。

| 策略 | Final Value | 初始資金 | DCA 總投入 | 總投入 | 淨利 | 投入資本報酬率 | DCA 次數 | 再平衡 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCA + PPO constrained raw 20k | 3,188,650 | 1,000,000 | 700,000 | 1,700,000 | 1,488,650 | 87.57% | 28 | 10 |
| DCA + PPO + range harvest raw 20k | 3,188,650 | 1,000,000 | 700,000 | 1,700,000 | 1,488,650 | 87.57% | 28 | 10 |
| DCA + PPO + PVA/SJM M-only raw 20k | 3,249,575 | 1,000,000 | 700,000 | 1,700,000 | 1,549,575 | 91.15% | 28 | 10 |

PPO 最終權重：

- 0050：100%
- 0056：0%
- 00713：0%
- 00878：0%

PPO constrained 最終權重：

- 0050：60.01%
- 0056：9.17%
- 00713：9.17%
- 00878：21.66%

PPO constrained 50k 最終權重：

- 0050：60.01%
- 0056：13.33%
- 00713：13.33%
- 00878：13.33%

DCA + PPO constrained 最終權重：

- 0050：62.70%
- 0056：12.27%
- 00713：11.76%
- 00878：12.97%

DCA + PPO + range harvest 最終權重：

- 0050：62.70%
- 0056：12.27%
- 00713：11.76%
- 00878：12.97%

DCA + PPO + PVA Sigmoid 最終權重：

- 0050：62.70%
- 0056：12.26%
- 00713：11.79%
- 00878：12.96%

PPO constrained 持有時間統計：

- 持有門檻：權重大於 1% 視為持有。
- 再平衡日期：`2024-01-02`, `2024-04-09`, `2024-07-04`, `2024-10-01`, `2024-12-30`, `2025-04-08`, `2025-07-03`, `2025-09-25`, `2025-12-24`, `2026-04-01`
- 再平衡間隔：平均 60 個交易日，最短 60，最長 60。
- 0050：持有 564 個交易日，持有比例 99.82%，最長連續持有 564 日。
- 0056：持有 564 個交易日，持有比例 99.82%，最長連續持有 564 日。
- 00713：持有 564 個交易日，持有比例 99.82%，最長連續持有 564 日。
- 00878：持有 564 個交易日，持有比例 99.82%，最長連續持有 564 日。

RSI 特徵測試：

- 新增可選 active features：`0050_rsi_14`, `0050_rsi_14_rank_252`, `high_dividend_rsi_14_avg`, `0050_rsi_minus_hd_rsi`
- RSI 版本最終權重接近等權：0050 25.00%、0056 25.00%、00713 25.00%、00878 24.99%。
- RSI 版本總報酬 78.28%，低於等權 B&H 的 79.90%，Sharpe 1.461 也低於等權 B&H 的 1.536。
- 結論：RSI 可保留為實驗特徵，但目前不應放進主策略預設 active features。

50k 測試：

- 50k 版本總報酬 90.19%，仍高於等權 B&H 的 79.90%，但低於 20k constrained 的 107.42%。
- Sharpe 由 20k 的 1.598 降到 1.430，低於等權 B&H 的 1.536。
- 再平衡 9 次，平均間隔 67.75 個交易日，最短 60，最長 122。
- 結論：單純把 PPO timesteps 從 20k 拉到 50k 沒有改善，反而更像保守配置。以 seed 42 看，20k constrained 仍是較好的 PPO constrained 版本。

DCA + PPO 測試：

- DCA 執行 28 次，總投入 700,000；含初始資金總投入 1,700,000。
- 最終資產 3,188,650，淨利 1,488,650，投入資本報酬率 87.57%。
- 2025-01 的排程日 `2025-01-26` 因春節無交易日，順延到 `2025-02-03` 執行。
- 每月 DCA 買入後，資金與持股會併入同一個 PPO portfolio；PPO 仍每 60 個交易日最多對整體持倉再平衡一次，回測期間再平衡 10 次。
- 結論：DCA + PPO 的資產終值高於 0050 B&H 終值，但這包含額外 700,000 外部投入，因此不能直接視為打贏 0050 B&H。較合理的解讀是：在固定加碼 0050/0056/00713/00878 的前提下，PPO constrained 仍可維持偏 0050 的配置並控制四檔持有。

Range harvest 測試：

- 新增參數：`--enable-range-harvest`、`--range-drift-threshold`。
- 震盪收割目標權重：0050 40%、0056 20%、00713 20%、00878 20%。
- 觸發條件：判斷為震盪市，且目前權重和目標權重的總偏離超過 5%，並符合最短再平衡天數。
- 2024-2026 回測結果：range harvest 觸發 0 次，因此結果與 DCA + PPO constrained 相同。
- 結論：這段回測行情被目前規則判定為非震盪，偏強趨勢，因此震盪收割沒有介入。此功能已可用，但需要用真正的震盪區間或 walk-forward 區間驗證效果。

PVA Sigmoid 測試：

- 新增參數：`--enable-pva-sigmoid`、`--pva-weight`、`--pva-drift-threshold`。
- PVA 定義：`P = close_ma120_ratio`，`V = momentum_63`，`A = V_today - V_20_days_ago`。
- 尺度修正：原本程式把 `close_ma120_ratio`、`close_ma240_ratio` 當成 `close / MA` 比值，實際上資料管線已經是「相對均線偏離」，中性值為 0，不是 1。已修正 PVA/SJM、趨勢分數與震盪判斷，統一用 0 當中性點。
- SJM 三態：回測期間共 `S=410`、`J=94`、`M=60`；修正版 PVA overlay 實際觸發 2 次。
- Sigmoid 權重：先用 P/V/A 算 mean-reversion score，再經 Sigmoid 轉成各 ETF 理論吸引力，最後限制最低/最高權重。
- Overlay 方式：S 平靜狀態不再觸發 PVA，避免非恐慌時大幅換倉；M 恐慌狀態由 PVA 100% 主導，並使用 `panic_beta_rebound` 權重偏向 0050/市場 beta；J 貪婪狀態先不觸發交易，只保留為 PPO observation，因多 seed 測試顯示 J 的 `greed_defensive` 在強趨勢段容易過早降 beta。
- 2024-2026 seed 42 M-only 回測結果：最終資產 3,249,575，總投入 1,700,000，淨利 1,549,575，投入資本報酬率 91.15%，高於同次 DCA + PPO baseline 的 88.54%。
- 觸發日期：`2024-10-01` M、`2025-04-08` M；原本 `2024-01-02` 第一日建倉、`2024-12-30` S 狀態觸發，以及 J 狀態防禦觸發已被排除。
- 結論：PVA/SJM 經多 seed 檢查後，不能保留 J 交易觸發；目前正式版改為 M-only 恐慌 overlay。三 seed 平均只小幅打贏 DCA + PPO，屬於「可保留、但仍需 walk-forward 驗證」的增強，不應宣稱已穩定大幅優於 baseline。

多 seed 比較工具：

```bash
python compare_dca_ppo_pva_sjm_multiseed.py --seeds 42 7 123 --timesteps 20000
```

多 seed 正式結果：

| 策略 | Seeds | 平均投入資本報酬率 | 報酬標準差 | 平均 Sharpe | 平均 MDD | 平均 PVA 觸發 |
|---|---:|---:|---:|---:|---:|---:|
| DCA + PPO | 42, 7, 123 | 93.95% | 6.06% | 2.546 | -21.22% | 0.00 |
| DCA + PPO + PVA/SJM M-only | 42, 7, 123 | 94.22% | 3.23% | 2.541 | -21.16% | 2.00 |

多 seed 分 seed 結果：

| Seed | DCA + PPO 投入報酬 | PVA/SJM M-only 投入報酬 | 差異 | PVA 觸發 |
|---:|---:|---:|---:|---:|
| 42 | 88.54% | 91.15% | +2.61% | 2 |
| 7 | 90.91% | 92.82% | +1.91% | 2 |
| 123 | 102.41% | 98.70% | -3.71% | 2 |

多 seed 結論：M-only PVA/SJM 平均只小幅優於 baseline，且 seed 123 輸給 baseline；好處是報酬標準差較低，表示結果較穩。下一步應做更多 seed 與 walk-forward，不應只看 seed 42。

PVA/SJM 舊版觸發點檢查：

| 日期 | SJM | 判定是否合理 | 權重變化 | 後續價格驗證 | 評估 |
|---|---|---|---|---|---|
| 2024-01-02 | S | 普通；`p_z/v_z/a_z` 皆為 0，主要是回測第一天建倉，不是真正訊號 | 從現金建倉：0050 16.69%、0056 49.59%、00713 16.82%、00878 16.91% | 後 60 日 0050 +21.02%，0056 +7.59%，00713 +9.51%，00878 +5.57% | 建倉點可以接受，但不應算成 PVA 有效觸發；0056 權重過高，錯過 0050 強勢 |
| 2024-10-01 | M | 合理；`V_z=-2.01` 達恐慌門檻 | 加 0050 +7.93%，減 0056/00713/00878 | 後 20 日 0050 +5.09%，後 60 日 0050 +7.73%，但後 120 日 0050 -16.53% | 短線買點正確，中期遇到 2025 下跌後失效 |
| 2024-12-30 | S | 偏弱；不是恐慌也不是貪婪，卻因偏離過大觸發 | 大幅加 0050 +35.89%，減高股息 ETF | 後 60 日 0050 -22.52%，0056 -16.92%，00713 -10.17%，00878 -15.96% | 錯誤買點；在非恐慌 S 狀態大幅追 0050，成為主要拖累 |
| 2025-04-08 | M | 很合理；`P_z=-3.53`, `V_z=-3.30`, `A_z=-2.79`，是明確恐慌 | 最終減 0050 -27.05%，加 0056/00713/00878 | 後 20 日 0050 +11.16%，後 60 日 0050 +28.73%，後 120 日 0050 +51.91% | 狀態判定正確，但交易方向錯；PVA 純權重偏好 0050，最後被 PPO 目標拉去高股息 ETF |

PVA/SJM 修正版觸發點檢查：

| 日期 | SJM | 判定是否合理 | 權重變化 | 後續價格驗證 | 評估 |
|---|---|---|---|---|---|
| 2024-10-01 | M | 合理；`V_z=-2.01` 達恐慌門檻 | 維持約半數以上 0050，避免被 PPO 拉到低 beta | 後 20 日 0050 +5.09%，後 60 日 0050 +7.73% | 訊號正確；M-only 規則避免 J/S 亂入，但仍不是全押 0050 |
| 2025-04-08 | M | 很合理；`P_z=-3.53`, `V_z=-3.30`, `A_z=-2.79` | 維持約半數以上 0050，其他 ETF 分散 | 後 20 日 0050 +11.16%，後 60 日 0050 +28.73%，後 120 日 0050 +51.91% | 訊號正確；M-only 版本保留恐慌反彈 beta，同時降低過度觸發 |

反推混合前 PPO 目標權重：

- 2024-01-02：約 0050 13.33%、0056 60.00%、00713 13.33%、00878 13.33%。
- 2024-10-01：約 0050 4.99%、0056 38.00%、00713 28.50%、00878 28.50%。
- 2024-12-30：約 0050 60.00%、0056 13.33%、00713 13.33%、00878 13.33%。
- 2025-04-08：約 0050 15.00%、0056 25.00%、00713 25.00%、00878 35.00%。

觸發點結論：舊版 SJM 狀態判定大致正確，但 overlay 混合方式錯，PVA 只佔 30%/45%，PPO 仍主導最終權重，導致 `2025-04-08` 這種明確恐慌低點反而賣出過多 0050。後續多 seed 檢查又發現 J 狀態的 `greed_defensive` 會過早降 beta，因此正式版改為「只允許 M 狀態觸發」、「M 狀態 PVA 100% 主導並提高 0050/市場 beta 權重」、「S/J 狀態不覆蓋 PPO」。

TD3 最終權重：

- 0050：68.96%
- 0056：5.23%
- 00713：20.50%
- 00878：5.31%

MVO 權重：

- 0050：0%
- 0056：0%
- 00713：100%
- 00878：0%

結論：修正為 raw OHLC 後，自由 PPO 20k 的總報酬最高，125.50%，但最終等同押到 100% 0050，最大回撤 -28.35% 也比 0050 B&H 的 -26.63% 更差，且仍輸給 0050 B&H 的 196.62%。PPO constrained 20k 犧牲部分報酬，總報酬降到 107.42%，但 Sharpe 提升到 1.598、再平衡降到 10 次、成本降到 8,421，且仍打贏等權 B&H 與 TD3。PPO constrained 50k 沒有改善，總報酬降到 90.19%、Sharpe 降到 1.430。RSI 版本反而低於等權 B&H，因此 RSI 先保留為可選測試特徵，不放入預設。DCA + PPO 可做實際資金流版本，但必須用投入資本報酬率看，不可直接拿 Final Value 和非 DCA 策略比較。Range harvest 已導入但 2024-2026 沒有觸發；PVA/SJM M-only 三 seed 平均投入資本報酬率 94.22%，只小幅高於 DCA + PPO 的 93.95%，且 Sharpe 略低。此版本可保留為主測試增強版，但還不能說穩定顯著優於 baseline。目前下一步應優先做更多 seed、walk-forward、純 DCA baseline，以及震盪區間敏感度測試，而不是再單純拉高 timesteps。先前調整價 + dividends 的含息結果不應再作為主結論，因為可能高估。

## 2026-05-10 TD3 低週轉版：每檔最低 5% 權重

依照「00878 是 0%，定至少 5%」要求，`portfolio_mvo_sac_td3.py` 新增：

- `--min-weight`
- target weight 會套用每檔最低權重。
- 若價格漂移造成實際權重低於最低值，會強制補回最低權重。

執行：

```bash
python portfolio_mvo_sac_td3.py --mode td3 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60 --min-weight 0.05
```

輸出：

- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_005719.json`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_005719.png`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_005719_drawdown.png`
- `models/portfolio/portfolio_0050_0056_00713_00878_td3_continuous_20090101_20231231_dji57_dividend_turnover0.08_minreb60_minw0.05`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 再平衡 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TD3 低週轉 + 每檔最低 5% | 2,230,984 | 123.10% | 43.12% | 1.941 | -19.65% | 61 | 15,406 |
| TD3 低週轉，不強制漂移補回 | 2,263,150 | 126.31% | 44.04% | 1.994 | -18.81% | 10 | 19,861 |
| TD3 低週轉，無最低權重 | 2,252,889 | 125.29% | 43.75% | 1.898 | -19.62% | 10 | 19,776 |
| 等權 B&H 含息 | 2,094,382 | 109.44% | 39.14% | 1.953 | -18.75% | 0 | 0 |
| 0050 B&H 含息 | 3,158,802 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |

最終權重：

- 0050：34.16%
- 0056：27.97%
- 00713：26.78%
- 00878：10.46%

結論：強制每檔最低 5% 後，00878 不再接近 0，最終為 10.46%。報酬略低於未強制漂移補回版本，但仍明顯打贏等權 B&H 的總報酬；Sharpe 則略低於等權 B&H。這版比較符合「四檔都要參與」的配置需求。

## 2026-05-10 TD3 低週轉版：不改 Reward

依照「reward 先不改，其他先做」，本次只新增/調整低週轉控制參數，沒有改 reward 公式。

`portfolio_mvo_sac_td3.py` 新增 CLI 參數：

- `--turnover-penalty`
- `--min-rebalance-days`

執行：

```bash
python portfolio_mvo_sac_td3.py --mode td3 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --timesteps 20000 --seed 42 --turnover-penalty 0.08 --min-rebalance-days 60
```

因 00878 上市較晚，4 ETF 共同資料實際區間仍為：

- Train: `2020-07-10` 到 `2023-12-29`，共 850 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

輸出：

- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_002724.json`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_002724.png`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260510_002724_drawdown.png`
- `models/portfolio/portfolio_0050_0056_00713_00878_td3_continuous_20090101_20231231_dji57_dividend_turnover0.08_minreb60`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 再平衡 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TD3 低週轉 20k | 2,252,889 | 125.29% | 43.75% | 1.898 | -19.62% | 10 | 19,776 |
| TD3 原版 20k | 2,095,558 | 109.56% | 39.17% | 1.842 | -18.03% | 29 | 38,446 |
| 等權 B&H 含息 | 2,094,382 | 109.44% | 39.14% | 1.953 | -18.75% | 0 | 0 |
| 0050 B&H 含息 | 3,158,802 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |

低週轉 TD3 最終權重：

- 0050：48.59%
- 0056：45.82%
- 00713：4.56%
- 00878：約 0%

結論：不改 reward、只提高週轉成本與最短再平衡天數後，TD3 明顯改善。報酬從 109.56% 提升到 125.29%，再平衡從 29 次降到 10 次，估計成本也從 38,446 降到 19,776。這版已經打贏等權 B&H 的總報酬，但 Sharpe 仍略低於等權 B&H，且仍大幅落後 0050 B&H 含息。

## 2026-05-09 MVO Baseline + SAC/TD3 連續倉位

新增 `portfolio_mvo_sac_td3.py`，支援：

- MVO baseline：用訓練期含息日報酬估計長期權重，long-only，單一資產上限預設 80%。
- SAC 連續倉位：action 為 4 檔 ETF 的連續目標權重。
- TD3 連續倉位：action 為 4 檔 ETF 的連續目標權重。
- 使用標的：`0050.TW`, `0056.TW`, `00713.TW`, `00878.TW`
- 使用含息現金流與 DJI 57 維資料管線。

100k steps 的 `--mode all` 曾執行但超過 30 分鐘逾時，因此先用 20k steps 跑通 SAC/TD3 第一版：

```bash
python portfolio_mvo_sac_td3.py --mode all --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --timesteps 20000 --seed 42
```

由於 00878 上市較晚，4 ETF 共同資料實際區間為：

- Train: `2020-07-10` 到 `2023-12-29`，共 850 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

輸出：

- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260509_235053.json`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260509_235053.png`
- `results/portfolio_mvo_sac_td3_20090101_20231231_backtest_20240101_20260508_20260509_235053_drawdown.png`
- `models/portfolio/portfolio_0050_0056_00713_00878_sac_continuous_20090101_20231231_dji57_dividend`
- `models/portfolio/portfolio_0050_0056_00713_00878_td3_continuous_20090101_20231231_dji57_dividend`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 再平衡 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| MVO | 1,611,303 | 61.13% | 23.76% | 1.529 | -13.22% | 0 | 0 |
| SAC 20k | 2,030,128 | 103.01% | 37.22% | 1.615 | -24.29% | 29 | 48,445 |
| TD3 20k | 2,095,558 | 109.56% | 39.17% | 1.842 | -18.03% | 29 | 38,446 |
| 等權 B&H 含息 | 2,094,382 | 109.44% | 39.14% | 1.953 | -18.75% | 0 | 0 |
| 0050 B&H 含息 | 3,158,803 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |

權重觀察：

- MVO 權重：0050 0.37%, 0056 7.15%, 00713 79.03%, 00878 13.45%。訓練期偏好 00713，回測防守但報酬低。
- SAC 最終權重：約 45.90% 0050、53.36% 00713，其餘接近 0。
- TD3 最終權重：約 49.92% 0050、50.02% 00713，其餘接近 0。

結論：TD3 20k 是目前 SAC/TD3 中較好的版本，報酬幾乎等於等權 B&H，MDD 稍低，但 Sharpe 低於等權 B&H，且仍大幅落後 0050 B&H 含息。MVO 可作為 baseline，但不是最佳策略。下一步若要改善，應先降低 SAC/TD3 的交易頻率與加入 0050 benchmark reward，而不是單純拉高 timesteps。

## 2026-05-09 00878：DJI 57 維特徵重訓 2009-2023，回測 2024-2026

依照要求以 `00878.TW` 執行訓練與回測。注意：00878 實際上市資料從 2020 開始，因此雖然指定 `2009-2023`，實際訓練區間是 `2020-07-10` 到 `2023-12-29`。

執行：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 00878.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --include-dividends
```

實際資料區間：

- Train: `2020-07-10` 到 `2023-12-29`，共 850 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

模型：

`models/portfolio/00878_TW_20090101_20231231_ppo_enhanced_dividend`

輸出：

- `results/training_00878_TW_20090101_20231231_ppo_dividend_backtest_20240101_20260508_20260509_225653.json`
- `results/training_00878_TW_20090101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_225653_comparison.png`
- `results/training_00878_TW_20090101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_225653_drawdown.png`
- `results/training_00878_TW_20090101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_225653_comparison_metrics.json`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 00878 PPO 含息 + DJI | 1,554,045 | 55.40% | 21.77% | 1.509 | -6.42% | 4 | 871 |
| 00878 B&H 含息 | 1,793,573 | 79.36% | 29.83% | 1.616 | -19.12% | 0 | 0 |
| 00878 B&H 不含息 | 1,558,314 | 55.83% | 21.92% | 1.132 | -22.29% | 0 | 0 |
| 0050 B&H 含息 | 3,158,802 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |

結論：00878 PPO + DJI 的 MDD 很低，只有 -6.42%，交易也少，但報酬幾乎等同 00878 不含息 B&H，明顯落後 00878 含息 B&H。這表示模型沒有充分吃到高股息 ETF 的配息總報酬優勢，偏向保守低波動策略。

## 2026-05-09 0050：DJI 57 維特徵重訓 2009-2023，回測 2024-2026

使用目前 57 維 state 環境重新訓練 0050，含 DJI lag 特徵與含息現金流。

執行：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0050.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --include-dividends
```

實際資料區間：

- Train: `2009-01-02` 到 `2023-12-29`，共 3,678 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

模型：

`models/portfolio/0050_TW_20090101_20231231_ppo_enhanced_dividend`

輸出：

- `results/training_0050_TW_20090101_20231231_ppo_dividend_backtest_20240101_20260508_20260509_222735.json`
- `results/training_0050_TW_20090101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_222735_comparison.png`
- `results/training_0050_TW_20090101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_222735_drawdown.png`
- `results/training_0050_TW_20090101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_222735_comparison_metrics.json`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO 含息 + DJI | 1,625,872 | 62.59% | 24.26% | 1.897 | -10.39% | 7 | 1,183 |
| 0050 B&H 含息 | 3,158,802 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |
| 0050 B&H 不含息 | 3,062,966 | 206.30% | 64.90% | 1.994 | -27.48% | 0 | 0 |

結論：0050 PPO + DJI 大幅降低回撤，但報酬明顯不足，總報酬落後 0050 B&H 含息約 153.29 個百分點。這版比較像低波動/保守模型，不適合作為追求資產成長的主策略。

## 2026-05-09 0056：DJI 57 維特徵重訓，回測 2024-2026

依照「DJI 特徵直接加入、不取代」後，重新訓練 0056。環境 state 維度為 57，包含原本台股市場情緒特徵與 5 個 DJI lag 特徵。

執行：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0056.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2014-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --include-dividends
```

實際資料區間：

- Train: `2014-01-02` 到 `2023-12-29`，共 2,445 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

輸出：

- `results/training_0056_TW_20140101_20231231_ppo_dividend_backtest_20240101_20260508_20260509_221702.json`
- `results/training_0056_TW_20140101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_221702_comparison.png`
- `results/training_0056_TW_20140101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_221702_drawdown.png`
- `results/training_0056_TW_20140101_20231231_dji57_dividend_backtest_20240101_20260508_20260509_221702_comparison_metrics.json`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0056 PPO 含息 + DJI | 1,981,801 | 98.18% | 35.75% | 1.252 | -12.14% | 468 | 102,086 |
| 0056 B&H 含息 | 1,876,124 | 87.61% | 32.46% | 1.647 | -19.80% | 0 | 0 |
| 0056 B&H 不含息 | 1,551,960 | 55.20% | 21.70% | 1.069 | -26.89% | 0 | 0 |
| 0050 B&H 含息 | 3,158,802 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |

與前一版 0056 含息 PPO 相比：

- Final Value：`1,977,707` -> `1,981,801`，小幅增加約 4,094。
- Sharpe：`0.909` -> `1.252`，改善。
- MDD：`-17.69%` -> `-12.14%`，明顯改善。
- 交易次數：`413` -> `468`，更高。
- 估計成本：`192,249` -> `102,086`，因單次交易金額較小而下降。

結論：加入 DJI 57 維特徵後，0056 PPO 的風險控制有改善，MDD 與 Sharpe 都比前一版好，但交易次數仍過高，且仍大幅落後 0050 B&H 含息。下一步不應再優先加特徵，而是做低週轉 action/reward 設計。

## 2026-05-09 新增 DJI 全球市場特徵

已將 DJI 道瓊指數加入資料特徵，用來提供美股前一交易日的全球風險訊號。資料來源為 Yahoo Finance `^DJI`。

新增於 `portfolio_data_loader.py`：

- `dji_return_1d_lag1`
- `dji_return_5d_lag1`
- `dji_volatility_20d_lag1`
- `dji_ma60_ratio_lag1`
- `dji_drawdown_60d_lag1`

為避免偷看未來，所有 DJI 原始特徵都先做 `shift(1)`，台股當日決策只使用前一個已知美股交易日資訊。

環境 `TaiwanStockTradingEnv` 已由 52 維 state 擴充為 57 維 state，不取代原本台股市場情緒欄位，而是直接新增 DJI 特徵。市場情緒欄位目前為 9 維：

- `twse_index_return`
- `twse_index_volume_change`
- `sector_correlation`
- `market_volatility`
- `dji_return_1d_lag1`
- `dji_return_5d_lag1`
- `dji_volatility_20d_lag1`
- `dji_ma60_ratio_lag1`
- `dji_drawdown_60d_lag1`

已用 0056 小區間驗證資料欄位可正常產生，環境 observation shape 為 `(57,)`。注意：因為 state 維度從 52 變 57，舊模型不能直接接在新環境上回測；0050/0056 若要使用 DJI 特徵，需要重新訓練。

## 2026-05-09 0056：含息訓練 2014-2023，回測 2024-2026

新增含息訓練/回測支援：

- `TaiwanStockTradingEnv` 新增 `include_dividends`，開啟後持有部位會在除息日把 `dividends * shares` 加到現金。
- `calculate_buy_and_hold_metrics` 新增 `include_dividends`，可計算 B&H 含息總報酬。
- `train_0050_2016_2023_backtest_2024_2026.py` 新增 `--include-dividends`。

執行：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0056.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2014-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08 --include-dividends
```

實際資料區間：

- Train: `2014-01-02` 到 `2023-12-29`，共 2,445 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

模型：

`models/portfolio/0056_TW_20140101_20231231_ppo_enhanced_dividend`

輸出：

- `results/training_0056_TW_20140101_20231231_ppo_dividend_backtest_20240101_20260508_20260509_215934.json`
- `results/training_0056_TW_20140101_20231231_dividend_backtest_20240101_20260508_20260509_215934_comparison.png`
- `results/training_0056_TW_20140101_20231231_dividend_backtest_20240101_20260508_20260509_215934_drawdown.png`
- `results/training_0056_TW_20140101_20231231_dividend_backtest_20240101_20260508_20260509_215934_comparison_metrics.json`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0056 PPO 含息 | 1,977,707 | 97.77% | 35.62% | 0.909 | -17.69% | 413 | 192,249 |
| 0056 B&H 含息 | 1,876,123 | 87.61% | 32.46% | 1.647 | -19.80% | 0 | 0 |
| 0056 B&H 不含息 | 1,551,959 | 55.20% | 21.70% | 1.069 | -26.89% | 0 | 0 |
| 0050 B&H 含息 | 3,158,802 | 215.88% | 67.18% | 2.098 | -26.47% | 0 | 0 |

結論：0056 PPO 含息小幅打贏 0056 含息 B&H，總報酬多約 10.16 個百分點，MDD 也略低。但交易次數高達 413 次、估計成本約 19.2 萬，Sharpe 明顯低於 0056 B&H。若與 0050 B&H 含息相比，0056 策略仍大幅落後。下一步應優先做低週轉版本，例如提高 turnover penalty、限制最短持有 60 天、或把 action space 改成季度調整。

## 2026-05-09 0056 資料起始日期檢查

新增資料範圍檢查工具：

```bash
python inspect_data_range.py 0056
```

本機快取檢查結果：

- `data/portfolio_cache/0056_TW.parquet`：最早為 `2014-01-02` 台北時間附近，最晚到 `2026-04-30` 附近，共 3,005 筆。
- `data/portfolio_cache/0056_TW_20160101_20260509_1d.parquet`：最早為 `2016-01-04` 台北時間附近，最晚到 `2026-05-08` 附近，共 2,516 筆。
- `data/portfolio_cache/0056_TW_20200101_20260509_1d.parquet`：最早為 `2020-01-02` 台北時間附近，最晚到 `2026-05-08` 附近，共 1,538 筆。

結論：目前專案內可用的 0056 本機資料最早約從 `2014-01-02` 開始；若使用目前下載器重新抓 `2016` 起區間，則會從 `2016-01-04` 開始。

## 2026-05-09 0050：訓練 2009-2023，回測 2024-2026

依照可取得的 0050 資料，明確使用 2009-2023 訓練、2024-2026 回測：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0050.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08
```

實際資料區間：

- Train: `2009-01-02` 到 `2023-12-29`，共 3,678 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

模型：

`models/portfolio/0050_TW_20090101_20231231_ppo_enhanced`

輸出：

- `results/training_0050_TW_20090101_20231231_ppo_backtest_20240101_20260508_20260509_152804.json`
- `results/training_0050_TW_20090101_20231231_backtest_20240101_20260508_20260509_152804.png`
- `results/training_0050_TW_20090101_20231231_backtest_20240101_20260508_20260509_152804_drawdown.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO | 1,483,556 | 48.36% | 19.27% | 1.730 | -10.99% | 8 | 1,926 | -157.94% |
| 0050 B&H | 3,062,966 | 206.30% | 64.90% | 1.994 | -27.48% | 0 | 0 | 基準 |

結論：這版 PPO 明顯偏保守，MDD 從 B&H 的 -27.48% 降到 -10.99%，但代價是大幅少賺，總報酬落後 B&H 約 157.94 個百分點。若目標是資產成長，這版不如 0050 B&H；若目標是低回撤，才有參考價值。

## 2026-05-09 0050 原始資料來源檢查

已檢查本機 0050 相關快取與外部資料來源：

- 本機 `FinRL/data/portfolio_cache/0050_TW_20030101_20260509_1d.parquet` 檔名雖然包含 20030101，但 parquet metadata 顯示實際資料範圍是 `2009-01-02` 到 `2026-05-08`，共 4,243 筆。
- 本機 `FinRL/data/portfolio_cache/0050_TW_20030101_20110101_1d.parquet` 同樣不是完整 2003 起資料。
- TWSE「個股日成交資訊」官方頁面註明資料自民國 99 年 1 月 4 日，也就是 `2010-01-04` 起提供，因此不能用它取得 2003-2009 的完整 OHLCV。
- TWSE「個股日收盤價及月平均價」自民國 88 年 1 月 5 日起提供，但欄位是日收盤價與月平均價，不是完整 OHLCV，不能直接取代目前 RL 訓練資料。
- 元大投信與 ETF 資訊頁可確認 0050 成立日 `2003-06-25`、掛牌日 `2003-06-30`，但不等於可直接取得 2003 起完整 OHLCV CSV。

結論：目前本機與 TWSE 免費官方 OHLCV 來源都不足以取得完整 `2003-2023` 的 0050 原始 OHLCV。若要真正訓練 2003-2023，需新增第三方歷史價格來源，或改用 `2010-2023` 作為官方 OHLCV 可驗證訓練區間。

## 2026-05-09 0050：訓練 2003-2023，回測 2024-2026

依照要求重新訓練 0050 單標的 PPO：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0050.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2003-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08
```

注意：要求訓練區間為 2003-2023，但目前資料源實際取得的 0050 訓練資料從 `2009-01-02` 開始，因此實際訓練區間是 `2009-01-02` 到 `2023-12-29`，共 3,678 筆。回測實際區間為 `2024-01-02` 到 `2026-05-07`，共 564 筆。

模型：

`models/portfolio/0050_TW_20030101_20231231_ppo_enhanced`

輸出：

- `results/training_0050_TW_20030101_20231231_ppo_backtest_20240101_20260508_20260509_130503.json`
- `results/training_0050_TW_20030101_20231231_backtest_20240101_20260508_20260509_130503.png`
- `results/training_0050_TW_20030101_20231231_backtest_20240101_20260508_20260509_130503_drawdown.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO | 3,113,744 | 211.37% | 66.26% | 2.018 | -26.92% | 3 | 2,783 | +2.87% |
| 0050 B&H | 3,085,070 | 208.51% | 65.58% | 2.009 | -27.48% | 0 | 0 | 基準 |

結論：這次 0050 PPO 在 2024-2026 小幅打贏 0050 B&H，總報酬多約 2.87 個百分點，MDD 也略低。不過差距很小，主要結論是「接近買進持有」，不是明顯優勢。

## 2026-05-09 0050 單標的：2003-2010 回測

新增 0050 單標的回測腳本，載入既有模型 `models/portfolio/0050_TW_2016_2023_ppo_enhanced`，不重新訓練：

```bash
python backtest_0050_2003_2010.py --start 2003-01-01 --end 2010-12-31
```

注意：雖然要求區間是 2003-2010，但目前資料下載源實際只回傳 `2009-01-02` 到 `2010-12-31` 的 0050 資料，共 499 筆交易日。因此下列結果是 2009-2010 的可用資料回測，不是完整 2003-2010。

輸出：

- `results/backtest_0050_20030101_20101231_20260509_123205.json`
- `results/backtest_0050_20030101_20101231_20260509_123205.png`
- `results/backtest_0050_20030101_20101231_20260509_123205_drawdown.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO | 1,543,388 | 54.34% | 24.56% | 0.990 | -12.24% | 8 | 2,191 |
| 0050 B&H | 1,867,966 | 86.80% | 37.19% | 0.984 | -18.01% | 0 | 0 |

結論：0050 PPO 在這段資料的 MDD 較低，但總報酬落後 B&H 約 32.46 個百分點。此結果也屬於跨時期回測，因為模型是用 2016-2023 訓練，再拿去測 2009-2010，市場結構差異較大。

## 2026-05-09 2000-2010 回測可行性檢查

嘗試使用目前的全持股自由配置模型回測 2000-2010：

```bash
python backtest_all_holdings_unrestricted_2024_2026.py --start 2000-01-01 --end 2010-12-31
```

結果：目前這個「所有持股、不限制持股」模型不能直接回測 2000-2010。原因是模型資產池包含 `0050.TW`, `0056.TW`, `00646.TW`, `00679B.TWO`, `00713.TW`, `00751B.TWO`, `00878.TW`, `2884.TW`，其中多數 ETF 在 2010 年前尚未上市，無法形成共同交易資料區間。程式因此停止在 `Not enough backtest rows`。

若要做 2000-2010 類型的長期回測，建議改成「早期存在的標的」獨立模型，例如：

- 0050 單標的：可從 2003 年後開始測。
- 2884 單股票：可測更早期，但與 ETF 資產配置模型不同。
- 0050 + 2884 雙標的：可作為早期資料版本，但不能與目前全持股 ETF 模型直接比較。

## 2026-05-09 不限制持股模型：訓練期 2020-2023 回測

使用同一個全持股自由配置模型 `models/portfolio/portfolio_all_holdings_2020_2023_ppo`，將回測區間改為 2020-2023。因為這段是模型訓練期，所以此結果屬於 in-sample replay，不可視為泛化能力。

執行：

```bash
python backtest_all_holdings_unrestricted_2024_2026.py --start 2020-01-01 --end 2023-12-31
```

實際共同資料區間為 2020-07-10 到 2023-12-29，共 850 筆交易日。

結果：

`results/backtest_all_holdings_unrestricted_20200101_20231231_20260509_115036.json`

圖檔：

- `results/all_holdings_unrestricted_backtest_20200101_20231231_20260509_115036.png`
- `results/all_holdings_unrestricted_drawdown_20200101_20231231_20260509_115036.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 PPO 不限制 | 1,649,076 | 64.91% | 16.01% | 0.924 | -28.66% | 43 | 58,338 | +5.56% |
| 全持股等權 B&H | 1,424,571 | 42.46% | 11.08% | 0.886 | -19.56% | 0 | 0 | -16.89% |
| 目前持股比例 B&H | 1,066,441 | 6.64% | 1.93% | 0.036 | -23.48% | 0 | 0 | -52.70% |
| 100% 0050 B&H | 1,593,429 | 59.34% | 14.83% | 0.738 | -33.83% | 0 | 0 | 基準 |

最後配置仍約為 70.00% 0050，其餘 7 檔各約 4.29%。

結論：在訓練期內，全持股 PPO 不限制模型小幅打贏 0050 B&H，且 MDD 較低。但交易成本高、交易次數 43 次，且這是 in-sample，因此不能直接代表 2024-2026 的未來泛化能力。

## 2026-05-09 不限制持股回測與圖形化比較

依照「不應限制持股」要求，新增專用回測腳本，載入原本全持股自由配置模型，不使用 core-satellite 限制版 action space，重新回測 2024-2026 並輸出圖形化比較。

新增腳本：

```bash
python backtest_all_holdings_unrestricted_2024_2026.py
```

載入模型：

`models/portfolio/portfolio_all_holdings_2020_2023_ppo`

回測結果：

`results/backtest_all_holdings_unrestricted_2024_2026_20260509_114612.json`

圖檔：

- `results/all_holdings_unrestricted_backtest_2024_2026_20260509_114612.png`
- `results/all_holdings_unrestricted_drawdown_2024_2026_20260509_114612.png`

實際回測區間為 2024-01-02 到 2026-05-07，共 563 筆共同交易日。

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 目前持股 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 PPO 不限制 | 2,298,782 | 129.88% | 45.24% | 1.816 | -22.84% | 29 | 22,045 | +98.30% | -78.63% |
| 全持股等權 B&H | 1,556,120 | 55.61% | 21.93% | 1.401 | -16.23% | 0 | 0 | +24.04% | -152.89% |
| 目前持股比例 B&H | 1,315,755 | 31.58% | 13.09% | 0.955 | -15.73% | 0 | 0 | 基準 | -176.93% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.72% | 2.010 | -27.48% | 0 | 0 | +176.93% | 基準 |

最後配置：

- 70.01% 0050
- 4.29% 0056
- 4.29% 00646
- 4.29% 00679B
- 4.29% 00713
- 4.29% 00751B
- 4.29% 00878
- 4.27% 2884

結論：不限制持股的自由配置模型仍然明顯打贏目前持股比例 B&H 和全持股等權 B&H，但輸給 100% 0050 B&H。模型自己仍收斂到 70% 0050 + 其他持股平均分散，代表它沒有把非核心持股完全排除，但核心仍然是 0050。

## 2026-05-09 全持股 Core-Satellite v2

依照改善建議，把全持股投組模型從「自由配置」改成「0050 核心 + 衛星」配置。這版不再允許模型任意押注非核心標的，而是在少數可執行配置中切換。

修改檔案：`train_all_holdings_portfolio_2020_2023_backtest_2024_2026.py`

Action space：

- hold current weights
- 100% 0050
- 90% 0050 / 10% 00878
- 80% 0050 / 20% 00878
- 80% 0050 / 10% 00713 / 10% 00878
- 70% 0050 / 10% 0056 / 10% 00713 / 10% 00878
- 70% 0050 / 15% 00646 / 7.5% 00679B / 7.5% 00751B
- 80% 0050 / 10% 00679B / 10% 00751B

Reward：

```text
daily return
+ 1.5 * excess vs equal-weight B&H
+ 1.0 * excess vs actual-holdings B&H
- 0.8 * underperformance vs 0050 B&H
- 0.5 * current drawdown
- turnover/cost penalty
```

執行：

```bash
python train_all_holdings_portfolio_2020_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

結果：`results/training_portfolio_all_holdings_2020_2023_ppo_backtest_2024_2026_20260509_085625.json`

模型：`models/portfolio/portfolio_all_holdings_2020_2023_core_satellite_v2_ppo`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 目前持股 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 Core-Satellite v2 | 2,999,386 | 199.94% | 63.64% | 2.073 | -27.48% | 11 | 8,615 | +168.36% | -8.57% |
| 全持股 PPO v1 | 2,298,782 | 129.88% | 45.24% | 1.816 | -22.84% | 29 | 22,045 | +98.30% | -78.63% |
| 目前持股比例 B&H | 1,315,755 | 31.58% | 13.09% | 0.955 | -15.73% | 0 | 0 | 基準 | -176.93% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.72% | 2.010 | -27.48% | 0 | 0 | +176.93% | 基準 |

最後配置：

- 80.06% 0050
- 10.01% 00679B
- 9.93% 00751B
- 其他 0%

結論：core-satellite v2 是目前最好的 RL 投組版本。它幾乎追上 0050 B&H，只落後 8.57%，Sharpe 2.073 甚至略高於 0050 B&H 的 2.010，交易次數與成本也比全持股 PPO v1 低很多。缺點是 MDD 沒有比 0050 低，代表債券 ETF 衛星沒有在 2024-2026 有效降低最大回撤。

下一步應先對 core-satellite v2 做多 seed 與 walk-forward，不建議再擴大 action space。

## 2026-05-09 全持股投組訓練：2020-2023 / 2024-2026

依照目前 `PORTFOLIO_HOLDINGS` / `ALL_TICKERS`，把所有持股一起納入單一 PPO 投組模型訓練。這不是逐檔各自訓練，而是一個模型在不同投組配置 action 間切換。

持股標的：

- 0050.TW
- 0056.TW
- 00646.TW
- 00679B.TWO
- 00713.TW
- 00751B.TWO
- 00878.TW
- 2884.TW

新增腳本：

```bash
python train_all_holdings_portfolio_2020_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

設定為 2020-2023 訓練、2024-2026 回測。因為 00878.TW 較晚有資料，實際共同訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-07。

結果：`results/training_portfolio_all_holdings_2020_2023_ppo_backtest_2024_2026_20260509_005241.json`

模型：`models/portfolio/portfolio_all_holdings_2020_2023_ppo`

Observation 維度：70

Action space：

- hold current weights
- equal weight all holdings
- actual current holding weights
- 100% 0050
- 70% 0050, rest equal
- 80% 0050 / 20% 00878
- 50% 0050 / 25% 00679B / 25% 00751B
- 0056/00713/00878 equal high-dividend basket
- 100% best 6M momentum
- top-2 6M momentum equal
- top-3 6M momentum equal

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 目前持股 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 PPO | 2,298,782 | 129.88% | 45.24% | 1.816 | -22.84% | 29 | 22,045 | +74.27% | +98.30% | -78.63% |
| 全持股等權 B&H | 1,556,120 | 55.61% | 21.93% | 1.401 | -16.23% | 0 | 0 | 基準 | +24.04% | -152.89% |
| 目前持股比例 B&H | 1,315,755 | 31.58% | 13.09% | 0.955 | -15.73% | 0 | 0 | -24.04% | 基準 | -176.93% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.72% | 2.010 | -27.48% | 0 | 0 | +152.89% | +176.93% | 基準 |

最後配置約為：

- 70.01% 0050
- 其餘 7 檔各約 4.29%

結論：把所有持股加入後，PPO 明顯打贏「全持股等權 B&H」與「目前持股比例 B&H」，代表它有學到應該提高 0050 權重。但它仍大幅輸給 100% 0050 B&H。這再次確認目前最有效的訊號不是增加更多標的，而是：0050 應該是核心，其他持股只能作為衛星或風險分散。

## 2026-05-09 特徵改善實驗：四 ETF 投組 v3

針對「52 個特徵是否不夠」的問題，本次沒有再堆疊更多單檔技術指標，而是在四 ETF 投組腳本加入投組專用特徵。

修改檔案：`train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py`

新增特徵類型：

- 0050 市場狀態：MA120/MA240 趨勢、MA60 vs MA240、63 日回撤風險、63 日波動率、252 日波動分位。
- 高股息 ETF 相對強弱：0056/00713/00878 平均動能 vs 0050。
- ETF 相對動能：00878 vs 0050、00713 vs 0050、0056 vs 0050、00878 vs 0056。
- 動能排名：0050 在 63/126/252 日動能排名、00878 在 126 日排名、最佳與最弱動能差距。
- 投組狀態：目前各 ETF 權重、現金權重、目前 MDD、距離上次換倉天數、相對等權 B&H/0050 B&H 的領先落後、高股息總權重。

Observation 維度從 v2 的 37 維提高到 60 維。

執行指令：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260509_003317.json`

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo_features_v3`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO v3 features | 1,875,722 | 87.57% | 32.52% | 1.341 | -31.45% | 24 | 66,363 | +0.29% | -120.93% |
| 四 ETF PPO v2 benchmark | 2,326,863 | 132.69% | 45.94% | 1.944 | -22.47% | 28 | 17,464 | +45.40% | -75.82% |
| 四 ETF 等權 B&H | 1,872,848 | 87.28% | 32.43% | 1.537 | -22.73% | 0 | 0 | 基準 | -121.22% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.58% | 2.009 | -27.48% | 0 | 0 | +121.22% | 基準 |

結論：特徵增加後沒有改善，反而讓 PPO 學得更差。v3 只小贏等權 B&H，且 MDD 擴大到 -31.45%，成本也升到 66,363。這表示問題不是「特徵數量太少」，而是特徵太多後樣本數只有 850 筆，PPO 更容易學到不穩定配置。現階段最佳版本仍是 v2 benchmark reward，而不是 v3 features。

下一步建議：保留少數高價值特徵，不要一次加入 30 多個狀態。優先保留 `0050_trend_score`、`high_dividend_vs_0050_momentum_126`、`0050_momentum_rank_126`、`relative_value_vs_equal_weight_bh`、`relative_value_vs_0050_bh`，其餘先移除或用 feature ablation 逐批測試。

### 四 ETF 投組 v4：精簡特徵

v4 依照 v3 結論，把投組衍生特徵縮小，只保留：

- `0050_trend_score`
- `0050_volatility_rank_252`
- `high_dividend_vs_0050_momentum_126`
- `00878_vs_0050_momentum_63`
- `0050_momentum_rank_126`

投組狀態仍保留目前權重、現金、MDD、距上次換倉天數、相對等權 B&H/0050 B&H 的領先落後。Observation 維度降為 43。

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260509_003758.json`

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo_features_v4_reduced`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO v4 reduced features | 1,953,868 | 95.39% | 34.96% | 1.499 | -25.13% | 29 | 9,640 | +8.10% | -113.12% |
| 四 ETF PPO v3 features | 1,875,722 | 87.57% | 32.52% | 1.341 | -31.45% | 24 | 66,363 | +0.29% | -120.93% |
| 四 ETF PPO v2 benchmark | 2,326,863 | 132.69% | 45.94% | 1.944 | -22.47% | 28 | 17,464 | +45.40% | -75.82% |

結論：v4 比 v3 改善，但仍明顯輸 v2。特徵精簡是正確方向，但目前加入投組狀態與相對特徵後，模型仍沒有學出更好的配置。現階段應保留 v2 作為最佳版本，v4 只作為特徵實驗紀錄。

## 2026-05-09 改善實驗：00878 多 seed 與四 ETF 投組 v2

### 00878 PPO 多 seed

執行 00878.TW、PPO、100k timesteps，seed 使用 1、7、42、99、123。實際訓練區間仍為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| Seed | Final Value | 總報酬 | Sharpe | MDD | 交易次數 | vs B&H |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1,393,381 | 39.34% | 0.749 | -5.16% | 2 | -16.49% |
| 7 | 1,629,973 | 63.00% | 1.044 | -13.93% | 39 | +7.17% |
| 42 | 1,635,155 | 63.52% | 1.025 | -13.79% | 3 | +7.68% |
| 99 | 1,652,890 | 65.29% | 1.075 | -13.58% | 2 | +9.07% |
| 123 | 1,607,563 | 60.76% | 1.078 | -11.28% | 10 | +4.53% |

摘要：平均總報酬 58.38%，平均 Sharpe 0.994，平均 vs B&H +2.39%，最差 seed vs B&H -16.49%。00878 PPO 仍值得追蹤，但 seed 1 明顯落後，代表單檔 00878 RL 還不能只靠一次訓練定案。

### 四 ETF 投組 PPO v2

更新內容：

- Reward 改為 `daily_return + 2.0 * excess_return_vs_max(equal_weight_BH, 0050_BH)`。
- Action space 從 8 個擴充為 10 個。
- 新增 `70% 0050 / 10% 0056 / 10% 00713 / 10% 00878`。
- 新增 `80% 0050 / 20% 00878`。

執行指令：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260509_001901.json`

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo_benchmark_v2`

實際訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-07。

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO v2 | 2,326,863 | 132.69% | 45.94% | 1.944 | -22.47% | 28 | 17,464 | +45.40% | -75.82% |
| 四 ETF 等權 B&H | 1,872,848 | 87.28% | 32.43% | 1.537 | -22.73% | 0 | 0 | 基準 | -121.22% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.58% | 2.009 | -27.48% | 0 | 0 | +121.22% | 基準 |

結論：v2 已成功從「輸等權 B&H」改善為「贏等權 B&H +45.40%」，最後配置約為 70% 0050 / 10% 0056 / 10% 00713 / 10% 00878，方向正確。但仍輸 0050 B&H -75.82%，代表這版比較像「比等權更積極的核心衛星策略」，還不是能取代 0050 B&H 的主策略。

## 0050+0056+00713+00878 投組 PPO 實驗紀錄

執行指令：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

這支腳本是單一 PPO 投組配置模型，不是逐檔各自訓練。Action space 會在等權、100% 0050、0050 偏重、高股息偏重、防守型高股息、6M 動能第一名、6M 動能前兩名等配置間切換。

設定為 2016-2023 訓練、2024-2026 回測，但四檔 ETF 需要共同可用資料；因 00878.TW 較晚上市，本次實際訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO 投組 | 1,797,774 | 79.78% | 29.96% | 1.445 | -21.79% | 22 | 7,644 | -7.24% | -126.52% |
| 四 ETF 等權 B&H | 1,870,153 | 87.02% | 32.27% | 1.532 | -22.73% | 0 | 0 | 基準 | -119.28% |
| 100% 0050 B&H | 3,062,966 | 206.30% | 64.90% | 1.994 | -27.48% | 0 | 0 | +119.28% | 基準 |

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo`

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260508_234521.json`

結論：這版多 ETF PPO 投組沒有打贏四 ETF 等權 B&H，也大幅輸給 0050 B&H。模型最後偏向 0% 0050、約 40% 0056、30% 00713、30% 00878，代表它太保守並錯過 0050 在 2024-2026 的強勢主升段。後續若要繼續做投組 RL，reward 應明確加入「等權 B&H / 0050 B&H 超額報酬」作為門檻，否則模型容易學成低波動但低報酬配置。

## 00878 PPO 實驗紀錄

執行指令：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 00878.TW --agent ppo --timesteps 100000 --seed 42
```

設定為 2016-2023 訓練、2024-2026 回測，但 00878.TW 的可用資料實際從 2020-07-10 開始。因此本次實際訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| 標的/策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 00878 PPO 100k | 1,635,155 | 63.52% | 24.57% | 1.025 | -13.79% | 3 | 680 | +7.68% |
| 00878 B&H | 約 1,558,314 | 55.83% | 21.92% | 1.132 | -22.29% | 0 | 0 | 基準 |

模型：`models/portfolio/00878_TW_2016_2023_ppo_enhanced`

結果：`results/training_00878_TW_2016_2023_ppo_backtest_2024_2026_20260508_233220.json`

結論：00878 PPO 在 2024-2026 回測贏過 B&H 約 7.68%，且 MDD 較低、交易次數只有 3 次，成本控制明顯優於 0056 PPO。訓練期仍輸給 B&H 約 31.79%，所以此結果應視為值得追蹤的候選，不應只用單一 seed 定案。

## 00713 PPO 實驗紀錄

執行指令：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 00713.TW --agent ppo --timesteps 100000 --seed 42
```

設定為 2016-2023 訓練、2024-2026 回測，但 00713.TW 的可用資料實際從 2017-09-19 開始。因此本次實際訓練區間為 2017-09-19 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| 標的/策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 00713 PPO 100k | 1,337,168 | 33.72% | 13.86% | 0.490 | -7.37% | 19 | 15,466 | +2.98% |
| 00713 B&H | 約 1,307,373 | 30.74% | 12.72% | 0.789 | -15.40% | 0 | 0 | 基準 |

模型：`models/portfolio/00713_TW_2016_2023_ppo_enhanced`

結果：`results/training_00713_TW_2016_2023_ppo_backtest_2024_2026_20260508_232301.json`

結論：00713 PPO 在 2024-2026 回測小幅贏過 B&H，且 MDD 較低；但訓練期 `train_excess_return_vs_bh=-90.63%`，表示模型在訓練期仍明顯輸給買進持有。這組結果可以保留，但不能只用單一 seed 當作正式結論，後續應補多 seed 與 walk-forward。

本資料夾是針對台灣 ETF/股票的強化學習交易實驗環境，主要使用 Stable-Baselines3 的 PPO/A2C/DQN，搭配台股交易限制、T+2 交割、交易成本、風控、增強 reward 與 walk-forward/backtest 流程。

## 目前重點改善

本版已把先前發現的高影響問題納入程式與文件：

- 回測輸出加入 `RL vs Buy & Hold` 基準比較。
- 回測輸出加入 `total_return`、`annual_return`、`sharpe`、`max_drawdown`、`volatility`、`excess_return_vs_bh`。
- 回測輸出加入 `fees_paid_estimate`、`turnover_trades`、`equity_curve`。
- 訓練加入 `--seed`，並寫入實驗 metadata。
- metadata 包含 `seed`、`git_commit`、`python`、`platform`、`model_path`、reward/env config。
- 修正 `reward_function_v3.py` 中最大回撤判斷順序，避免 `max_drawdown > 0.30` 永遠不會觸發。
- `.gitignore` 已排除 `results/`、`models/`、cache、圖表、JSON/CSV 等實驗輸出。
- README 已同步實作中的 9-action action space。
- 新增 DQN baseline，可用 `--agent dqn` 與 PPO/A2C/B&H 比較。
- 訓練摘要改為訓練後回放 train-set 統計，不再只顯示未更新的 `best_sharpe=-999`。
- Reward  now 加重 B&H 超額報酬、低週轉與最短持有約束，降低頻繁交易。
- 資料載入流程新增長週期趨勢/風險特徵，包含 3M/6M/12M momentum、MA120/MA240 比例、52 週位置與 63 日 rolling MDD。

## 主要檔案

```text
FinRL/
  portfolio_train_v2.py                         # 主要訓練入口，含 seed、metadata、benchmark 回測輸出
  backtest_0050_2016_2023_model_2024_2026.py    # 0050 固定模型回測，輸出 RL vs B&H
  portfolio_data_loader.py                      # Yahoo Finance 下載、快取與技術指標資料整理
  environments/taiwan_stock_env.py              # 9-action 台股交易環境
  environments/reward_function_v3.py            # Dynamic reward shaping
  risk_manager_v2.py                            # 風控、early stopping、Kelly 建議
  safe_ppo.py                                   # PPO logits/gradient 保護
  walk_forward_v2.py                            # Walk-forward 分段訓練與測試
  results/                                      # 訓練與回測輸出
  models/                                       # 模型輸出
  data/cache/                                   # 單標的資料快取
  data/portfolio_cache/                         # 投組資料快取
```

## 狀態空間

`TaiwanStockTradingEnv` 使用 52 維狀態：

| 類別 | 維度 | 內容 |
|---|---:|---|
| 價格/量 | 6 | close、open、high、low、volume、turnover |
| 技術指標 | 20 | MA、MACD、RSI、KDJ、BB、ATR、ADX、MFI 等 |
| 型態/動能 | 8 | 突破、跌破、量增、momentum、volatility、連漲連跌、gap |
| 基本/籌碼 | 8 | 外資、投信、自營商、殖利率、PER、PBR |
| 持倉狀態 | 6 | position、現金比例、未實現損益、MDD、距上次交易日數 |
| 市場情緒 | 4 | 加權指數報酬、量變化、相關性、市場波動 |

## Action Space

目前實作為 9 個離散動作：

| Action | ID | 說明 |
|---|---:|---|
| HOLD | 0 | 不交易 |
| BUY_1000 | 1 | 買入 1000 股 |
| BUY_5000 | 2 | 買入 5000 股 |
| BUY_10000 | 3 | 買入 10000 股 |
| SELL_1000 | 4 | 賣出 1000 股 |
| SELL_5000 | 5 | 賣出 5000 股 |
| SELL_10000 | 6 | 賣出 10000 股 |
| TARGET_50_PERCENT | 7 | 調整至約 50% 倉位 |
| TARGET_100_PERCENT | 8 | 調整至約 100% 倉位 |

## 台股交易設定

- 交易單位：1000 股。
- 最大持股：預設 40000 股。
- 漲跌停限制：10%。
- 買入成本：成交金額加券商手續費。
- 賣出成本：成交金額扣券商手續費與證交稅。
- T+2：新買入股數會被鎖定，解鎖前不可賣出。

## 訓練

安裝依賴：

```bash
cd FinRL
pip install -r requirements.txt
```

單一標的訓練：

```bash
python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000 --seed 42
```

固定 0050 訓練/回測，支援選擇 agent：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --agent ppo --timesteps 100000 --seed 42
python train_0050_2016_2023_backtest_2024_2026.py --agent dqn --timesteps 100000 --seed 42
```

指定 agent：

```bash
python portfolio_train_v2.py --tickers 0050.TW --agent ppo --timesteps 100000 --seed 42
python portfolio_train_v2.py --tickers 0050.TW --agent a2c --timesteps 100000 --seed 42
python portfolio_train_v2.py --tickers 0050.TW --agent dqn --timesteps 100000 --seed 42
```

停用風控或增強 reward：

```bash
python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000 --no-risk
python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000 --no-enhanced-reward
```

Walk-forward：

```bash
python portfolio_train_v2.py --tickers 0050.TW --walk-forward --timesteps 50000 --seed 42
```

## 固定 0050 回測

這支腳本會載入 `models/portfolio/0050_TW_2016_2023_enhanced`，用 2016-2023 作為訓練區間紀錄，回測 2024-2026。

```bash
python backtest_0050_2016_2023_model_2024_2026.py
```

輸出會寫入 `results/training_0050_2016_2023_backtest_2024_2026_fixed_*.json`，包含：

- `final_value`
- `total_reward`
- `num_trades`
- `final_position`
- `rl_metrics`
- `buy_and_hold_metrics`
- `excess_return_vs_bh`
- `fees_paid_estimate`
- `turnover_trades`
- `equity_curve`
- `metadata`

## 回測指標

每次 `EnhancedStockTrainer.backtest()` 會回傳：

```json
{
  "rl_metrics": {
    "total_return": 0.0,
    "annual_return": 0.0,
    "sharpe": 0.0,
    "max_drawdown": 0.0,
    "volatility": 0.0
  },
  "buy_and_hold_metrics": {
    "total_return": 0.0,
    "annual_return": 0.0,
    "sharpe": 0.0,
    "max_drawdown": 0.0,
    "volatility": 0.0,
    "initial_price": 0.0,
    "final_price": 0.0
  },
  "excess_return_vs_bh": 0.0,
  "fees_paid_estimate": 0.0,
  "turnover_trades": 0
}
```

`max_drawdown` 使用負值表示回撤，例如 `-0.18` 代表 -18%。

## Reward 與低週轉約束

目前 PPO/A2C/DQN 共用同一個 env 與 enhanced reward。重要設計：

- `benchmark_weight=2.0`：提高 RL 相對 B&H 的每日超額報酬權重。
- `underperform_penalty=1.0`：輸給 B&H 時加重懲罰。
- `trade_reward=0.0`、`trade_penalty=0.02`：不再鼓勵為交易而交易。
- env 額外加入 `turnover_penalty=0.01`。
- env 額外加入 `min_hold_days=20` 與 `short_hold_penalty=0.02`，短持有賣出會被扣 reward。
- 訓練摘要會在 `model.learn()` 後回放訓練區間，輸出 `train_total_return`、`train_max_drawdown`、`train_excess_return_vs_bh` 與實際 train-set Sharpe。

## 長週期特徵

`download_all_stocks()` 會在讀取 cache 或下載後補上：

- `close_ma120_ratio`
- `close_ma240_ratio`
- `ma60_ma240_ratio`
- `momentum_63`
- `momentum_126`
- `momentum_252`
- `high_252_position`
- `rolling_mdd_63`

這些特徵優先進入 `TaiwanStockTradingEnv` 的 20 個技術指標槽，目標是讓 ETF 策略更容易學會大週期趨勢與長抱。

## DQN Baseline

DQN 已接入 `portfolio_train_v2.py --agent dqn`。目前定位是比較基準，不是預設主力模型。

DQN 目前設定：

- MLP policy，網路寬度 `[256, 256]`。
- Replay buffer：`100000`。
- Learning starts：`5000`。
- Batch size：`128`。
- Target network update interval：`2000`。
- Epsilon exploration：從 `1.0` 線性降到 `0.05`，探索期佔 `25%`。
- Reward 與 env 與 PPO/A2C 共用，因此可以直接比較同一組 benchmark。

建議比較方式：

```bash
python portfolio_train_v2.py --tickers 0050.TW --agent ppo --timesteps 100000 --seed 42
python portfolio_train_v2.py --tickers 0050.TW --agent dqn --timesteps 100000 --seed 42
```

比較時不要只看 `final_value`，要同時看：

- `excess_return_vs_bh`
- `rl_metrics.sharpe`
- `rl_metrics.max_drawdown`
- `fees_paid_estimate`
- `turnover_trades`
- 多個 seed 的平均與最差結果

## 實驗追蹤

每筆訓練結果會加入 `metadata`：

```json
{
  "created_at": "2026-05-08T20:00:00",
  "ticker": "0050.TW",
  "agent_type": "ppo",
  "timesteps": 100000,
  "seed": 42,
  "train_rows": 1200,
  "test_rows": 600,
  "model_path": "...",
  "git_commit": "...",
  "python": "3.12.0",
  "platform": "...",
  "reward_config": {
    "enhanced_reward": true
  },
  "env_config": {
    "risk_manager": true,
    "action_space": 9
  }
}
```

建議後續將每次實驗輸出整理成：

```text
results/experiments/YYYYMMDD_HHMMSS_name/
  config.json
  metrics.json
  trades.csv
  equity.csv
  model.zip
```

目前程式已先把必要 metadata 寫入 JSON，後續可以再把輸出目錄改成上述結構。

## 目前風險與後續優先順序

1. 優先確認 RL 是否穩定贏過 Buy & Hold，而不是只看 final value。
2. 對 `taiwan_stock_env.py` 進一步清掉舊 5-action 註解與不可達舊碼，降低維護成本。
3. 把 `results/`、`models/`、`data/cache/` 明確排除版控或移到 experiment 目錄。
4. 對 reward 權重做 grid search 或 walk-forward，不要只用單一回測期間調參。
5. 每次報告都應同時列出交易成本、交易次數、超額報酬與最大回撤。

## 免責

此專案是研究與回測用途，不構成投資建議。實盤前需要獨立驗證資料品質、滑價、手續費、稅負、成交量限制與風險控管。

## 三段倉位規則策略 Baseline

`rule_based_trend_strategy.py` 是 0/50/100 三段倉位的低頻趨勢策略，不使用 RL，目標是建立 RL 必須先打贏的規則型 baseline。

主要邏輯：

- 強多頭：`close_ma120_ratio > 0`、`close_ma240_ratio > 0`、`ma60_ma240_ratio > 0`、6M/12M momentum 皆大於 0，持倉 100%。
- 風險轉弱：`close_ma240_ratio < -5%` 或 `rolling_mdd_63 < -15%`，持倉 0%。
- 其他中性狀態：持倉 50%。
- 預設每 60 個交易日最多調倉一次。

執行範例：

```bash
python rule_based_trend_strategy.py --ticker 0056.TW --min-rebalance-days 60 --defensive-position 0.5
python rule_based_trend_strategy.py --ticker 0050.TW --min-rebalance-days 20 --defensive-position 0.5
```

0056 在 2024-2026 的目前結果：

| 策略 | Final Value | 總報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs B&H |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0056 PPO 100k | 1,265,538 | 26.55% | -1.632 | -19.72% | 311 | 261,013 | -28.64% |
| 0056 三段倉位 | 1,418,244 | 41.82% | 1.143 | -18.78% | 7 | 7,846 | -13.37% |
| 0056 B&H | 約 1,551,960 | 55.20% | 1.069 | -26.89% | 0 | 0 | 基準 |

## 0050+0056 投組規則 Baseline

`portfolio_rule_baseline_0050_0056.py` 是第一版 0050/0056/現金配置規則，不使用 RL。邏輯是每 20 個交易日根據 0050 與 0056 的 3M/6M/12M 相對動能與風險狀態，在以下配置間切換：

- 70% 0050 / 30% 0056
- 30% 0050 / 70% 0056
- 50% 0050 / 50% 0056
- 風險轉弱時保留部分現金

執行：

```bash
python portfolio_rule_baseline_0050_0056.py
```

2024-2026 目前結果：

| 策略 | Final Value | 總報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|
| 0050+0056 規則投組 | 1,992,777 | 99.28% | 1.546 | -29.01% | 25 | 11,334 |
| 50/50 B&H | 約 2,307,463 | 130.75% | 1.740 | -26.68% | 0 | 0 |
| 100% 0050 B&H | 約 3,062,966 | 206.30% | 1.994 | -27.48% | 0 | 0 |
| 100% 0056 B&H | 約 1,551,960 | 55.20% | 1.069 | -26.89% | 0 | 0 |

結論：第一版投組規則 baseline 尚未打贏 50/50 B&H，主要問題是切換太保守且錯過 0050 大波段。後續 PortfolioEnv/RL 應以 50/50 B&H 和 100% 0050 B&H 作為主要門檻。
